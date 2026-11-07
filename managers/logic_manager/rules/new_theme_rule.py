"""NewThemeRule: a theme nobody has confirmed yet can't be counted."""

from managers.models import FeedbackRecord

from ..theme_normaliser import ThemeNormaliser
from .review_rule import ReviewRule


class NewThemeRule(ReviewRule):
    """Flags a record whose final theme is not known yet. It is not counted until
    an admin confirms the theme or changes it (design reference 7.4). Unclear is
    left to UnclearThemeRule. Expects a record whose final values are already set."""

    def __init__(self, normaliser: ThemeNormaliser):
        super().__init__(excludes=True)
        self.__normaliser = normaliser

    def _flags(self, record: FeedbackRecord) -> bool:
        return self.__normaliser.is_new(record.theme)

    def _reason(self, record: FeedbackRecord) -> str:
        return f"New theme '{record.theme}': confirm it or change it."
