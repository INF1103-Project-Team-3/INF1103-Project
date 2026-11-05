"""AI manager: every LLM API call goes through here.

Call 1 (classify_entries) classifies feedback entries; call 2 (summarise)
summarises a run's aggregated stats. Both share one retry loop, which works
with any AITask and any LLMClient. API only: no print(), no domain rules;
progress goes to a ProgressReporter as events.
"""

import json
import logging
import os
import time
from collections.abc import Callable

from ai_task import AITask
from batch_progress import BatchProgress
from classification_task import ClassificationTask
from llm_client import LLMClient
from llm_request_error import LLMRequestError
from progress_reporter import ProgressReporter
from prompt_library import PromptLibrary
from summary_task import SummaryTask
from token_ledger import TokenLedger

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_USAGE_LOG_PATH = os.path.join(BASE_DIR, "config", "token-usage-log.json")

MAX_ATTEMPTS = 3  # per request, covering schema mismatches and retryable API failures
BACKOFF_BASE_S = 2  # failed attempt n waits BACKOFF_BASE_S ** n without headers
# The per-minute limit resets within 60 seconds, and clients add a small buffer
# to that, so a longer wait means the daily cap, which could stall a batch for hours.
MAX_WAIT_S = 61
AI_FIELD_PREFIX = "ai_"
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
        ledger_path: str = TOKEN_USAGE_LOG_PATH,
    ):
        self.__client = client
        self.__key_label = key_label
        self.__prompts = prompts
        self.__reporter = reporter
        self.__ledger = TokenLedger(client.model, ledger_path)

    def classify_entries(
        self, entries: list[dict], stored_records: list[dict], on_classified: Callable[[dict], object]
    ) -> tuple[list[dict], list[dict], bool]:
        """Classify each entry (call 1), and never exit the app.

        An entry needs feedback_id and text. Only the text reaches the model,
        along with any labels it coined in stored_records or earlier in this
        batch; everything else, human tags included, passes through untouched.
        A classified record is its entry plus ai_theme, ai_sentiment and
        ai_severity, and goes to on_classified as soon as it finishes, so a
        crash does not lose paid work.

        Returns (classified, pending, stopped). A record with invalid output
        goes pending and the batch continues. A missing or rejected key, every
        attempt lost to connection errors, or a wait over MAX_WAIT_S stops the
        batch and leaves the rest pending, since retrying every record could
        take about 100 seconds each.
        """
        known_themes = self.__prompts.find_new_themes(stored_records)
        progress = BatchProgress(len(entries))
        self.__reporter.on_batch_start(
            f"Classifying {len(entries)} records",
            [self.__client.model, "1 sample each", f"key: {self.__key_label}"],
            progress,
        )
        classified = []
        pending = []
        for index, entry in enumerate(entries):
            record = self._classify_entry(entry, known_themes, progress)
            if record is None:
                pending.append(entry)
            else:
                known_themes = self.__prompts.find_new_themes([record], known_themes)
                classified.append(record)
                on_classified(record)
            if progress.stopped:
                pending.extend(entries[index + 1:])
                progress.leave_pending([left["feedback_id"] for left in entries[index + 1:]])
                break
        self._end_batch(progress)
        return classified, pending, progress.stopped

    def summarise(self, stats: dict) -> dict | None:
        """Summarise one run's aggregated stats (call 2).

        stats is logic_manager.aggregate_themes' output. Returns
        {"overall_summary", "theme_actions"}, with one action per theme in
        stats' order, or None if every attempt failed.
        """
        task = SummaryTask(stats, self.__prompts.summary_prompt)
        progress = BatchProgress(1)
        self.__reporter.on_batch_start(
            "Summarising this run", [self.__client.model, f"key: {self.__key_label}"], progress
        )
        progress.start_record()
        result = self._request(task, progress)
        if result is not None:
            progress.finish_ok()
            retries = progress.record_retries
            self.__reporter.on_record_ok(
                task.request_id, "1 retry" if retries == 1 else f"{retries} retries", progress
            )
        self._end_batch(progress)
        return result

    def _classify_entry(self, entry: dict, known_themes: list[str], progress: BatchProgress) -> dict | None:
        """Classify one entry. Returns its record, or None if the request failed."""
        task = ClassificationTask(entry, self.__prompts.system_prompt, self.__prompts.themes, known_themes)
        progress.start_record()
        result = self._request(task, progress)
        if result is None:
            return None
        progress.finish_ok()
        self.__reporter.on_record_ok(
            task.request_id, f"{result['theme']} / {result['sentiment']} / {result['severity']}", progress
        )
        # The model's own keys stay unprefixed, keeping the prompt close to its tested form.
        return {**entry, **{f"{AI_FIELD_PREFIX}{key}": value for key, value in result.items()}}

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
