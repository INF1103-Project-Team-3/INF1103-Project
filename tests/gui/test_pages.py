import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QComboBox, QLabel, QPushButton  # noqa: E402

from tests.gui.support.fake_data_manager import FakeDataManager  # noqa: E402
from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from managers.gui.pages.base_page import BasePage  # noqa: E402
from managers.gui.pages.feedback_page import FeedbackPage  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EMPTY, EntryDetailPanel  # noqa: E402
from managers.io_manager import ReviewDecision  # noqa: E402


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


def flagged_panel(qtbot):
    record = [r for r in build_sample_records() if r.needs_review and r.ai is not None][0]
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    panel.show_record(record, ["Facilities", "Administration"])
    return record, panel


def click_for_decision(qtbot, panel, text):
    with qtbot.waitSignal(panel.decision_requested, timeout=1000) as blocker:
        button(panel, text).click()
    return blocker.args[0]


def test_use_students_builds_an_update_with_the_users_values(qtbot):
    record, panel = flagged_panel(qtbot)
    assert click_for_decision(qtbot, panel, "Use student's") == ReviewDecision.update(record.feedback_id, record.user)


def test_use_ais_builds_an_update_with_the_ais_values(qtbot):
    record, panel = flagged_panel(qtbot)
    assert click_for_decision(qtbot, panel, "Use AI's") == ReviewDecision.update(record.feedback_id, record.ai)


def test_save_builds_an_update_with_the_final_values(qtbot):
    record, panel = flagged_panel(qtbot)
    theme, sentiment, severity = panel.findChildren(QComboBox)
    theme.setCurrentText("Administration")
    sentiment.setCurrentText("neutral")
    severity.setCurrentText("low")
    decision = click_for_decision(qtbot, panel, "Save final labels")
    assert decision == ReviewDecision(record.feedback_id, ReviewDecision.UPDATE, "Administration", "neutral", "low")


def test_delete_builds_a_delete_after_confirming(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    record, panel = flagged_panel(qtbot)
    assert click_for_decision(qtbot, panel, "Delete") == ReviewDecision.delete(record.feedback_id)


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
    record = SimpleNamespace(needs_review=True, review_reasons=[
        "AI disagrees with the user on severity (user 'critical', AI 'high')", "Critical severity"])
    assert record_tags(record) == [("Critical", "critical"), ("AI disagrees", "warn")]


def test_each_logic_reason_gets_its_own_tag():
    from managers.gui.widgets.record_tags import reason_tag
    assert reason_tag("New theme 'Academic': confirm it or change it.") == ("New theme", "info")
    assert reason_tag("Unclear theme (user said 'n/a') - needs a theme assigned") == ("Unclear theme", "caution")
    assert reason_tag("Something new") == ("Something new", "warn")


def test_reason_is_shown_as_logic_wrote_it():
    from html import escape
    from managers.gui.widgets.record_tags import explain_reason
    reason = "AI disagrees with the user on theme (user 'Academic', AI 'Facilities')"
    assert explain_reason(reason) == "<b>AI disagrees:</b> " + escape(reason)


def test_sample_records_are_checked_by_the_real_logic():
    reasons = {reason for r in build_sample_records() for reason in r.review_reasons}
    assert "Critical severity" in reasons
    assert any(reason.startswith("New theme") for reason in reasons)


def sort_sample(name):
    from managers.gui.pages.feedback_page import FeedbackPage
    return FeedbackPage.sort_records(FakeDataManager(build_sample_records()).load_records(), name)


def test_sort_by_date_newest_and_oldest_first():
    newest = [r.timestamp for r in sort_sample("Newest first")]
    assert newest == sorted(newest, reverse=True)
    assert [r.timestamp for r in sort_sample("Oldest first")] == newest[::-1]


def test_sort_most_severe_first_puts_critical_on_top():
    from managers.models import SEVERITIES
    ranks = [SEVERITIES.index(r.current_labels["severity"]) for r in sort_sample("Most severe first")]
    assert ranks == sorted(ranks, reverse=True) and ranks[0] == SEVERITIES.index("critical")


def test_sort_by_theme_is_alphabetical():
    themes = [r.current_labels["theme"].lower() for r in sort_sample("Theme (A-Z)")]
    assert themes == sorted(themes)


def test_choosing_a_sort_reorders_the_list_and_selects_the_new_first_entry(qtbot):
    data = FakeDataManager(build_sample_records())
    page = FeedbackPage(data)
    qtbot.addWidget(page)
    page.refresh()
    page.set_sort("Oldest first")
    panel = page.findChild(EntryDetailPanel)
    queue = data.load_review_queue()
    assert panel.record.feedback_id == min(queue, key=lambda r: r.timestamp).feedback_id


def feedback_window(qtbot):
    from managers.gui import MainWindow, QtProgressReporter
    from managers.io_manager import EntryValidator, ThemeValidator
    from managers.logic_manager import LogicManager
    from tests.gui.support.stub_pipeline import StubPipeline
    data = FakeDataManager(build_sample_records())
    logic, reporter = LogicManager(), QtProgressReporter()
    window = MainWindow(StubPipeline(), data, logic, EntryValidator(ThemeValidator(logic)), [], reporter)
    qtbot.addWidget(window)
    page = window.findChild(FeedbackPage)
    window.show_page("Feedback")
    return window, page, page.findChild(EntryDetailPanel), data


def visible_tags(page):
    from managers.gui.widgets.entry_card import EntryCard
    return {c.feedback_id: c.queued_text for c in page.findChildren(EntryCard) if not c.isHidden()}


def test_a_decision_tags_the_card_and_opens_the_next_entry(qtbot):
    window, page, panel, data = feedback_window(qtbot)
    first = panel.record.feedback_id
    button(panel, "Use student's").click()
    assert visible_tags(page)[first].startswith("Will be saved as")
    assert panel.record.feedback_id != first


def test_delete_shows_will_be_deleted_and_undo_clears_it(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    window, page, panel, data = feedback_window(qtbot)
    first = panel.record.feedback_id
    button(panel, "Delete").click()
    assert visible_tags(page)[first] == "Will be deleted"
    page._FeedbackPage__select(first)
    assert "Will be deleted" in " ".join(l.text() for l in panel.findChildren(QLabel))
    assert not button(panel, "Use student's").isEnabled()
    button(panel, "Undo").click()
    assert visible_tags(page)[first] == "" and window._MainWindow__build_session().decisions == []
    assert button(panel, "Use student's").isEnabled()


def test_process_now_runs_the_queued_decision(qtbot):
    window, page, panel, data = feedback_window(qtbot)
    first = panel.record.feedback_id
    button(panel, "Use student's").click()
    page._FeedbackPage__select(first)
    with qtbot.waitSignal(page.process_requested, timeout=1000):
        button(panel, "Process now").click()
