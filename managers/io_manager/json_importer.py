from __future__ import annotations

from typing import Any

from managers.models import LABEL_FIELDS

from .entry_validator import EntryValidator
from .feedback_importer import FeedbackImporter


class JsonImporter(FeedbackImporter):
    """Imports .json files holding a list of objects.

    Inheritance: the base class does the whole import; I only add the check
    that is particular to JSON. Unlike a CSV cell, a JSON value can be a list or
    a nested object, which would otherwise be saved as text like "['a', 'b']".
    I reject such a row with a reason. (A row that is not an object at all is
    already reported by the EntryValidator.)
    """

    @property
    def extension(self) -> str:
        return ".json"

    def _row_problem(self, raw: Any) -> str:
        if not isinstance(raw, dict):
            return ""
        nested = [f for f in EntryValidator.FILE_FIELDS + LABEL_FIELDS
                  if isinstance(raw.get(f), (dict, list))]
        if nested:
            return f"field(s) must be plain values, not lists or objects: {', '.join(nested)}"
        return ""
