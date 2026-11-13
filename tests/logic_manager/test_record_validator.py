import pytest

from managers.logic_manager.record_validator import RecordValidator
from managers.models import CRITICAL, HIGH, LOW, NEGATIVE, POSITIVE, REVIEWED, FeedbackRecord


def make_record(**changes):
    """A valid record; from_dict restores values unchecked, so tests can break any field."""
    data = {
        "feedback_id": "fb_001",
        "text": "The library wifi keeps dropping.",
        "timestamp": "2026-09-17T08:03:00",
        "user": {"theme": "Facilities", "sentiment": NEGATIVE, "severity": HIGH},
        "ai": None,
    }
    data.update(changes)
    return FeedbackRecord.from_dict(data)


@pytest.fixture
def validator():
    return RecordValidator()


def test_valid_record_passes(validator):
    record = make_record()
    assert validator.validate([record]) == ([record], [])


def test_valid_ai_values_pass(validator):
    record = make_record(ai={"theme": "Wi-Fi", "sentiment": NEGATIVE, "severity": CRITICAL})
    assert validator.validate([record]) == ([record], [])


@pytest.mark.parametrize("changes, expected", [
    ({"feedback_id": ""}, "'feedback_id' must be non-empty text"),
    ({"text": "   "}, "'text' must be non-empty text"),
    ({"timestamp": "2026-09-17 08:03:00"}, "'timestamp' must be YYYY-MM-DDTHH:MM:SS"),
    ({"timestamp": "17/09/2026"}, "'timestamp' must be YYYY-MM-DDTHH:MM:SS"),
    ({"timestamp": "2026-09-17T8:03:00"}, "'timestamp' must be YYYY-MM-DDTHH:MM:SS"),
    ({"timestamp": "2026-02-30T10:00:00"}, "'timestamp' must be YYYY-MM-DDTHH:MM:SS"),
    ({"user": {"theme": "", "sentiment": NEGATIVE, "severity": HIGH}}, "user theme must be non-empty text"),
    ({"user": {"theme": "Facilities", "sentiment": "angry", "severity": HIGH}}, "user sentiment must be one of"),
    ({"user": {"theme": "Facilities", "sentiment": NEGATIVE}}, "user severity must be one of"),
    ({"ai": {"theme": "Wi-Fi", "sentiment": NEGATIVE, "severity": "urgent"}}, "ai severity must be one of"),
    ({"verification": "approved"}, "'verification' must be one of"),
    ({"verification": REVIEWED, "theme": "Facilities", "sentiment": NEGATIVE, "severity": "urgent"},
     "final severity must be one of"),
])
def test_bad_record_is_invalid_with_the_reason(validator, changes, expected):
    record = make_record(**changes)
    valid, invalid = validator.validate([record])
    assert valid == []
    assert invalid[0][0] is record
    assert any(expected in problem for problem in invalid[0][1])


def test_every_problem_is_reported(validator):
    record = make_record(text="", user={"theme": "Facilities", "sentiment": POSITIVE, "severity": "urgent"})
    _, invalid = validator.validate([record])
    assert len(invalid[0][1]) == 2


def test_reviewed_record_with_valid_admin_values_passes(validator):
    record = make_record(verification=REVIEWED, theme="Administration", sentiment=NEGATIVE, severity=LOW)
    assert validator.validate([record]) == ([record], [])


def test_repeated_id_keeps_the_first_and_rejects_the_rest(validator):
    first, repeat = make_record(), make_record(text="Same id, different text.")
    valid, invalid = validator.validate([first, repeat])
    assert valid == [first]
    assert invalid == [(repeat, ["duplicate feedback_id 'fb_001'"])]


def test_one_bad_record_does_not_stop_the_rest(validator):
    good_1, bad, good_2 = make_record(feedback_id="fb_001"), make_record(text=""), make_record(feedback_id="fb_002")
    valid, invalid = validator.validate([good_1, bad, good_2])
    assert valid == [good_1, good_2]
    assert [record for record, _ in invalid] == [bad]


def test_something_that_is_not_a_record_is_invalid(validator):
    raw = {"feedback_id": "fb_009"}
    assert validator.validate([raw]) == ([], [(raw, ["not a FeedbackRecord, got dict"])])
