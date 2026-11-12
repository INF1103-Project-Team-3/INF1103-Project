"""EntryForm: asks for one piece of feedback or one action, question by question."""
import pytest

from managers.io_manager.entry_form import EntryForm
from managers.io_manager.record_builder import RecordBuilder
from managers.io_manager.theme_validator import ThemeValidator
from managers.models import THEMES

OTHER = str(len(THEMES) + 1)            # "Other" is the last item of the theme menu
WORKLOAD = str(THEMES.index("Workload") + 1)


@pytest.fixture
def form(prompter, screen, data, logic):
    def make(answers):
        return EntryForm(prompter(answers), screen.view, data, ThemeValidator(logic), RecordBuilder())
    return make


def test_collects_feedback_with_the_writers_own_labels(form):
    record = form(["Three deadlines in one week", WORKLOAD, "negative", "high"]).collect_feedback()
    assert record.text == "Three deadlines in one week"
    assert record.user == {"theme": "Workload", "sentiment": "negative", "severity": "high"}
    assert record.feedback_id.startswith("fb_")


def test_other_lets_the_writer_type_a_new_theme(form, logic):
    record = form(["Parking costs too much", OTHER, "parking fees", "negative", "high"]).collect_feedback()
    assert record.user["theme"] == "Parking Fees"
    assert logic.calls == ["parking fees"]       # cleaned up by Logic, not by I/O


def test_the_theme_menu_comes_from_data(form, data, screen):
    data.themes = ["Workload", "Car Park"]
    form(["Good", "2", "positive", "low"]).collect_feedback()
    assert "Theme:\n  1. Workload\n  2. Car Park\n  3. Other" in screen.lines


def test_bad_answers_are_asked_again(form, screen):
    record = form(["", "Good lectures", "0", "1", "great", "positive", "low"]).collect_feedback()
    assert record.text == "Good lectures"
    assert "  Invalid: text is empty" in screen.lines
    assert f"  Invalid: enter a number from 1 to {len(THEMES) + 1}" in screen.lines


@pytest.mark.parametrize("answers", [["quit"], ["Good", "q"], ["Good", "1", "quit"],
                                     ["Good", "1", "positive", "q"]])
def test_quitting_at_any_question_returns_none(form, answers):
    assert form(answers).collect_feedback() is None


def test_collects_an_action_and_re_asks_a_bad_date(form, screen):
    action = form(["3", "Upgraded the library wifi", "2026-9-30", "2026-09-30", "wifi"]).collect_action()
    assert (action.theme, action.action_date, action.keyword) == (THEMES[2], "2026-09-30", "wifi")
    assert "  Invalid: date must look like YYYY-MM-DD (e.g. 2026-11-05)" in screen.lines


def test_an_action_needs_an_existing_theme(form, screen):
    form(["1", "Did a thing", "2026-11-05", ""]).collect_action()
    assert "Other" not in screen.text


def test_a_blank_keyword_measures_the_whole_theme(form):
    assert form(["1", "Did a thing", "2026-11-05", ""]).collect_action().keyword is None


def test_an_action_the_model_refuses_is_reported_not_raised(form, data, screen):
    data.themes = ["   "]                         # a corrupt theme name from Data
    assert form(["1", "Did a thing", "2026-11-05", ""]).collect_action() is None
    assert any(line.startswith("  Invalid: theme must be non-empty text") for line in screen.lines)
