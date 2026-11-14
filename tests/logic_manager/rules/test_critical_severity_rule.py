import pytest

from managers.logic_manager import CriticalSeverityRule, ReviewRule
from managers.models import CRITICAL, HIGH, LOW, MATCHED, NEGATIVE, FeedbackRecord


def make_checked_record(severity):
    record = FeedbackRecord("fb_001", "The lab smells of gas.", "2026-09-17T08:03:00", None,
                            {"theme": "Facilities", "sentiment": NEGATIVE, "severity": severity})
    record.set_final("Facilities", NEGATIVE, severity, MATCHED)
    return record


def test_is_a_review_rule_that_keeps_records_counted():
    rule = CriticalSeverityRule()
    assert isinstance(rule, ReviewRule)
    assert not rule.excludes


def test_flags_critical_feedback_but_still_counts_it():
    record = make_checked_record(CRITICAL)
    CriticalSeverityRule().apply(record)
    assert record.review_reasons == ["Critical severity"]
    assert record.counted


@pytest.mark.parametrize("severity", [LOW, HIGH])
def test_leaves_other_severities_alone(severity):
    record = make_checked_record(severity)
    CriticalSeverityRule().apply(record)
    assert not record.needs_review


def test_uses_the_final_severity_not_the_users():
    record = make_checked_record(HIGH)
    record.mark_reviewed("Facilities", NEGATIVE, CRITICAL)
    CriticalSeverityRule().apply(record)
    assert record.needs_review
