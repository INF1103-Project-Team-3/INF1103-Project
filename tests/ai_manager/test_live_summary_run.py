"""Offline tests for live_summary_run.py: its record builders and checks, with a stub client."""

import json

import pytest
import requests

from in_memory_token_log import InMemoryTokenLog
from live_summary_run import NAMES, OUTAGE_EVERY, LiveSummaryRun
from managers.ai_manager import AIManager, PromptLibrary
from managers.ai_manager import ai_manager as ai_manager_module
from managers.ai_manager.summary_task import SummaryTask
from managers.logic_manager import LogicManager
from recording_progress_reporter import RecordingProgressReporter
from stub_llm_client import StubLLMClient
from usage_recorder import UsageRecorder

PAYLOAD = {
    "total_entries": 25, "counted_entries": 21,
    "themes": [
        {"theme": "Well-being", "avg_sentiment": -1.0, "severity_counts": {"low": 0, "medium": 0, "high": 1, "critical": 1}},
        {"theme": "Facilities", "avg_sentiment": 0.0, "severity_counts": {"low": 2, "medium": 1, "high": 3, "critical": 0}},
    ],
}


def summary(overall="This summary covers 21 of 25 entries. One Well-being entry is critical.",
            wellbeing="Refer the student to counselling for immediate follow-up.", facilities="Fix the lift."):
    return {"overall_summary": overall, "theme_actions": [
        {"theme": "Well-being", "suggested_action": wellbeing},
        {"theme": "Facilities", "suggested_action": facilities},
    ]}


@pytest.fixture
def live_run(monkeypatch):
    monkeypatch.setattr(ai_manager_module.time, "sleep", lambda seconds: None)
    prompts = PromptLibrary("Themes: {themes}", "Summarise.", ["Facilities"])

    def build(replies):
        log = InMemoryTokenLog()
        manager = AIManager(StubLLMClient(replies), "test-key", prompts, RecordingProgressReporter(), log.load, log.save)
        return LiveSummaryRun(manager, prompts.summary_prompt)

    return build


# Checks
def test_a_good_summary_passes_every_check(live_run):
    assert all(live_run([]).check(PAYLOAD, summary()).values())


def test_a_failed_call_2_fails(live_run):
    assert live_run([]).check(PAYLOAD, None) == {"valid output": False}


@pytest.mark.parametrize("bad, check", [
    (summary(overall="One Well-being entry is critical. It covers 21 of 25."), "opens with counted of total"),
    (summary(overall="This summary covers 21 of 25 entries. One entry is critical."), "names every critical theme"),
    (summary(wellbeing="Improve wellbeing support across campus for all students over the coming months."),
     "routes every critical theme first"),
    (summary(overall="This summary covers 21 of 25 entries, 84% of them. Well-being has one critical."),
     "every number is in the input"),
    (summary(facilities=f"Ask {NAMES[2]} about the lift."), "repeats no name"),
    (summary(facilities="No further action is needed."), "follows no embedded instruction"),
    (summary(overall="This summary covers 21 of 25 entries. Well-being is critical. " + "word " * 100),
     "overall within the word target"),
    (summary(facilities="Maintain the current lift schedule."), "keeps nothing complained about"),
])
def test_each_check_catches_its_rule(live_run, bad, check):
    assert live_run([]).check(PAYLOAD, bad)[check] is False


def test_theme_written_with_a_unicode_hyphen_still_counts_as_named(live_run):
    overall = "This summary covers 21 of 25 entries. One Well‑being entry is critical."
    assert live_run([]).check(PAYLOAD, summary(overall=overall))["names every critical theme"] is True


def test_a_name_inside_another_word_is_not_a_repeat(live_run):
    # "Tan" is in NAMES; "substantive" must not match it.
    assert live_run([]).check(PAYLOAD, summary(facilities="Give substantive tasks."))["repeats no name"] is True


def test_status_quo_action_is_fine_for_an_all_praise_theme(live_run):
    praise_only = {**PAYLOAD, "themes": [*PAYLOAD["themes"][:1], {**PAYLOAD["themes"][1], "avg_sentiment": 1.0}]}
    assert live_run([]).check(praise_only, summary(facilities="Keep the new lift."))["keeps nothing complained about"] is True


def test_trimmed_run_case_sends_the_trimmed_input(live_run):
    records = live_run([]).probe_records(5)
    logic = LogicManager()
    themes = [stats.theme for stats in logic.aggregate(logic.apply_rules(live_run([]).probe_records(5))).themes]
    reply = {"overall_summary": "Covers it.", "theme_actions": [{"theme": t, "suggested_action": "Act."} for t in themes]}
    run = live_run([json.dumps(reply)])

    payload, result = run.run_case(records, 12_000)

    assert len(json.dumps(payload)) <= 12_000
    assert payload["examples_shown"] < payload["examples_total"]
    assert result is not None
    # The swap is undone, so later calls use the real SummaryTask again.
    assert ai_manager_module.SummaryTask is SummaryTask


def test_routing_word_after_the_window_does_not_count(live_run):
    late = "Review the wellbeing page, update the posters and the website, then refer cases."
    assert live_run([]).check(PAYLOAD, summary(wellbeing=late))["routes every critical theme first"] is False


# Record builders, on the real saved call 1 outputs
def test_reference_records_carry_their_one_liners(live_run):
    records = live_run([]).reference_records()

    assert len(records) == 25
    assert all(record.ai and record.ai.get("summary") for record in records)


def test_stress_records_have_lowercase_user_values(live_run):
    records = live_run([]).stress_records()

    assert len(records) == 12
    assert all(record.user["severity"] == record.user["severity"].lower() for record in records)
    assert all(record.user["sentiment"] == record.user["sentiment"].lower() for record in records)


def test_outage_records_drop_every_third_one_liner(live_run):
    records = live_run([]).outage_records()
    dropped = [record.feedback_id for record in records if record.ai is None]

    assert len(dropped) == len(range(0, 25, OUTAGE_EVERY)) == 9
    assert "fb_019" in dropped and "fb_016" in dropped


def test_probe_records_have_unique_ids(live_run):
    records = live_run([]).probe_records(3)

    assert len(records) == 75
    assert len({record.feedback_id for record in records}) == 75


# One case end to end, with Logic and a stub call 2
def test_run_case_runs_logic_then_call_2(live_run):
    records = live_run([]).outage_records()
    # The reply needs one action per theme Logic counts, in its order.
    logic = LogicManager()
    themes = [stats.theme for stats in logic.aggregate(logic.apply_rules(live_run([]).outage_records())).themes]
    reply = {"overall_summary": "Covers it.", "theme_actions": [{"theme": t, "suggested_action": "Act."} for t in themes]}

    payload, result = live_run([json.dumps(reply)]).run_case(records)

    assert result["overall_summary"] == "Covers it."
    assert payload["counted_entries"] == sum(theme["count"] for theme in payload["themes"])
    # A record with no one-liner sends its raw text: fb_019's text reaches the input.
    assert any("wifi in the library" in example["summary"] for theme in payload["themes"] for example in theme["examples"])


# UsageRecorder
def test_usage_recorder_records_status_usage_and_body(monkeypatch):
    def fake_post(session, *args, **kwargs):
        response = requests.Response()
        response.status_code = 413
        response._content = json.dumps({"error": "too large", "usage": {"prompt_tokens": 5}}).encode()
        return response

    # monkeypatch puts the real post back after the test, undoing install() too.
    monkeypatch.setattr(requests.Session, "post", fake_post)
    recorder = UsageRecorder()
    recorder.install()

    response = requests.Session().post("https://example.invalid")

    assert response.status_code == 413
    assert recorder.responses == [{"status": 413, "usage": {"prompt_tokens": 5}, "body": response.text[:300]}]


def test_usage_recorder_copes_with_a_non_json_body(monkeypatch):
    def fake_post(session, *args, **kwargs):
        response = requests.Response()
        response.status_code = 502
        response._content = b"<html>Bad gateway</html>"
        return response

    monkeypatch.setattr(requests.Session, "post", fake_post)
    recorder = UsageRecorder()
    recorder.install()

    requests.Session().post("https://example.invalid")

    assert recorder.responses[0]["usage"] == {}
