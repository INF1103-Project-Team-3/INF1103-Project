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

    @property
    def total(self) -> int:
        """Rows in the file: every row is either accepted or rejected."""
        return len(self.records) + len(self.rejected)
