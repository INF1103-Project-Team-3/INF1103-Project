# Fixes from the live GUI check of 2026-11-16 (GUI-A to GUI-F).

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QLabel, QPlainTextEdit, QPushButton, QStyle, QStyleOptionComboBox,
)

from managers.ai_manager import AIManager  # noqa: E402
from managers.gui import MainWindow, QtProgressReporter  # noqa: E402
from managers.gui.dialogs.log_action_dialog import LogActionDialog  # noqa: E402
from managers.gui.pages.add_feedback_page import AddFeedbackPage  # noqa: E402
from managers.gui.pages.dashboard_page import DashboardPage  # noqa: E402
from managers.gui.pages.feedback_page import FeedbackPage  # noqa: E402
from managers.gui.pages.student_form_page import StudentFormPage  # noqa: E402
from managers.gui.progress_signals import ProgressSignals  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EntryDetailPanel  # noqa: E402
from managers.gui.widgets.import_panel import ImportPanel  # noqa: E402
from managers.gui.widgets.option_card import OptionCard  # noqa: E402
from managers.gui.widgets.progress_panel import ProgressPanel  # noqa: E402
from managers.io_manager import (  # noqa: E402
    EntryValidator, RecordBuilder, ReviewDecision, ThemeValidator,
)
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import THEMES  # noqa: E402
from tests.gui.support.fake_data_manager import FakeDataManager  # noqa: E402
from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from tests.gui.support.stub_pipeline import StubPipeline  # noqa: E402


def labels(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def make_window(qtbot, width=1280, height=800):
    logic = LogicManager()
    window = MainWindow(StubPipeline(), FakeDataManager(build_sample_records()), logic,
                        EntryValidator(ThemeValidator(logic)), [], QtProgressReporter())
    qtbot.addWidget(window)
    window.setWindowState(Qt.WindowState.WindowNoState)
    window.resize(width, height)
    return window


def new_entry(text="Lab is cold"):
    return RecordBuilder().build({"text": text, "theme": "Facilities", "sentiment": "negative", "severity": "low"})


# GUI-A: a long "waiting for the AI" line wraps instead of pushing Process out of the window
def test_add_feedback_fits_the_window_with_a_long_status_line(qtbot):
    window = make_window(qtbot)
    window.show_admin()
    window.show()
    qtbot.waitExposed(window)
    add = window.findChild(AddFeedbackPage)
    add._AddFeedbackPage__waiting = lambda: (set(), {f"fb_{n}" for n in range(7)})
    window._MainWindow__queue_record(new_entry())
    window._MainWindow__queue_theme("Parking Fees")
    window.show_page("Add feedback")
    QApplication.processEvents()
    process = [b for b in add.findChildren(QPushButton) if b.text().startswith("Process")][0]
    assert "7 unverified" in labels(add) and "queued in this session" in labels(add)
    assert process.mapTo(window, process.rect().topRight()).x() <= window.width()


# GUI-B: every base theme shows in full in the review panel's Final theme box
def test_final_theme_box_shows_the_longest_theme_in_full(qtbot):
    window = make_window(qtbot)
    window.show_admin()
    window.show_page("Feedback")
    window.show()
    qtbot.waitExposed(window)
    panel = window.findChild(FeedbackPage).findChild(EntryDetailPanel)
    box = panel._EntryDetailPanel__theme_box
    for theme in THEMES:
        box.setCurrentIndex(box.findText(theme))
        QApplication.processEvents()
        option = QStyleOptionComboBox()
        box.initStyleOption(option)
        field = box.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                           QStyle.SubControl.SC_ComboBoxEditField, box)
        assert field.width() >= box.fontMetrics().horizontalAdvance(theme), theme
    assert box.mapTo(window, box.rect().topRight()).x() <= window.width()     # and it still fits


def test_feedback_page_still_fits_after_a_decision_is_queued(qtbot):
    from PySide6.QtWidgets import QScrollArea
    window = make_window(qtbot)
    window.show_admin()
    window.show_page("Feedback")
    window.show()
    qtbot.waitExposed(window)
    window._MainWindow__on_decision(ReviewDecision.update(
        "st_005", {"theme": "Internship Placement", "sentiment": "negative", "severity": "critical"}))
    QApplication.processEvents()
    scroll = window.findChild(FeedbackPage).findChild(QScrollArea)
    assert scroll.widget().minimumSizeHint().width() <= scroll.viewport().width()


# GUI-C: the hint states D23's rule (7 days and 3 matching entries), not 14 days
def test_log_action_hint_matches_d23(qtbot):
    dialog = LogActionDialog(list(THEMES))
    qtbot.addWidget(dialog)
    hint = [text for text in labels(dialog).splitlines() if "Too early" in text][0]
    assert "7 days" in hint and "3 matching entries" in hint and "14 days" not in hint


# GUI-D: the subtitle counts entries queued in the session, uses the singular, and the
# AI notice says its number counts only the counted entries
def test_dashboard_subtitle_counts_queued_entries_and_singular(qtbot):
    page = DashboardPage(FakeDataManager(build_sample_records()))
    qtbot.addWidget(page)
    page.set_queued(2)
    page.show_values(None, None, None, [], records=[], pending=1)
    text = labels(page)
    assert "1 entry waiting for the AI" in text and "2 queued in this session" in text
    page.set_queued(0)
    page.show_values(None, None, None, [], records=[], pending=0)
    assert "Every entry has been processed" in labels(page)
    page.set_queued(1)
    page.show_values(None, None, None, [], records=[], pending=0)
    assert "Every entry has been processed" not in labels(page) and "1 queued in this session" in labels(page)


def test_main_window_tells_the_dashboard_what_is_queued(qtbot):
    window = make_window(qtbot)
    window._MainWindow__queue_record(new_entry())
    window.show_page("Dashboard")
    assert "1 queued in this session" in labels(window.findChild(DashboardPage))


# GUI-E: a theme a queued decision confirms is offered in the theme pickers until undone
def test_a_queued_confirmed_theme_is_offered_until_undone(qtbot):
    window = make_window(qtbot)
    window.show_admin()
    page = window.findChild(FeedbackPage)
    decision = ReviewDecision.update("fb_x", {"theme": "car park", "sentiment": "negative", "severity": "low"})
    window._MainWindow__on_decision(decision)
    window.show_page("Feedback")
    box = page.findChild(EntryDetailPanel)._EntryDetailPanel__theme_box
    assert box.findText("Car Park") != -1
    assert "Car Park" in window._MainWindow__themes()
    window._MainWindow__undo_decision("fb_x")
    window.show_page("Feedback")
    assert box.findText("Car Park") == -1


def test_a_queued_decision_with_a_known_theme_adds_nothing(qtbot):
    window = make_window(qtbot)
    known = window._MainWindow__themes()
    window._MainWindow__on_decision(
        ReviewDecision.update("fb_x", {"theme": "wifi", "sentiment": "negative", "severity": "low"}))
    assert window._MainWindow__themes() == known


# GUI-F: wording
def test_student_banner_has_a_colon_after_a_new_theme(qtbot):
    page = StudentFormPage(list(THEMES), EntryValidator(ThemeValidator(LogicManager())), RecordBuilder())
    qtbot.addWidget(page)
    page.findChild(QPlainTextEdit, "feedbackBox").setPlainText("Parking costs too much")
    page.theme_picker.type_other("car park")
    for card in page.findChildren(OptionCard):
        if card.value in ("negative", "low"):
            card.radio.setChecked(True)
    [b for b in page.findChildren(QPushButton) if b.text() == "Submit feedback"][0].click()
    assert '"car park": staff will sort it into a theme' in page.findChild(QLabel, "successText").text()


def test_import_summary_and_queued_line_say_one_row_and_one_entry(qtbot, tmp_path):
    from managers.data_manager import DataManager
    from managers.io_manager import IOManager
    data = DataManager(str(tmp_path / "data"))
    path = tmp_path / "one.csv"
    path.write_text("feedback_id,text,timestamp,theme,sentiment,severity\n"
                    "fb_1,Lab is cold,2026-11-10T09:00:00,Facilities,negative,low\n", encoding="utf-8")
    panel = ImportPanel(IOManager.create_importers(data, LogicManager()), data)
    qtbot.addWidget(panel)
    panel.load_file(str(path))
    assert "one.csv: 1 row ·" in labels(panel)
    [b for b in panel.findChildren(QPushButton) if b.text().startswith("Add 1")][0].click()
    assert "Queued 1 entry from one.csv." in labels(panel)


def test_progress_panel_wording_for_one_entry_and_the_summary(qtbot):
    signals = ProgressSignals()
    panel = ProgressPanel(signals)
    qtbot.addWidget(panel)
    signals.batch_started.emit("Classifying 1 records", 1)
    log = panel.findChild(type(panel._ProgressPanel__log))
    assert "(1 entry)" in log.toPlainText()
    signals.batch_started.emit(AIManager.SUMMARY_TITLE, 1)
    signals.batch_finished.emit(1, 0, 1, None, None)
    assert "Finished: summary written" in labels(panel)
    assert "classified" not in panel._ProgressPanel__title.text()
