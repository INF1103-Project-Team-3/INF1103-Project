import pytest

from managers.logic_manager import TrendReport
from managers.models import Serializable


def make_row(theme, status):
    return {
        "theme": theme,
        "status": status,
        "count": {"previous": 2, "current": 3, "change": 1, "text": "2 -> 3 (+1)"},
        "priority": {"previous": 40, "current": 50, "change": 10, "text": "40 -> 50 (+10)"},
    }


def make_report():
    return TrendReport(
        True,
        previous_run={"run_at": "2026-11-04T10:00:00", "source_file": "week1.csv"},
        headline={"total_entries": {"previous": 5, "current": 8, "change": 3, "text": "5 -> 8 (+3)"}},
        themes=[
            make_row("Facilities", TrendReport.ESCALATING),
            make_row("Parking Fees", TrendReport.NEW),
            make_row("Assessment", TrendReport.EASING),
            make_row("Workload", TrendReport.STEADY),
            make_row("Well-being", TrendReport.NOT_REPORTED),
        ],
    )


def test_is_serializable():
    assert isinstance(make_report(), Serializable)


def test_needs_attention_lists_escalating_and_new_themes():
    assert make_report().needs_attention() == ["Facilities", "Parking Fees"]


def test_getting_better_lists_easing_themes():
    assert make_report().getting_better() == ["Assessment"]


def test_a_first_run_report_has_empty_details():
    report = TrendReport(False, message="First run - nothing to compare yet.")
    assert report.previous_run is None
    assert report.headline == {}
    assert report.themes == []
    assert report.needs_attention() == []


def test_fields_are_read_only():
    with pytest.raises(AttributeError):
        make_report().has_previous = False


def test_rows_cannot_be_changed_from_outside():
    report = make_report()
    report.themes[0]["status"] = TrendReport.STEADY
    report.themes[0]["count"]["current"] = 99
    assert report.themes[0]["status"] == TrendReport.ESCALATING
    assert report.themes[0]["count"]["current"] == 3


def test_to_dict_includes_the_attention_lists_for_readers():
    data = make_report().to_dict()
    assert data["needs_attention"] == ["Facilities", "Parking Fees"]
    assert data["getting_better"] == ["Assessment"]


def test_round_trip_gives_an_equal_report():
    report = make_report()
    assert TrendReport.from_dict(report.to_dict()) == report


@pytest.mark.parametrize("data", [None, [], {}, {"has_previous": True, "themes": [{"theme": "Facilities"}]}])
def test_from_dict_raises_value_error_for_anything_unreadable(data):
    with pytest.raises(ValueError):
        TrendReport.from_dict(data)
