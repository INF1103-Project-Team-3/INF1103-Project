"""KeywordMatcher: whether a piece of feedback mentions a word."""

import re


class KeywordMatcher:
    """The one rule for finding a keyword in feedback text. ActionAdvisor uses it to
    pick an action and ImpactAnalyser to measure one, so both agree on what counts
    as a mention."""

    @staticmethod
    def mentions(text: str, word: str) -> bool:
        """True when text has word as a whole word or phrase, in any case:
        "wifi" matches "The WIFI drops." but not "wifiplus"."""
        return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None
