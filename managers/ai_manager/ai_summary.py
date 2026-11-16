"""AISummary: call 2's result for one run."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from managers.models import Serializable


@dataclass(frozen=True)
class AISummary(Serializable):
    """The overall summary and one suggested action per theme. Data saves it as summary.json."""

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    overall_summary: str
    theme_actions: list[dict[str, str]]
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        """A copy, so a caller cannot change the frozen summary's actions."""
        return {
            "overall_summary": self.overall_summary,
            "theme_actions": [dict(action) for action in self.theme_actions],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds a summary saved by to_dict(). Raises KeyError if a field is missing."""
        return cls(data["overall_summary"], data["theme_actions"], data["created_at"])
