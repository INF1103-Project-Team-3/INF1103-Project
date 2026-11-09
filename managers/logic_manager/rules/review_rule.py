"""ReviewRule: the code every review rule shares."""

from abc import ABC, abstractmethod

from managers.models import FeedbackRecord


class ReviewRule(ABC):
    """Abstract: apply() is written once here. Each subclass only says when it
    flags a record (_flags), why (_reason), and whether a flagged record is
    still counted (excludes, passed to the constructor)."""

    def __init__(self, excludes: bool):
        self.__excludes = excludes

    @property
    def excludes(self) -> bool:
        """True if a flagged record is left out of the statistics until an admin reviews it."""
        return self.__excludes

    def apply(self, record: FeedbackRecord) -> None:
        """Adds a review reason to the record if the rule applies to it."""
        if self._flags(record):
            record.add_review_reason(self._reason(record), self.__excludes)

    @abstractmethod
    def _flags(self, record: FeedbackRecord) -> bool:
        """True if this rule flags the record."""

    @abstractmethod
    def _reason(self, record: FeedbackRecord) -> str:
        """Why the record was flagged, as shown in the review queue."""
