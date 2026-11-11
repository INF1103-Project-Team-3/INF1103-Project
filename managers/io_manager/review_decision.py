from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Mapping

from managers.models import LABEL_FIELDS


@dataclass(frozen=True)
class ReviewDecision:
    """What an admin decided about one flagged record: update its labels, or delete it.

    I only describe the decision; I never touch the record. The pipeline
    applies it later (record.mark_reviewed() for an update), so the final
    labels keep a single writer. frozen=True makes a decision read-only once made.
    """

    UPDATE: ClassVar[str] = "update"
    DELETE: ClassVar[str] = "delete"

    feedback_id: str
    action: str                     # UPDATE or DELETE
    theme: str | None = None        # the three labels are only set for an update
    sentiment: str | None = None
    severity: str | None = None

    @classmethod
    def update(cls, feedback_id: str, labels: Mapping[str, str]) -> "ReviewDecision":
        """An update to the given theme, sentiment and severity.

        labels can be the admin's typed values, record.user ("use the student's")
        or record.ai ("use the AI's"); any extra key, such as the AI's summary,
        is ignored.
        """
        return cls(feedback_id, cls.UPDATE, *(labels[name] for name in LABEL_FIELDS))

    @classmethod
    def delete(cls, feedback_id: str) -> "ReviewDecision":
        return cls(feedback_id, cls.DELETE)
