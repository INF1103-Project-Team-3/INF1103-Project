"""ActionSuggestions: suggested actions worked out by rules, for when the AI's summary can't run."""

from copy import deepcopy
from datetime import datetime
from typing import Self

from managers.models import Serializable


class ActionSuggestions(Serializable):
    """One suggested action per theme, in the same [{"theme", "suggested_action"}]
    shape as AISummary.theme_actions, so a view can show either. Built by
    ActionAdvisor from keyword rules, with no AI (design reference D21)."""

    LABEL = "Suggested by rules (AI unavailable)"

    def __init__(self, theme_actions: list[dict[str, str]], created_at: str | None = None):
        self.__theme_actions = deepcopy(theme_actions)
        self.__created_at = created_at or datetime.now().isoformat(timespec="seconds")

    @property
    def theme_actions(self) -> list[dict[str, str]]:
        """[{"theme", "suggested_action"}], one per theme (a copy)."""
        return deepcopy(self.__theme_actions)

    @property
    def created_at(self) -> str:
        return self.__created_at

    def to_dict(self) -> dict:
        return {"source": "rules", "theme_actions": self.theme_actions, "created_at": self.__created_at}

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds suggestions saved by to_dict(). Raises ValueError if they can't be read."""
        try:
            actions = data["theme_actions"]
            if not all(isinstance(a, dict) and {"theme", "suggested_action"} <= set(a) for a in actions):
                raise ValueError("each action needs a theme and a suggested_action")
            return cls(actions, data["created_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"not readable action suggestions: {error!r}") from error

    def __eq__(self, other) -> bool:
        return isinstance(other, ActionSuggestions) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return f"ActionSuggestions({len(self.__theme_actions)} themes)"
