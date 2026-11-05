"""BatchProgress: the running counts and timings for one batch of LLM records."""

import time
from collections.abc import Callable


class BatchProgress:
    """What has happened so far in a batch, for a ProgressReporter to show."""

    def __init__(self, total: int, clock: Callable[[], float] = time.monotonic):
        self.__total = total
        self.__clock = clock
        self.__started = clock()
        self.__ok = 0
        self.__failed_ids = []
        self.__unattempted_ids = []
        self.__stop_reason = None
        self.__stopped_after = None
        self.__tokens = 0
        self.__last_finished = None
        self.__record_started = self.__started
        self.__record_tokens = 0
        self.__record_retries = 0

    @property
    def total(self) -> int:
        return self.__total

    @property
    def done(self) -> int:
        return self.__ok + len(self.__failed_ids)

    @property
    def ok(self) -> int:
        return self.__ok

    @property
    def failed(self) -> int:
        return len(self.__failed_ids)

    @property
    def failed_ids(self) -> list[str]:
        return list(self.__failed_ids)

    @property
    def pending_ids(self) -> list[str]:
        """Every record to retry next run: those that failed, then those never tried."""
        return self.__failed_ids + self.__unattempted_ids

    @property
    def stopped(self) -> bool:
        return self.__stop_reason is not None

    @property
    def stop_reason(self) -> str | None:
        return self.__stop_reason

    @property
    def stopped_after(self) -> str | None:
        """The request_id the batch stopped at."""
        return self.__stopped_after

    @property
    def tokens(self) -> int:
        return self.__tokens

    @property
    def elapsed(self) -> float:
        return self.__clock() - self.__started

    @property
    def eta_seconds(self) -> float | None:
        """Average seconds per finished record times records left, so waits count too.

        None until the first record finishes.
        """
        if self.__last_finished is None:
            return None
        average = (self.__last_finished - self.__started) / self.done
        return average * (self.__total - self.done)

    @property
    def record_seconds(self) -> float:
        """Seconds since the current record started."""
        return self.__clock() - self.__record_started

    @property
    def record_tokens(self) -> int:
        return self.__record_tokens

    @property
    def record_retries(self) -> int:
        return self.__record_retries

    def start_record(self) -> None:
        self.__record_started = self.__clock()
        self.__record_tokens = 0
        self.__record_retries = 0

    def add_tokens(self, tokens: int) -> None:
        self.__tokens += tokens
        self.__record_tokens += tokens

    def add_retry(self) -> None:
        self.__record_retries += 1

    def finish_ok(self) -> None:
        self.__ok += 1
        self.__last_finished = self.__clock()

    def finish_failed(self, request_id: str) -> None:
        self.__failed_ids.append(request_id)
        self.__last_finished = self.__clock()

    def stop(self, reason: str, request_id: str) -> None:
        self.__stop_reason = reason
        self.__stopped_after = request_id

    def leave_pending(self, request_ids: list[str]) -> None:
        """Record the entries a stopped batch never tried."""
        self.__unattempted_ids.extend(request_ids)
