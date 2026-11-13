"""ThemeValidator: a typed theme is cleaned up by the Logic Manager, not by I/O."""
from managers.io_manager.theme_validator import ThemeValidator
from managers.models import UNCLEAR_THEME


def test_theme_is_normalised_by_logic(logic):
    assert ThemeValidator(logic).check("  workload ") == ("Workload", "")
    assert logic.calls == ["workload"]        # I/O passed the trimmed text on


def test_new_and_filler_labels_are_accepted_as_logic_decides(logic):
    validator = ThemeValidator(logic)
    assert validator.check("parking fees") == ("Parking Fees", "")
    assert validator.check("n/a") == (UNCLEAR_THEME, "")


def test_empty_theme_is_rejected_without_asking_logic(logic):
    assert ThemeValidator(logic).check("   ") == (None, "theme cannot be empty")
    assert logic.calls == []


def test_blank_allowed_means_keep_the_current_theme(logic):
    assert ThemeValidator(logic, allow_blank=True).check("") == ("", "")
    assert logic.calls == []
