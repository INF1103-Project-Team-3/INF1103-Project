"""ConsoleProgressReporter: shows AI progress in the terminal."""

import shutil
import sys
import threading
import time
from typing import TextIO

from batch_progress import BatchProgress
from progress_reporter import ProgressReporter

BAR_WIDTH = 20
REDRAW_INTERVAL_S = 1
THREAD_STOP_TIMEOUT_S = 2
# Shorter waits are the routine gap between requests: shown on the bar, without a line each.
MIN_WAIT_LINE_S = 1
CLEAR_LINE = "\r\x1b[K"


class ConsoleProgressReporter(ProgressReporter):
    """Prints a line per event, under a bar that redraws every second.

    The redraw runs on a small timer thread, so the bar keeps moving during a
    blocking request or a rate-limit wait. It is for display only. Output that
    is not a terminal (CI, a redirected log) gets plain lines and no thread.
    """

    def __init__(self, stream: TextIO | None = None, live: bool | None = None):
        self.__stream = stream or sys.stdout
        self.__live = self.__stream.isatty() if live is None else live
        self.__lock = threading.Lock()
        self.__stop_timer = threading.Event()
        self.__timer = None
        self.__progress = None
        self.__status = ""
        self.__status_started = 0.0
        self.__wait_until = None
        self.__wait_reason = ""

    def on_batch_start(self, title: str, details: list[str], progress: BatchProgress) -> None:
        self._end_timer()
        with self.__lock:
            self.__progress = progress
            self.__status = ""
            self.__wait_until = None
            self._write_line(" | ".join([f"[AI] {title}", *details]))
        if self.__live:
            self.__stop_timer.clear()
            self.__timer = threading.Thread(target=self._run_timer, name="ai-progress-timer", daemon=True)
            self.__timer.start()

    def on_attempt_start(self, request_id: str, attempt: int, max_attempts: int) -> None:
        with self.__lock:
            self.__status = f"{request_id} attempt {attempt}/{max_attempts}"
            self.__status_started = time.monotonic()
            self.__wait_until = None
            self._redraw()

    def on_attempt_failed(self, request_id: str, attempt: int, max_attempts: int, reason: str) -> None:
        with self.__lock:
            self._write_line(f"  retry {request_id}  attempt {attempt}/{max_attempts}: {reason}")

    def on_wait(self, seconds: float, reason: str) -> None:
        with self.__lock:
            self.__wait_until = time.monotonic() + seconds
            self.__wait_reason = reason
            if seconds >= MIN_WAIT_LINE_S:
                self._write_line(f"  wait  {reason}: {seconds:.1f}s")
            else:
                self._redraw()

    def on_record_ok(self, request_id: str, description: str, progress: BatchProgress) -> None:
        with self.__lock:
            self._finish_record(
                f"  ok    {request_id}  {description}   {progress.record_seconds:.1f}s  "
                f"{progress.record_tokens:,} tokens"
            )

    def on_record_failed(self, request_id: str, reason: str, progress: BatchProgress) -> None:
        with self.__lock:
            self._finish_record(f"  FAIL  {request_id}  left pending: {reason}")

    def on_batch_end(self, progress: BatchProgress, tokens_today: int | None, daily_limit: int | None) -> None:
        self._end_timer()
        counts = f"{progress.ok} ok"
        if progress.failed:
            counts += f", {progress.failed} pending ({', '.join(progress.failed_ids)})"
        parts = [f"[AI] Done in {self._format_duration(progress.elapsed)}: {counts}", f"{progress.tokens:,} tokens"]
        if tokens_today is not None:
            limit = f" / {daily_limit:,}" if daily_limit is not None else ""
            parts.append(f"today {tokens_today:,}{limit} (local estimate)")
        with self.__lock:
            self.__progress = None
            self._write_line(" | ".join(parts))

    def _finish_record(self, line: str) -> None:
        self.__status = ""
        self.__wait_until = None
        self._write_line(line)
        if not self.__live:  # no bar to redraw, so each record ends with its progress
            self.__stream.write(self._bar_line() + "\n")
            self.__stream.flush()

    def _write_line(self, line: str) -> None:
        """Print one permanent line, with the bar redrawn underneath it."""
        if self.__live:
            self.__stream.write(CLEAR_LINE)
        self.__stream.write(line + "\n")
        self.__stream.flush()
        self._redraw()

    def _redraw(self) -> None:
        if not self.__live or self.__progress is None:
            return
        # One character short of the width, as a wrapped line cannot be redrawn.
        width = shutil.get_terminal_size().columns - 1
        self.__stream.write(CLEAR_LINE + self._bar_line()[:width])
        self.__stream.flush()

    def _bar_line(self) -> str:
        progress = self.__progress
        share = progress.done / progress.total if progress.total else 0
        filled = int(share * BAR_WIDTH)
        eta = progress.eta_seconds
        line = (
            f"[{'#' * filled}{'.' * (BAR_WIDTH - filled)}] {progress.done}/{progress.total}  {share:.0%}"
            f"  ETA {'--' if eta is None else self._format_duration(eta)}"
            f"  ok {progress.ok}  failed {progress.failed}"
        )
        status = self._status_text()
        return f"{line}  | {status}" if status else line

    def _status_text(self) -> str:
        """Return what is happening now, with a countdown or the time so far."""
        now = time.monotonic()
        if self.__wait_until is not None:
            return f"wait {self.__wait_reason} {max(self.__wait_until - now, 0):.0f}s"
        if self.__status:
            return f"{self.__status} {self._format_duration(now - self.__status_started)}"
        return ""

    def _format_duration(self, seconds: float) -> str:
        minutes, remainder = divmod(int(seconds), 60)
        return f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"

    def _run_timer(self) -> None:
        while not self.__stop_timer.wait(REDRAW_INTERVAL_S):
            with self.__lock:
                self._redraw()

    def _end_timer(self) -> None:
        if self.__timer is None:
            return
        self.__stop_timer.set()
        self.__timer.join(THREAD_STOP_TIMEOUT_S)
        self.__timer = None
