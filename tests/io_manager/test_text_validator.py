"""TextValidator: free text that is not empty, has letters and is not too long."""
import pytest

from managers.io_manager.text_validator import TextValidator


def test_returns_the_text_trimmed():
    assert TextValidator().check("  Wifi keeps dropping  ") == ("Wifi keeps dropping", "")


def test_empty_text_is_rejected_with_its_label():
    assert TextValidator("description").check("   ") == (None, "description is empty")


def test_optional_text_may_be_blank():
    assert TextValidator("keyword", required=False).check("") == ("", "")


@pytest.mark.parametrize("answer", ["12345", "!!!", "-- 42 --"])
def test_text_without_letters_is_rejected(answer):
    assert TextValidator().check(answer) == (None, "text contains no letters")


def test_letters_can_be_made_optional():
    # an action keyword such as "5G" or "2026" is allowed
    assert TextValidator("keyword", require_letter=False).check("2026") == ("2026", "")


def test_length_limit():
    validator = TextValidator("description", max_length=10)
    assert validator.check("a" * 10) == ("a" * 10, "")
    assert validator.check("a" * 11) == (None, "description longer than 10 characters")


def test_default_limit_is_2000_characters():
    assert TextValidator().check("a" * 2000)[1] == ""
    assert TextValidator().check("a" * 2001)[0] is None
