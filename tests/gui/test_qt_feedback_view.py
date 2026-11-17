# QtFeedbackView: each FeedbackView method switches to the right page and shows the given data.

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402

from tests.gui.support.fake_data_manager import FakeDataManager  # noqa: E402
from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from tests.gui.support.stub_pipeline import StubPipeline  # noqa: E402
from managers.gui import MainWindow, QtFeedbackView, QtProgressReporter  # noqa: E402
from managers.gui.pages.add_feedback_page import AddFeedbackPage  # noqa: E402
from managers.gui.pages.dashboard_page import DashboardPage  # noqa: E402
from managers.gui.pages.feedback_page import FeedbackPage  # noqa: E402
from managers.gui.widgets.entry_card import EntryCard  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EntryDetailPanel  # noqa: E402
from managers.gui.widgets.import_panel import ImportPanel  # noqa: E402
from managers.io_manager import EntryValidator, FeedbackView, ThemeValidator  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402


@pytest.fixture
def window(qtbot):
    data = FakeDataManager(build_sample_records())
    reporter = QtProgressReporter()
    logic = LogicManager()
    window = MainWindow(StubPipeline(), data, logic,
                        EntryValidator(ThemeValidator(logic)), [], reporter)
    qtbot.addWidget(window)
    window.data = data
    return window


def showing(window, page_type) -> bool:
    return not window.findChild(page_type).isHidden()


def labels(widget) -> str:
    return " ".join(label.text() for label in widget.findChildren(QLabel))


def test_view_is_a_feedback_view_exported_by_the_package(window):
    assert isinstance(window.view, QtFeedbackView) and isinstance(window.view, FeedbackView)


def test_show_message_uses_the_status_bar(window):
    window.view.show_message("Run finished")
    assert window.statusBar().currentMessage() == "Run finished"


def test_show_notice_opens_a_warning_without_blocking(window):
    window.view.show_notice("The AI is unavailable: entries keep the student's values.")
    assert window.view.notice_box.text() == "The AI is unavailable: entries keep the student's values."
    assert "AI is unavailable" in window.statusBar().currentMessage()


def test_show_dashboard_shows_the_given_results(window):
    records = window.data.load_records()
    queue = window.data.load_review_queue()
    result = LogicManager().aggregate(records)
    window.view.show_dashboard(result, None, None, queue)
    assert showing(window, DashboardPage)
    page = window.findChild(DashboardPage)
    text = labels(page)
    assert str(result.total_entries) in text and str(len(queue)) in text
    assert "First run: nothing to compare with yet." in text


def test_show_search_results_lists_exactly_those_records(window):
    found = window.data.load_records()[:2]
    window.view.show_search_results(found)
    assert showing(window, FeedbackPage)
    page = window.findChild(FeedbackPage)
    cards = [c for c in page.findChildren(EntryCard) if not c.isHidden()]
    assert len(cards) == 2
    assert [b for b in page.findChildren(QPushButton) if b.text().startswith("All feedback")][0].isChecked()
    assert window.statusBar().currentMessage() == "2 entries found"


def test_show_review_entry_selects_the_record_in_needs_review(window):
    record = window.data.load_review_queue()[1]
    window.view.show_review_entry(record, 2, 5)
    page = window.findChild(FeedbackPage)
    assert showing(window, FeedbackPage)
    assert page.findChild(EntryDetailPanel).record.feedback_id == record.feedback_id
    assert [b for b in page.findChildren(QPushButton) if b.text().startswith("Needs review")][0].isChecked()
    assert window.statusBar().currentMessage() == f"Reviewing 2 of 5: {record.feedback_id}"


def test_show_rejected_rows_lists_the_reasons_on_the_import_tab(window):
    window.view.show_rejected_rows([(3, "missing field(s): severity"), (7, "duplicate feedback_id 'x'")])
    assert showing(window, AddFeedbackPage)
    panel = window.findChild(ImportPanel)
    assert not panel.isHidden()
    text = labels(panel)
    assert "2 rows were rejected" in text
    assert "Row 3: missing field(s): severity" in text and "Row 7: duplicate feedback_id" in text


def test_show_settings_opens_the_settings_page_with_those_values(window):
    from managers.gui.pages.settings_page import SettingsPage
    window.view.show_settings(["Facilities", "Car Park"], ["Parking Fees"], {"AI connection": "ready"})
    assert showing(window, SettingsPage)
    text = labels(window.findChild(SettingsPage))
    assert "Car Park" in text and "Parking Fees" in text and "Saved on the next run" in text
    assert "AI connection" in text and "ready" in text

def test_main_window_opens_maximized(window):
    from PySide6.QtCore import Qt
    assert window.windowState() & Qt.WindowState.WindowMaximized
