# QtProgressReporter: AI progress events turned into Qt signals.

from managers.ai_manager import BatchProgress, ProgressReporter

from .progress_signals import ProgressSignals


# The GUI's ProgressReporter.
class QtProgressReporter(ProgressReporter):
    def __init__(self):
        self.__signals = ProgressSignals()

    # Connect widgets to these.
    @property
    def signals(self) -> ProgressSignals:
        return self.__signals

    def on_batch_start(self, title: str, details: list[str], progress: BatchProgress) -> None:
        self.__signals.batch_started.emit(title, progress.total)

    def on_attempt_start(self, request_id: str, attempt: int, max_attempts: int) -> None:
        self.__signals.attempt_started.emit(request_id, attempt, max_attempts)

    def on_attempt_failed(self, request_id: str, attempt: int, max_attempts: int, reason: str) -> None:
        self.__signals.attempt_failed.emit(request_id, attempt, max_attempts, reason)

    def on_wait(self, seconds: float, reason: str) -> None:
        self.__signals.waiting.emit(float(seconds), reason)

    def on_record_ok(self, request_id: str, description: str, progress: BatchProgress) -> None:
        self.__signals.record_ok.emit(request_id, description, progress.done, progress.total)

    def on_record_failed(self, request_id: str, reason: str, progress: BatchProgress) -> None:
        self.__signals.record_failed.emit(request_id, reason, progress.done, progress.total)

    def on_batch_stopped(self, progress: BatchProgress) -> None:
        self.__signals.batch_stopped.emit(progress.stop_reason or "", progress.done, progress.total)

    def on_batch_end(self, progress: BatchProgress, tokens_today: int | None, daily_limit: int | None) -> None:
        self.__signals.batch_finished.emit(progress.ok, progress.failed, progress.total,
                                           tokens_today, daily_limit)
