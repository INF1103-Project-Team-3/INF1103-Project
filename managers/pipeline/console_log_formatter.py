from __future__ import annotations

import logging

# Carriage return, then erase to the end of the line: removes the AI progress bar
# drawn on the current terminal line, so the log line starts clean (F8)
CLEAR_LINE = "\r\x1b[K"


class ConsoleLogFormatter(logging.Formatter):
    """Formats a log line for the console as "Level: message", leaving out any
    traceback, so the person at the terminal sees a plain line (P3, P4).
    clear_line=True (the stream is a terminal) first clears the line, where the
    AI progress bar may be drawn; the bar redraws below on its next tick."""

    def __init__(self, clear_line: bool = False) -> None:
        super().__init__()
        self.__clear_line = clear_line

    def format(self, record: logging.LogRecord) -> str:
        line = f"{record.levelname.capitalize()}: {record.getMessage()}"
        return CLEAR_LINE + line if self.__clear_line else line
