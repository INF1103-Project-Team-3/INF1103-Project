"""ThemeStats: the numbers for one theme in one run."""

from typing import Self

from managers.models import Serializable


class ThemeStats(Serializable):
    """Read-only statistics for one theme, built by ThemeAggregator."""

    def __init__(
        self,
        theme: str,
        count: int,
        severity_counts: dict[str, int],
        sentiment_counts: dict[str, int],
        avg_sentiment: float,
        priority: int,
        unverified: int,
    ):
        self.__theme = theme
        self.__count = count
        self.__severity_counts = dict(severity_counts)
        self.__sentiment_counts = dict(sentiment_counts)
        self.__avg_sentiment = avg_sentiment
        self.__priority = priority
        self.__unverified = unverified

    @property
    def theme(self) -> str:
        return self.__theme

    @property
    def count(self) -> int:
        """How many counted entries have this theme."""
        return self.__count

    @property
    def severity_counts(self) -> dict[str, int]:
        """Entries per severity (a copy)."""
        return dict(self.__severity_counts)

    @property
    def sentiment_counts(self) -> dict[str, int]:
        """Entries per sentiment (a copy)."""
        return dict(self.__sentiment_counts)

    @property
    def avg_sentiment(self) -> float:
        """From -1 (all negative) to 1 (all positive), to 2 decimal places."""
        return self.__avg_sentiment

    @property
    def priority(self) -> int:
        """How urgent the theme is, 0-100 (PriorityScorer)."""
        return self.__priority

    @property
    def unverified(self) -> int:
        """How many of the counted entries the AI has not checked yet (D4)."""
        return self.__unverified

    def to_dict(self) -> dict:
        return {
            "theme": self.__theme,
            "count": self.__count,
            "severity_counts": self.severity_counts,
            "sentiment_counts": self.sentiment_counts,
            "avg_sentiment": self.__avg_sentiment,
            "priority": self.__priority,
            "unverified": self.__unverified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Raises KeyError if a field is missing, and ValueError if one has the
        wrong type, so a hand-edited or corrupt run can be skipped."""
        if not isinstance(data["theme"], str):
            raise ValueError(f"theme must be text, got {data['theme']!r}")
        for name in ("count", "priority", "unverified"):
            if not cls._is_whole_number(data[name]):
                raise ValueError(f"{name} must be a whole number, got {data[name]!r}")
        average = data["avg_sentiment"]
        if isinstance(average, bool) or not isinstance(average, (int, float)):
            raise ValueError(f"avg_sentiment must be a number, got {average!r}")
        for name in ("severity_counts", "sentiment_counts"):
            counts = data[name]
            if not isinstance(counts, dict) or not all(cls._is_whole_number(n) for n in counts.values()):
                raise ValueError(f"{name} must map each label to a whole number, got {counts!r}")
        return cls(data["theme"], data["count"], data["severity_counts"], data["sentiment_counts"],
                   average, data["priority"], data["unverified"])

    @staticmethod
    def _is_whole_number(value: object) -> bool:
        # bool is a subclass of int, but true/false in a saved run is not a count
        return isinstance(value, int) and not isinstance(value, bool)

    def __eq__(self, other) -> bool:
        return isinstance(other, ThemeStats) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return f"ThemeStats({self.__theme!r}, count={self.__count}, priority={self.__priority})"
