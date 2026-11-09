"""UnclearThemeRule: feedback with no real theme can't be counted under one."""

from managers.models import UNCLEAR_THEME, FeedbackRecord

from ..theme_normaliser import ThemeNormaliser
from .review_rule import ReviewRule


class UnclearThemeRule(ReviewRule):
    """Flags a record whose user or AI theme normalises to "Unclear" (e.g.
    "other", "n/a", "spam"). It is not counted until an admin assigns a theme
    (design reference 7.2)."""

    def __init__(self, normaliser: ThemeNormaliser):
        super().__init__(excludes=True)
        self.__normaliser = normaliser

    def _flags(self, record: FeedbackRecord) -> bool:
        return bool(self.__unclear_labels(record))

    def _reason(self, record: FeedbackRecord) -> str:
        return f"Unclear theme ({'; '.join(self.__unclear_labels(record))}) - needs a theme assigned"

    def __unclear_labels(self, record: FeedbackRecord) -> list[str]:
        """Which side gave an unclear label, e.g. ["user said 'n/a'", "AI said 'other'"]."""
        labels = []
        for who, values in (("user", record.user), ("AI", record.ai)):
            if values is not None and self.__normaliser.normalise(values["theme"]) == UNCLEAR_THEME:
                labels.append(f"{who} said '{values['theme']}'")
        return labels
