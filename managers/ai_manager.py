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
from collections import Counter

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
# Each entry is classified this many times so run-to-run instability is
# measured (the agreement field) rather than hidden. Triples token use.
SAMPLES_PER_ENTRY = 3
CLASSIFIED_FIELDS = ("theme", "sentiment", "severity")
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
        samples_per_entry: int = SAMPLES_PER_ENTRY,
        ledger_path: str = TOKEN_USAGE_LOG_PATH,
    ):
        self.__client = client
        self.__key_label = key_label
        self.__prompts = prompts
        self.__reporter = reporter
        self.__samples_per_entry = samples_per_entry
        self.__ledger = TokenLedger(client.model, ledger_path)

    def classify_entries(self, entries: list[dict[str, str]], stored_records: list[dict]) -> list[dict]:
        """Classify each entry (call 1) and return the records that succeeded.

        Each entry is {"feedback_id", "text", "timestamp"} from io_manager; its
        record is the entry merged with the five AI fields plus agreement. An
        entry that fails is left out, and is retried on the next run. Coined
        themes in stored_records, and then in each new record, are offered back
        to the model.
        """
        known_themes = self.__prompts.find_new_themes(stored_records)
        progress = BatchProgress(len(entries))
        samples = self.__samples_per_entry
        samples_each = f"{samples} sample{'' if samples == 1 else 's'} each"
        self.__reporter.on_batch_start(
            f"Classifying {len(entries)} records",
            [self.__client.model, samples_each, f"key: {self.__key_label}"],
            progress,
        )
        classified = []
        for entry in entries:
            record = self._classify_entry(entry, known_themes, progress)
            if record is None:
                continue
            known_themes = self.__prompts.find_new_themes([record], known_themes)
            classified.append(record)
        self._end_batch(progress)
        return classified

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

    def _classify_entry(self, entry: dict[str, str], known_themes: list[str], progress: BatchProgress) -> dict | None:
        """Classify one entry, samples_per_entry times.

        Returns entry merged with the five AI fields plus agreement, or None if
        any sample fails.
        """
        task = ClassificationTask(entry, self.__prompts.system_prompt, known_themes)
        progress.start_record()
        samples = []
        for _ in range(self.__samples_per_entry):
            result = self._request(task, progress)
            if result is None:
                # Agreement is only meaningful over the full set of samples.
                return None
            samples.append(result)
        record = {**entry, **self._aggregate_samples(samples)}
        progress.finish_ok()
        self.__reporter.on_record_ok(
            task.request_id, " / ".join(record[field] for field in CLASSIFIED_FIELDS), progress
        )
        return record

    def _request(self, task: AITask, progress: BatchProgress) -> dict | None:
        """Send a task's request until its output validates, up to MAX_ATTEMPTS times.

        Every attempt is followed by the wait the client calls for, so callers
        never need their own throttle; a failure that a retry cannot fix stops
        at once. Returns the validated output, or None after reporting the
        record as failed.
        """
        messages = task.build_messages()
        result = None
        reason = None
        stopped_early = False
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
                if not exc.retryable:
                    stopped_early = True
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
            failure = reason if stopped_early else f"no valid output after {MAX_ATTEMPTS} attempts: {reason}"
            self.__reporter.on_record_failed(task.request_id, failure, progress)
        return result

    def _end_batch(self, progress: BatchProgress) -> None:
        self.__reporter.on_batch_end(
            progress, self.__ledger.today_total(self.__key_label), self.__ledger.daily_limit
        )

    def _aggregate_samples(self, samples: list[dict]) -> dict:
        """Combine repeated classifications of one entry into one result.

        Theme, sentiment and severity each take the majority value, falling back
        to the first sample's (confidence does not track correctness, so it is
        not used as a tie-breaker). Summary and confidence come from the
        highest-confidence sample that agrees with all three final values.
        agreement is the weakest field's share of samples matching its final
        value: 1.0 means unanimous; logic_manager decides what to flag.
        """
        final = {field: self._majority_or_first([s[field] for s in samples]) for field in CLASSIFIED_FIELDS}
        agreeing = [s for s in samples if all(s[f] == final[f] for f in CLASSIFIED_FIELDS)]
        source = max(agreeing or samples, key=lambda s: s["confidence"])
        agreement = min(
            sum(s[field] == final[field] for s in samples) / len(samples) for field in CLASSIFIED_FIELDS
        )
        return {**final, "summary": source["summary"], "confidence": source["confidence"],
                "agreement": round(agreement, 2)}

    def _majority_or_first(self, values: list[str]) -> str:
        """Return the value most samples share, or the first sample's if none has a majority."""
        value, count = Counter(values).most_common(1)[0]
        return value if count > len(values) / 2 else values[0]
