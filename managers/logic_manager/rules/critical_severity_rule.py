"""CriticalSeverityRule: critical feedback always gets an admin's attention."""

from managers.models import CRITICAL, FeedbackRecord

from .review_rule import ReviewRule


class CriticalSeverityRule(ReviewRule):
    """Flags a record whose final severity is critical. It is still counted
    (design reference 7.2)."""

    def __init__(self):
        super().__init__(excludes=False)

    def _flags(self, record: FeedbackRecord) -> bool:
        return record.severity == CRITICAL

    def _reason(self, record: FeedbackRecord) -> str:
        return "Critical severity"
