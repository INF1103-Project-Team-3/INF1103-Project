import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QPushButton  # noqa: E402

from managers.gui.pages.start_page import StartPage  # noqa: E402
from managers.gui.pages.student_form_page import StudentFormPage  # noqa: E402
from managers.gui.widgets.option_card import OptionCard  # noqa: E402
from managers.io_manager import EntryValidator, RecordBuilder, ThemeValidator  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import THEMES  # noqa: E402


def button(widget, text):
    return [b for b in widget.findChildren(QPushButton) if b.text() == text][0]


def student_form(qtbot):
    page = StudentFormPage(list(THEMES), EntryValidator(ThemeValidator(LogicManager())), RecordBuilder())
    qtbot.addWidget(page)
    return page


# A known theme is picked from the dropdown; anything else is typed under "Other…".
def fill(page, text, theme, chosen):
    page.findChild(QPlainTextEdit, "feedbackBox").setPlainText(text)
    if theme in THEMES:
        page.theme_picker.choose(theme)
    else:
        page.theme_picker.type_other(theme)
    for card in page.findChildren(OptionCard):
        if card.value in chosen:
            card.radio.setChecked(True)


def test_login_sends_the_typed_password(qtbot):
    page = StartPage()
    qtbot.addWidget(page)
    page.show_login()
    page.findChild(QLineEdit, "passwordBox").setText("secret")
    with qtbot.waitSignal(page.login_requested, timeout=1000) as blocker:
        button(page, "Log in").click()
    assert blocker.args == ["secret"]


def test_empty_form_shows_the_validators_error_and_sends_nothing(qtbot):
    page = student_form(qtbot)
    with qtbot.assertNotEmitted(page.feedback_submitted):
        button(page, "Submit feedback").click()
    assert "missing field(s): text" in page.findChild(QLabel, "errorText").text()


def test_missing_severity_is_rejected(qtbot):
    page = student_form(qtbot)
    fill(page, "The library wifi keeps dropping", "Facilities", ("negative",))
    with qtbot.assertNotEmitted(page.feedback_submitted):
        button(page, "Submit feedback").click()
    assert "severity" in page.findChild(QLabel, "errorText").text()


def test_text_without_letters_is_rejected(qtbot):
    page = student_form(qtbot)
    fill(page, "!!! ???", "Facilities", ("negative", "low"))
    with qtbot.assertNotEmitted(page.feedback_submitted):
        button(page, "Submit feedback").click()
    assert "no letters" in page.findChild(QLabel, "errorText").text()


def test_complete_form_builds_a_record(qtbot):
    page = student_form(qtbot)
    fill(page, "The library wifi keeps dropping", "wifi", ("negative", "medium"))
    with qtbot.waitSignal(page.feedback_submitted, timeout=1000) as blocker:
        button(page, "Submit feedback").click()
    record = blocker.args[0]
    assert record.user == {"theme": "Facilities", "sentiment": "negative", "severity": "medium"}
    assert record.feedback_id.startswith("fb_") and record.ai is None


def test_typed_new_theme_is_normalised_by_the_theme_validator(qtbot):
    page = student_form(qtbot)
    fill(page, "Parking costs too much", "  parking fees ", ("negative", "low"))
    with qtbot.waitSignal(page.feedback_submitted, timeout=1000) as blocker:
        button(page, "Submit feedback").click()
    assert blocker.args[0].user["theme"] == "Parking Fees"


def test_picking_a_known_theme_builds_the_record_with_it(qtbot):
    page = student_form(qtbot)
    fill(page, "The tutorials are paced really well", "Teaching Quality", ("positive", "low"))
    with qtbot.waitSignal(page.feedback_submitted, timeout=1000) as blocker:
        button(page, "Submit feedback").click()
    assert blocker.args[0].user["theme"] == "Teaching Quality"


def test_other_with_a_known_name_in_other_case_ends_up_as_the_known_theme(qtbot):
    page = student_form(qtbot)
    fill(page, "The lab aircon is broken", "fACILITIES", ("negative", "medium"))
    assert page.theme_picker.is_other()
    with qtbot.waitSignal(page.feedback_submitted, timeout=1000) as blocker:
        button(page, "Submit feedback").click()
    assert blocker.args[0].user["theme"] == "Facilities"


def test_other_left_empty_shows_an_error_and_builds_nothing(qtbot):
    page = student_form(qtbot)
    fill(page, "The lab aircon is broken", "", ("negative", "medium"))
    assert page.theme_picker.is_other()
    with qtbot.assertNotEmitted(page.feedback_submitted):
        button(page, "Submit feedback").click()
    assert "theme" in page.findChild(QLabel, "errorText").text()


def test_theme_list_is_a_dropdown_and_refreshes_with_new_themes(qtbot):
    from managers.gui.widgets.combo_box import ComboBox
    page = student_form(qtbot)
    assert not [b for b in page.findChildren(QPushButton) if b.objectName() == "chip"]
    page.set_themes([*THEMES, "Parking Fees"])
    box = page.findChild(ComboBox, "studentTheme")
    assert [box.itemText(i) for i in range(box.count())][-2:] == ["Parking Fees", "Other…"]
