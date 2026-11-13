import pytest

from managers.logic_manager import ImpactReport
from managers.models import Action, Serializable

ACTION = Action("act_001", "Facilities", "Upgraded library Wi-Fi", "2026-10-01", "wifi", "2026-10-01T09:00:00")


def make_report():
    return ImpactReport(
        ACTION,
        ImpactReport.EFFECTIVE,
        "Since 2026-10-01, negative Facilities feedback mentioning 'wifi' fell from 3 to 1 per week.",
        before={"days": 14, "entries": 8, "negative": 6, "negative_per_week": 3.0, "priority": 62},
        after={"days": 14, "entries": 3, "negative": 2, "negative_per_week": 1.0, "priority": 30},
        weekly=[{"week_start": "2026-09-24", "negative": 3, "total": 4}],
        warnings=["1 of these entries is unverified."],
    )


def test_is_serializable():
    assert isinstance(make_report(), Serializable)


def test_round_trip_gives_an_equal_report():
    report = make_report()
    assert ImpactReport.from_dict(report.to_dict()) == report


def test_details_cannot_be_changed_from_outside():
    report = make_report()
    report.before["negative"] = 99
    report.weekly[0]["total"] = 99
    report.warnings.append("changed")
    assert report.before["negative"] == 6
    assert report.weekly[0]["total"] == 4
    assert report.warnings == ["1 of these entries is unverified."]


def test_an_action_too_recent_to_measure_has_no_windows():
    report = ImpactReport(ACTION, ImpactReport.TOO_EARLY, "The action is dated today.")
    assert (report.before, report.after, report.weekly, report.warnings) == (None, None, [], [])


def test_rejects_a_label_that_is_not_one_of_the_four():
    with pytest.raises(ValueError):
        ImpactReport(ACTION, "Great", "message")


@pytest.mark.parametrize("data", [None, {}, {"action": {}, "label": "Effective", "message": "m"}])
def test_from_dict_raises_value_error_for_anything_unreadable(data):
    with pytest.raises(ValueError):
        ImpactReport.from_dict(data)
