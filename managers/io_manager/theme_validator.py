from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from managers.models import UNCLEAR_THEME

from .input_validator import InputValidator

if TYPE_CHECKING:
    from managers.logic_manager import LogicManager


class ThemeValidator(InputValidator):
    """Cleans up a typed theme by asking the Logic Manager to normalise it.

    Themes are free text, so I only reject an empty answer. Deciding what a
    label means (an existing theme, the Unclear theme, or a brand-new theme) is
    business logic, so I do not do it here; I call logic.normalise_theme()
    instead of copying its rules. With allow_blank=True an empty answer is
    accepted (a reviewer pressing Enter to keep the current theme).
    """

    NEW, UNUSABLE, KNOWN = "new", "unusable", "known"

    def __init__(self, logic: "LogicManager", allow_blank: bool = False):
        self._logic = logic
        self._allow_blank = allow_blank

    def check(self, answer: str):
        label = str(answer).strip()
        if not label:
            return ("", "") if self._allow_blank else (None, "theme cannot be empty")
        return self._logic.normalise_theme(label), ""

    def new_theme_outcome(self, theme: str, known: Iterable[str]) -> str:
        """For a theme an admin wants to add in Settings (terminal or GUI), already cleaned
        up by check(): NEW if it is not in known (the saved and queued themes, ignoring
        case), UNUSABLE if Logic read it as Unclear, KNOWN otherwise. Each view words it."""
        if theme == UNCLEAR_THEME:              # Logic treats filler words as Unclear
            return self.UNUSABLE
        if theme.lower() in {name.lower() for name in known}:
            return self.KNOWN
        return self.NEW
