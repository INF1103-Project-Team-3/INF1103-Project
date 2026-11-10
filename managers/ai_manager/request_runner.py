"""RequestRunner: sends one AI request until its output validates, or gives up."""

import json
import logging
import time

from .ai_task import AITask
from .llm_client import LLMClient
from .llm_request_error import LLMRequestError
from .progress_reporter import ProgressReporter
from .progress_tracker import ProgressTracker
from .token_ledger import TokenLedger

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # per request, covering schema mismatches and retryable API failures
BACKOFF_BASE_S = 2  # failed attempt n waits BACKOFF_BASE_S ** n without headers
# The per-minute limit resets within 60 seconds, and clients add a small buffer
# to that, so a longer wait means the daily cap, which could stall a batch for hours.
MAX_WAIT_S = 61
INVALID_OUTPUT = "invalid output"
WAIT_RATE_LIMIT = "rate limit"
WAIT_BACKOFF = "backoff"


class RequestRunner:
    """The retry policy shared by both calls: attempts, waits, when to stop the
    batch, and the token ledger entry for each request. It works with any
    AITask and any LLMClient, so AIManager only decides what to send."""

    def __init__(self, client: LLMClient, reporter: ProgressReporter, ledger: TokenLedger, key_label: str):
        self.__client = client
        self.__reporter = reporter
        self.__ledger = ledger
        self.__key_label = key_label

    def run(self, task: AITask, tracker: ProgressTracker) -> dict | None:
        """Send a task's request until its output validates, up to MAX_ATTEMPTS times.

        Every attempt is followed by the wait the client calls for, so callers
        never need their own throttle; a failure that a retry cannot fix stops
        at once. A failure that would hit every later request too also marks
        the batch as stopped. Returns the validated output, or None after
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
                tracker.add_tokens(tokens)
                result = task.parse(raw)
                if result is None:
                    logger.debug("schema mismatch %s attempt %d: %s", task.request_id, attempt, raw)
                    reason = INVALID_OUTPUT
            except LLMRequestError as exc:
                logger.debug("%s error %s attempt %d: %s", exc.kind, task.request_id, attempt, exc)
                reason = str(exc)
                if exc.kind == LLMRequestError.AUTH:
                    tracker.stop(reason, task.request_id)
                if not exc.retryable:
                    gave_up_early = True
                    break
                if exc.kind == LLMRequestError.CONNECTION:
                    connection_failures += 1
                    if connection_failures == MAX_ATTEMPTS:
                        tracker.stop("connection lost", task.request_id)
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
                tracker.stop(f"rate-limit wait of {delay:.0f}s", task.request_id)
                gave_up_early = result is None
                break
            if result is None and attempt < MAX_ATTEMPTS:
                tracker.add_retry()
                self.__reporter.on_attempt_failed(task.request_id, attempt, MAX_ATTEMPTS, reason)
            self.__reporter.on_wait(delay, wait_reason)
            time.sleep(delay)
            if result is not None:
                break

        self.__ledger.record(self.__key_label, task.request_id, total_tokens)
        if result is None:
            tracker.finish_failed(task.request_id)
            failure = reason if gave_up_early else f"no valid output after {MAX_ATTEMPTS} attempts: {reason}"
            self.__reporter.on_record_failed(task.request_id, failure, tracker.progress)
        return result
