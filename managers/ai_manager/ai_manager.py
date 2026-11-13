"""AI manager: every LLM API call goes through here.

Call 1 (classify_entries) classifies feedback entries and writes each a
one-line summary; call 2 (summarise) summarises a run's aggregated stats from
those one-liners. Both send their requests through one RequestRunner, which
works with any AITask and any LLMClient. API only: no print(), no domain
rules; progress goes to a ProgressReporter as events.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from managers.models import THEMES, FeedbackRecord

from .ai_summary import AISummary
from .classification_task import ClassificationTask
from .llm_client import LLMClient
from .progress_reporter import ProgressReporter
from .progress_tracker import ProgressTracker
from .prompt_library import PromptLibrary
from .request_runner import RequestRunner
from .summary_input import MAX_INPUT_CHARS
from .summary_task import SummaryTask
from .token_ledger import TokenLedger

if TYPE_CHECKING:
    from managers.logic_manager import AggregationResult


class AIManager:
    """Public API for the app's two LLM calls. It decides what to send and
    what a result means for each record; RequestRunner decides how to send it."""

    def __init__(
        self,
        client: LLMClient,
        key_label: str,
        prompts: PromptLibrary,
        reporter: ProgressReporter,
        load_token_log: Callable[[], dict | None],
        save_token_log: Callable[[dict], object],
        summary_input_chars: int | None = MAX_INPUT_CHARS,
    ):
        """summary_input_chars caps call 2's input (D19); None sends every
        example. The default is the limit measured live; a caller can pass
        another, e.g. to probe Groq's limit."""
        self.__client = client
        self.__key_label = key_label
        self.__prompts = prompts
        self.__reporter = reporter
        self.__summary_input_chars = summary_input_chars
        self.__ledger = TokenLedger(client.model, load_token_log, save_token_log)
        self.__runner = RequestRunner(client, reporter, self.__ledger, key_label)

    def set_known_themes(self, themes: list[str]) -> None:
        """Update the themes call 1 offers the model, e.g. after an admin
        confirms a new one (7.4). The 8 base themes are always kept, so themes
        may be the full list from data.load_known_themes() or only the
        confirmed ones. Raises ValueError, keeping the old themes, if a theme
        is not a non-empty name.
        """
        self.__prompts.set_themes(list(dict.fromkeys([*THEMES, *themes])))

    def classify_entries(
        self,
        records: list[FeedbackRecord],
        stored_records: list[FeedbackRecord],
        on_classified: Callable[[FeedbackRecord], object],
    ) -> tuple[list[FeedbackRecord], list[FeedbackRecord], bool]:
        """Classify each record (call 1), and never exit the app.

        Only the text reaches the model, along with any labels it coined in
        stored_records or earlier in this batch, so user values cannot anchor
        it. A classified record has its AI values set through set_ai and goes
        to on_classified as soon as it finishes, so a crash does not lose paid
        work.

        Returns (classified, pending, stopped). A pending record keeps ai = None.
        A record with invalid output goes pending and the batch continues. A
        missing or rejected key, every attempt lost to connection errors, or a
        rate-limit wait over a minute stops the batch and leaves the rest
        pending, since retrying every record could take about 100 seconds each.
        """
        known_themes = self.__prompts.find_new_themes(stored_records)
        tracker = ProgressTracker(len(records))
        self.__reporter.on_batch_start(
            f"Classifying {len(records)} records",
            [self.__client.model, "1 sample each", f"key: {self.__key_label}"],
            tracker.progress,
        )
        classified = []
        pending = []
        for index, record in enumerate(records):
            if self._classify_entry(record, known_themes, tracker) is None:
                pending.append(record)
            else:
                known_themes = self.__prompts.find_new_themes([record], known_themes)
                classified.append(record)
                on_classified(record)
            if tracker.stopped:
                pending.extend(records[index + 1:])
                tracker.leave_pending([left.feedback_id for left in records[index + 1:]])
                break
        self._end_batch(tracker)
        return classified, pending, tracker.stopped

    def summarise(self, result: AggregationResult, records: list[FeedbackRecord]) -> AISummary | None:
        """Summarise one run (call 2).

        Sends result's counts and, per theme, the one-liner of every counted
        record in records (its raw text, cut short, if it has none), as
        Part 1 did (D18). Over summary_input_chars, the least severe examples
        are left out (D19). Returns an AISummary with one action per theme in
        result's order, or None if every attempt failed, so the caller keeps
        the last summary. The pipeline skips this call when classify_entries
        stopped, as the API is then unlikely to answer (D20), and when it
        classified nothing (e.g. a review-only run), to save a call; the last
        summary then stays until the next run that classifies a record.
        """
        task = SummaryTask(result.to_dict(), records, self.__prompts.summary_prompt, self.__summary_input_chars)
        tracker = ProgressTracker(1)
        self.__reporter.on_batch_start(
            "Summarising this run", [self.__client.model, f"key: {self.__key_label}"], tracker.progress
        )
        tracker.start_record()
        output = self.__runner.run(task, tracker)
        summary = None
        if output is not None:
            summary = AISummary(output["overall_summary"], output["theme_actions"])
            tracker.finish_ok()
            retries = tracker.record_retries
            self.__reporter.on_record_ok(
                task.request_id, "1 retry" if retries == 1 else f"{retries} retries", tracker.progress
            )
        self._end_batch(tracker)
        return summary

    def _classify_entry(
        self, record: FeedbackRecord, known_themes: list[str], tracker: ProgressTracker
    ) -> FeedbackRecord | None:
        """Classify one record. Returns it, or None if it failed and so keeps ai = None."""
        task = ClassificationTask(record, self.__prompts.system_prompt, self.__prompts.themes, known_themes)
        tracker.start_record()
        result = self.__runner.run(task, tracker)
        if result is None:
            return None
        try:
            # The summary rides along in record.ai, so Data saves it with the
            # record and call 2 can read it later without another request.
            record.set_ai(result["theme"], result["sentiment"], result["severity"], result["summary"])
        except ValueError as exc:
            tracker.finish_failed(task.request_id)
            self.__reporter.on_record_failed(task.request_id, str(exc), tracker.progress)
            return None
        tracker.finish_ok()
        self.__reporter.on_record_ok(
            task.request_id, f"{result['theme']} / {result['sentiment']} / {result['severity']}", tracker.progress
        )
        return record

    def _end_batch(self, tracker: ProgressTracker) -> None:
        if tracker.stopped:
            self.__reporter.on_batch_stopped(tracker.progress)
        self.__reporter.on_batch_end(
            tracker.progress, self.__ledger.today_total(self.__key_label), self.__ledger.daily_limit
        )
