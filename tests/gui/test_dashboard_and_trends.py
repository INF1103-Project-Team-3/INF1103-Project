# Dashboard, Trends page, chart gaps and the Confirm new theme button, on real Data in a temp folder.

from datetime import date

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402

from demo.interim_pipeline import InterimPipeline  # noqa: E402
from demo.sample_data import build_sample_records  # noqa: E402
from managers.data_manager import DataManager  # noqa: E402
from managers.gui.data_reader import DataReader  # noqa: E402
from managers.gui.pages.dashboard_page import DashboardPage  # noqa: E402
from managers.gui.pages.trends_page import TrendsPage  # noqa: E402
from managers.gui.widgets.entry_detail_panel import EntryDetailPanel  # noqa: E402
from managers.gui.widgets.sparkline import Sparkline  # noqa: E402
from managers.gui.widgets.trend_chart import TrendChart  # noqa: E402
from managers.io_manager import RecordBuilder, ReviewDecision, SessionResult  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import THEMES  # noqa: E402


def entry(text, theme="Facilities", sentiment="negative", severity="medium"):
    return RecordBuilder().build({"text": text, "theme": theme, "sentiment": sentiment, "severity": severity})


def labels(widget):
    return " ".join(label.text() for label in widget.findChildren(QLabel))


# Two AI-down runs: Facilities in both, Parking Fees (a new theme) confirmed in the second.
@pytest.fixture
def reader(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    logic = LogicManager()
    parking = entry("Parking costs too much", theme="Parking Fees")
    InterimPipeline(data, logic, today=lambda: date(2026, 11, 1)).execute_pipeline(
        SessionResult(records=[entry("Wifi drops"), parking]))
    InterimPipeline(data, logic, today=lambda: date(2026, 11, 8)).execute_pipeline(
        SessionResult(records=[entry("Lab is cold", severity="high")],
                      decisions=[ReviewDecision.update(parking.feedback_id, parking.user)]))
    return DataReader(data)


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
    assert "AI unavailable for 2 entries" in text
    assert "Compared with the run on" in text
    assert "Facilities" in text and "Parking Fees" in text
    assert "No AI summary yet" in text


def test_confirm_new_theme_builds_an_update_that_keeps_the_theme(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    record = [r for r in build_sample_records() if any(x.startswith("New theme") for x in r.review_reasons)][0]
    panel = EntryDetailPanel()
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
    panel = EntryDetailPanel()
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
