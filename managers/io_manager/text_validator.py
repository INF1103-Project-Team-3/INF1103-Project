from __future__ import annotations

from .input_validator import InputValidator


class TextValidator(InputValidator):
    """Checks free text: not empty, contains letters, and not too long.

    I use one class for the feedback text, the action description and the
    optional keyword, and only change the settings: the label appears in the
    error message ("text is empty", "description is empty", ...), and
    required=False lets a blank answer through, returned as "" (the keyword).
    """

    DEFAULT_MAX_LENGTH = 2000

    def __init__(self, label: str = "text", max_length: int | None = None,
                 required: bool = True, require_letter: bool = True):
        self._label = label
        self._max_length = max_length or self.DEFAULT_MAX_LENGTH
        self._required = required
        self._require_letter = require_letter

    def check(self, answer: str):
        text = str(answer).strip()
        if not text:
            return ("", "") if not self._required else (None, f"{self._label} is empty")
        if self._require_letter and not any(c.isalpha() for c in text):
            return None, f"{self._label} contains no letters"
        if len(text) > self._max_length:
            return None, f"{self._label} longer than {self._max_length} characters"
        return text, ""
