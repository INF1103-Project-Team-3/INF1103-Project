import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QComboBox, QLabel, QPushButton  # noqa: E402

from demo.fake_data_manager import FakeDataManager  # noqa: E402
from demo.sample_data import build_sample_records  # noqa: E402
from managers.gui.pages.base_page import BasePage  # noqa: E402
from managers.gui.pages.feedback_page import FeedbackPage  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EMPTY, EntryDetailPanel  # noqa: E402


def button(widget, text):
    return [b for b in widget.findChildren(QPushButton) if b.text() == text][0]


def test_base_page_is_abstract(qtbot):
    with pytest.raises(TypeError):
        BasePage("Nothing")


def test_feedback_page_counts_flagged_records(qtbot):
    data = FakeDataManager(build_sample_records())
    page = FeedbackPage(data)
    qtbot.addWidget(page)
    page.refresh()
    assert page.review_count() == len(data.load_review_queue()) > 0


def test_detail_panel_shows_a_dash_while_ai_values_are_missing(qtbot):
    record = [r for r in build_sample_records() if r.ai is None][0]
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    panel.show_record(record, ["Facilities"])
    assert [label.text() for label in panel.findChildren(QLabel)].count(EMPTY) >= 3
    assert all(box.currentIndex() == -1 for box in panel.findChildren(QComboBox))
    assert not button(panel, "Use AI's").isEnabled()


def test_use_students_emits_an_update_with_the_users_values(qtbot):
    record = [r for r in build_sample_records() if r.needs_review][0]
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    panel.show_record(record, ["Facilities"])
    with qtbot.waitSignal(panel.decision_requested, timeout=1000) as blocker:
        button(panel, "Use student's").click()
    user = record.user
    assert blocker.args == [record.feedback_id, "update", (user["theme"], user["sentiment"], user["severity"])]


def test_sidebar_badge_and_ampersand(qtbot):
    from managers.gui.widgets.sidebar import Sidebar
    sidebar = Sidebar(["Feedback", "Trends & actions"])
    qtbot.addWidget(sidebar)
    sidebar.set_badge("Feedback", "5 to review")
    assert sidebar.badge("Feedback") == "5 to review"
    names = [label.text() for label in sidebar.findChildren(QLabel)]
    assert "Trends & actions" in names


def test_critical_reasons_come_first():
    from types import SimpleNamespace
    from managers.gui.widgets.record_tags import record_tags
    record = SimpleNamespace(needs_review=True, review_reasons=["Severity gap", "Critical (one side only)"])
    assert record_tags(record) == [("Critical", "critical"), ("Severity gap", "warn")]
