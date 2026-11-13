from __future__ import annotations

from typing import Iterable

from .input_validator import InputValidator


class ChoiceValidator(InputValidator):
    """Accepts one value from a fixed list, ignoring upper/lower case.

    I use it for menu numbers, sentiments, severities and the user/admin role,
    so those rules are written once. With allow_blank=True an empty answer is
    accepted and returned as "" (used when a reviewer presses Enter to keep a value).
    """

    def __init__(self, options: Iterable[str], allow_blank: bool = False,
                 error: str | None = None):
        # map the lower-case form to the real option, so typing capitals still matches
        self._options = {str(option).lower(): str(option) for option in options}
        self._allow_blank = allow_blank
        self._error = error or f"choose one of: {', '.join(self._options.values())}"

    def check(self, answer: str):
        text = answer.strip().lower()
        if not text and self._allow_blank:
            return "", ""
        if text in self._options:
            return self._options[text], ""
        return None, self._error
