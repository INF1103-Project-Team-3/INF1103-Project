from __future__ import annotations

from dataclasses import dataclass, field

from managers.models import FeedbackRecord


@dataclass
class ImportResult:
    """What importing one file produced.

    I return the valid records together with the rejected rows, instead of
    stopping at the first bad row, so the admin can fix every problem in one go.
    """

    source_file: str                                        # the file's name, e.g. "week5.csv"
    records: list[FeedbackRecord] = field(default_factory=list)
    rejected: list[tuple[int, str]] = field(default_factory=list)   # (row number, reason)
    already_saved: list[str] = field(default_factory=list)  # feedback_ids skipped, already stored

    @property
    def total(self) -> int:
        """Rows in the file: every row is accepted, rejected or already saved."""
        return len(self.records) + len(self.rejected) + len(self.already_saved)
