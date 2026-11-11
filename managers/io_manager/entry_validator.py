from __future__ import annotations

from typing import Any, Callable, Iterable

from managers.models import LABEL_FIELDS, SENTIMENTS, SEVERITIES, FeedbackRecord

from .choice_validator import ChoiceValidator
from .text_validator import TextValidator
from .theme_validator import ThemeValidator


class EntryValidator:
    """Checks one whole feedback entry (a dictionary) and returns it cleaned up.

    Two callers use EntryValidator: the importers check every row of a file through
    validate_rows(), and the GUI's student form checks its fields through
    validate(). Built from the smaller validators instead of re-writing
    their rules, so a typed answer and an imported row obey exactly the same
    rules. I only return errors and never print them, so each front end can show
    them its own way.
    """

    # what an imported row must carry besides the three labels; typed feedback
    # only needs "text", because the RecordBuilder creates the ID and timestamp
    FILE_FIELDS = ("feedback_id", "text", "timestamp")

    def __init__(self, theme_validator: ThemeValidator):
        # every field validator answers in the same (value, error) shape, so
        # validate() can check them all in one loop
        self._fields = {
            "text": TextValidator("text"),
            "sentiment": ChoiceValidator(
                SENTIMENTS, error=f"sentiment must be one of: {', '.join(SENTIMENTS)}"),
            "severity": ChoiceValidator(
                SEVERITIES, error=f"severity must be one of: {', '.join(SEVERITIES)}"),
            "theme": theme_validator,
        }

    def validate(self, raw: Any, require_ids: bool = False) -> tuple[dict | None, str]:
        """Returns (clean_entry, "") if valid, or (None, reason) if not.

        A typed entry has no feedback_id or timestamp yet (the RecordBuilder
        creates them), so they are optional by default; if one is supplied it
        is still checked. Rows from a file must carry both: require_ids=True.
        """
        if not isinstance(raw, dict):
            return None, "row is not an object"

        required = (self.FILE_FIELDS if require_ids else ("text",)) + LABEL_FIELDS
        missing = [f for f in required if not self._value(raw, f)]
        if missing:
            return None, f"missing field(s): {', '.join(missing)}"

        # keep only the fields I know about, trimmed; any extra columns are dropped
        entry = {f: self._value(raw, f) for f in self.FILE_FIELDS + LABEL_FIELDS
                 if self._value(raw, f)}

        # the record decides what a valid timestamp looks like
        if "timestamp" in entry and not FeedbackRecord.is_valid_timestamp(entry["timestamp"]):
            return None, "timestamp must look like YYYY-MM-DDTHH:MM:SS"

        for name, validator in self._fields.items():
            value, error = validator.check(entry[name])
            if error:
                return None, error
            entry[name] = value       # canonical form, e.g. "Negative" -> "negative"
        return entry, ""

    def validate_rows(self, rows: Iterable[Any],
                      row_problem: Callable[[Any], str] | None = None
                      ) -> tuple[list[dict], list[tuple[int, str]]]:
        """Validate every row of a file. Returns (accepted_entries, rejected).

        rejected holds (row number from 1, reason). row_problem is an optional
        extra check for the file format (each importer passes its own), run
        before the field checks. A feedback_id that appears twice in one file is
        rejected, so IDs stay unique.
        """
        accepted, rejected, seen = [], [], set()
        for number, raw in enumerate(rows, start=1):
            error = row_problem(raw) if row_problem else ""
            entry = None
            if not error:
                entry, error = self.validate(raw, require_ids=True)
            if not error and entry["feedback_id"] in seen:
                error = f"duplicate feedback_id '{entry['feedback_id']}'"
            if error:
                rejected.append((number, error))
            else:
                seen.add(entry["feedback_id"])
                accepted.append(entry)
        return accepted, rejected

    @staticmethod
    def _value(raw: dict, name: str) -> str:
        """The field as trimmed text, or "" if it is absent or blank."""
        value = raw.get(name)
        return "" if value is None else str(value).strip()
