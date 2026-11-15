from __future__ import annotations

import logging


class ConsoleLogFormatter(logging.Formatter):
    """Formats a log line for the console as "Level: message", leaving out any
    traceback, so the person at the terminal sees a plain line (P3, P4)."""

    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname.capitalize()}: {record.getMessage()}"
