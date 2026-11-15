# Settings: known themes, Add theme (checked like the terminal's) and the read-only status.

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton  # noqa: E402

from managers.gui.pages.settings_page import SettingsPage  # noqa: E402
from managers.io_manager import EntryValidator, ThemeValidator  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import THEMES  # noqa: E402
from tests.gui.support.fake_data_manager import FakeDataManager  # noqa: E402
from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from tests.gui.support.stub_pipeline import StubPipeline  # noqa: E402


def labels(widget) -> str:
    return " ".join(label.text() for label in widget.findChildren(QLabel))


def settings(qtbot, ai_ready=None):
    page = SettingsPage(FakeDataManager(build_sample_records()), ThemeValidator(LogicManager()), ai_ready)
    qtbot.addWidget(page)
    page.refresh()
    return page


def type_and_add(page, text):
    page.findChild(QLineEdit, "newThemeBox").setText(text)
    [b for b in page.findChildren(QPushButton) if b.text() == "Add theme"][0].click()


def test_lists_the_known_themes_and_the_status(qtbot):
    page = settings(qtbot, ai_ready=True)
    text = labels(page)
    assert all(theme in text for theme in THEMES)
    assert "AI connection" in text and "ready" in text
    assert "Processed records" in text and "Waiting for review" in text and "Tokens used today" in text


def test_a_new_theme_is_cleaned_up_and_emitted(qtbot):
    page = settings(qtbot)
    with qtbot.waitSignal(page.theme_added, timeout=1000) as blocker:
        type_and_add(page, "  parking fees ")
    assert blocker.args == ["Parking Fees"]


@pytest.mark.parametrize("typed, message", [("", "can't add it"), ("n/a", "isn't a usable"),
                                             ("FACILITIES", "already a known theme")])
def test_empty_unclear_or_known_themes_are_refused(qtbot, typed, message):
    page = settings(qtbot)
    with qtbot.assertNotEmitted(page.theme_added):
        type_and_add(page, typed)
    assert message in labels(page).lower()


def test_a_queued_theme_shows_and_cant_be_added_twice(qtbot):
    page = settings(qtbot)
    page.set_queued(["Parking Fees"])
    assert "Saved on the next run" in labels(page)
    with qtbot.assertNotEmitted(page.theme_added):
        type_and_add(page, "parking fees")


def test_main_window_queues_the_theme_in_the_session_and_enables_process(qtbot):
    from managers.gui import MainWindow, QtProgressReporter
    data = FakeDataManager(build_sample_records())
    logic = LogicManager()
    reporter = QtProgressReporter()
    window = MainWindow(StubPipeline(), data, logic, EntryValidator(ThemeValidator(logic)), [], reporter)
    qtbot.addWidget(window)
    type_and_add(window.findChild(SettingsPage), "Parking Fees")
    assert window._MainWindow__build_session().themes_to_add == ["Parking Fees"]
    process = [b for b in window.findChildren(QPushButton) if b.text().startswith("Process")][0]
    assert process.isEnabled()
