"""AggregationResult: one run's statistics, theme by theme."""

from typing import Self

from managers.models import NEGATIVE, SENTIMENTS, Serializable

from .theme_stats import ThemeStats


class AggregationResult(Serializable):
    """Read-only statistics for one run, built by ThemeAggregator. Data saves
    it after every run (aggregated_output.json, aggregated_history.json)."""

    def __init__(
        self,
        themes: list[ThemeStats],
        total_entries: int,
        pending_themes: dict[str, int] | None = None,
        run_at: str | None = None,
        source_file: str | None = None,
    ):
        self.__themes = tuple(themes)
        self.__total_entries = total_entries
        self.__pending_themes = dict(pending_themes or {})
        self.__run_at = run_at
        self.__source_file = source_file

    @property
    def themes(self) -> tuple[ThemeStats, ...]:
        """Every counted theme, most-mentioned first."""
        return self.__themes

    def get(self, theme: str) -> ThemeStats | None:
        """The stats for one theme, or None if it has no counted entries."""
        return next((stats for stats in self.__themes if stats.theme == theme), None)

    @property
    def total_entries(self) -> int:
        """Every valid record in the run, counted or not."""
        return self.__total_entries

    @property
    def counted_entries(self) -> int:
        return sum(stats.count for stats in self.__themes)

    @property
    def sentiment_counts(self) -> dict[str, int]:
        """Counted entries per sentiment, across all themes."""
        totals = dict.fromkeys(SENTIMENTS, 0)
        for stats in self.__themes:
            for sentiment, count in stats.sentiment_counts.items():
                totals[sentiment] = totals.get(sentiment, 0) + count
        return totals

    @property
    def negative_percent(self) -> int:
        """Whole-number percentage of counted entries with negative sentiment."""
        counted = self.counted_entries
        return round(100 * self.sentiment_counts[NEGATIVE] / counted) if counted else 0

    @property
    def unverified_count(self) -> int:
        """Counted entries the AI has not checked yet (D4)."""
        return sum(stats.unverified for stats in self.__themes)

    @property
    def pending_themes(self) -> dict[str, int]:
        """New themes waiting for an admin to confirm them, with how many records each has (D16)."""
        return dict(self.__pending_themes)

    @property
    def run_at(self) -> str | None:
        """When the run happened. Set only when rebuilt from a history entry."""
        return self.__run_at

    @property
    def source_file(self) -> str | None:
        """The file imported in that run. Set only when rebuilt from a history entry."""
        return self.__source_file

    def to_dict(self) -> dict:
        """The result itself; run_at and source_file belong to the history entry
        that Data wraps around it. Derived numbers are included for readers."""
        return {
            "total_entries": self.__total_entries,
            "counted_entries": self.counted_entries,
            "negative_percent": self.negative_percent,
            "unverified_count": self.unverified_count,
            "sentiment_counts": self.sentiment_counts,
            "themes": [stats.to_dict() for stats in self.__themes],
            "pending_themes": self.pending_themes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Accepts a result made by to_dict() or a history entry
        ({"run_at", "source_file", "result"}). Raises ValueError if it can't be
        read, including Part 1 history entries, so the caller can skip it (G4)."""
        if not isinstance(data, dict):
            raise ValueError(f"expected a dictionary, got {type(data).__name__}")
        if "stats" in data:
            raise ValueError("this is a Part 1 history entry ('stats'); Part 2 entries hold a 'result'")
        body = data["result"] if "result" in data else data
        try:
            themes = [ThemeStats.from_dict(stats) for stats in body["themes"]]
            return cls(themes, body["total_entries"], body.get("pending_themes"),
                       data.get("run_at"), data.get("source_file"))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"not a readable aggregation result: {error!r}") from error

    def __eq__(self, other) -> bool:
        return (isinstance(other, AggregationResult) and self.to_dict() == other.to_dict()
                and (self.__run_at, self.__source_file) == (other.run_at, other.source_file))

    def __repr__(self) -> str:
        return (f"AggregationResult({len(self.__themes)} themes, "
                f"{self.counted_entries} of {self.__total_entries} counted)")
