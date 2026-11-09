"""ImpactReport: whether one logged action was followed by less negative feedback."""

from copy import deepcopy
from typing import Self

from managers.models import Action, Serializable


class ImpactReport(Serializable):
    """Read-only result for one action, built by ImpactAnalyser.

    before and after describe the two equal windows either side of the action
    date, or are None when there is no after window yet (an action dated today
    or later). weekly is the chart data: {week_start, negative, total} per week.
    """

    EFFECTIVE = "Effective"
    NO_CHANGE = "No change"
    WORSE = "Worse"
    TOO_EARLY = "Too early to tell"
    LABELS = (EFFECTIVE, NO_CHANGE, WORSE, TOO_EARLY)

    def __init__(
        self,
        action: Action,
        label: str,
        message: str,
        before: dict | None = None,
        after: dict | None = None,
        weekly: list[dict] | None = None,
        warnings: list[str] | None = None,
    ):
        """Raises ValueError for a label not in LABELS."""
        if label not in self.LABELS:
            raise ValueError(f"label must be one of {self.LABELS}, got {label!r}")
        self.__action = action
        self.__label = label
        self.__message = message
        self.__before = deepcopy(before)
        self.__after = deepcopy(after)
        self.__weekly = deepcopy(weekly) if weekly else []
        self.__warnings = list(warnings or [])

    @property
    def action(self) -> Action:
        """The action measured (read-only itself)."""
        return self.__action

    @property
    def label(self) -> str:
        """One of LABELS."""
        return self.__label

    @property
    def message(self) -> str:
        """A sentence ready to show, e.g. why it is too early to tell."""
        return self.__message

    @property
    def before(self) -> dict | None:
        """The window before the action date (a copy), or None."""
        return deepcopy(self.__before)

    @property
    def after(self) -> dict | None:
        """The window from the action date (a copy), or None."""
        return deepcopy(self.__after)

    @property
    def weekly(self) -> list[dict]:
        """{week_start, negative, total} per week around the action date (a copy)."""
        return deepcopy(self.__weekly)

    @property
    def warnings(self) -> list[str]:
        """Reasons to treat the label with care, e.g. an overlapping action (a copy)."""
        return list(self.__warnings)

    def to_dict(self) -> dict:
        return {
            "action": self.__action.to_dict(),
            "label": self.__label,
            "message": self.__message,
            "before": self.before,
            "after": self.after,
            "weekly": self.weekly,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds a report saved by to_dict(). Raises ValueError if it can't be read."""
        try:
            return cls(Action.from_dict(data["action"]), data["label"], data["message"],
                       data.get("before"), data.get("after"), data.get("weekly"), data.get("warnings"))
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"not a readable impact report: {error!r}") from error

    def __eq__(self, other) -> bool:
        return isinstance(other, ImpactReport) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return f"ImpactReport({self.__action.action_id!r}, {self.__label!r})"
