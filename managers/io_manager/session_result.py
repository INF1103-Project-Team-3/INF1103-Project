from __future__ import annotations

from dataclasses import dataclass, field

from managers.models import Action, FeedbackRecord

from .review_decision import ReviewDecision


@dataclass
class SessionResult:
    """Everything one input session collected, handed on to the pipeline.

    I deliberately never save anything from the I/O side. I only fill in this
    object and return it, and the pipeline decides what to store. That keeps
    input/output separate from storage and from business rules.
    """

    records: list[FeedbackRecord] = field(default_factory=list)   # new feedback (typed or imported)
    source_file: str | None = None                                # name of the last file imported
    decisions: list[ReviewDecision] = field(default_factory=list) # admin review choices
    actions: list[Action] = field(default_factory=list)           # actions the admin logged
    themes_to_add: list[str] = field(default_factory=list)        # new themes from Settings

    def is_empty(self) -> bool:
        """True when nothing at all was collected."""
        return not (self.records or self.decisions or self.actions or self.themes_to_add)

    def decided_ids(self) -> set[str]:
        """IDs already reviewed in this session, so a record is not offered twice."""
        return {decision.feedback_id for decision in self.decisions}
