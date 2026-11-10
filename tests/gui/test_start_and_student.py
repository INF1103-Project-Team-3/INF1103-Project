import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QPushButton  # noqa: E402

from managers.gui.pages.start_page import StartPage  # noqa: E402
from managers.gui.pages.student_form_page import StudentFormPage  # noqa: E402
from managers.gui.widgets.option_card import OptionCard  # noqa: E402
from managers.models import THEMES  # noqa: E402


def button(widget, text):
    return [b for b in widget.findChildren(QPushButton) if b.text() == text][0]


def test_login_sends_the_typed_password(qtbot):
    page = StartPage()
    qtbot.addWidget(page)
    page.show_login()
    page.findChild(QLineEdit, "passwordBox").setText("secret")
    with qtbot.waitSignal(page.login_requested, timeout=1000) as blocker:
        button(page, "Log in").click()
    assert blocker.args == ["secret"]


def test_incomplete_form_shows_problems_and_sends_nothing(qtbot):
    page = StudentFormPage(list(THEMES))
    qtbot.addWidget(page)
    with qtbot.assertNotEmitted(page.feedback_submitted):
        button(page, "Submit feedback").click()
    assert "words" in page.findChild(QLabel, "errorText").text()


def test_complete_form_builds_a_record(qtbot):
    page = StudentFormPage(list(THEMES))
    qtbot.addWidget(page)
    page.findChild(QPlainTextEdit, "feedbackBox").setPlainText("The library wifi keeps dropping")
    page.findChild(QLineEdit, "studentTheme").setText("facilities")
    for card in page.findChildren(OptionCard):
        if card.value in ("negative", "medium"):
            card.radio.setChecked(True)
    with qtbot.waitSignal(page.feedback_submitted, timeout=1000) as blocker:
        button(page, "Submit feedback").click()
    record = blocker.args[0]
    assert record.user == {"theme": "Facilities", "sentiment": "negative", "severity": "medium"}
    assert record.ai is None
