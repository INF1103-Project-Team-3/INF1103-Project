# DateText: timestamps written the way the pages show them.

from datetime import datetime


class DateText:
    # "2026-10-05T09:15:00" -> "5 Oct"; anything else is shown as it is.
    @staticmethod
    def short(timestamp: str) -> str:
        try:
            moment = datetime.fromisoformat(timestamp)
        except (TypeError, ValueError):
            return timestamp or ""
        return f"{moment.day} {moment:%b}"

    # "2026-10-05T09:15:00" -> "5 Oct 2026, 09:15".
    @staticmethod
    def long(timestamp: str) -> str:
        try:
            moment = datetime.fromisoformat(timestamp)
        except (TypeError, ValueError):
            return timestamp or ""
        return f"{moment.day} {moment:%b %Y, %H:%M}"
