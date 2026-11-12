"""EntryValidator: checks a whole entry (typed or imported) and cleans it up."""
import pytest

from managers.io_manager.entry_validator import EntryValidator
from managers.io_manager.theme_validator import ThemeValidator


def row(**fields):
    """A complete, valid imported row; keyword arguments change or add fields."""
    base = {"feedback_id": "a1", "text": "Wifi keeps dropping", "timestamp": "2026-10-01T09:00:00",
            "theme": "facilities", "sentiment": "Negative", "severity": "HIGH"}
    return {**base, **fields}


@pytest.fixture
def validator(logic):
    return EntryValidator(ThemeValidator(logic))


def test_typed_entry_needs_no_id_or_timestamp(validator):
    entry, error = validator.validate(
        {"text": " Too much work ", "theme": "workload", "sentiment": "negative", "severity": "low"})
    assert error == ""
    assert entry == {"text": "Too much work", "theme": "Workload",
                     "sentiment": "negative", "severity": "low"}


def test_values_are_returned_in_their_canonical_form(validator):
    entry, _ = validator.validate(row(), require_ids=True)
    assert (entry["theme"], entry["sentiment"], entry["severity"]) == ("Facilities", "negative", "high")


def test_unknown_columns_are_dropped(validator):
    entry, _ = validator.validate(row(comment="ignore me"), require_ids=True)
    assert "comment" not in entry


@pytest.mark.parametrize("raw, require_ids, reason", [
    ("not a dict", False, "row is not an object"),
    (row(text="   "), True, "missing field(s): text"),
    ({"text": "Hi"}, False, "missing field(s): theme, sentiment, severity"),
    (row(feedback_id=None, timestamp=""), True, "missing field(s): feedback_id, timestamp"),
    (row(text="1234"), True, "text contains no letters"),
    (row(timestamp="2026-13-01T09:00:00"), True, "timestamp must look like YYYY-MM-DDTHH:MM:SS"),
    (row(timestamp="2026-1-5T9:0:0"), True, "timestamp must look like YYYY-MM-DDTHH:MM:SS"),
    (row(sentiment="angry"), True, "sentiment must be one of: positive, neutral, negative"),
    (row(severity="urgent"), True, "severity must be one of: low, medium, high, critical"),
])
def test_invalid_entries_give_one_clear_reason(validator, raw, require_ids, reason):
    assert validator.validate(raw, require_ids=require_ids) == (None, reason)


def test_rows_are_numbered_from_one_and_bad_rows_do_not_stop_the_rest(validator):
    accepted, rejected = validator.validate_rows([row(), row(feedback_id="a2", text=""), row(feedback_id="a3")])
    assert [e["feedback_id"] for e in accepted] == ["a1", "a3"]
    assert rejected == [(2, "missing field(s): text")]


def test_duplicate_ids_in_one_file_are_rejected(validator):
    _, rejected = validator.validate_rows([row(), row(text="Another one")])
    assert rejected == [(2, "duplicate feedback_id 'a1'")]


def test_a_format_check_runs_before_the_field_checks(validator):
    def no_short_ids(raw):
        return "id too short" if len(raw["feedback_id"]) < 3 else ""
    accepted, rejected = validator.validate_rows([row(), row(feedback_id="abc")], no_short_ids)
    assert rejected == [(1, "id too short")]
    assert [e["feedback_id"] for e in accepted] == ["abc"]
