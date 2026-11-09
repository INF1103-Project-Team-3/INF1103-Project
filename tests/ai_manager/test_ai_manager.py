import json
import logging
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import managers.ai_manager
from managers.ai_manager import AIManager, AISummary, GroqClient, LLMClient, PromptLibrary, ai_manager as ai_manager_module
from managers.ai_manager.ai_manager import BACKOFF_BASE_S, MAX_ATTEMPTS
from managers.ai_manager.ai_task import AITask
from managers.ai_manager.classification_task import (
    CLASSIFY_TOKEN_MARGIN, ClassificationTask, MAX_COINED_THEME_WORDS, MAX_SUMMARY_WORDS
)
from managers.ai_manager.groq_client import MODEL
from managers.ai_manager.llm_request_error import LLMRequestError
from managers.ai_manager.rate_limiter import DELAY_BUFFER_S, FALLBACK_DELAY_S, MIN_DELAY_S, RateLimiter
from managers.ai_manager.summary_task import (
    MAX_ACTION_WORDS, SUMMARY_MAX_COMPLETION_TOKENS, SUMMARY_TOKEN_MARGIN, SummaryTask
)
from managers.ai_manager.token_ledger import TokenLedger
from managers.models import FeedbackRecord, PENDING, Serializable, THEMES
from in_memory_token_log import InMemoryTokenLog
from recording_progress_reporter import RecordingProgressReporter
from stub_llm_client import StubLLMClient

CONFIG_DIR = Path(__file__).resolve().parents[2] / "managers" / "config"
STATS = {"themes": [{"theme": "Facilities"}, {"theme": "Assessment"}]}
RESULT = SimpleNamespace(to_dict=lambda: STATS)  # stands in for AggregationResult
USER = {"theme": "Assessment", "sentiment": "neutral", "severity": "low"}


def make_record(feedback_id="fb_001", user=None):
    return FeedbackRecord(feedback_id, "The slides move too fast.", "2026-09-15T10:32:00", None, user or USER)


@pytest.fixture
def entry():
    return make_record()


def with_ai(theme, user=None):
    record = make_record("fb_stored", user)
    record.set_ai(theme, "negative", "high")
    return record


def classification(theme="Facilities", sentiment="negative", severity="high", summary="Slides move too fast."):
    return {"theme": theme, "sentiment": sentiment, "severity": severity, "summary": summary}


def without(result, field):
    return {key: value for key, value in result.items() if key != field}


def discard(record):
    pass


def summary_output(themes=("Facilities", "Assessment")):
    return {"overall_summary": "Overall.", "theme_actions": [{"theme": t, "suggested_action": "Act."} for t in themes]}


def error(kind=LLMRequestError.SERVER, retryable=True, wait_seconds=None):
    return LLMRequestError("failed", kind, retryable, wait_seconds)


def response(status, body=b"{}", headers=None):
    built = requests.Response()
    built.status_code = status
    built._content = body
    built.headers.update(headers or {})
    return built


def groq_reply(content="{}", tokens=1234):
    return json.dumps({"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}}).encode()


@pytest.fixture
def prompts():
    return PromptLibrary("Themes: {themes}", "Summarise.", ["Facilities", "Assessment"])


# Records every wait instead of sleeping
@pytest.fixture
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr(ai_manager_module.time, "sleep", waits.append)
    return waits


@pytest.fixture
def token_log():
    return InMemoryTokenLog()


def build_manager(client, prompts, token_log, reporter=None):
    return AIManager(client, "test-key", prompts, reporter or RecordingProgressReporter(), token_log.load, token_log.save)


def today_usage(token_log, model="stub-model"):
    log = token_log.log
    day = next(iter(log))
    return log[day]["test-key"]["candidates"][f"groq/{model}"]


# Interfaces and abstract classes
@pytest.mark.parametrize("abstract_class", [LLMClient, AITask])
def test_abstract_classes_cannot_be_instantiated(abstract_class):
    with pytest.raises(TypeError):
        abstract_class()


# The stub stands in for GroqClient, and both tasks run through the same retry loop
def test_stub_substitutes_for_groq_client(prompts, token_log, sleeps, entry):
    client = StubLLMClient([json.dumps(classification()), json.dumps(summary_output())])
    manager = build_manager(client, prompts, token_log)

    assert isinstance(client, LLMClient)
    assert manager.classify_entries([entry], [], discard)[0][0].ai["theme"] == "Facilities"
    assert manager.summarise(RESULT, []).overall_summary == "Overall."


def test_both_tasks_are_ai_tasks(prompts, entry):
    assert isinstance(ClassificationTask(entry, prompts.system_prompt, prompts.themes, []), AITask)
    assert isinstance(SummaryTask(STATS, prompts.summary_prompt), AITask)


# Call 1: the record contract
def test_success_sets_ai_and_leaves_everything_else(prompts, token_log, sleeps, entry):
    client = StubLLMClient([json.dumps(classification())])

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry], [], discard)

    assert classified == [entry]
    assert entry.ai == classification()
    assert entry.user == USER
    assert (entry.theme, entry.sentiment, entry.severity) == (None, None, None)
    assert entry.verification == PENDING
    assert pending == []
    assert stopped is False


def test_summary_is_stored_in_ai_through_set_ai(prompts, token_log, sleeps, entry):
    saved = []
    client = StubLLMClient([json.dumps(classification(summary="Student cannot keep up with the slides."))])

    build_manager(client, prompts, token_log).classify_entries([entry], [], saved.append)

    assert entry.ai["summary"] == "Student cannot keep up with the slides."
    # The record handed to on_classified already carries it, so Data saves it.
    assert saved[0].ai["summary"] == "Student cannot keep up with the slides."
    assert FeedbackRecord.from_dict(entry.to_dict()).ai["summary"] == "Student cannot keep up with the slides."


def test_summary_over_the_word_limit_is_retried(prompts, token_log, sleeps, entry):
    too_long = classification(summary="word " * (MAX_SUMMARY_WORDS + 1))
    client = StubLLMClient([json.dumps(too_long), json.dumps(classification())])

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry], [], discard)

    assert len(client.calls) == 2
    assert classified == [entry]
    assert entry.ai["summary"] == classification()["summary"]


def test_summary_over_the_word_limit_every_attempt_leaves_record_pending(prompts, token_log, sleeps, entry):
    too_long = classification(summary="word " * (MAX_SUMMARY_WORDS + 1))
    client = StubLLMClient([json.dumps(too_long)] * MAX_ATTEMPTS)

    assert build_manager(client, prompts, token_log).classify_entries([entry], [], discard) == ([], [entry], False)
    assert entry.ai is None


def test_only_the_text_reaches_the_model(prompts, token_log, sleeps):
    record = make_record(user={"theme": "HUMAN-THEME", "sentiment": "HUMAN-SENTIMENT", "severity": "HUMAN-SEVERITY"})
    client = StubLLMClient([json.dumps(classification())])

    build_manager(client, prompts, token_log).classify_entries([record], [], discard)

    assert json.loads(client.calls[0]["messages"][1]["content"]) == {"text": record.text}
    assert "HUMAN" not in json.dumps(client.calls[0]["messages"])


def test_on_classified_fires_per_record_as_it_finishes(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    third = make_record("fb_003")
    saved = []
    client = StubLLMClient([json.dumps(classification())] + ["not json"] * MAX_ATTEMPTS + [json.dumps(classification())])

    build_manager(client, prompts, token_log).classify_entries([entry, second, third], [], saved.append)

    assert [record.feedback_id for record in saved] == ["fb_001", "fb_003"]


@pytest.mark.parametrize("returned, stored", [
    ("facilities", "Facilities"),
    ("FACILITIES", "Facilities"),
    ("Wellbeing", "Well-being"),
    ("well being", "Well-being"),
    ("Well-Being", "Well-being"),
    ("teaching-quality", "Teaching Quality"),
    ("unclear.", "Unclear"),
    ("Well-being", "Well-being"),
    ("Facility", "Facility"),
    ("Mental Health", "Mental Health"),
    ("Teaching", "Teaching"),
])
def test_spelling_variants_map_to_the_listed_label(returned, stored, entry):
    task = ClassificationTask(entry, "prompt", ["Facilities", "Well-being", "Teaching Quality"], [])

    assert task.parse(json.dumps(classification(theme=returned)))["theme"] == stored


def test_spelling_variant_is_stored_as_listed_and_not_offered_back(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient([json.dumps(classification(theme="facilities")), json.dumps(classification())])

    classified, _, _ = build_manager(client, prompts, token_log).classify_entries([entry, second], [], discard)

    assert classified[0].ai["theme"] == "Facilities"
    assert "existing_new_themes" not in json.loads(client.calls[1]["messages"][1]["content"])


@pytest.mark.parametrize("raw", ['"not a dict"', '{"theme": 1}', "[]"])
def test_spelling_match_leaves_malformed_output_for_validation(prompts, raw, entry):
    assert ClassificationTask(entry, prompts.system_prompt, prompts.themes, []).parse(raw) is None


def test_long_listed_theme_is_still_valid(entry):
    long_theme = "word " * (MAX_COINED_THEME_WORDS + 1)
    task = ClassificationTask(entry, "prompt", [long_theme], [])

    assert task.validate(classification(theme=long_theme)) is True


# Call 1: coined themes
def test_coined_themes_are_offered_back_to_the_model(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient([json.dumps(classification(theme="Catering")), json.dumps(classification())])

    build_manager(client, prompts, token_log).classify_entries([entry, second], [with_ai("Stored")], discard)

    payloads = [json.loads(call["messages"][1]["content"]) for call in client.calls]
    assert payloads[0] == {"text": entry.text, "existing_new_themes": ["Stored"]}
    assert payloads[1]["existing_new_themes"] == ["Stored", "Catering"]


def test_human_themes_are_never_offered_to_the_model(prompts, token_log, sleeps, entry):
    client = StubLLMClient([json.dumps(classification())])
    stored = [with_ai("Facilities", {**USER, "theme": "HUMAN-THEME"})]

    build_manager(client, prompts, token_log).classify_entries([entry], stored, discard)

    assert json.loads(client.calls[0]["messages"][1]["content"]) == {"text": entry.text}


def test_failed_record_does_not_change_the_known_themes(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient(["not json"] * MAX_ATTEMPTS + [json.dumps(classification())])

    build_manager(client, prompts, token_log).classify_entries([entry, second], [], discard)

    assert json.loads(client.calls[-1]["messages"][1]["content"]) == {"text": entry.text}


# Call 1: failure behaviour
def test_invalid_output_leaves_record_pending_and_batch_continues(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient(["not json"] * MAX_ATTEMPTS + [json.dumps(classification())])

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry, second], [], discard)

    assert pending == [entry]
    assert entry.ai is None
    assert [record.feedback_id for record in classified] == ["fb_002"]
    assert stopped is False


def test_value_set_ai_refuses_counts_as_a_failed_record(prompts, token_log, sleeps, entry, monkeypatch):
    monkeypatch.setattr(ClassificationTask, "validate", lambda self, result: True)
    second = make_record("fb_002")
    reporter = RecordingProgressReporter()
    saved = []
    client = StubLLMClient([json.dumps(classification(sentiment="angry")), json.dumps(classification())])

    classified, pending, stopped = build_manager(client, prompts, token_log, reporter).classify_entries(
        [entry, second], [], saved.append
    )

    assert pending == [entry]
    assert entry.ai is None
    assert classified == [second]
    assert saved == [second]
    assert stopped is False
    assert "record_failed" in reporter.names


def test_rejected_key_stops_the_batch(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient([error(LLMRequestError.AUTH, retryable=False)])

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry, second], [], discard)

    assert classified == []
    assert pending == [entry, second]
    assert stopped is True
    assert len(client.calls) == 1


def test_missing_key_stops_the_batch_without_a_request(prompts, token_log, sleeps, monkeypatch, entry):
    def fail(*args, **kwargs):
        raise AssertionError("no request should be sent")
    monkeypatch.setattr(requests.Session, "post", fail)
    manager = AIManager(GroqClient(None), "none", prompts, RecordingProgressReporter(), token_log.load, token_log.save)

    classified, pending, stopped = manager.classify_entries([entry], [], discard)

    assert (classified, pending, stopped) == ([], [entry], True)


def test_every_attempt_lost_to_connection_errors_stops_the_batch(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient([error(LLMRequestError.CONNECTION)] * MAX_ATTEMPTS)

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry, second], [], discard)

    assert (classified, pending, stopped) == ([], [entry, second], True)
    assert len(client.calls) == MAX_ATTEMPTS
    assert sleeps == [BACKOFF_BASE_S, BACKOFF_BASE_S**2]  # no wait once it has stopped


def test_connection_recovering_does_not_stop_the_batch(prompts, token_log, sleeps, entry):
    client = StubLLMClient([error(LLMRequestError.CONNECTION), error(LLMRequestError.CONNECTION), json.dumps(classification())])

    classified, _, stopped = build_manager(client, prompts, token_log).classify_entries([entry], [], discard)

    assert len(classified) == 1
    assert stopped is False


def test_rejected_request_leaves_record_pending_and_batch_continues(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient([error(LLMRequestError.REQUEST, retryable=False), json.dumps(classification())])

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry, second], [], discard)

    assert pending == [entry]
    assert len(classified) == 1
    assert stopped is False


def test_rate_limit_wait_over_a_minute_stops_the_batch(prompts, token_log, sleeps, monkeypatch, entry):
    second = make_record("fb_002")
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(429, headers={"retry-after": "3600"}))
    manager = AIManager(GroqClient("key"), "test-key", prompts, RecordingProgressReporter(), token_log.load, token_log.save)

    classified, pending, stopped = manager.classify_entries([entry, second], [], discard)

    assert (classified, pending, stopped) == ([], [entry, second], True)
    assert sleeps == []


def test_long_wait_after_a_success_keeps_the_record_and_stops(prompts, token_log, sleeps, entry):
    second = make_record("fb_002")
    client = StubLLMClient([json.dumps(classification())], wait_seconds=62)
    saved = []

    classified, pending, stopped = build_manager(client, prompts, token_log).classify_entries([entry, second], [], saved.append)

    assert len(classified) == 1
    assert saved == classified
    assert (pending, stopped) == ([second], True)
    assert sleeps == []


def test_retry_after_of_a_minute_does_not_stop_despite_the_buffer(prompts, token_log, sleeps, monkeypatch, entry):
    replies = [response(429, headers={"retry-after": "60"}), response(200, groq_reply(json.dumps(classification())))]
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: replies.pop(0))
    manager = AIManager(GroqClient("key"), "test-key", prompts, RecordingProgressReporter(), token_log.load, token_log.save)

    classified, _, stopped = manager.classify_entries([entry], [], discard)

    assert len(classified) == 1
    assert stopped is False
    assert sleeps[0] == 60 + DELAY_BUFFER_S


def test_token_reset_near_a_minute_does_not_stop_despite_the_buffer(prompts, token_log, sleeps, monkeypatch, entry):
    headers = {"x-ratelimit-remaining-tokens": "100", "x-ratelimit-reset-tokens": "59.9s"}
    reply = response(200, groq_reply(json.dumps(classification())), headers)
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: reply)
    manager = AIManager(GroqClient("key"), "test-key", prompts, RecordingProgressReporter(), token_log.load, token_log.save)

    _, _, stopped = manager.classify_entries([entry], [], discard)

    assert stopped is False


def test_retry_after_over_a_minute_and_a_second_stops(prompts, token_log, sleeps, monkeypatch, entry):
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(429, headers={"retry-after": "61"}))
    manager = AIManager(GroqClient("key"), "test-key", prompts, RecordingProgressReporter(), token_log.load, token_log.save)

    _, _, stopped = manager.classify_entries([entry], [], discard)

    assert stopped is True
    assert sleeps == []


def test_stored_record_with_no_ai_theme_does_not_crash_the_batch(prompts, token_log, sleeps, entry):
    client = StubLLMClient([json.dumps(classification())])
    # from_dict restores saved values unchecked, so ai can be missing or empty
    stored = [make_record(), FeedbackRecord.from_dict({**make_record().to_dict(), "ai": {}}), with_ai("Stored")]

    classified, _, _ = build_manager(client, prompts, token_log).classify_entries([entry], stored, discard)

    assert len(classified) == 1
    assert json.loads(client.calls[0]["messages"][1]["content"])["existing_new_themes"] == ["Stored"]


def test_wait_of_exactly_a_minute_does_not_stop(prompts, token_log, sleeps, entry):
    client = StubLLMClient([error(wait_seconds=60), json.dumps(classification())])

    classified, _, stopped = build_manager(client, prompts, token_log).classify_entries([entry], [], discard)

    assert len(classified) == 1
    assert stopped is False
    assert sleeps[0] == 60


# Retry loop
def test_retries_until_output_validates(prompts, token_log, sleeps, entry):
    client = StubLLMClient(["not json", json.dumps({"theme": "incomplete"}), json.dumps(classification())])

    records, _, _ = build_manager(client, prompts, token_log).classify_entries([entry], [], discard)

    assert len(records) == 1
    assert len(client.calls) == 3
    # Non-JSON content backs off; a schema mismatch and a success follow the client's wait
    assert sleeps == [BACKOFF_BASE_S, 0.5, 0.5]
    assert today_usage(token_log)["total_tokens"] == 300


def test_error_without_wait_uses_backoff_and_error_with_wait_uses_it(prompts, token_log, sleeps, entry):
    client = StubLLMClient([error(), error(wait_seconds=7.5), json.dumps(classification())])

    build_manager(client, prompts, token_log).classify_entries([entry], [], discard)

    assert sleeps == [BACKOFF_BASE_S, 7.5, 0.5]


def test_gives_up_after_max_attempts(prompts, token_log, sleeps, entry):
    client = StubLLMClient([error() for _ in range(MAX_ATTEMPTS)])

    assert build_manager(client, prompts, token_log).classify_entries([entry], [], discard) == ([], [entry], False)
    assert len(client.calls) == MAX_ATTEMPTS
    # A request whose every attempt failed is still recorded, with 0
    assert today_usage(token_log)["requests"] == [{"feedback_id": entry.feedback_id, "total_tokens": 0}]


def test_non_retryable_error_stops_after_one_call(prompts, token_log, sleeps, entry):
    client = StubLLMClient([error(LLMRequestError.REQUEST, retryable=False)])

    assert build_manager(client, prompts, token_log).classify_entries([entry], [], discard) == ([], [entry], False)
    assert len(client.calls) == 1
    assert sleeps == []


# Call 2
def test_summarise_sends_its_own_limits(prompts, token_log, sleeps):
    client = StubLLMClient([json.dumps(summary_output())])

    build_manager(client, prompts, token_log).summarise(RESULT, [])

    call = client.calls[0]
    assert call["token_margin"] == SUMMARY_TOKEN_MARGIN
    assert call["max_completion_tokens"] == SUMMARY_MAX_COMPLETION_TOKENS
    assert json.loads(call["messages"][1]["content"]) == STATS
    assert today_usage(token_log)["requests"][0]["feedback_id"] == "summary"


def test_summarise_returns_an_ai_summary(prompts, token_log, sleeps):
    client = StubLLMClient([json.dumps(summary_output())])

    summary = build_manager(client, prompts, token_log).summarise(RESULT, [make_record()])

    assert isinstance(summary, AISummary)
    assert summary.overall_summary == "Overall."
    assert summary.theme_actions == summary_output()["theme_actions"]
    assert summary.created_at


def test_summarise_does_not_send_the_records_yet(prompts, token_log, sleeps):
    client = StubLLMClient([json.dumps(summary_output())])

    build_manager(client, prompts, token_log).summarise(RESULT, [make_record()])

    assert "slides" not in json.dumps(client.calls[0]["messages"])


def test_summarise_returns_none_when_every_attempt_fails(prompts, token_log, sleeps):
    client = StubLLMClient([json.dumps(summary_output(("Assessment", "Facilities")))] * MAX_ATTEMPTS)

    assert build_manager(client, prompts, token_log).summarise(RESULT, []) is None


# AISummary
def test_ai_summary_survives_a_round_trip():
    summary = AISummary("Overall.", [{"theme": "Facilities", "suggested_action": "Act."}], "2026-11-05T10:00:00")

    assert isinstance(summary, Serializable)
    assert AISummary.from_dict(summary.to_dict()) == summary


def test_ai_summary_cannot_be_changed():
    with pytest.raises(FrozenInstanceError):
        AISummary("Overall.", []).overall_summary = "Changed."


@pytest.mark.parametrize("missing", ["overall_summary", "theme_actions", "created_at"])
def test_ai_summary_from_dict_raises_on_a_missing_field(missing):
    data = AISummary("Overall.", []).to_dict()
    del data[missing]

    with pytest.raises(KeyError):
        AISummary.from_dict(data)


# Package exports
@pytest.mark.parametrize("name", [
    "AIManager", "LLMClient", "GroqClient", "PromptLibrary", "ProgressReporter",
    "ConsoleProgressReporter", "BatchProgress", "AISummary",
])
def test_package_exports_the_public_classes(name):
    assert hasattr(managers.ai_manager, name)


# Response validation
def test_classification_uses_its_own_limits(prompts, entry):
    task = ClassificationTask(entry, prompts.system_prompt, prompts.themes, [])

    assert task.request_id == entry.feedback_id
    assert task.token_margin == CLASSIFY_TOKEN_MARGIN
    assert task.max_completion_tokens is None


@pytest.mark.parametrize("bad_result", [
    "not a dict",
    {"theme": "missing fields"},
    {**classification(), "extra": 1},
    without(classification(), "summary"),
    classification(summary=" "),
    classification(summary=""),
    classification(summary=None),
    classification(summary=15),
    classification(summary="word " * (MAX_SUMMARY_WORDS + 1)),
    {**classification(), "confidence": 0.9},
    classification(theme=" "),
    classification(theme="word " * (MAX_COINED_THEME_WORDS + 1)),
    classification(theme=1),
    classification(sentiment="angry"),
    classification(severity="urgent"),
    {**classification(), "alternative_themes": []},
])
def test_classification_rejects_bad_output(prompts, bad_result, entry):
    assert ClassificationTask(entry, prompts.system_prompt, prompts.themes, []).validate(bad_result) is False


@pytest.mark.parametrize("good_result", [
    classification(),
    classification(theme="Unclear"),
    classification(theme="Catering"),
    classification(theme="word " * MAX_COINED_THEME_WORDS),
    classification(summary="word " * MAX_SUMMARY_WORDS),
    classification(summary="One."),
])
def test_classification_accepts_valid_output(prompts, good_result, entry):
    assert ClassificationTask(entry, prompts.system_prompt, prompts.themes, []).validate(good_result) is True


def test_classification_schema_lets_theme_be_coined(prompts, entry):
    properties = ClassificationTask(entry, prompts.system_prompt, prompts.themes, []).schema["properties"]

    assert "enum" not in properties["theme"]
    assert set(properties) == {"theme", "sentiment", "severity", "summary"}


def test_classification_schema_requires_a_string_summary(prompts, entry):
    schema = ClassificationTask(entry, prompts.system_prompt, prompts.themes, []).schema

    assert schema["properties"]["summary"] == {"type": "string"}
    assert "summary" in schema["required"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("bad_result", [
    "not a dict",
    {"overall_summary": "missing actions"},
    {**summary_output(), "overall_summary": " "},
    {**summary_output(), "overall_summary": "word " * 121},
    {**summary_output(), "theme_actions": "not a list"},
    {**summary_output(), "theme_actions": ["not a dict"]},
    summary_output(("Facilities",)),
    summary_output(("Assessment", "Facilities")),
    {**summary_output(), "theme_actions": [
        {"theme": "Facilities", "suggested_action": " "},
        {"theme": "Assessment", "suggested_action": "Act."},
    ]},
    {**summary_output(), "theme_actions": [
        {"theme": "Facilities", "suggested_action": "word " * (MAX_ACTION_WORDS + 1)},
        {"theme": "Assessment", "suggested_action": "Act."},
    ]},
])
def test_summary_rejects_bad_output(prompts, bad_result):
    assert SummaryTask(STATS, prompts.summary_prompt).validate(bad_result) is False


def test_parse_raises_on_non_json(prompts, entry):
    task = ClassificationTask(entry, prompts.system_prompt, prompts.themes, [])

    with pytest.raises(json.JSONDecodeError):
        task.parse("not json")
    with pytest.raises(TypeError):
        task.parse(None)


# GroqClient error mapping
@pytest.mark.parametrize("status, body, kind, retryable", [
    (429, b"{}", LLMRequestError.RATE_LIMIT, True),
    (498, b"{}", LLMRequestError.RATE_LIMIT, True),
    (500, b"{}", LLMRequestError.SERVER, True),
    (503, b"{}", LLMRequestError.SERVER, True),
    (401, b"{}", LLMRequestError.AUTH, False),
    (403, b"{}", LLMRequestError.AUTH, False),
    (400, b'{"error": {"code": "json_validate_failed"}}', LLMRequestError.OUTPUT, True),
    (400, b'{"error": {"code": "invalid_request_error"}}', LLMRequestError.REQUEST, False),
    (400, b"not json", LLMRequestError.REQUEST, False),
    (404, b"{}", LLMRequestError.REQUEST, False),
])
def test_groq_status_mapping(monkeypatch, status, body, kind, retryable):
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(status, body))

    with pytest.raises(LLMRequestError) as caught:
        GroqClient("key").send([], "name", {}, 1600)

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.wait_seconds is None


def test_groq_error_wait_comes_from_headers(monkeypatch):
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(429, headers={"retry-after": "5"}))

    with pytest.raises(LLMRequestError) as caught:
        GroqClient("key").send([], "name", {}, 1600)

    assert caught.value.wait_seconds == 5 + DELAY_BUFFER_S


def test_groq_response_body_only_goes_to_debug(monkeypatch, caplog):
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(500, b"the body"))

    with caplog.at_level(logging.WARNING), pytest.raises(LLMRequestError):
        GroqClient("key").send([], "name", {}, 1600)
    assert "the body" not in caplog.text

    with caplog.at_level(logging.DEBUG), pytest.raises(LLMRequestError):
        GroqClient("key").send([], "name", {}, 1600)
    assert "the body" in caplog.text


def test_groq_connection_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(requests.Session, "post", fail)

    with pytest.raises(LLMRequestError) as caught:
        GroqClient("key").send([], "name", {}, 1600)

    assert str(caught.value) == "connection failed"
    assert caught.value.kind == LLMRequestError.CONNECTION
    assert caught.value.retryable is True
    assert caught.value.wait_seconds is None


@pytest.mark.parametrize("body", [b"not json", b"[]", b"{}", b'{"choices": []}', b'{"choices": [{"message": {}}]}'])
def test_groq_malformed_body_is_retryable_output_error(monkeypatch, body):
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(200, body))

    with pytest.raises(LLMRequestError) as caught:
        GroqClient("key").send([], "name", {}, 1600)

    assert caught.value.kind == LLMRequestError.OUTPUT
    assert caught.value.retryable is True
    assert caught.value.wait_seconds is None


def test_groq_success_returns_content_tokens_and_wait(monkeypatch):
    monkeypatch.setattr(requests.Session, "post", lambda *a, **k: response(200, groq_reply('{"a": 1}', 1234)))

    assert GroqClient("key").send([], "name", {}, 1600) == ('{"a": 1}', 1234, FALLBACK_DELAY_S)


def test_groq_sends_key_schema_and_output_cap(monkeypatch):
    sent = {}
    def capture(self, url, headers, json, timeout):
        sent.update(headers=headers, body=json)
        return response(200, groq_reply())
    monkeypatch.setattr(requests.Session, "post", capture)
    client = GroqClient("secret-key", "some-model")

    client.send([{"role": "user", "content": "hi"}], "name", {"type": "object"}, 1600, 5000)

    assert client.model == "some-model"
    assert sent["headers"]["Authorization"] == "Bearer secret-key"
    assert sent["body"]["model"] == "some-model"
    assert sent["body"]["max_completion_tokens"] == 5000
    assert sent["body"]["response_format"]["json_schema"] == {"name": "name", "strict": True, "schema": {"type": "object"}}


def test_groq_uses_its_default_model_when_given_none():
    assert GroqClient("key").model == MODEL
    assert GroqClient("key", None).model == MODEL


def test_groq_leaves_out_output_cap_by_default(monkeypatch):
    sent = {}
    def capture(self, url, headers, json, timeout):
        sent.update(json)
        return response(200, groq_reply())
    monkeypatch.setattr(requests.Session, "post", capture)

    GroqClient("key").send([], "name", {}, 1600)

    assert "max_completion_tokens" not in sent


# RateLimiter
@pytest.mark.parametrize("value, seconds", [
    ("11.317s", 11.317),
    ("25m55.199s", 25 * 60 + 55.199),
    ("250ms", 0.25),
    ("1h2m3s", 3723),
    ("nonsense", 0),
])
def test_parse_reset_duration(value, seconds):
    assert RateLimiter().parse_reset_duration(value) == pytest.approx(seconds)


@pytest.mark.parametrize("headers, delay", [
    ({"retry-after": "5"}, 5 + DELAY_BUFFER_S),
    ({"x-ratelimit-remaining-tokens": "100", "x-ratelimit-reset-tokens": "10s"}, 10 + DELAY_BUFFER_S),
    ({"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-reset-tokens": "10s"}, MIN_DELAY_S),
    ({}, "fallback"),
    ({"x-ratelimit-remaining-tokens": "100"}, "fallback"),
    ({"retry-after": "soon"}, "fallback"),
    ({"x-ratelimit-remaining-tokens": "many", "x-ratelimit-reset-tokens": "10s"}, "fallback"),
])
def test_compute_delay(headers, delay):
    assert RateLimiter().compute_delay(headers, "fallback", 1600) == delay


# TokenLedger
def test_ledger_keeps_the_harness_schema(token_log):
    ledger = TokenLedger("some-model", token_log.load, token_log.save)

    ledger.record("test-key", "fb_001", 100)
    ledger.record("test-key", "fb_002", 0)
    ledger.record("test-key", "fb_003", 50)

    key_log = next(iter(token_log.log.values()))["test-key"]
    assert key_log["totals"] == {"some-model": 150}
    assert key_log["candidates"]["groq/some-model"] == {
        "model": "some-model",
        "total_tokens": 150,
        "requests": [
            {"feedback_id": "fb_001", "total_tokens": 100},
            {"feedback_id": "fb_002", "total_tokens": 0},
            {"feedback_id": "fb_003", "total_tokens": 50},
        ],
    }


def test_corrupt_ledger_is_not_overwritten(token_log, caplog):
    token_log.corrupt = True

    with caplog.at_level(logging.WARNING):
        TokenLedger("some-model", token_log.load, token_log.save).record("test-key", "fb_001", 100)

    assert token_log.saves == 0
    assert "unreadable" in caplog.text


def test_ledger_save_failure_is_logged_not_raised(token_log, caplog):
    def fail(log):
        raise OSError("disk full")

    with caplog.at_level(logging.WARNING):
        TokenLedger("some-model", token_log.load, fail).record("test-key", "fb_001", 100)

    assert "not written" in caplog.text


def test_ledger_warns_once_when_crossing_the_threshold(token_log, caplog):
    ledger = TokenLedger("openai/gpt-oss-120b", token_log.load, token_log.save)

    with caplog.at_level(logging.WARNING):
        ledger.record("test-key", "fb_001", 159_999)
        assert caplog.text == ""
        ledger.record("test-key", "fb_002", 1)
        assert "crossed" in caplog.text
        caplog.clear()
        ledger.record("test-key", "fb_003", 1)
        assert caplog.text == ""


# PromptLibrary
def test_prompt_library_fills_in_themes(prompts):
    assert prompts.system_prompt == "Themes: Facilities, Assessment"
    assert prompts.summary_prompt == "Summarise."
    assert prompts.themes == ["Facilities", "Assessment"]


def test_prompt_library_themes_cannot_be_changed_from_outside(prompts):
    prompts.themes.append("Changed")

    assert prompts.themes == ["Facilities", "Assessment"]


def test_prompt_library_works_with_the_real_prompts_and_base_themes():
    prompts = PromptLibrary(
        (CONFIG_DIR / "system_prompt.txt").read_text(encoding="utf-8"),
        (CONFIG_DIR / "summary_prompt.txt").read_text(encoding="utf-8"),
        THEMES,
    )

    assert prompts.themes == list(THEMES)
    assert ", ".join(THEMES) in prompts.system_prompt
    assert "{themes}" not in prompts.system_prompt
    assert prompts.summary_prompt
    assert "existing_new_themes" in prompts.system_prompt
    assert f"summary: one-line restatement, {MAX_SUMMARY_WORDS} words maximum." in prompts.system_prompt
    for removed in ("confidence", "alternative_themes"):
        assert removed not in prompts.system_prompt


def test_real_prompt_examples_pass_classification_validation(entry):
    # Every few-shot output must itself be valid, or the prompt teaches the model
    # an answer validation would reject (e.g. a summary over the word limit).
    prompts = PromptLibrary((CONFIG_DIR / "system_prompt.txt").read_text(encoding="utf-8"), "Summarise.", THEMES)
    task = ClassificationTask(entry, prompts.system_prompt, prompts.themes, [])
    outputs = [line.removeprefix("Output: ") for line in prompts.system_prompt.splitlines() if line.startswith("Output: ")]

    assert len(outputs) == 7
    for output in outputs:
        assert task.validate(json.loads(output)) is True, output


@pytest.mark.parametrize("themes", ["Facilities", [], [""], [1], None])
def test_prompt_library_rejects_bad_themes(themes):
    with pytest.raises(ValueError):
        PromptLibrary("Themes: {themes}", "Summarise.", themes)


@pytest.mark.parametrize("prompt", ["No placeholder.", "{themes} twice {themes}"])
def test_prompt_library_rejects_bad_placeholder(prompt):
    with pytest.raises(ValueError):
        PromptLibrary(prompt, "Summarise.", ["Facilities"])


def test_prompt_library_rejects_empty_summary_prompt():
    with pytest.raises(ValueError):
        PromptLibrary("Themes: {themes}", "  \n", ["Facilities"])


def test_find_new_themes(prompts):
    records = [
        with_ai("Facilities"),
        with_ai("Catering"),
        with_ai("Catering"),
        with_ai("Unclear"),
        make_record(user={**USER, "theme": "Human Label"}),
    ]

    assert prompts.find_new_themes(records, ["Earlier"]) == ["Earlier", "Catering"]
