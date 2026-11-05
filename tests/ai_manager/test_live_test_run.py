import json

import pytest

from managers.ai_manager import AIManager, PromptLibrary, ai_manager as ai_manager_module
from managers.ai_manager.llm_request_error import LLMRequestError
from managers.models import FeedbackRecord
from in_memory_token_log import InMemoryTokenLog
from live_test_run import (
    HUMAN_TAGS_FILE, LiveTestRun, OUTPUT_FILE, REFERENCE_ENTRIES_FILE,
    STRESS_ENTRIES_FILE, STRESS_OUTPUT_FILE, STRESS_TAGS_FILE,
)
from recording_progress_reporter import RecordingProgressReporter
from stub_llm_client import StubLLMClient

THEMES = ["Facilities", "Assessment"]


def ai_reply(theme="Facilities", sentiment="negative", severity="high"):
    return json.dumps({"theme": theme, "sentiment": sentiment, "severity": severity})


def record(feedback_id="fb_001", theme="Facilities", ai_theme="Facilities",
           sentiment="negative", ai_sentiment="negative", severity="high", ai_severity="high"):
    built = FeedbackRecord(feedback_id, "Text.", "t", None, {"theme": theme, "sentiment": sentiment, "severity": severity})
    built.set_ai(ai_theme, ai_sentiment, ai_severity)
    return built


@pytest.fixture
def samples_dir(tmp_path):
    reference = [
        {"feedback_id": "fb_001", "text": "First.", "timestamp": "t1", "theme": "OLD", "summary": "OLD", "confidence": 0.5},
        {"feedback_id": "fb_002", "text": "Second.", "timestamp": "t2", "theme": "OLD", "summary": "OLD", "confidence": 0.5},
    ]
    labels = [
        {"feedback_id": "fb_001", "theme": "Facilities", "sentiment": "negative", "severity": "high", "note": "n"},
        {"feedback_id": "fb_002", "theme": "Assessment", "sentiment": "neutral", "severity": "low", "note": "n"},
        {"feedback_id": "fb_003", "theme": "Unused", "sentiment": "neutral", "severity": "low", "note": "n"},
    ]
    (tmp_path / REFERENCE_ENTRIES_FILE).write_text(json.dumps(reference), encoding="utf-8")
    (tmp_path / HUMAN_TAGS_FILE).write_text(json.dumps(labels), encoding="utf-8")
    return tmp_path


def build_run(samples_dir, replies, monkeypatch):
    monkeypatch.setattr(ai_manager_module.time, "sleep", lambda seconds: None)
    client = StubLLMClient(replies)
    token_log = InMemoryTokenLog()
    manager = AIManager(
        client, "test-key", PromptLibrary("Themes: {themes}", "Summarise.", THEMES),
        RecordingProgressReporter(), token_log.load, token_log.save,
    )
    return LiveTestRun(manager, THEMES, samples_dir), client


def test_run_sends_only_the_text_and_keeps_hand_labels_as_human_tags(samples_dir, monkeypatch):
    live_run, client = build_run(samples_dir, [ai_reply(), ai_reply()], monkeypatch)

    classified, pending, stopped = live_run.run_reference()

    assert (pending, stopped) == ([], False)
    assert json.loads(client.calls[0]["messages"][1]["content"]) == {"text": "First."}
    assert classified[1].user == {"theme": "Assessment", "sentiment": "neutral", "severity": "low"}


def test_run_saves_each_record_as_it_finishes(samples_dir, monkeypatch):
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)
    live_run, _ = build_run(samples_dir, [ai_reply(), rejected], monkeypatch)

    _, pending, stopped = live_run.run_reference()

    saved = json.loads((samples_dir / OUTPUT_FILE).read_text(encoding="utf-8"))
    assert [item["feedback_id"] for item in saved] == ["fb_001"]
    assert [item.feedback_id for item in pending] == ["fb_002"]
    assert stopped is True


def test_find_disagreements_follows_the_flag_rule(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)
    records = [
        record("fb_001"),
        record("fb_002", theme="FACILITIES"),
        record("fb_003", theme="Canteen", ai_theme="Catering"),
        record("fb_004", sentiment="neutral"),
        record("fb_005", severity="medium"),
    ]

    assert live_run.find_disagreements(records) == [
        "fb_003 theme: human Canteen, AI Catering",
        "fb_004 sentiment: human neutral, AI negative",
        "fb_005 severity: human medium, AI high",
    ]


def test_find_coined_themes(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)
    records = [record(ai_theme=theme) for theme in ("Facilities", "Catering", "Catering", "Unclear")]

    assert live_run.find_coined_themes(records) == ["Catering"]


def test_report_counts_each_flagged_record_once(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)
    records = [record("fb_001", sentiment="neutral", severity="low"), record("fb_002")]

    report = live_run.build_report(records, [], False)

    assert "Records flagged: 1 of 2" in report
    assert "fb_001 sentiment" in report
    assert "fb_001 severity" in report


def test_comparison_ignores_case(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)
    records = [record(theme="FACILITIES", sentiment="Negative", severity="High")]

    assert live_run.find_disagreements(records) == []


def test_catch_rate_counts_wrong_labels_outside_the_plausible_set(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)

    # Wrong labels for human Facilities: Assessment (the AI's theme, so missed) and Unclear (caught)
    assert live_run.measure_catch_rate([record(ai_theme="Assessment")]) == (1, 2)


def test_catch_rate_verdict_uses_the_pass_mark(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)

    assert "2 of 2 (100.0%), pass mark 85%: pass" in live_run.build_report([record()], [], False)
    assert "1 of 2 (50.0%), pass mark 85%: fail" in live_run.build_report([record(ai_theme="Assessment")], [], False)


def test_critical_results_list_entries_the_human_tagged_critical(samples_dir, monkeypatch):
    live_run, _ = build_run(samples_dir, [], monkeypatch)
    records = [record("fb_001", severity="Critical", ai_severity="high"), record("fb_002")]

    assert live_run.find_critical_results(records) == ["fb_001: AI high"]


def test_stress_run_uses_the_stress_files(samples_dir, monkeypatch):
    entries = [{"feedback_id": "st_001", "text": "Long text.", "timestamp": "t"}]
    tags = [{"feedback_id": "st_001", "theme": "Academic", "sentiment": "Positive", "severity": "Low"}]
    (samples_dir / STRESS_ENTRIES_FILE).write_text(json.dumps(entries), encoding="utf-8")
    (samples_dir / STRESS_TAGS_FILE).write_text(json.dumps(tags), encoding="utf-8")
    live_run, client = build_run(samples_dir, [ai_reply()], monkeypatch)

    classified, _, _ = live_run.run_stress()

    assert classified[0].user["theme"] == "Academic"
    assert json.loads(client.calls[0]["messages"][1]["content"]) == {"text": "Long text."}
    saved = json.loads((samples_dir / STRESS_OUTPUT_FILE).read_text(encoding="utf-8"))
    assert saved[0]["ai"]["theme"] == "Facilities"
