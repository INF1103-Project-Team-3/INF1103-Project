from managers.logic_manager import AggregationResult
from managers.logic_manager.theme_aggregator import ThemeAggregator
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MEDIUM, MISMATCH, NEGATIVE, NEUTRAL, POSITIVE, UNCLEAR_THEME, UNVERIFIED,
    FeedbackRecord,
)


def make_record(feedback_id, theme="Facilities", sentiment=NEGATIVE, severity=HIGH, verification=MATCHED):
    record = FeedbackRecord(feedback_id, "Some feedback.", "2026-09-17T08:03:00", None,
                            {"theme": theme, "sentiment": sentiment, "severity": severity})
    record.set_final(theme, sentiment, severity, verification)
    return record


def aggregate(records):
    return ThemeAggregator(ThemeNormaliser()).aggregate(records)


def make_excluded_record(feedback_id, theme):
    record = make_record(feedback_id, theme)
    record.add_review_reason("Not counted", excludes=True)
    return record


def test_returns_an_aggregation_result():
    assert isinstance(aggregate([make_record("fb_001")]), AggregationResult)


def test_no_records_gives_an_empty_result():
    result = aggregate([])
    assert result.themes == ()
    assert result.total_entries == 0
    assert result.negative_percent == 0


def test_total_covers_every_record_but_themes_only_the_counted_ones():
    excluded = make_record("fb_002", verification=MISMATCH)
    excluded.add_review_reason("AI disagrees on theme", excludes=True)
    result = aggregate([make_record("fb_001"), excluded])
    assert result.total_entries == 2
    assert result.counted_entries == 1


def test_a_record_not_yet_checked_by_logic_is_not_counted():
    unchecked = FeedbackRecord("fb_001", "Some feedback.", "2026-09-17T08:03:00", None,
                               {"theme": "Facilities", "sentiment": NEGATIVE, "severity": HIGH})
    result = aggregate([unchecked])
    assert result.total_entries == 1
    assert result.themes == ()


def test_a_flagged_critical_record_is_still_counted():
    record = make_record("fb_001", severity=CRITICAL)
    record.add_review_reason("Critical severity", excludes=False)
    assert aggregate([record]).get("Facilities").severity_counts[CRITICAL] == 1


def test_counts_have_every_severity_and_sentiment_even_when_zero():
    stats = aggregate([make_record("fb_001", severity=LOW, sentiment=POSITIVE)]).get("Facilities")
    assert stats.severity_counts == {LOW: 1, MEDIUM: 0, HIGH: 0, CRITICAL: 0}
    assert stats.sentiment_counts == {POSITIVE: 1, NEUTRAL: 0, NEGATIVE: 0}


def test_average_sentiment_is_rounded_to_two_decimals():
    records = [make_record("fb_001"), make_record("fb_002"), make_record("fb_003", sentiment=NEUTRAL)]
    assert aggregate(records).get("Facilities").avg_sentiment == -0.67


def test_priority_comes_from_the_scorer():
    # 3/3 severe * 45 + 1.0 * 20 + 3/10 * 35 = 45 + 20 + 10.5 = 75.5, which rounds to 76
    records = [make_record(f"fb_00{i}") for i in range(3)]
    assert aggregate(records).get("Facilities").priority == 76


def test_unverified_records_are_counted_and_reported():
    records = [make_record("fb_001", verification=UNVERIFIED), make_record("fb_002")]
    result = aggregate(records)
    assert result.get("Facilities").count == 2
    assert result.get("Facilities").unverified == 1
    assert result.unverified_count == 1


def test_uses_the_final_theme_after_an_admin_review():
    record = make_record("fb_001", theme="Facilities", verification=MISMATCH)
    record.mark_reviewed("Administration", NEGATIVE, LOW)
    result = aggregate([record])
    assert result.get("Administration").count == 1
    assert result.get("Facilities") is None


def test_themes_sort_by_count_then_priority_then_name():
    records = [
        # one low, positive entry each: same count and priority, so name decides
        make_record("fb_001", "Workload", POSITIVE, LOW),
        make_record("fb_002", "Assessment", POSITIVE, LOW),
        # same count as those two, but severe and negative: higher priority
        make_record("fb_003", "Well-being", NEGATIVE, CRITICAL),
        # most entries, so it comes first even with a low priority
        make_record("fb_004", "Facilities", POSITIVE, LOW),
        make_record("fb_005", "Facilities", POSITIVE, LOW),
    ]
    assert [stats.theme for stats in aggregate(records).themes] == [
        "Facilities", "Well-being", "Assessment", "Workload",
    ]


def test_negative_percent_covers_all_themes():
    records = [make_record("fb_001", "Facilities"), make_record("fb_002", "Assessment", POSITIVE, LOW)]
    assert aggregate(records).negative_percent == 50


def test_pending_themes_count_each_new_theme_most_first_then_by_name():
    records = [make_excluded_record("fb_001", "Zoo Trips"), make_excluded_record("fb_002", "Car Park"),
               make_excluded_record("fb_003", "Parking Fees"), make_excluded_record("fb_004", "Parking Fees")]
    assert list(aggregate(records).pending_themes.items()) == [("Parking Fees", 2), ("Car Park", 1), ("Zoo Trips", 1)]


def test_only_new_themes_that_are_not_counted_are_pending():
    reviewed = make_excluded_record("fb_001", "Parking Fees")
    reviewed.mark_reviewed("Parking Fees", NEGATIVE, HIGH)
    unchecked = FeedbackRecord("fb_002", "Some feedback.", "2026-09-17T08:03:00", None,
                               {"theme": "Parking Fees", "sentiment": NEGATIVE, "severity": HIGH})
    records = [reviewed, unchecked, make_excluded_record("fb_003", "Facilities"),
               make_excluded_record("fb_004", UNCLEAR_THEME)]
    assert aggregate(records).pending_themes == {}
