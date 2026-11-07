"""ThemeAggregator: turns checked records into each theme's statistics."""

from managers.models import (
    NEGATIVE, NEUTRAL, POSITIVE, SENTIMENTS, SEVERITIES, UNVERIFIED, FeedbackRecord,
)

from .priority_scorer import PriorityScorer
from .results import AggregationResult, ThemeStats
from .theme_normaliser import ThemeNormaliser


class ThemeAggregator:
    """Groups the counted records by final theme. Expects records that have
    already been through the rules."""

    __SENTIMENT_SCORE = {POSITIVE: 1, NEUTRAL: 0, NEGATIVE: -1}

    def __init__(self, normaliser: ThemeNormaliser):
        self.__normaliser = normaliser
        self.__scorer = PriorityScorer()

    def aggregate(self, records: list[FeedbackRecord]) -> AggregationResult:
        """Statistics for one run. total_entries covers every record passed in;
        the themes cover only the counted ones."""
        by_theme = {}
        for record in records:
            if record.counted:
                by_theme.setdefault(record.theme, []).append(record)
        themes = [self.__theme_stats(theme, group) for theme, group in by_theme.items()]
        # most-mentioned first; ties broken by priority, then name, so the order is stable
        themes.sort(key=lambda stats: (-stats.count, -stats.priority, stats.theme))
        return AggregationResult(themes, total_entries=len(records), pending_themes=self.__pending_themes(records))

    def __pending_themes(self, records: list[FeedbackRecord]) -> dict[str, int]:
        """New themes not counted yet, with how many records each has, most first."""
        pending = {}
        for record in records:
            # theme is None on a record Logic has not checked yet
            if not record.counted and record.theme is not None and self.__normaliser.is_new(record.theme):
                pending[record.theme] = pending.get(record.theme, 0) + 1
        return dict(sorted(pending.items(), key=lambda item: (-item[1], item[0])))

    def __theme_stats(self, theme: str, records: list[FeedbackRecord]) -> ThemeStats:
        count = len(records)
        severity_counts = dict.fromkeys(SEVERITIES, 0)
        sentiment_counts = dict.fromkeys(SENTIMENTS, 0)
        for record in records:
            severity_counts[record.severity] += 1
            sentiment_counts[record.sentiment] += 1
        total_score = sum(self.__SENTIMENT_SCORE[record.sentiment] for record in records)
        # the priority uses this rounded average, as Part 1 did
        avg_sentiment = round(total_score / count, 2)
        return ThemeStats(
            theme,
            count,
            severity_counts,
            sentiment_counts,
            avg_sentiment,
            self.__scorer.score(count, severity_counts, avg_sentiment),
            sum(record.verification == UNVERIFIED for record in records),
        )
