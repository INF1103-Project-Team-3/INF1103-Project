"""ConsoleView: the only class that prints. Output is captured, not printed.

The result objects normally come from Logic and AI; ConsoleView reads every
field through _get(), so plain dictionaries stand in for them here.
"""
import pytest

from managers.io_manager.feedback_view import FeedbackView
from managers.models import FeedbackRecord


@pytest.fixture
def result():
    return {"themes": [
                {"theme": "Workload", "count": 14, "avg_sentiment": -0.71, "priority": 8.5,
                 "severity_counts": {"high": 4, "critical": 2}},
                {"theme": "Teaching Quality", "count": 6, "avg_sentiment": 0.5, "priority": 2.0,
                 "severity_counts": {}}],
            "total_entries": 31, "counted_entries": 29, "unverified_count": 2,
            "pending_themes": {"Parking Fees": 3}}


@pytest.fixture
def trend():
    return {"has_previous": True, "previous_run": {"run_at": "2026-10-01T08:00:00"},
            "headline": {"total_entries": {"text": "31 (+6)"},
                         "negative_percent": {"text": "58% (+4)"}},
            "themes": [{"theme": "Workload", "status": "Getting worse",
                        "count": {"text": "14 (+5)"}, "priority": {"text": "8.5 (+2.1)"}}]}


def test_console_view_implements_the_feedback_view_interface(screen):
    assert isinstance(screen.view, FeedbackView)


def test_every_message_starts_with_a_blank_line(screen):
    screen.view.show_message("Hello")
    assert screen.lines == ["", "Hello"]


def test_rejected_rows_are_listed_with_their_reason(screen):
    screen.view.show_rejected_rows([])
    assert screen.lines == []                   # nothing rejected, nothing shown
    screen.view.show_rejected_rows([(2, "missing field(s): text")])
    assert "  Row 2: missing field(s): text" in screen.lines


def test_empty_dashboard_says_so_without_column_headings(screen):
    screen.view.show_dashboard(None, None, None, [])
    assert "No aggregated data yet." in screen.lines
    assert "Nothing waiting for review." in screen.lines
    assert "REASON" not in screen.text


def test_dashboard_shows_counts_themes_and_pending_themes(screen, result):
    screen.view.show_dashboard(result, None, None, [])
    assert "entries: 31" in screen.text and "counted: 29" in screen.text
    assert "2 record(s) unverified" in screen.text
    assert any(line.startswith("Workload") and "8.5" in line for line in screen.lines)
    assert "  Parking Fees (3 record(s))" in screen.lines


def test_dashboard_with_a_previous_run_shows_the_merged_trend_table(screen, result, trend):
    screen.view.show_dashboard(result, trend, None, [])
    assert "Trend vs previous run (2026-10-01 08:00:00)" in screen.lines
    assert any("Getting worse" in line and "14 (+5)" in line for line in screen.lines)
    # a theme with no previous figures still appears, with "-" for its status
    assert any(line.startswith("Teaching Quality") and " - " in line for line in screen.lines)


def test_summary_and_suggested_actions_skip_the_unclear_theme(screen, result):
    summary = {"overall_summary": "Workload is up. Wifi is better.",
               "created_at": "2026-10-08T08:05:00",
               "theme_actions": [{"theme": "Workload", "suggested_action": "Spread deadlines."},
                                 {"theme": "Unclear", "suggested_action": "Nothing useful."}]}
    screen.view.show_dashboard(result, None, summary, [])
    assert "OVERALL (summary from 2026-10-08 08:05:00)" in screen.lines
    assert "  - Workload is up." in screen.lines        # one bullet per sentence
    assert "Spread deadlines." in screen.text
    assert "Nothing useful." not in screen.text


@pytest.mark.parametrize("count, wording", [(1, "1 critical entry is in both"),
                                            (2, "2 critical entries are in both")])
def test_critical_count_uses_the_right_plural(screen, result, make_record, count, wording):
    queue = [make_record(f"fb_{n}", final=("Workload", "negative", "critical", "matched"),
                         reasons=["Critical severity"]) for n in range(count)]
    screen.view.show_dashboard(result, None, None, queue)
    assert wording in screen.text


def test_review_queue_has_column_headings_and_logics_reason(screen, result, make_record):
    queue = [make_record("fb_9c1e22ab", reasons=["Critical severity"])]
    screen.view.show_dashboard(result, None, None, queue)
    heading = next(line for line in screen.lines if line.startswith("ID"))
    assert ["ID", "THEME", "REASON", "FEEDBACK"] == heading.split()
    assert any(line.startswith("fb_9c1e22ab") and "Critical severity" in line
               for line in screen.lines)


def test_search_shows_the_ai_summary_when_there_is_one(screen, make_record):
    with_summary = FeedbackRecord.from_dict({
        "feedback_id": "fb_1", "text": "A very long complaint about the wifi ...",
        "timestamp": "2026-10-01T09:00:00", "user": {"theme": "Facilities"},
        "ai": {"theme": "Facilities", "sentiment": "negative", "severity": "high",
               "summary": "Wifi drops in the library"}})
    screen.view.show_search_results([with_summary, make_record("fb_2", text="Raw text only")])
    assert "Found 2 matching record(s):" in screen.lines
    assert "  Wifi drops in the library" in screen.lines
    assert "very long complaint" not in screen.text
    assert "  Raw text only" in screen.lines            # no summary: fall back to the text


@pytest.mark.parametrize("summary", [None, "", "   ", 123, ["a", "list"]])
def test_missing_blank_or_corrupt_summary_falls_back_to_the_text(screen, summary):
    # a saved record is restored without checks, so its summary may be anything
    record = FeedbackRecord.from_dict({
        "feedback_id": "fb_1", "text": "The student's own words", "timestamp": "2026-10-01T09:00:00",
        "user": {"theme": "Facilities"},
        "ai": {"theme": "Facilities", "sentiment": "negative", "severity": "high", "summary": summary}})
    screen.view.show_search_results([record])
    assert "  The student's own words" in screen.lines


def test_review_entry_before_logic_and_without_ai(screen, make_record):
    screen.view.show_review_entry(make_record("fb_7", reasons=["Theme differs from AI"]), 1, 3)
    assert "Review 1 of 3   ID: fb_7" in screen.lines
    assert "  AI      : no result (AI failed)" in screen.lines
    assert "  Final   : not checked yet" in screen.lines
    assert "  Flagged : Theme differs from AI" in screen.lines


def test_settings_lists_themes_marks_added_ones_and_shows_status(screen):
    screen.view.show_settings(["Workload", "Facilities", "Car Park"], ["Parking Fees"],
                              {"AI connection": "ready", "Last analysis run": "never"})
    assert "Known themes (3)" in screen.lines
    assert "  Workload" in screen.lines                  # a base theme, no marker
    assert "  Car Park   (added)" in screen.lines        # confirmed by an admin earlier
    assert "Added this session, saved when you finish:" in screen.lines
    assert "  Parking Fees" in screen.lines
    assert "SYSTEM STATUS (read only)" in screen.lines
    assert any(line.startswith("  AI connection") and line.endswith(": ready")
               for line in screen.lines)


def test_settings_without_new_themes_has_no_added_section(screen):
    screen.view.show_settings(["Workload"], [], {})
    assert "Added this session, saved when you finish:" not in screen.lines


def test_typographic_characters_are_replaced_for_old_terminals(screen, make_record):
    screen.view.show_search_results([make_record(text="It’s slow — again")])
    assert "  It's slow - again" in screen.lines
