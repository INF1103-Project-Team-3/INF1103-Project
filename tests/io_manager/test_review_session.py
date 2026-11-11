"""ReviewSession: turns an admin's choices about flagged records into ReviewDecisions."""
import pytest

from managers.io_manager.review_decision import ReviewDecision
from managers.io_manager.review_session import ReviewSession
from managers.io_manager.theme_validator import ThemeValidator

AI = {"theme": "Assessment", "sentiment": "neutral", "severity": "low"}
CHECKED = ("Workload", "negative", "critical", "matched")     # final values set by Logic


@pytest.fixture
def review(prompter, screen, logic):
    def make(answers):
        return ReviewSession(screen.view, prompter(answers), ThemeValidator(logic, allow_blank=True))
    return make


def test_nothing_to_review(review, screen):
    assert review([]).run([]) == []
    assert "Nothing waiting for review." in screen.lines


def test_records_already_decided_this_session_are_skipped(review, make_record):
    queue = [make_record("fb_1"), make_record("fb_2")]
    assert review(["d", "y"]).run(queue, decided_ids={"fb_1"}) == [ReviewDecision.delete("fb_2")]


def test_update_keeps_logics_values_where_enter_is_pressed(review, make_record):
    record = make_record("fb_1", final=CHECKED, reasons=["Critical severity"])
    decisions = review(["u", "", "", "high"]).run([record])
    assert decisions == [ReviewDecision.update(
        "fb_1", {"theme": "Workload", "sentiment": "negative", "severity": "high"})]


def test_before_logic_runs_enter_keeps_the_writers_values(review, make_record):
    record = make_record("fb_1", user={"theme": "Facilities", "sentiment": "negative", "severity": "low"})
    assert review(["u", "", "", ""]).run([record])[0].severity == "low"


def test_a_typed_theme_is_normalised_by_logic(review, make_record):
    assert review(["u", "car park", "", ""]).run([make_record()])[0].theme == "Car Park"


def test_accept_ai_uses_the_ais_values(review, make_record):
    record = make_record("fb_1", ai=AI, reasons=["Theme differs from AI"])
    assert review(["a"]).run([record]) == [ReviewDecision.update("fb_1", AI)]


def test_accept_ai_is_not_offered_when_the_ai_failed(review, make_record, screen):
    decisions = review(["a", "s"]).run([make_record("fb_1")])
    assert decisions == []
    assert "  Invalid: enter one of: u, d, s" in screen.lines


@pytest.mark.parametrize("answer, expected", [("y", [ReviewDecision.delete("fb_1")]), ("n", [])])
def test_delete_must_be_confirmed(review, make_record, answer, expected):
    assert review(["d", answer]).run([make_record("fb_1")]) == expected


def test_quitting_keeps_the_decisions_made_so_far(review, make_record, screen):
    queue = [make_record("fb_1"), make_record("fb_2"), make_record("fb_3")]
    assert review(["d", "y", "quit"]).run(queue) == [ReviewDecision.delete("fb_1")]
    assert any("1 decision(s) recorded" in line for line in screen.lines)


def test_quitting_part_way_through_an_update_makes_no_decision(review, make_record, screen):
    assert review(["u", "", "quit"]).run([make_record()]) == []
    assert "Update cancelled." in screen.lines
