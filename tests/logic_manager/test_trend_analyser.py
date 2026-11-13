import pytest

from managers.logic_manager import AggregationResult, ThemeStats, TrendReport
from managers.logic_manager.trend_analyser import TrendAnalyser
from managers.models import NEGATIVE, POSITIVE


def make_stats(theme, priority=50, count=4, negative=0):
    return ThemeStats(theme, count, {}, {NEGATIVE: negative, POSITIVE: count - negative}, 0.0, priority, 0)


def make_result(*themes, total_entries=10, run_at="2026-11-04T10:00:00", source_file="week1.csv"):
    return AggregationResult(list(themes), total_entries, run_at=run_at, source_file=source_file)


def compare(current, previous):
    return TrendAnalyser().compare(current, previous)


def row_for(report, theme):
    return next(row for row in report.themes if row["theme"] == theme)


def test_first_run_has_nothing_to_compare():
    report = compare(make_result(make_stats("Facilities")), None)
    assert not report.has_previous
    assert report.message == "First run - nothing to compare yet."
    assert report.themes == []


def test_records_which_run_it_compared_with():
    report = compare(make_result(), make_result())
    assert report.has_previous
    assert report.message is None
    assert report.previous_run == {"run_at": "2026-11-04T10:00:00", "source_file": "week1.csv"}


@pytest.mark.parametrize("before, after, status", [
    (50, 55, TrendReport.ESCALATING),
    (50, 54, TrendReport.STEADY),
    (50, 50, TrendReport.STEADY),
    (50, 46, TrendReport.STEADY),
    (50, 45, TrendReport.EASING),
])
def test_status_depends_on_how_far_priority_moved(before, after, status):
    report = compare(make_result(make_stats("Facilities", after)), make_result(make_stats("Facilities", before)))
    assert row_for(report, "Facilities")["status"] == status


def test_a_theme_only_in_the_current_run_is_new():
    row = row_for(compare(make_result(make_stats("Parking Fees", 40, count=3)), make_result()), "Parking Fees")
    assert row["status"] == TrendReport.NEW
    assert row["count"]["text"] == "0 -> 3 (+3)"
    assert row["priority"] == {"previous": None, "current": 40, "change": None, "text": "- -> 40"}


def test_a_theme_only_in_the_previous_run_is_not_reported():
    row = row_for(compare(make_result(), make_result(make_stats("Workload", 40, count=3))), "Workload")
    assert row["status"] == TrendReport.NOT_REPORTED
    assert row["count"]["text"] == "3 -> 0 (-3)"
    assert row["priority"] == {"previous": 40, "current": None, "change": None, "text": "40 -> -"}


def test_rows_sort_by_status_then_priority_then_name():
    previous = make_result(make_stats("Steady B", 50), make_stats("Steady A", 50), make_stats("Up", 40),
                           make_stats("Down", 60), make_stats("Gone", 70))
    current = make_result(make_stats("Steady B", 50), make_stats("Steady A", 50), make_stats("Up", 60),
                          make_stats("Down", 30), make_stats("Fresh", 20))
    assert [row["theme"] for row in compare(current, previous).themes] == [
        "Up", "Fresh", "Down", "Steady A", "Steady B", "Gone",
    ]


def test_headline_compares_the_totals():
    previous = make_result(make_stats("Facilities", count=2, negative=1), total_entries=4)
    current = make_result(make_stats("Facilities", count=4, negative=3), total_entries=9)
    headline = compare(current, previous).headline
    assert headline["total_entries"]["text"] == "4 -> 9 (+5)"
    assert headline["counted_entries"]["text"] == "2 -> 4 (+2)"
    assert headline["negative_percent"]["text"] == "50% -> 75% (+25 pts)"


def test_no_change_is_shown_as_0():
    result = make_result(make_stats("Facilities"))
    assert compare(result, result).headline["total_entries"]["text"] == "10 -> 10 (0)"


def test_status_counts_cover_every_status_and_add_up():
    report = compare(make_result(make_stats("Facilities", 60), make_stats("Fresh")),
                     make_result(make_stats("Facilities", 50)))
    assert report.headline["status_counts"] == {
        TrendReport.ESCALATING: 1, TrendReport.NEW: 1, TrendReport.EASING: 0,
        TrendReport.STEADY: 0, TrendReport.NOT_REPORTED: 0,
    }
    assert report.needs_attention() == ["Facilities", "Fresh"]


def test_works_on_runs_rebuilt_from_saved_history():
    saved = {"run_at": "2026-11-01T09:00:00", "source_file": None,
             "result": make_result(make_stats("Facilities", 50)).to_dict()}
    report = compare(make_result(make_stats("Facilities", 60)), AggregationResult.from_dict(saved))
    assert report.previous_run == {"run_at": "2026-11-01T09:00:00", "source_file": None}
    assert report.getting_better() == []
