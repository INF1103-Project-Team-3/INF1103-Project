# MainWindow: what stays queued across a run, the Process button, login, imports and run messages.

import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QPushButton  # noqa: E402

from managers.gui import MainWindow, QtProgressReporter  # noqa: E402
from managers.gui.pages.add_feedback_page import AddFeedbackPage  # noqa: E402
from managers.gui.pages.feedback_page import FeedbackPage  # noqa: E402
from managers.gui.pages.start_page import StartPage  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EntryDetailPanel  # noqa: E402
from managers.io_manager import (  # noqa: E402
    EntryValidator, ImportResult, PasswordValidator, RecordBuilder, ThemeValidator,
)
from managers.logic_manager import LogicManager  # noqa: E402
from tests.gui.support.fake_data_manager import FakeDataManager  # noqa: E402
from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from tests.gui.support.stub_pipeline import StubPipeline  # noqa: E402


class BlockingPipeline(StubPipeline):
    """Holds each run until release is set, so the test can act while it is going."""

    def __init__(self, context=None):
        super().__init__(context)
        self.release = threading.Event()

    def execute_pipeline(self, session):
        self.release.wait(5)
        return super().execute_pipeline(session)


def button(widget, text):
    return [b for b in widget.findChildren(QPushButton) if b.text() == text][0]


def make_window(qtbot, pipeline=None, password=None):
    data = FakeDataManager(build_sample_records())
    logic = LogicManager()
    window = MainWindow(pipeline or StubPipeline(), data, logic, EntryValidator(ThemeValidator(logic)), [],
                        QtProgressReporter(), password=password)
    qtbot.addWidget(window)
    window.show_page("Feedback")
    page = window.findChild(FeedbackPage)
    return window, page, page.findChild(EntryDetailPanel)


def wait_for_run(qtbot, window):
    qtbot.waitUntil(lambda: window._MainWindow__worker is None, timeout=3000)


def new_entry(text="Lab is cold"):
    return RecordBuilder().build({"text": text, "theme": "Facilities", "sentiment": "negative", "severity": "low"})


# G1: decisions, actions and themes queued while a run is going are kept for the next run
def test_work_queued_during_a_run_is_kept_when_it_ends(qtbot):
    pipeline = BlockingPipeline()
    window, page, panel = make_window(qtbot, pipeline)
    first = panel.record.feedback_id
    button(panel, "Use student's").click()
    assert window.run_pipeline(show_progress=False)

    second = panel.record.feedback_id
    button(panel, "Use student's").click()
    action = RecordBuilder().build_action("Facilities", "Fixed the heating", "2026-11-15")
    window._MainWindow__on_action_logged(action)
    window._MainWindow__queue_theme("Parking Fees")
    pipeline.release.set()
    wait_for_run(qtbot, window)

    assert [d.feedback_id for d in pipeline.sessions[0].decisions] == [first]
    session = window._MainWindow__build_session()
    assert [d.feedback_id for d in session.decisions] == [second]
    assert session.actions == [action]
    assert session.themes_to_add == ["Parking Fees"]


def test_work_sent_in_a_run_is_cleared_when_it_ends(qtbot):
    window, page, panel = make_window(qtbot)
    button(panel, "Use student's").click()
    window._MainWindow__queue_theme("Parking Fees")
    window.run_pipeline(show_progress=False)
    wait_for_run(qtbot, window)
    session = window._MainWindow__build_session()
    assert (session.decisions, session.actions, session.themes_to_add) == ([], [], [])


# G7: importing the same entries twice before Process reports what was really added
def test_importing_the_same_entries_twice_reports_none_added(qtbot):
    window, *_ = make_window(qtbot)
    records = [new_entry("Lab is cold"), new_entry("Wifi drops")]
    window._MainWindow__on_import(ImportResult("week6.csv", records))
    assert "2 entries from week6.csv queued" in window.statusBar().currentMessage()
    window._MainWindow__on_import(ImportResult("week6.csv", records))
    assert "0 entries from week6.csv queued (2 already queued)" in window.statusBar().currentMessage()
    assert len(window._MainWindow__build_session().records) == 2


# G8: the Process button counts entries and other changes apart
def process_text(window):
    add = window.findChild(AddFeedbackPage)
    return [b.text() for b in add.findChildren(QPushButton) if b.text().startswith(("Process", "Nothing"))][0]


@pytest.mark.parametrize("entries, decisions, themes, wording", [
    (1, 1, 0, "Process 1 entry, 1 change"),
    (2, 0, 0, "Process 2 entries"),
    (0, 1, 1, "Process 2 changes"),
    (0, 0, 0, "Nothing to process"),
])
def test_process_counts_entries_and_changes_apart(qtbot, entries, decisions, themes, wording):
    window, page, panel = make_window(qtbot)
    add = window.findChild(AddFeedbackPage)
    add._AddFeedbackPage__waiting = lambda: (set(), set())     # nothing saved is waiting for the AI
    for n in range(entries):
        window._MainWindow__queue_record(new_entry(f"Lab is cold {n}"))
    for _ in range(decisions):
        button(panel, "Use student's").click()
    for _ in range(themes):
        window._MainWindow__queue_theme("Parking Fees")
    add.refresh()
    assert process_text(window) == wording


# G9: with no admin password, the login says it is turned off, like the terminal
def test_login_is_disabled_without_an_admin_password(qtbot):
    window, *_ = make_window(qtbot, password=None)
    start = window.findChild(StartPage)
    start.show_login()
    assert not start.findChild(QLineEdit, "passwordBox").isEnabled()
    assert not button(start, "Log in").isEnabled()
    texts = [label.text() for label in start.findChildren(QLabel) if label.isVisibleTo(start)]
    assert "Admin login is disabled: no admin password is configured." in texts


def test_login_works_with_a_password(qtbot):
    window, *_ = make_window(qtbot, password=PasswordValidator("pw"))
    start = window.findChild(StartPage)
    start.show_login()
    assert start.findChild(QLineEdit, "passwordBox").isEnabled()
    window._MainWindow__on_login("pw")
    assert window._MainWindow__screens.currentWidget() is window._MainWindow__admin


# G10: the progress log says when the AI stopped during the run
def test_run_end_says_the_ai_stopped(qtbot):
    context = SimpleNamespace(records=[], halted=False, ai_stopped=True, sent_to_ai=3, classified_count=1)
    window, *_ = make_window(qtbot, StubPipeline(context))
    window.run_pipeline(show_progress=False)
    wait_for_run(qtbot, window)
    log = window.findChild(AddFeedbackPage).progress_panel.findChild(QPlainTextEdit).toPlainText()
    assert "Run finished, but the AI stopped: 2 entries left for the next run." in log


def test_run_end_says_finished_when_the_ai_did_not_stop(qtbot):
    window, *_ = make_window(qtbot)
    window.run_pipeline(show_progress=False)
    wait_for_run(qtbot, window)
    log = window.findChild(AddFeedbackPage).progress_panel.findChild(QPlainTextEdit).toPlainText()
    assert "Run finished." in log and "AI stopped" not in log


# G15: closing while a run is going is refused, and the run still finishes
def test_closing_during_a_run_is_refused(qtbot, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: told.append(args[1]))
    pipeline = BlockingPipeline()
    window, *_ = make_window(qtbot, pipeline)
    window.run_pipeline(show_progress=False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and told == ["Run in progress"]
    pipeline.release.set()
    wait_for_run(qtbot, window)
    assert len(pipeline.sessions) == 1


def test_a_wrong_password_shows_the_error(qtbot):
    window, *_ = make_window(qtbot, password=PasswordValidator("pw"))
    start = window.findChild(StartPage)
    start.show_login()
    window._MainWindow__on_login("nope")
    assert window._MainWindow__screens.currentWidget() is start
    assert start.findChild(QLabel, "errorText").isVisibleTo(start)
