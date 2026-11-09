from datetime import date

import pytest

from managers.logic_manager import ImpactReport
from managers.logic_manager.impact_analyser import ImpactAnalyser
from managers.logic_manager.theme_aggregator import ThemeAggregator
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import (
    HIGH, LOW, MATCHED, NEGATIVE, NEUTRAL, POSITIVE, UNVERIFIED, Action, FeedbackRecord,
)

ACTION_DATE = "2026-10-15"


def make_action(keyword=None, action_date=ACTION_DATE, theme="Facilities"):
    return Action("act_001", theme, "Upgraded library Wi-Fi", action_date, keyword, "2026-10-15T09:00:00")


def make_record(day, sentiment=NEGATIVE, severity=HIGH, theme="Facilities", text="The wifi keeps dropping.",
                verification=MATCHED):
    record = FeedbackRecord(f"fb_{day}_{text[:5]}", text, f"{day}T10:00:00", None,
                            {"theme": theme, "sentiment": sentiment, "severity": severity})
    record.set_final(theme, sentiment, severity, verification)
    return record


def evaluate(records, today="2026-10-29", keyword=None, action_date=ACTION_DATE, theme="Facilities"):
    normaliser = ThemeNormaliser()
    analyser = ImpactAnalyser(normaliser, ThemeAggregator(normaliser))
    return analyser.evaluate(make_action(keyword, action_date, theme), records, date.fromisoformat(today))


def window(first_day, count, **values):
    """count records on consecutive days from first_day (2026-10-dd)."""
    return [make_record(f"2026-10-{first_day + i:02d}", **values) for i in range(count)]


@pytest.mark.parametrize("today", ["2026-10-15", "2026-10-10"])
def test_an_action_dated_today_or_later_is_too_early_to_tell(today):
    report = evaluate([make_record("2026-10-10")], today=today)
    assert report.label == ImpactReport.TOO_EARLY
    assert (report.before, report.after) == (None, None)


def test_under_seven_days_after_is_too_early_to_tell():
    report = evaluate([make_record("2026-10-14")] * 5, today="2026-10-20")
    assert report.label == ImpactReport.TOO_EARLY
    assert report.message == "Too early to tell: only 6 day(s) of feedback since 2026-10-15; at least 7 are needed."


def test_fewer_than_three_matching_entries_is_too_early_to_tell():
    report = evaluate([make_record("2026-10-10"), make_record("2026-10-20")])
    assert report.label == ImpactReport.TOO_EARLY


def test_windows_are_equal_and_the_after_window_includes_today():
    days = ["2026-10-07", "2026-10-08", "2026-10-14", "2026-10-15", "2026-10-21"]
    report = evaluate([make_record(day) for day in days], today="2026-10-21")
    assert (report.before["start"], report.before["end"], report.before["days"]) == ("2026-10-08", "2026-10-14", 7)
    assert (report.after["start"], report.after["end"], report.after["days"]) == ("2026-10-15", "2026-10-21", 7)
    assert (report.before["entries"], report.after["entries"]) == (2, 2)


def test_only_counted_records_on_the_theme_with_the_keyword_are_measured():
    excluded = make_record("2026-10-10")
    excluded.add_review_reason("Not counted", excludes=True)
    records = [
        make_record("2026-10-10"),
        make_record("2026-10-11", text="Library WIFI is slow."),                   # any case
        make_record("2026-10-12", text="The printers keep jamming."),              # no keyword
        make_record("2026-10-12", text="Free wifiplus vouchers ran out."),         # not the whole word
        make_record("2026-10-13", theme="Assessment"),                             # other theme
        excluded,
        make_record("2026-10-20", verification=UNVERIFIED),
    ]
    report = evaluate(records, keyword="wifi", theme="facilities")                 # theme as an admin might type it
    assert (report.before["entries"], report.after["entries"]) == (2, 1)
    assert report.before["share_percent"] == 40       # 2 of the 5 counted entries before
    assert report.before["high_or_critical"] == 2
    assert report.after["unverified"] == 1


def test_exactly_three_matching_entries_is_enough_to_judge():
    report = evaluate([make_record("2026-10-10"), make_record("2026-10-20"), make_record("2026-10-21")])
    assert report.label != ImpactReport.TOO_EARLY


@pytest.mark.parametrize("before, after, label", [
    # 1.5 -> 1.0 negative per week (-33%), priority 76 -> 27: both past the limits
    (window(1, 3), window(15, 2, severity=LOW), ImpactReport.EFFECTIVE),
    # 2.5 -> 2.0 negative per week (-20%), priority 82 -> 34: not a big enough fall
    (window(1, 5), window(15, 4, severity=LOW), ImpactReport.NO_CHANGE),
    # same negatives, priority 34 -> 45 (+11): priority alone is enough for Worse
    (window(1, 4, severity=LOW), window(15, 3, severity=LOW) + window(18, 1), ImpactReport.WORSE),
    # same negatives, priority 52 -> 53 (+1): too small to count
    (window(1, 9, severity=LOW), window(15, 9, severity=LOW) + window(24, 1, severity=LOW, sentiment=NEUTRAL),
     ImpactReport.NO_CHANGE),
    # no negatives before, some after: any rise from zero counts, even with priority falling (66 -> 24)
    (window(1, 6, sentiment=POSITIVE), window(15, 1, severity=LOW), ImpactReport.WORSE),
])
def test_labels_near_the_limits(before, after, label):
    assert evaluate(before + after).label == label


def test_fewer_negative_entries_and_a_lower_priority_is_effective():
    records = [make_record(f"2026-10-0{d}") for d in range(1, 7)] + [make_record("2026-10-20", severity=LOW)]
    report = evaluate(records)
    assert report.label == ImpactReport.EFFECTIVE
    assert report.message == ("Since Upgraded library Wi-Fi (2026-10-15), negative Facilities feedback fell from "
                              "3 to 0.5 per week, and its priority dropped from 86 to 24.")


def test_more_negative_entries_is_worse():
    records = [make_record("2026-10-10", severity=LOW)] + [make_record(f"2026-10-2{d}") for d in range(4)]
    assert evaluate(records).label == ImpactReport.WORSE


def test_a_small_move_is_no_change():
    records = [make_record("2026-10-09"), make_record("2026-10-10"),
               make_record("2026-10-20"), make_record("2026-10-21"), make_record("2026-10-22", sentiment=POSITIVE)]
    assert evaluate(records).label == ImpactReport.NO_CHANGE
