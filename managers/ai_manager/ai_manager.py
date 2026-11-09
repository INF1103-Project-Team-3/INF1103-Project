"""AI manager: every LLM API call goes through here.

Call 1 (classify_entries) classifies feedback entries and writes each a
one-line summary; call 2 (summarise) summarises a run's aggregated stats from
those one-liners. Both share one retry loop, which works
with any AITask and any LLMClient. API only: no print(), no domain rules;
progress goes to a ProgressReporter as events.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from managers.models import FeedbackRecord

from .ai_summary import AISummary
from .ai_task import AITask
from .batch_progress import BatchProgress
from .classification_task import ClassificationTask
from .llm_client import LLMClient
from .llm_request_error import LLMRequestError
from .progress_reporter import ProgressReporter
from .prompt_library import PromptLibrary
from .summary_task import SummaryTask
from .token_ledger import TokenLedger

if TYPE_CHECKING:
    from managers.logic_manager import AggregationResult

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # per request, covering schema mismatches and retryable API failures
BACKOFF_BASE_S = 2  # failed attempt n waits BACKOFF_BASE_S ** n without headers
# The per-minute limit resets within 60 seconds, and clients add a small buffer
# to that, so a longer wait means the daily cap, which could stall a batch for hours.
MAX_WAIT_S = 61
INVALID_OUTPUT = "invalid output"
WAIT_RATE_LIMIT = "rate limit"
WAIT_BACKOFF = "backoff"


class AIManager:
    """Public API for the app's two LLM calls."""

    def __init__(
        self,
        client: LLMClient,
        key_label: str,
        prompts: PromptLibrary,
        reporter: ProgressReporter,
        load_token_log: Callable[[], dict | None],
        save_token_log: Callable[[dict], object],
    ):
        self.__client = client
        self.__key_label = key_label
        self.__prompts = prompts
        self.__reporter = reporter
        self.__ledger = TokenLedger(client.model, load_token_log, save_token_log)

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
        wait over MAX_WAIT_S stops the batch and leaves the rest pending, since
        retrying every record could take about 100 seconds each.
        """
        known_themes = self.__prompts.find_new_themes(stored_records)
        progress = BatchProgress(len(records))
        self.__reporter.on_batch_start(
            f"Classifying {len(records)} records",
            [self.__client.model, "1 sample each", f"key: {self.__key_label}"],
            progress,
        )
        classified = []
        pending = []
        for index, record in enumerate(records):
            if self._classify_entry(record, known_themes, progress) is None:
                pending.append(record)
            else:
                known_themes = self.__prompts.find_new_themes([record], known_themes)
                classified.append(record)
                on_classified(record)
            if progress.stopped:
                pending.extend(records[index + 1:])
                progress.leave_pending([left.feedback_id for left in records[index + 1:]])
                break
        self._end_batch(progress)
        return classified, pending, progress.stopped

    def summarise(self, result: AggregationResult, records: list[FeedbackRecord]) -> AISummary | None:
        """Summarise one run (call 2).

        Sends result's counts and, per theme, the one-liner of every counted
        record in records (its raw text, cut short, if it has none), as
        Part 1 did (D18). Over the size limit, the least severe examples are
        left out (D19). Returns an AISummary with one action per theme in
        result's order, or None if every attempt failed, so the caller keeps
        the last summary. The pipeline skips this call when classify_entries
        stopped, as the API is then unlikely to answer (D20).
        """
        task = SummaryTask(result.to_dict(), records, self.__prompts.summary_prompt)
        progress = BatchProgress(1)
        self.__reporter.on_batch_start(
            "Summarising this run", [self.__client.model, f"key: {self.__key_label}"], progress
        )
        progress.start_record()
        output = self._request(task, progress)
        summary = None
        if output is not None:
            summary = AISummary(output["overall_summary"], output["theme_actions"])
            progress.finish_ok()
            retries = progress.record_retries
            self.__reporter.on_record_ok(
                task.request_id, "1 retry" if retries == 1 else f"{retries} retries", progress
            )
        self._end_batch(progress)
        return summary

    def _classify_entry(
        self, record: FeedbackRecord, known_themes: list[str], progress: BatchProgress
    ) -> FeedbackRecord | None:
        """Classify one record. Returns it, or None if it failed and so keeps ai = None."""
        task = ClassificationTask(record, self.__prompts.system_prompt, self.__prompts.themes, known_themes)
        progress.start_record()
        result = self._request(task, progress)
        if result is None:
            return None
        try:
            # The summary rides along in record.ai, so Data saves it with the
            # record and call 2 can read it later without another request.
            record.set_ai(result["theme"], result["sentiment"], result["severity"], result["summary"])
        except ValueError as exc:
            progress.finish_failed(task.request_id)
            self.__reporter.on_record_failed(task.request_id, str(exc), progress)
            return None
        progress.finish_ok()
        self.__reporter.on_record_ok(
            task.request_id, f"{result['theme']} / {result['sentiment']} / {result['severity']}", progress
        )
        return record

    def _request(self, task: AITask, progress: BatchProgress) -> dict | None:
        """Send a task's request until its output validates, up to MAX_ATTEMPTS times.

        Every attempt is followed by the wait the client calls for, so callers
        never need their own throttle; a failure that a retry cannot fix stops
        at once. A failure that would hit every later request too also marks
        progress as stopped. Returns the validated output, or None after
        reporting the record as failed.
        """
        messages = task.build_messages()
        result = None
        reason = None
        gave_up_early = False
        connection_failures = 0
        total_tokens = 0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            backoff = BACKOFF_BASE_S**attempt
            wait_reason = WAIT_RATE_LIMIT
            self.__reporter.on_attempt_start(task.request_id, attempt, MAX_ATTEMPTS)
            try:
                raw, tokens, delay = self.__client.send(
                    messages, task.schema_name, task.schema, task.token_margin, task.max_completion_tokens
                )
                total_tokens += tokens
                progress.add_tokens(tokens)
                result = task.parse(raw)
                if result is None:
                    logger.debug("schema mismatch %s attempt %d: %s", task.request_id, attempt, raw)
                    reason = INVALID_OUTPUT
            except LLMRequestError as exc:
                logger.debug("%s error %s attempt %d: %s", exc.kind, task.request_id, attempt, exc)
                reason = str(exc)
                if exc.kind == LLMRequestError.AUTH:
                    progress.stop(reason, task.request_id)
                if not exc.retryable:
                    gave_up_early = True
                    break
                if exc.kind == LLMRequestError.CONNECTION:
                    connection_failures += 1
                    if connection_failures == MAX_ATTEMPTS:
                        progress.stop("connection lost", task.request_id)
                        break
                delay = exc.wait_seconds
                if delay is None:
                    delay = backoff
                    wait_reason = WAIT_BACKOFF
            except (json.JSONDecodeError, TypeError) as exc:
                # The model's content was not JSON text.
                logger.debug("non-JSON output %s attempt %d: %s", task.request_id, attempt, exc)
                reason = INVALID_OUTPUT
                delay = backoff
                wait_reason = WAIT_BACKOFF
            if delay > MAX_WAIT_S:
                progress.stop(f"rate-limit wait of {delay:.0f}s", task.request_id)
                gave_up_early = result is None
                break
            if result is None and attempt < MAX_ATTEMPTS:
                progress.add_retry()
                self.__reporter.on_attempt_failed(task.request_id, attempt, MAX_ATTEMPTS, reason)
            self.__reporter.on_wait(delay, wait_reason)
            time.sleep(delay)
            if result is not None:
                break

        self.__ledger.record(self.__key_label, task.request_id, total_tokens)
        if result is None:
            progress.finish_failed(task.request_id)
            failure = reason if gave_up_early else f"no valid output after {MAX_ATTEMPTS} attempts: {reason}"
            self.__reporter.on_record_failed(task.request_id, failure, progress)
        return result

    def _end_batch(self, progress: BatchProgress) -> None:
        if progress.stopped:
            self.__reporter.on_batch_stopped(progress)
        self.__reporter.on_batch_end(
            progress, self.__ledger.today_total(self.__key_label), self.__ledger.daily_limit
        )
