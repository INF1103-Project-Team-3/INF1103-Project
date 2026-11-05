"""ProgressReporter: what AIManager tells the outside world about a batch."""

from abc import ABC, abstractmethod

from .batch_progress import BatchProgress


class ProgressReporter(ABC):
    """Interface: must be able to receive run events.

    Events can arrive off a UI thread, and handlers must not block.
    """

    @abstractmethod
    def on_batch_start(self, title: str, details: list[str], progress: BatchProgress) -> None:
        """A batch is starting. details are short facts, such as the model."""

    @abstractmethod
    def on_attempt_start(self, request_id: str, attempt: int, max_attempts: int) -> None:
        """A request is about to be sent."""

    @abstractmethod
    def on_attempt_failed(self, request_id: str, attempt: int, max_attempts: int, reason: str) -> None:
        """An attempt failed and another will follow."""

    @abstractmethod
    def on_wait(self, seconds: float, reason: str) -> None:
        """The batch is about to wait this long before its next request."""

    @abstractmethod
    def on_record_ok(self, request_id: str, description: str, progress: BatchProgress) -> None:
        """A record finished. description is a short account of the result."""

    @abstractmethod
    def on_record_failed(self, request_id: str, reason: str, progress: BatchProgress) -> None:
        """A record failed, and is retried on the next run."""

    @abstractmethod
    def on_batch_stopped(self, progress: BatchProgress) -> None:
        """The batch stopped early: further requests would fail the same way."""

    @abstractmethod
    def on_batch_end(self, progress: BatchProgress, tokens_today: int | None, daily_limit: int | None) -> None:
        """The batch is over. tokens_today is None if the ledger could not be read."""
