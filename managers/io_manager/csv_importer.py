from __future__ import annotations

from typing import Any

from .feedback_importer import FeedbackImporter


class CsvImporter(FeedbackImporter):
    """Imports .csv files.

    Inheritance: the base class does the whole import; I only add the check
    that is particular to CSV. A row with more cells than the header (usually
    an unquoted comma inside the text) keeps the extra cells under the key None
    when it is read. Quietly dropping them could hide a shifted column, so I
    reject that row and say why.
    """

    @property
    def extension(self) -> str:
        return ".csv"

    def _row_problem(self, raw: Any) -> str:
        return "row has more cells than the header" if None in raw else ""
