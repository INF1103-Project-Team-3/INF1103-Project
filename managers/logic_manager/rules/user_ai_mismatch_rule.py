"""UserAIMismatchRule: the multi-condition rule, comparing the user's values with the AI's."""

from managers.models import CRITICAL, MISMATCH, SEVERITIES, UNCLEAR_THEME, FeedbackRecord

from ..theme_normaliser import ThemeNormaliser
from .review_rule import ReviewRule


class UserAIMismatchRule(ReviewRule):
    """Flags a record when the AI's theme, sentiment or severity conflicts with
    the user's. It is marked mismatch and not counted until an admin reviews it
    (design reference 7.1, 7.2). A record the AI failed on has nothing to compare."""

    # low/medium and medium/high still agree; critical never does (see __severities_match)
    __SEVERITY_STEPS_ALLOWED = 1

    def __init__(self, normaliser: ThemeNormaliser):
        super().__init__(excludes=True)
        self.__normaliser = normaliser

    def apply(self, record: FeedbackRecord) -> None:
        """Flags the record as usual, and also marks it mismatch. Expects a
        record whose final values are already set."""
        super().apply(record)
        if self._flags(record):
            record.set_final(record.theme, record.sentiment, record.severity, MISMATCH)

    def _flags(self, record: FeedbackRecord) -> bool:
        return bool(self.__conflicts(record))

    def _reason(self, record: FeedbackRecord) -> str:
        return f"AI disagrees with the user on {'; '.join(self.__conflicts(record))}"

    def __conflicts(self, record: FeedbackRecord) -> list[str]:
        """Each field that conflicts, e.g. ["sentiment (user 'negative', AI 'neutral')"]."""
        ai = record.ai
        if ai is None:
            return []
        user = record.user
        matches = {
            "theme": self.__themes_match(user["theme"], ai["theme"]),
            "sentiment": user["sentiment"] == ai["sentiment"],
            "severity": self.__severities_match(user["severity"], ai["severity"]),
        }
        return [f"{field} (user '{user[field]}', AI '{ai[field]}')"
                for field, match in matches.items() if not match]

    def __themes_match(self, user_theme: str, ai_theme: str) -> bool:
        """Compared after normalising. Unclear never matches, even with Unclear."""
        theme = self.__normaliser.normalise(user_theme)
        return theme != UNCLEAR_THEME and theme == self.__normaliser.normalise(ai_theme)

    def __severities_match(self, user_severity: str, ai_severity: str) -> bool:
        if user_severity == ai_severity:
            return True
        if CRITICAL in (user_severity, ai_severity):  # only one side says critical
            return False
        steps = abs(SEVERITIES.index(user_severity) - SEVERITIES.index(ai_severity))
        return steps <= self.__SEVERITY_STEPS_ALLOWED
