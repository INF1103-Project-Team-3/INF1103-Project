"""BatchProgress: a read-only view of one batch's counts and timings."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .progress_tracker import ProgressTracker


class BatchProgress:
    """What has happened so far in a batch, for a ProgressReporter to show.

    Read-only (section 8.4): every member reads the ProgressTracker behind it,
    so a reporter always sees the current counts but cannot change them.
    """

    def __init__(self, tracker: ProgressTracker):
        self.__tracker = tracker

    @property
    def total(self) -> int:
        return self.__tracker.total

    @property
    def done(self) -> int:
        return self.__tracker.done

    @property
    def ok(self) -> int:
        return self.__tracker.ok

    @property
    def failed(self) -> int:
        return self.__tracker.failed

    @property
    def failed_ids(self) -> list[str]:
        return self.__tracker.failed_ids

    @property
    def pending_ids(self) -> list[str]:
        """Every record to retry next run: those that failed, then those never tried."""
        return self.__tracker.pending_ids

    @property
    def stopped(self) -> bool:
        return self.__tracker.stopped

    @property
    def stop_reason(self) -> str | None:
        return self.__tracker.stop_reason

    @property
    def stopped_after(self) -> str | None:
        """The request_id the batch stopped at."""
        return self.__tracker.stopped_after

    @property
    def tokens(self) -> int:
        return self.__tracker.tokens

    @property
    def elapsed(self) -> float:
        return self.__tracker.elapsed

    @property
    def eta_seconds(self) -> float | None:
        """Average seconds per finished record times records left; None until one finishes."""
        return self.__tracker.eta_seconds

    @property
    def record_seconds(self) -> float:
        """Seconds since the current record started."""
        return self.__tracker.record_seconds

    @property
    def record_tokens(self) -> int:
        return self.__tracker.record_tokens

    @property
    def record_retries(self) -> int:
        return self.__tracker.record_retries
