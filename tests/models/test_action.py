import pytest

from managers.models import Action, Serializable


def make_action(**changes):
    values = {
        "action_id": "act_001",
        "theme": "Facilities",
        "description": "Upgraded library Wi-Fi",
        "action_date": "2026-11-01",
        "keyword": "wifi",
        "logged_at": "2026-11-02T14:00:00",
    }
    values.update(changes)
    return Action(**values)


def test_stores_every_field():
    action = make_action()
    assert (action.action_id, action.theme, action.description) == ("act_001", "Facilities", "Upgraded library Wi-Fi")
    assert (action.action_date, action.keyword, action.logged_at) == ("2026-11-01", "wifi", "2026-11-02T14:00:00")


def test_is_serializable():
    assert isinstance(make_action(), Serializable)


def test_fields_are_read_only():
    with pytest.raises(AttributeError):
        make_action().theme = "Workload"


@pytest.mark.parametrize("keyword", [None, "", "   "])
def test_no_keyword_or_blank_keyword_becomes_none(keyword):
    assert make_action(keyword=keyword).keyword is None


def test_keyword_is_trimmed():
    assert make_action(keyword="  wifi ").keyword == "wifi"


def test_future_date_is_allowed():
    # ImpactAnalyser reports "Too early to tell" for these; Action does not reject them
    assert make_action(action_date="2030-01-01").action_date == "2030-01-01"


@pytest.mark.parametrize("action_date", ["01/11/2026", "2026-1-5", "2026-02-30", "20261101", "", None])
def test_bad_action_date_is_rejected(action_date):
    with pytest.raises(ValueError):
        make_action(action_date=action_date)


@pytest.mark.parametrize("field", ["action_id", "theme", "description", "logged_at"])
def test_empty_text_is_rejected(field):
    with pytest.raises(ValueError):
        make_action(**{field: "  "})


def test_non_text_keyword_is_rejected():
    with pytest.raises(ValueError):
        make_action(keyword=5)


def test_round_trip_keeps_every_field():
    action = make_action()
    assert Action.from_dict(action.to_dict()).to_dict() == action.to_dict()


def test_from_dict_rejects_a_corrupt_entry():
    data = make_action().to_dict()
    data["action_date"] = "next week"
    with pytest.raises(ValueError):
        Action.from_dict(data)
