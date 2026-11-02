"""RecordingProgressReporter: a ProgressReporter that keeps every event for tests to check."""

from progress_reporter import ProgressReporter


class RecordingProgressReporter(ProgressReporter):
    """Each event is stored as (name, *arguments), without the BatchProgress."""

    def __init__(self):
        self.__events = []

    @property
    def events(self) -> list[tuple]:
        return list(self.__events)

    @property
    def names(self) -> list[str]:
        return [event[0] for event in self.__events]

    def on_batch_start(self, title, details, progress):
        self.__events.append(("batch_start", title, details))

    def on_attempt_start(self, request_id, attempt, max_attempts):
        self.__events.append(("attempt_start", request_id, attempt, max_attempts))

    def on_attempt_failed(self, request_id, attempt, max_attempts, reason):
        self.__events.append(("attempt_failed", request_id, attempt, max_attempts, reason))

    def on_wait(self, seconds, reason):
        self.__events.append(("wait", seconds, reason))

    def on_record_ok(self, request_id, description, progress):
        self.__events.append(("record_ok", request_id, description))

    def on_record_failed(self, request_id, reason, progress):
        self.__events.append(("record_failed", request_id, reason))

    def on_batch_stopped(self, progress):
        self.__events.append(("batch_stopped", progress.stop_reason, progress.stopped_after))

    def on_batch_end(self, progress, tokens_today, daily_limit):
        self.__events.append(("batch_end", tokens_today, daily_limit))
