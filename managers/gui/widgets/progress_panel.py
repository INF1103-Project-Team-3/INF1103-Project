# ProgressPanel: shows a pipeline run's progress from QtProgressReporter's signals.

import html
from datetime import datetime

from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout

from ..progress_signals import ProgressSignals
from ..style import LOG_ERROR, LOG_TEXT, LOG_WARN, restyle

MAX_LOG_LINES = 500


# Title, progress bar, a status line and a dark log.
class ProgressPanel(QFrame):
    def __init__(self, signals: ProgressSignals, parent=None):
        super().__init__(parent)
        self.setObjectName("progressCard")
        self.__title = QLabel("No run yet")
        self.__title.setObjectName("cardTitle")
        self.__bar = QProgressBar()
        self.__bar.setTextVisible(False)
        self.__bar.setFixedHeight(12)
        self.__bar.setRange(0, 1)
        self.__bar.setValue(0)
        self.__status = QLabel("Process sends every entry still waiting for the AI through the pipeline.")
        self.__status.setObjectName("statusLine")
        self.__status.setWordWrap(True)
        self.__log = QPlainTextEdit()
        self.__log.setReadOnly(True)
        self.__log.setMaximumBlockCount(MAX_LOG_LINES)
        self.__log.setObjectName("runLog")
        self.__log.setMinimumHeight(200)
        self.__log.setMaximumHeight(320)
        note = QLabel("Runs in the background, so other pages stay usable. If the AI can't be reached "
                      "for an entry, the student's values are used, it's marked Unverified and "
                      "counted, and it's sent to the AI again on the next run.")
        note.setObjectName("statusLine")
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(self.__title)
        layout.addWidget(self.__bar)
        layout.addWidget(self.__status)
        layout.addWidget(self.__log, 1)
        layout.addWidget(note)
        self.set_running(False)

        signals.batch_started.connect(self.__on_batch_started)
        signals.attempt_failed.connect(self.__on_attempt_failed)
        signals.waiting.connect(self.__on_waiting)
        signals.record_ok.connect(self.__on_record_ok)
        signals.record_failed.connect(self.__on_record_failed)
        signals.batch_stopped.connect(self.__on_batch_stopped)
        signals.batch_finished.connect(self.__on_batch_finished)

    # Blue border while a run is going, plain border otherwise.
    def set_running(self, running: bool) -> None:
        self.setProperty("idle", not running)
        restyle(self)

    # Adds a line from outside the AI batch (e.g. "Run finished", "Run failed: ...").
    def show_message(self, text: str) -> None:
        self.__write(text)

    def __write(self, text: str, colour: str = LOG_TEXT) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = html.escape(f"[{stamp}] {text}")
        self.__log.appendHtml(f'<span style="color:{colour}; white-space:pre">{line}</span>')

    def __on_batch_started(self, title: str, total: int) -> None:
        self.__title.setText(f"{title}: 0 of {total}")
        self.__bar.setRange(0, max(total, 1))
        self.__bar.setValue(0)
        self.__status.setText(f"0 of {total} done")
        self.__write(f"Started: {title} ({total} entries)")

    def __on_attempt_failed(self, request_id: str, attempt: int, max_attempts: int, reason: str) -> None:
        self.__write(f"{request_id} → attempt {attempt} of {max_attempts} failed ({reason})", LOG_WARN)

    def __on_waiting(self, seconds: float, reason: str) -> None:
        self.__status.setText(f"Waiting {seconds:.0f}s ({reason})…")
        self.__write(f"waiting {seconds:.0f}s ({reason})…", LOG_WARN)

    def __on_record_ok(self, request_id: str, description: str, done: int, total: int) -> None:
        self.__progress(done, total)
        self.__write(f"{request_id} → {description}")

    def __on_record_failed(self, request_id: str, reason: str, done: int, total: int) -> None:
        self.__progress(done, total)
        self.__write(f"{request_id} failed: {reason} (retried next run)", LOG_ERROR)

    def __on_batch_stopped(self, reason: str, done: int, total: int) -> None:
        self.__status.setText(f"Stopped after {done} of {total}: {reason}")
        self.__write(f"Batch stopped: {reason}", LOG_ERROR)

    def __on_batch_finished(self, ok: int, failed: int, total: int, tokens_today, daily_limit) -> None:
        text = f"Finished: {ok} classified, {failed} failed, of {total}"
        if tokens_today is not None and daily_limit:
            text += f" · tokens today {tokens_today:,} of {daily_limit:,}"
        self.__title.setText(f"Finished: {ok} of {total} classified")
        self.__bar.setValue(self.__bar.maximum())
        self.__status.setText(text)
        self.__write(text)

    def __progress(self, done: int, total: int) -> None:
        self.__bar.setValue(done)
        self.__status.setText(f"{done} of {total} done")
        title = self.__title.text().rsplit(":", 1)[0]
        self.__title.setText(f"{title}: {done} of {total}")
