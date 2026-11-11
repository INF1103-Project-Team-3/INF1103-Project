"""ChoiceValidator: accepts one value from a fixed list, ignoring case."""
from managers.io_manager.choice_validator import ChoiceValidator
from managers.models import SEVERITIES


def test_accepts_any_case_and_returns_the_real_option():
    validator = ChoiceValidator(SEVERITIES)
    assert validator.check("  HIGH ") == ("high", "")


def test_rejects_an_unknown_value_and_lists_the_options():
    value, error = ChoiceValidator(("user", "admin")).check("boss")
    assert value is None
    assert error == "choose one of: user, admin"


def test_custom_error_message_replaces_the_default():
    validator = ChoiceValidator(("1", "2"), error="enter a number from 1 to 2")
    assert validator.check("3") == (None, "enter a number from 1 to 2")


def test_blank_is_rejected_unless_allowed():
    assert ChoiceValidator(SEVERITIES).check("")[0] is None
    # a reviewer presses Enter to keep the current value
    assert ChoiceValidator(SEVERITIES, allow_blank=True).check("  ") == ("", "")
