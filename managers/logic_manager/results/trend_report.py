"""TrendReport: how one run compares with an earlier one."""

from copy import deepcopy
from typing import Self

from managers.models import Serializable


class TrendReport(Serializable):
    """Read-only, display-ready comparison of two runs, built by TrendAnalyser."""

    ESCALATING = "Escalating"
    NEW = "New"
    EASING = "Easing"
    STEADY = "Steady"
    NOT_REPORTED = "Not reported"
    # the order themes are shown in
    STATUS_ORDER = (ESCALATING, NEW, EASING, STEADY, NOT_REPORTED)

    def __init__(
        self,
        has_previous: bool,
        message: str | None = None,
        previous_run: dict | None = None,
        headline: dict | None = None,
        themes: list[dict] | None = None,
    ):
        self.__has_previous = has_previous
        self.__message = message
        self.__previous_run = deepcopy(previous_run)
        self.__headline = deepcopy(headline) if headline else {}
        self.__themes = deepcopy(themes) if themes else []

    @property
    def has_previous(self) -> bool:
        """False when there was nothing to compare with."""
        return self.__has_previous

    @property
    def message(self) -> str | None:
        """Why there is no comparison, or None if there is one."""
        return self.__message

    @property
    def previous_run(self) -> dict | None:
        """The earlier run's run_at and source_file (a copy), or None."""
        return deepcopy(self.__previous_run)

    @property
    def headline(self) -> dict:
        """total_entries, counted_entries and negative_percent, each with
        previous, current, change and text, plus status_counts (a copy)."""
        return deepcopy(self.__headline)

    @property
    def themes(self) -> list[dict]:
        """One row per theme (a copy): theme, status, and count and priority,
        each with previous, current, change and text."""
        return deepcopy(self.__themes)

    def needs_attention(self) -> list[str]:
        """Themes that are escalating or new."""
        return [row["theme"] for row in self.__themes if row["status"] in (self.ESCALATING, self.NEW)]

    def getting_better(self) -> list[str]:
        """Themes that are easing."""
        return [row["theme"] for row in self.__themes if row["status"] == self.EASING]

    def to_dict(self) -> dict:
        return {
            "has_previous": self.__has_previous,
            "message": self.__message,
            "previous_run": self.previous_run,
            "headline": self.headline,
            "themes": self.themes,
            "needs_attention": self.needs_attention(),
            "getting_better": self.getting_better(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds a report saved by to_dict(). Raises ValueError if it can't be read."""
        try:
            report = cls(data["has_previous"], data.get("message"), data.get("previous_run"),
                         data.get("headline"), data.get("themes"))
            report.needs_attention()  # every row must have a theme and a status
        except (AttributeError, KeyError, TypeError) as error:
            raise ValueError(f"not a readable trend report: {error!r}") from error
        return report

    def __eq__(self, other) -> bool:
        return isinstance(other, TrendReport) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return f"TrendReport(has_previous={self.__has_previous}, {len(self.__themes)} themes)"
