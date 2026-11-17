# Page and widget fixes: Feedback edits across a refresh, the log dialog's theme, dropdown wheel,
# text shown as written, progress lines, the Critical card, undated runs and chart colours.

import json

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPlainTextEdit  # noqa: E402

from managers.data_manager import DataManager  # noqa: E402
from managers.gui.data_reader import DataReader  # noqa: E402
from managers.gui.dialogs.log_action_dialog import LogActionDialog  # noqa: E402
from managers.gui.pages import trends_page  # noqa: E402
from managers.gui.pages.dashboard_page import DashboardPage  # noqa: E402
from managers.gui.pages.feedback_page import FeedbackPage  # noqa: E402
from managers.gui.pages.settings_page import SettingsPage  # noqa: E402
from managers.gui.pages.trends_page import TrendsPage  # noqa: E402
from managers.gui.progress_signals import ProgressSignals  # noqa: E402
from managers.gui.widgets.combo_box import ComboBox  # noqa: E402
from managers.gui.widgets.entry_card import EntryCard  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EntryDetailPanel  # noqa: E402
from managers.gui.widgets.progress_panel import ProgressPanel  # noqa: E402
from managers.gui.widgets.trend_chart import TrendChart  # noqa: E402
from managers.io_manager import RecordBuilder, ReviewDecision, SessionResult, ThemeValidator  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import CRITICAL, FeedbackRecord  # noqa: E402
from tests.gui.support.fake_data_manager import FakeDataManager  # noqa: E402
from tests.gui.support.real_pipeline import build_pipeline  # noqa: E402
from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from tests.gui.support.stub_ai import StubAI  # noqa: E402


def feedback_page(qtbot, records=None):
    page = FeedbackPage(FakeDataManager(records or build_sample_records()))
    qtbot.addWidget(page)
    page.refresh()
    return page, page.findChild(EntryDetailPanel)


# G2: a refresh keeps the selected entry and its unsaved Final values
def test_a_refresh_keeps_the_selected_entry_and_its_unsaved_edits(qtbot):
    page, panel = feedback_page(qtbot)
    second = list(page._FeedbackPage__cards)[1]
    page._FeedbackPage__on_card_clicked(second)
    _theme, sentiment, _severity = panel.findChildren(QComboBox)
    edited = next(s for s in ("positive", "neutral", "negative") if s != sentiment.currentText())
    sentiment.setCurrentText(edited)

    page.refresh()

    assert panel.record.feedback_id == second
    assert sentiment.currentText() == edited
    assert panel.has_unsaved_changes()


def test_a_refresh_without_edits_keeps_the_selected_entry(qtbot):
    page, panel = feedback_page(qtbot)
    second = list(page._FeedbackPage__cards)[1]
    page._FeedbackPage__on_card_clicked(second)
    page.refresh()
    assert panel.record.feedback_id == second and not panel.has_unsaved_changes()


# G13: a queued decision's values show in the Final column
def test_the_final_column_shows_the_queued_values(qtbot):
    page, panel = feedback_page(qtbot)
    record = panel.record
    decision = ReviewDecision(record.feedback_id, ReviewDecision.UPDATE, "Workload", "positive", "low")
    page.set_queued([decision])
    page._FeedbackPage__select(record.feedback_id)
    assert [box.currentText() for box in panel.findChildren(QComboBox)] == ["Workload", "positive", "low"]
    assert not panel.has_unsaved_changes()


# G3: the log dialog keeps a theme that is pending or only queued
def test_the_log_dialog_adds_a_theme_it_does_not_know(qtbot):
    dialog = LogActionDialog(["Facilities", "Workload"], theme="Parking Fees")
    qtbot.addWidget(dialog)
    assert dialog.findChild(QComboBox, "themeBox").currentText() == "Parking Fees"


def test_trends_offers_queued_themes_in_the_log_dialog(qtbot, monkeypatch):
    seen = {}

    class Capture:
        def __init__(self, themes, parent=None, theme=None, description=None):
            seen.update(themes=list(themes), theme=theme)

        def exec(self):
            return False

    monkeypatch.setattr(trends_page, "LogActionDialog", Capture)
    page = TrendsPage(FakeDataManager(build_sample_records()), LogicManager())
    qtbot.addWidget(page)
    page.set_queued_themes(["Parking Fees"])
    page.open_log_dialog("Parking Fees")
    assert "Parking Fees" in seen["themes"] and seen["theme"] == "Parking Fees"


# G4: the mouse wheel over a closed dropdown leaves its value alone
def test_the_wheel_does_not_change_a_closed_dropdown(qtbot):
    box = ComboBox()
    qtbot.addWidget(box)
    box.addItems(["negative", "neutral", "positive"])
    box.setCurrentIndex(0)
    box.show()
    wheel = QWheelEvent(QPointF(5, 5), QPointF(box.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
                        False)
    QApplication.sendEvent(box, wheel)
    assert box.currentIndex() == 0


# G6: feedback text and action descriptions show as written, never as rich text
TEXT = "I <3 the <b>library</b>"


def odd_record():
    return FeedbackRecord("fb_odd", TEXT, "2026-11-10T10:00:00", None,
                          {"theme": "Facilities", "sentiment": "positive", "severity": "low"})


def test_the_detail_panel_and_card_show_the_text_as_written(qtbot):
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    panel.show_record(odd_record(), ["Facilities"])
    assert panel.findChild(QLabel, "feedbackText").textFormat() == Qt.TextFormat.PlainText
    card = EntryCard(odd_record())
    qtbot.addWidget(card)
    assert card.findChild(QLabel, "entryText").textFormat() == Qt.TextFormat.PlainText


def test_the_ai_summary_line_shows_as_written(qtbot):
    record = odd_record()
    record.set_ai("Facilities", "positive", "low", "Student <3 the library")
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    panel.show_record(record, ["Facilities"])
    summary = [label for label in panel.findChildren(QLabel) if label.text().startswith("AI summary")][0]
    assert summary.textFormat() == Qt.TextFormat.PlainText


def test_an_action_description_shows_as_written(qtbot):
    action = RecordBuilder().build_action("Facilities", "Fixed <b>heating</b> <3", "2026-11-10")
    page = TrendsPage(FakeDataManager(build_sample_records(), actions=[action]), LogicManager())
    qtbot.addWidget(page)
    page.refresh()
    title = page.findChild(QLabel, "actionTitle")
    assert title.text() == action.description and title.textFormat() == Qt.TextFormat.PlainText


# G10: attempts show on the status line; sub-second waits are not logged
def test_the_progress_panel_shows_attempts_and_hides_short_waits(qtbot):
    signals = ProgressSignals()
    panel = ProgressPanel(signals)
    qtbot.addWidget(panel)
    signals.attempt_started.emit("fb_1", 2, 3)
    assert panel.findChild(QLabel, "statusLine").text() == "fb_1: attempt 2 of 3"
    signals.waiting.emit(0.5, "rate limit")
    signals.waiting.emit(4.0, "rate limit")
    log = panel.findChild(QPlainTextEdit).toPlainText()
    assert "waiting 0s" not in log and "waiting 4s (rate limit)" in log


# G11: the Critical card counts critical entries waiting for review, the same way every time
def test_the_critical_card_counts_the_queue_both_ways(qtbot):
    logic = LogicManager()
    waiting = RecordBuilder().build({"text": "Fire exit blocked", "theme": "Facilities",
                                     "sentiment": "negative", "severity": CRITICAL})
    reviewed = RecordBuilder().build({"text": "Gas smell in lab", "theme": "Facilities",
                                      "sentiment": "negative", "severity": CRITICAL})
    for record in (waiting, reviewed):
        record.set_ai("Facilities", "negative", CRITICAL, "Safety issue.")
    logic.apply_rules([waiting, reviewed])
    reviewed.mark_reviewed("Facilities", "negative", CRITICAL)
    data = FakeDataManager([waiting, reviewed])
    page = DashboardPage(data)
    qtbot.addWidget(page)
    card = page._DashboardPage__values["Critical"]

    page.refresh()
    assert card.text() == "1"
    page.show_values(data.load_result(), data.load_trend(), data.load_summary(), data.load_review_queue())
    assert card.text() == "1"


# G5: Settings says only what is known: a key is set
def test_settings_says_key_set_rather_than_ready(qtbot):
    page = SettingsPage(FakeDataManager(build_sample_records()), ThemeValidator(LogicManager()), True)
    qtbot.addWidget(page)
    assert page.status()["AI connection"] == "Key set"


# F9: the AI is also not ready when the key is set but GROQ_KEY_LABEL is missing (P2)
def test_settings_names_both_settings_when_the_ai_is_not_ready(qtbot):
    page = SettingsPage(FakeDataManager(build_sample_records()), ThemeValidator(LogicManager()), False)
    qtbot.addWidget(page)
    assert page.status()["AI connection"] == "not configured (no API key or key label)"


# G12: a hand-edited run with no date is skipped instead of crashing the Trends page
def test_an_undated_run_is_skipped(qtbot, tmp_path):
    data = DataManager(str(tmp_path / "data"))
    pipeline = build_pipeline(data, LogicManager(), StubAI())
    for text in ("Wifi drops", "Lab is cold", "Heating is off"):
        record = RecordBuilder().build({"text": text, "theme": "Facilities", "sentiment": "negative",
                                        "severity": "medium"})
        pipeline.execute_pipeline(SessionResult(records=[record]))
    data.save_action(RecordBuilder().build_action("Facilities", "Fixed the heating", "2026-11-10"))
    path = tmp_path / "data" / "aggregated_history.json"
    history = json.loads(path.read_text())
    history[1]["run_at"] = ""
    path.write_text(json.dumps(history))

    reader = DataReader(data)
    assert len(reader.load_history()) == 2 and len(reader.load_runs()) == 2
    page = TrendsPage(reader, LogicManager())
    qtbot.addWidget(page)
    page.refresh()


# G13: a theme keeps its chart colour when another theme is added
def test_a_theme_keeps_its_colour_when_a_theme_is_added(qtbot):
    chart = TrendChart()
    qtbot.addWidget(chart)
    chart.set_data(["Run 1"], {"Facilities": [10], "Workload": [20]})
    before = {name: chart.colour(name) for name in ("Facilities", "Workload")}
    chart.set_data(["Run 1"], {"Assessment": [5], "Facilities": [10], "Workload": [20]})
    assert {name: chart.colour(name) for name in ("Facilities", "Workload")} == before


# G13: text that turns bold (a chosen segment, the open page's name) has room for its bold width
def bold_width(widget):
    from PySide6.QtGui import QFont, QFontMetrics
    widget.ensurePolished()
    font = QFont(widget.font())
    font.setWeight(QFont.Weight.DemiBold)
    return QFontMetrics(font).horizontalAdvance(widget.text())


def test_segments_and_page_names_have_room_for_bold(qtbot):
    from PySide6.QtWidgets import QPushButton
    from managers.gui.style import STYLE
    from managers.gui.widgets.sidebar import Sidebar
    page, _panel = feedback_page(qtbot)
    page.setStyleSheet(STYLE)
    page.refresh()
    segments = [b for b in page.findChildren(QPushButton) if b.objectName() == "segment"]
    assert segments and all(b.minimumWidth() >= bold_width(b) + 32 for b in segments)
    sidebar = Sidebar(["Add feedback"])
    qtbot.addWidget(sidebar)
    sidebar.setStyleSheet(STYLE)
    sidebar.select("Add feedback")
    name = [label for label in sidebar.findChildren(QLabel) if label.text() == "Add feedback"][0]
    assert name.minimumWidth() >= bold_width(name)


def test_the_final_dropdowns_get_the_widest_column(qtbot):
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    assert all(box.minimumWidth() >= 170 for box in panel.findChildren(QComboBox))
