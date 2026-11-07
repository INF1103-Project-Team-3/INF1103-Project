import json

import pytest

from managers.logic_manager import AggregationResult, LogicManager, ReviewRule, TrendReport
from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MISMATCH, NEGATIVE, POSITIVE, REVIEWED, THEMES, UNCLEAR_THEME, UNVERIFIED,
    FeedbackRecord,
)


def make_record(feedback_id="fb_001", theme="Facilities", sentiment=NEGATIVE, severity=HIGH, ai_theme=None):
    record = FeedbackRecord(feedback_id, "The library wifi keeps dropping.", "2026-09-17T08:03:00", None,
                            {"theme": theme, "sentiment": sentiment, "severity": severity})
    if ai_theme is not None:
        record.set_ai(ai_theme, sentiment, severity)
    return record


class _FlagEverythingRule(ReviewRule):
    """Test-only rule, to show rules can be swapped through the constructor."""

    def __init__(self):
        super().__init__(excludes=True)

    def _flags(self, record):
        return True

    def _reason(self, record):
        return "Flagged by test rule"


@pytest.fixture
def logic():
    return LogicManager()


# ------------------------------------------------------------------ themes
def test_normalise_theme_handles_every_kind_of_label(logic):
    assert logic.normalise_theme("wifi") == "Facilities"
    assert logic.normalise_theme("n/a") == UNCLEAR_THEME
    assert logic.normalise_theme("parking fees") == "Parking Fees"


def test_set_known_themes_is_used_when_normalising(logic):
    logic.set_known_themes([*THEMES, "CCA Clubs"])
    assert logic.normalise_theme("cca-clubs") == "CCA Clubs"


def test_known_themes_can_be_given_to_the_constructor():
    assert LogicManager(known_themes=["CCA Clubs"]).normalise_theme("cca clubs") == "CCA Clubs"


# ------------------------------------------------------------------ validate
def test_validate_splits_valid_and_invalid_records(logic):
    good, bad = make_record("fb_001"), make_record("fb_002", sentiment="angry")
    valid, invalid = logic.validate([good, bad])
    assert valid == [good]
    assert invalid[0][0] is bad


# ------------------------------------------------------------------ apply_rules
def test_apply_rules_returns_the_same_records(logic):
    records = [make_record()]
    assert logic.apply_rules(records) is records


def test_final_values_are_the_users_with_the_theme_normalised(logic):
    record = make_record(theme="wifi", ai_theme="Facilities")
    logic.apply_rules([record])
    assert (record.theme, record.sentiment, record.severity) == ("Facilities", NEGATIVE, HIGH)


def test_a_record_the_ai_failed_on_is_unverified_and_counted(logic):
    record = make_record()
    logic.apply_rules([record])
    assert record.verification == UNVERIFIED
    assert record.counted


def test_a_record_with_ai_values_is_matched_and_counted(logic):
    record = make_record(ai_theme="Facilities")
    logic.apply_rules([record])
    assert record.verification == MATCHED
    assert record.counted


def test_an_unverified_record_is_matched_once_the_ai_succeeds(logic):
    record = make_record()
    logic.apply_rules([record])
    record.set_ai("Facilities", NEGATIVE, HIGH)
    logic.apply_rules([record])
    assert record.verification == MATCHED


def test_default_rules_flag_critical_and_unclear_records(logic):
    critical, unclear = make_record("fb_001", severity=CRITICAL), make_record("fb_002", theme="other")
    logic.apply_rules([critical, unclear])
    assert critical.review_reasons == ["Critical severity"]
    assert critical.counted
    assert unclear.theme == UNCLEAR_THEME
    assert unclear.needs_review
    assert not unclear.counted


def test_a_disagreement_with_the_ai_goes_to_review_and_is_not_counted(logic):
    record = make_record(theme="Facilities", ai_theme="Assessment")
    records = logic.apply_rules([record])
    assert record.verification == MISMATCH
    assert record.review_reasons == ["AI disagrees with the user on theme (user 'Facilities', AI 'Assessment')"]
    assert logic.review_queue(records) == [record]
    assert logic.aggregate(records).counted_entries == 0


def test_a_new_theme_waits_until_it_is_confirmed(logic):
    record = make_record(theme="parking fees")
    logic.apply_rules([record])
    assert record.review_reasons == ["New theme 'Parking Fees': confirm it or change it."]
    assert not record.counted

    logic.set_known_themes(["Parking Fees"])
    logic.apply_rules([record])
    assert not record.needs_review
    assert record.counted


def test_an_unclear_record_gets_both_reasons(logic):
    record = make_record(theme="other", ai_theme="n/a")
    logic.apply_rules([record])
    assert record.verification == MISMATCH
    assert len(record.review_reasons) == 2
    assert not record.counted


def test_applying_the_rules_again_does_not_repeat_a_mismatch(logic):
    record = make_record(theme="Facilities", ai_theme="Assessment")
    logic.apply_rules([record])
    logic.apply_rules([record])
    assert record.verification == MISMATCH
    assert len(record.review_reasons) == 1


def test_a_mismatch_clears_once_the_ai_agrees(logic):
    record = make_record(theme="Facilities", ai_theme="Assessment")
    logic.apply_rules([record])
    record.set_ai("Facilities", NEGATIVE, HIGH)
    logic.apply_rules([record])
    assert record.verification == MATCHED
    assert not record.needs_review
    assert record.counted


def test_an_admin_review_resolves_a_mismatch_for_good(logic):
    record = make_record(theme="Facilities", ai_theme="Assessment")
    logic.apply_rules([record])
    record.mark_reviewed("Assessment", NEGATIVE, HIGH)
    logic.apply_rules([record])
    assert record.verification == REVIEWED
    assert not record.needs_review
    assert record.counted


def test_a_reviewed_record_keeps_the_admins_values(logic):
    record = make_record(theme="other", severity=CRITICAL, ai_theme="spam")
    logic.apply_rules([record])
    record.mark_reviewed("Administration", POSITIVE, LOW)
    logic.apply_rules([record])
    assert (record.theme, record.sentiment, record.severity) == ("Administration", POSITIVE, LOW)
    assert record.verification == REVIEWED
    assert not record.needs_review
    assert record.counted


def test_rules_can_be_chosen_through_the_constructor():
    record = make_record()
    LogicManager(rules=[_FlagEverythingRule()]).apply_rules([record])
    assert record.review_reasons == ["Flagged by test rule"]


def test_an_empty_rule_list_means_no_rules():
    record = make_record(severity=CRITICAL)
    LogicManager(rules=[]).apply_rules([record])
    assert not record.needs_review


# ------------------------------------------------------------------ the rest of a run
def test_review_queue_puts_critical_first(logic):
    unclear, critical = make_record("fb_001", theme="other"), make_record("fb_002", severity=CRITICAL)
    records = logic.apply_rules([unclear, critical])
    assert logic.review_queue(records) == [critical, unclear]


def test_aggregate_returns_the_runs_statistics(logic):
    records = logic.apply_rules([make_record("fb_001"), make_record("fb_002", theme="other")])
    result = logic.aggregate(records)
    assert isinstance(result, AggregationResult)
    assert (result.total_entries, result.counted_entries) == (2, 1)
    assert result.get("Facilities").count == 1


def test_compare_runs_handles_a_first_run_and_a_later_one(logic):
    first = logic.aggregate(logic.apply_rules([make_record("fb_001")]))
    assert not logic.compare_runs(first, None).has_previous
    second = logic.aggregate(logic.apply_rules([make_record("fb_001"), make_record("fb_002", theme="Workload")]))
    report = logic.compare_runs(second, first)
    assert isinstance(report, TrendReport)
    assert report.needs_attention() == ["Workload"]


def test_a_whole_run_produces_results_that_can_be_saved_as_json(logic):
    """The order in design reference section 6, step 4."""
    incoming = [make_record("fb_001", severity=CRITICAL), make_record("fb_002", theme="n/a"),
                make_record("fb_003", sentiment="angry"), make_record("fb_001", theme="repeat")]
    valid, invalid = logic.validate(incoming)
    records = logic.apply_rules(valid)
    queue = logic.review_queue(records)
    result = logic.aggregate(records)
    trend = logic.compare_runs(result, None)

    assert len(valid) == 2
    assert len(invalid) == 2
    assert [r.feedback_id for r in queue] == ["fb_001", "fb_002"]
    assert result.counted_entries == 1
    rebuilt = AggregationResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert rebuilt == result
    assert TrendReport.from_dict(json.loads(json.dumps(trend.to_dict()))) == trend
