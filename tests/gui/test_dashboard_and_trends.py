# Dashboard, Trends page, chart gaps and the Confirm new theme button, on real Data and the
# real pipeline in a temp folder (with a stub AI).

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402

from tests.gui.support.sample_data import build_sample_records  # noqa: E402
from managers.data_manager import DataManager  # noqa: E402
from managers.gui.data_reader import DataReader  # noqa: E402
from managers.gui.pages.dashboard_page import DashboardPage  # noqa: E402
from managers.gui.pages.trends_page import TrendsPage  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EntryDetailPanel  # noqa: E402
from managers.gui.widgets.sparkline import Sparkline  # noqa: E402
from managers.gui.widgets.trend_chart import TrendChart  # noqa: E402
from managers.gui.widgets.combo_box import ComboBox  # noqa: E402
from managers.io_manager import RecordBuilder, ReviewDecision, SessionResult  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import THEMES  # noqa: E402
from tests.gui.support.real_pipeline import build_pipeline  # noqa: E402
from tests.gui.support.stub_ai import StubAI  # noqa: E402


def entry(text, theme="Facilities", sentiment="negative", severity="medium"):
    return RecordBuilder().build({"text": text, "theme": theme, "sentiment": sentiment, "severity": severity})


def labels(widget):
    return " ".join(label.text() for label in widget.findChildren(QLabel))


# Run 1 with the AI working (summary written), run 2 with it down (one unverified entry and
# rule-based actions); Parking Fees, a new theme, is confirmed in run 2.
@pytest.fixture
def data(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    logic = LogicManager()
    parking = entry("Parking costs too much", theme="Parking Fees")
    build_pipeline(data, logic, StubAI()).execute_pipeline(SessionResult(records=[entry("Wifi drops"), parking]))
    build_pipeline(data, logic, StubAI(down=True)).execute_pipeline(
        SessionResult(records=[entry("Lab is cold", severity="high")],
                      decisions=[ReviewDecision.update(parking.feedback_id, parking.user)]))
    return data


# The pages read the two runs through DataReader.
@pytest.fixture
def reader(data):
    return DataReader(data)


# With the AI back, an empty Process retries the unverified entry (D4) and keeps every entry (#89, #94).
def test_a_run_after_the_ai_was_down_retries_the_unverified_entry(qtbot, data):
    build_pipeline(data, LogicManager(), StubAI()).execute_pipeline(SessionResult())
    reader = DataReader(data)
    assert len(reader.load_records()) == 3 and not reader.load_pending()
    assert len(reader.load_history()) == 3 and reader.load_result().unverified_count == 0
    page = DashboardPage(reader)
    qtbot.addWidget(page)
    page.refresh()
    assert "unverified." not in labels(page)


def test_trend_chart_breaks_the_line_at_a_missing_run(qtbot):
    chart = TrendChart()
    qtbot.addWidget(chart)
    chart.set_data(["Run 1", "Run 2", "Run 3", "Run 4"], {"Parking Fees": [None, 40, None, 55]}, top=100)
    assert chart.segments("Parking Fees") == [[(1, 40)], [(3, 55)]]


def test_sparkline_leaves_a_gap_instead_of_zero(qtbot):
    spark = Sparkline()
    qtbot.addWidget(spark)
    spark.set_values([None, None, 30, 45, None])
    assert spark.segments() == [[(2, 30), (3, 45)]]


def test_history_rows_carry_priority_and_skip_themes_without_entries(reader):
    first, second = reader.load_history()
    assert "Parking Fees" not in first["theme_priority"]
    assert "Parking Fees" in second["theme_priority"] and "Facilities" in second["theme_priority"]


def test_trends_page_plots_priority_with_a_gap_for_a_new_theme(qtbot, reader):
    page = TrendsPage(reader, LogicManager())
    qtbot.addWidget(page)
    page.refresh()
    assert page.chart.segments("Parking Fees") == [[(1, reader.load_history()[1]["theme_priority"]["Parking Fees"])]]
    page.compare(1, 2)
    assert "Parking Fees · new" in labels(page)


def test_dashboard_shows_the_ai_notice_strip_and_themes(qtbot, reader):
    page = DashboardPage(reader)
    qtbot.addWidget(page)
    page.refresh()
    text = labels(page)
    assert "so 1 counted entry is unverified" in text
    assert "Compared with the run on" in text
    assert "Facilities" in text and "Parking Fees" in text
    assert "All fine." not in text and "summary and suggested actions are on Trends" in text


def test_confirm_new_theme_builds_an_update_that_keeps_the_theme(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    record = [r for r in build_sample_records() if any(x.startswith("New theme") for x in r.review_reasons)][0]
    panel = EntryDetailPanel(LogicManager().is_new_theme)
    qtbot.addWidget(panel)
    panel.show_record(record, list(THEMES))
    confirm = [b for b in panel.findChildren(QPushButton) if b.text().startswith("Confirm new theme")][0]
    assert confirm.isVisibleTo(panel) and record.theme in confirm.text()
    with qtbot.waitSignal(panel.decision_requested, timeout=1000) as blocker:
        confirm.click()
    assert blocker.args[0] == ReviewDecision.update(record.feedback_id, {**record.current_labels,
                                                                          "theme": record.theme})


def test_confirm_button_is_hidden_without_a_new_theme(qtbot):
    record = [r for r in build_sample_records() if r.review_reasons
              and not any(x.startswith("New theme") for x in r.review_reasons)][0]
    panel = EntryDetailPanel(LogicManager().is_new_theme)
    qtbot.addWidget(panel)
    panel.show_record(record, list(THEMES))
    confirm = [b for b in panel.findChildren(QPushButton) if b.text().startswith("Confirm new theme")][0]
    assert not confirm.isVisibleTo(panel)


# G14: Logic decides whether the theme is new; a theme confirmed since is not offered again
def test_confirm_button_asks_logic_not_the_reason_text(qtbot):
    record = [r for r in build_sample_records() if any(x.startswith("New theme") for x in r.review_reasons)][0]
    panel = EntryDetailPanel(LogicManager(known_themes=[*THEMES, record.theme]).is_new_theme)
    qtbot.addWidget(panel)
    panel.show_record(record, list(THEMES))
    confirm = [b for b in panel.findChildren(QPushButton) if b.text().startswith("Confirm new theme")][0]
    assert not confirm.isVisibleTo(panel)


def test_cards_and_detail_show_the_ai_summary_when_there_is_one(qtbot):
    from managers.gui.widgets.entry_card import EntryCard
    record = entry("The wifi in the library basement keeps dropping during quizzes")
    record.set_ai("Facilities", "negative", "medium", "Basement wifi drops during quizzes")
    card = EntryCard(record)
    qtbot.addWidget(card)
    assert "Basement wifi drops during quizzes" in labels(card)
    panel = EntryDetailPanel()
    qtbot.addWidget(panel)
    panel.show_record(record, list(THEMES))
    assert "AI summary: Basement wifi drops during quizzes" in labels(panel)
    assert record.text in labels(panel)


def test_summary_card_shows_rule_based_actions_with_their_label(qtbot, reader):
    from managers.logic_manager import ActionSuggestions
    page = TrendsPage(reader)
    qtbot.addWidget(page)
    page.refresh()
    text = labels(page)
    assert ActionSuggestions.LABEL in text and "All fine." in text and "Keep going" not in text
    assert [b for b in page.findChildren(QPushButton) if b.text() == "Log this action"]


def test_summary_card_shows_the_ais_actions_after_a_fresh_summary(qtbot, tmp_path):
    from managers.ai_manager import AISummary
    from managers.logic_manager import ActionSuggestions
    data = DataManager(str(tmp_path / "data"))
    data.save_object("summary", AISummary("Wifi is the main issue.",
                                          [{"theme": "Facilities", "suggested_action": "Fix the library wifi"}]))
    data.save_object("fallback_actions", [])
    page = TrendsPage(DataReader(data))
    qtbot.addWidget(page)
    page.refresh()
    text = labels(page)
    assert "Wifi is the main issue." in text and "Fix the library wifi" in text
    assert ActionSuggestions.LABEL not in text


def test_log_this_action_opens_the_log_dialog_prefilled_with_the_suggestion(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLineEdit
    from managers.ai_manager import AISummary
    from managers.gui.dialogs.log_action_dialog import LogActionDialog
    opened = []
    monkeypatch.setattr(TrendsPage, "open_log_dialog", lambda self, theme=None, description=None:
                        opened.append((theme, description)))
    data = DataManager(str(tmp_path / "data"))
    data.save_object("summary", AISummary("Summary.", [{"theme": "Facilities", "suggested_action": "Fix the wifi"}]))
    page = TrendsPage(DataReader(data))
    qtbot.addWidget(page)
    page.refresh()
    [b for b in page.findChildren(QPushButton) if b.text() == "Log this action"][0].click()
    assert opened == [("Facilities", "Fix the wifi")]
    dialog = LogActionDialog(list(THEMES), theme="Facilities", description="Fix the wifi")
    qtbot.addWidget(dialog)
    assert dialog.findChild(QLineEdit, "descriptionEdit").text() == "Fix the wifi"

def test_summary_card_without_an_ai_summary_shows_rule_based_actions_below(qtbot, tmp_path):
    from managers.logic_manager import ActionSuggestions
    data = DataManager(str(tmp_path / "data"))
    data.save_object("fallback_actions", ActionSuggestions([{"theme": "Workload", "suggested_action": "Space out deadlines"}]))
    page = TrendsPage(DataReader(data))
    qtbot.addWidget(page)
    page.refresh()
    text = labels(page)
    assert "No AI summary yet" in text and ActionSuggestions.LABEL in text and "Space out deadlines" in text


# 25 flat runs, like many test runs with little new feedback.
def many_runs(count=25):
    from tests.gui.support.fake_data_manager import FakeDataManager
    history = [{"run": i + 1, "finished_at": f"2026-10-{i + 1:02d}", "theme_counts": {"Facilities": 3},
                "theme_priority": {"Facilities": 50}} for i in range(count)]
    return FakeDataManager([], history=history)


def test_trends_shows_the_last_10_runs_by_default_and_all_on_request(qtbot):
    page = TrendsPage(many_runs())
    qtbot.addWidget(page)
    page.refresh()
    assert page.chart.segments("Facilities") == [[(i, 50) for i in range(10)]]
    page.findChild(ComboBox, "runSpan").setCurrentText("All runs")
    assert len(page.chart.segments("Facilities")[0]) == 25
    assert page.findChild(ComboBox, "compareFrom").count() == 25


def test_trend_chart_skips_x_labels_that_would_overlap(qtbot):
    chart = TrendChart()
    qtbot.addWidget(chart)
    chart.resize(700, 320)
    chart.set_data([f"14 Nov · Run {i}" for i in range(1, 26)], {"Facilities": [50] * 25}, top=100)
    shown = chart.label_indices()
    assert shown[0] == 0 and shown[-1] == 24 and len(shown) < 25
    chart.resize(2000, 320)
    chart.set_data(["Run 1", "Run 2", "Run 3"], {"Facilities": [1, 2, 3]}, top=100)
    assert chart.label_indices() == [0, 1, 2]


def dashboard(qtbot, reader, ai_ready):
    page = DashboardPage(reader, ai_ready)
    qtbot.addWidget(page)
    page.refresh()
    return page


# The AI notice says whether the AI is back (with Process now) or still down.
def test_the_ai_notice_offers_process_now_once_the_ai_is_back(qtbot, reader):
    page = dashboard(qtbot, reader, ai_ready=True)
    assert "The AI was unavailable on the last run, so 1 counted entry is unverified" in labels(page)
    process = [b for b in page.findChildren(QPushButton) if b.text() == "Process now"][0]
    assert process.isVisibleTo(page)
    with qtbot.waitSignal(page.run_requested, timeout=1000):
        process.click()


def test_the_ai_notice_says_the_ai_is_down_without_a_button(qtbot, reader):
    page = dashboard(qtbot, reader, ai_ready=False)
    assert "The AI is unavailable, so 1 counted entry is unverified" in labels(page)
    assert not [b for b in page.findChildren(QPushButton) if b.text() == "Process now"][0].isVisibleTo(page)
