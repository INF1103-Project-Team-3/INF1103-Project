import pytest

from managers.logic_manager import CriticalSeverityRule, ReviewRule, UnclearThemeRule
from managers.logic_manager.rule_engine import RuleEngine
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import CRITICAL, HIGH, LOW, MATCHED, MEDIUM, NEGATIVE, FeedbackRecord


def make_checked_record(feedback_id="fb_001", theme="Facilities", severity=HIGH, text="Some feedback."):
    record = FeedbackRecord(feedback_id, text, "2026-09-17T08:03:00", None,
                            {"theme": theme, "sentiment": NEGATIVE, "severity": severity})
    record.set_final(theme, NEGATIVE, severity, MATCHED)
    return record


def make_engine():
    return RuleEngine([CriticalSeverityRule(), UnclearThemeRule(ThemeNormaliser())])


class _ShortTextRule(ReviewRule):
    """Test-only rule, to show a new rule runs with no change to RuleEngine (OCP)."""

    def __init__(self):
        super().__init__(excludes=True)

    def _flags(self, record):
        return len(record.text) < 5

    def _reason(self, record):
        return "Text too short to act on"


def test_runs_every_rule_on_every_record_in_order():
    record = make_checked_record(theme="other", severity=CRITICAL)
    make_engine().apply([record])
    assert record.review_reasons == [
        "Critical severity",
        "Unclear theme (user said 'other') - needs a theme assigned",
    ]


def test_a_new_rule_runs_without_changing_the_engine():
    short, normal = make_checked_record(text="Bad."), make_checked_record(text="The wifi drops often.")
    RuleEngine([_ShortTextRule()]).apply([short, normal])
    assert short.review_reasons == ["Text too short to act on"]
    assert not normal.needs_review


def test_running_twice_does_not_repeat_reasons():
    record = make_checked_record(severity=CRITICAL)
    engine = make_engine()
    engine.apply([record])
    engine.apply([record])
    assert record.review_reasons == ["Critical severity"]


def test_a_reason_that_no_longer_applies_is_removed():
    record = make_checked_record(text="Bad.")
    RuleEngine([_ShortTextRule()]).apply([record])
    RuleEngine([]).apply([record])
    assert not record.needs_review
    assert record.counted


def test_reviewed_records_are_skipped():
    record = make_checked_record()
    record.mark_reviewed("Facilities", NEGATIVE, CRITICAL)
    make_engine().apply([record])
    assert not record.needs_review


def test_review_queue_has_only_flagged_records_critical_first_then_theme_then_id():
    records = [
        make_checked_record("fb_005", "Facilities", HIGH),
        make_checked_record("fb_004", "other", MEDIUM),
        make_checked_record("fb_003", "Assessment", CRITICAL),
        make_checked_record("fb_002", "spam", LOW),
        make_checked_record("fb_001", "Facilities", CRITICAL),
        make_checked_record("fb_006", "Assessment", CRITICAL),
    ]
    engine = make_engine()
    engine.apply(records)
    queue = engine.review_queue(records)
    assert [r.feedback_id for r in queue] == ["fb_003", "fb_006", "fb_001", "fb_004", "fb_002"]


def test_rejects_something_that_is_not_a_rule():
    with pytest.raises(TypeError):
        RuleEngine([CriticalSeverityRule(), "not a rule"])


def test_changing_the_callers_list_does_not_change_the_engine():
    rules = [CriticalSeverityRule()]
    engine = RuleEngine(rules)
    rules.append(_ShortTextRule())
    assert len(engine.rules) == 1
