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


def fill(page, text, theme, chosen):
    page.findChild(QPlainTextEdit, "feedbackBox").setPlainText(text)
    page.findChild(QLineEdit, "studentTheme").setText(theme)
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
