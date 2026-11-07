import pytest

from managers.logic_manager import ReviewRule
from managers.models import HIGH, MATCHED, NEGATIVE, FeedbackRecord


class _LongTextRule(ReviewRule):
    """Test-only rule: flags feedback longer than 20 characters."""

    def __init__(self, excludes=True):
        super().__init__(excludes)

    def _flags(self, record):
        return len(record.text) > 20

    def _reason(self, record):
        return f"Text is {len(record.text)} characters long"


class _NoReason(ReviewRule):
    def _flags(self, record):
        return True


def make_checked_record(text):
    record = FeedbackRecord("fb_001", text, "2026-09-17T08:03:00", None,
                            {"theme": "Facilities", "sentiment": NEGATIVE, "severity": HIGH})
    record.set_final("Facilities", NEGATIVE, HIGH, MATCHED)
    return record


def test_review_rule_cannot_be_created_on_its_own():
    with pytest.raises(TypeError):
        ReviewRule(excludes=True)


def test_a_rule_missing_its_reason_cannot_be_created():
    with pytest.raises(TypeError):
        _NoReason(excludes=True)


def test_flags_a_matching_record_and_stops_it_being_counted():
    record = make_checked_record("The library wifi keeps dropping.")
    _LongTextRule(excludes=True).apply(record)
    assert record.review_reasons == ["Text is 32 characters long"]
    assert not record.counted


def test_a_rule_that_does_not_exclude_flags_but_still_counts():
    record = make_checked_record("The library wifi keeps dropping.")
    _LongTextRule(excludes=False).apply(record)
    assert record.needs_review
    assert record.counted


def test_leaves_a_record_it_does_not_match_alone():
    record = make_checked_record("Wifi is fine.")
    _LongTextRule().apply(record)
    assert not record.needs_review
    assert record.counted


def test_excludes_is_read_only():
    with pytest.raises(AttributeError):
        _LongTextRule().excludes = False
