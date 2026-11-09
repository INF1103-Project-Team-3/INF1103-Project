"""PriorityScorer: one 0-100 number saying how urgent a theme is."""

from managers.models import CRITICAL, HIGH


class PriorityScorer:
    """Combines the share of severe entries, how negative they are and how
    often the theme comes up, instead of needing to look at several numbers
    to see which themes matter most. Adjust the weights here to change what
    counts most; they add up to 100."""

    __SEVERITY_WEIGHT = 45     # share of high + critical entries
    __NEGATIVITY_WEIGHT = 20   # how negative the average sentiment is
    __FREQUENCY_WEIGHT = 35    # how many entries, up to the cap below
    __FREQUENCY_CAP = 10       # this many entries or more gives the full frequency weight

    def score(self, count: int, severity_counts: dict[str, int], avg_sentiment: float) -> int:
        """Priority from 0 to 100. avg_sentiment runs from -1 (all negative) to
        1 (all positive); only negative sentiment raises the score."""
        severe = severity_counts.get(HIGH, 0) + severity_counts.get(CRITICAL, 0)
        severity_share = severe / count if count else 0
        negativity = max(0, -avg_sentiment)
        frequency = min(count / self.__FREQUENCY_CAP, 1.0)
        # Python's round() sends .5 to the nearest even number, as Part 1 did
        return round(severity_share * self.__SEVERITY_WEIGHT
                     + negativity * self.__NEGATIVITY_WEIGHT
                     + frequency * self.__FREQUENCY_WEIGHT)
