import pytest

from managers.logic_manager import ActionSuggestions
from managers.models import Serializable

ACTIONS = [{"theme": "Facilities", "suggested_action": "Check Wi-Fi coverage with IT services."}]


def test_is_serializable():
    assert isinstance(ActionSuggestions(ACTIONS), Serializable)


def test_round_trip_gives_equal_suggestions():
    suggestions = ActionSuggestions(ACTIONS, "2026-11-12T10:00:00")
    assert ActionSuggestions.from_dict(suggestions.to_dict()) == suggestions


def test_actions_cannot_be_changed_from_outside():
    given = [dict(ACTIONS[0])]
    suggestions = ActionSuggestions(given)
    given[0]["theme"] = "changed"
    suggestions.theme_actions[0]["theme"] = "changed"
    assert suggestions.theme_actions == ACTIONS


@pytest.mark.parametrize("data", [None, {}, {"theme_actions": [{"theme": "Facilities"}], "created_at": "x"}])
def test_from_dict_raises_value_error_for_anything_unreadable(data):
    with pytest.raises(ValueError):
        ActionSuggestions.from_dict(data)
