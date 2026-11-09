from __future__ import annotations

from typing import TYPE_CHECKING

from .input_validator import InputValidator

if TYPE_CHECKING:
    from ..logic_manager import LogicManager


class ThemeValidator(InputValidator):
    """Cleans up a typed theme by asking the Logic Manager to normalise it.

    Themes are free text, so I only reject an empty answer. Deciding what a
    label means (an existing theme, the Unclear theme, or a brand-new theme) is
    business logic, so I do not do it here; I call logic.normalise_theme()
    instead of copying its rules. With allow_blank=True an empty answer is
    accepted (a reviewer pressing Enter to keep the current theme).
    """

    def __init__(self, logic: "LogicManager", allow_blank: bool = False):
        self._logic = logic
        self._allow_blank = allow_blank

    def check(self, answer: str):
        label = str(answer).strip()
        if not label:
            return ("", "") if self._allow_blank else (None, "theme cannot be empty")
        return self._logic.normalise_theme(label), ""
