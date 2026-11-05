"""Rule: what RuleEngine needs from any review rule."""

from abc import ABC, abstractmethod

from managers.models import FeedbackRecord


class Rule(ABC):
    """Interface: look at one record and flag it if the rule applies."""

    @abstractmethod
    def apply(self, record: FeedbackRecord) -> None:
        """Adds a review reason to the record if the rule applies to it."""
