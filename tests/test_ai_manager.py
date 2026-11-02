import json
import logging

import pytest
import requests

import ai_manager
from ai_manager import AIManager, BACKOFF_BASE_S, MAX_ATTEMPTS
from ai_task import AITask
from classification_task import CLASSIFY_TOKEN_MARGIN, ClassificationTask, MAX_SUMMARY_WORDS
from groq_client import GroqClient
from llm_client import LLMClient
from llm_request_error import LLMRequestError
from prompt_library import PromptLibrary
from rate_limiter import DELAY_BUFFER_S, FALLBACK_DELAY_S, MIN_DELAY_S, RateLimiter
from recording_progress_reporter import RecordingProgressReporter
from stub_llm_client import StubLLMClient
from summary_task import MAX_ACTION_WORDS, SUMMARY_MAX_COMPLETION_TOKENS, SUMMARY_TOKEN_MARGIN, SummaryTask
from token_ledger import TokenLedger

ENTRY = {"feedback_id": "fb_001", "text": "The slides move too fast.", "timestamp": "2026-09-15T10:32:00"}
STATS = {"themes": [{"theme": "Facilities"}, {"theme": "Assessment"}]}


def classification(theme="Facilities", sentiment="negative", severity="high", summary="Short summary.", confidence=0.9):
    return {"theme": theme, "sentiment": sentiment, "severity": severity, "summary": summary, "confidence": confidence}


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


def write_prompts(folder, themes='["Facilities", "Assessment"]', prompt="Themes: {themes}", summary="Summarise."):
    paths = (folder / "themes.json", folder / "prompt.txt", folder / "summary.txt")
    for path, content in zip(paths, (themes, prompt, summary)):
        path.write_text(content, encoding="utf-8")
    return [str(path) for path in paths]


@pytest.fixture
def prompts(tmp_path):
    return PromptLibrary(*write_prompts(tmp_path))


# Records every wait instead of sleeping
@pytest.fixture
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr(ai_manager.time, "sleep", waits.append)
    return waits


@pytest.fixture
def ledger_path(tmp_path):
    return tmp_path / "ledger.json"


def build_manager(client, prompts, ledger_path, samples=1, reporter=None):
    return AIManager(client, "test-key", prompts, reporter or RecordingProgressReporter(), samples, str(ledger_path))


def today_usage(ledger_path, model="stub-model"):
    log = json.loads(ledger_path.read_text(encoding="utf-8"))
    day = next(iter(log))
    return log[day]["test-key"]["candidates"][f"groq/{model}"]


# Interfaces and abstract classes
@pytest.mark.parametrize("abstract_class", [LLMClient, AITask])
def test_abstract_classes_cannot_be_instantiated(abstract_class):
    with pytest.raises(TypeError):
        abstract_class()


# The stub stands in for GroqClient, and both tasks run through the same retry loop
def test_stub_substitutes_for_groq_client(prompts, ledger_path, sleeps):
    client = StubLLMClient([json.dumps(classification()), json.dumps(summary_output())])
    manager = build_manager(client, prompts, ledger_path)

    assert isinstance(client, LLMClient)
    assert manager.classify_entries([ENTRY], [])[0]["theme"] == "Facilities"
    assert manager.summarise(STATS) == summary_output()


def test_both_tasks_are_ai_tasks(prompts):
    assert isinstance(ClassificationTask(ENTRY, prompts.system_prompt, []), AITask)
    assert isinstance(SummaryTask(STATS, prompts.summary_prompt), AITask)


# Call 1: aggregating samples
def test_majority_and_pass_through(prompts, ledger_path, sleeps):
    samples = [
        classification(theme="Facilities", summary="Low confidence.", confidence=0.5),
        classification(theme="Facilities", summary="High confidence.", confidence=0.8),
        classification(theme="Assessment", summary="Outvoted.", confidence=0.99),
    ]
    entry = {**ENTRY, "course": "INF1103"}
    client = StubLLMClient([json.dumps(sample) for sample in samples])

    record = build_manager(client, prompts, ledger_path, samples=3).classify_entries([entry], [])[0]

    assert record == {
        **entry,
        "theme": "Facilities",
        "sentiment": "negative",
        "severity": "high",
        "summary": "High confidence.",
        "confidence": 0.8,
        "agreement": 0.67,
    }


def test_no_majority_falls_back_to_first_sample(prompts, ledger_path, sleeps):
    samples = [classification(theme=theme) for theme in ("Facilities", "Assessment", "Workload")]
    client = StubLLMClient([json.dumps(sample) for sample in samples])

    record = build_manager(client, prompts, ledger_path, samples=3).classify_entries([ENTRY], [])[0]

    assert record["theme"] == "Facilities"
    assert record["agreement"] == 0.33


def test_failed_sample_leaves_entry_out_and_batch_continues(prompts, ledger_path, sleeps):
    second = {**ENTRY, "feedback_id": "fb_002"}
    client = StubLLMClient([
        json.dumps(classification()),
        error(LLMRequestError.REQUEST, retryable=False),
        json.dumps(classification(theme="Assessment")),
        json.dumps(classification(theme="Assessment")),
    ])

    records = build_manager(client, prompts, ledger_path, samples=2).classify_entries([ENTRY, second], [])

    assert [record["feedback_id"] for record in records] == ["fb_002"]


# Call 1: coined themes
def test_coined_themes_are_offered_back_to_the_model(prompts, ledger_path, sleeps):
    second = {**ENTRY, "feedback_id": "fb_002"}
    client = StubLLMClient([json.dumps(classification(theme="Coined")), json.dumps(classification())])

    build_manager(client, prompts, ledger_path).classify_entries([ENTRY, second], [{"theme": "Stored"}])

    payloads = [json.loads(call["messages"][1]["content"]) for call in client.calls]
    assert payloads[0] == {"text": ENTRY["text"], "existing_new_themes": ["Stored"]}
    assert payloads[1]["existing_new_themes"] == ["Stored", "Coined"]


def test_no_coined_themes_leaves_the_key_out(prompts, ledger_path, sleeps):
    client = StubLLMClient([json.dumps(classification())])

    build_manager(client, prompts, ledger_path).classify_entries([ENTRY], [])

    assert json.loads(client.calls[0]["messages"][1]["content"]) == {"text": ENTRY["text"]}


# Retry loop
def test_retries_until_output_validates(prompts, ledger_path, sleeps):
    client = StubLLMClient(["not json", json.dumps({"theme": "incomplete"}), json.dumps(classification())])

    records = build_manager(client, prompts, ledger_path).classify_entries([ENTRY], [])

    assert len(records) == 1
    assert len(client.calls) == 3
    # Non-JSON content backs off; a schema mismatch and a success follow the client's wait
    assert sleeps == [BACKOFF_BASE_S, 0.5, 0.5]
    assert today_usage(ledger_path)["total_tokens"] == 300


def test_error_without_wait_uses_backoff_and_error_with_wait_uses_it(prompts, ledger_path, sleeps):
    client = StubLLMClient([error(), error(wait_seconds=7.5), json.dumps(classification())])

    build_manager(client, prompts, ledger_path).classify_entries([ENTRY], [])

    assert sleeps == [BACKOFF_BASE_S, 7.5, 0.5]


def test_gives_up_after_max_attempts(prompts, ledger_path, sleeps):
    client = StubLLMClient([error() for _ in range(MAX_ATTEMPTS)])

    assert build_manager(client, prompts, ledger_path).classify_entries([ENTRY], []) == []
    assert len(client.calls) == MAX_ATTEMPTS
    # A request whose every attempt failed is still recorded, with 0
    assert today_usage(ledger_path)["requests"] == [{"feedback_id": ENTRY["feedback_id"], "total_tokens": 0}]


def test_non_retryable_error_stops_after_one_call(prompts, ledger_path, sleeps):
    client = StubLLMClient([error(LLMRequestError.AUTH, retryable=False)])

    assert build_manager(client, prompts, ledger_path).classify_entries([ENTRY], []) == []
    assert len(client.calls) == 1
    assert sleeps == []


# Call 2
def test_summarise_sends_its_own_limits(prompts, ledger_path, sleeps):
    client = StubLLMClient([json.dumps(summary_output())])

    build_manager(client, prompts, ledger_path).summarise(STATS)

    call = client.calls[0]
    assert call["token_margin"] == SUMMARY_TOKEN_MARGIN
    assert call["max_completion_tokens"] == SUMMARY_MAX_COMPLETION_TOKENS
    assert json.loads(call["messages"][1]["content"]) == STATS
    assert today_usage(ledger_path)["requests"][0]["feedback_id"] == "summary"


def test_summarise_returns_none_when_every_attempt_fails(prompts, ledger_path, sleeps):
    client = StubLLMClient([json.dumps(summary_output(("Assessment", "Facilities")))] * MAX_ATTEMPTS)

    assert build_manager(client, prompts, ledger_path).summarise(STATS) is None


# Response validation
def test_classification_uses_its_own_limits(prompts):
    task = ClassificationTask(ENTRY, prompts.system_prompt, [])

    assert task.request_id == ENTRY["feedback_id"]
    assert task.token_margin == CLASSIFY_TOKEN_MARGIN
    assert task.max_completion_tokens is None


@pytest.mark.parametrize("bad_result", [
    "not a dict",
    {"theme": "missing fields"},
    {**classification(), "extra": 1},
    classification(theme=" "),
    classification(theme=1),
    classification(sentiment="angry"),
    classification(severity="urgent"),
    classification(confidence=1.5),
    classification(confidence=-0.1),
    classification(confidence="high"),
    classification(summary=" "),
    classification(summary="word " * (MAX_SUMMARY_WORDS + 1)),
])
def test_classification_rejects_bad_output(prompts, bad_result):
    assert ClassificationTask(ENTRY, prompts.system_prompt, []).validate(bad_result) is False


def test_classification_accepts_valid_output(prompts):
    assert ClassificationTask(ENTRY, prompts.system_prompt, []).validate(classification()) is True


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


def test_parse_raises_on_non_json(prompts):
    task = ClassificationTask(ENTRY, prompts.system_prompt, [])

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
def test_ledger_keeps_the_harness_schema(ledger_path):
    ledger = TokenLedger("some-model", str(ledger_path))

    ledger.record("test-key", "fb_001", 100)
    ledger.record("test-key", "fb_002", 0)
    ledger.record("test-key", "fb_003", 50)

    log = json.loads(ledger_path.read_text(encoding="utf-8"))
    key_log = next(iter(log.values()))["test-key"]
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


def test_corrupt_ledger_is_not_overwritten(ledger_path, caplog):
    ledger_path.write_text("{corrupt", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        TokenLedger("some-model", str(ledger_path)).record("test-key", "fb_001", 100)

    assert ledger_path.read_text(encoding="utf-8") == "{corrupt"
    assert "unreadable" in caplog.text


def test_ledger_warns_once_when_crossing_the_threshold(ledger_path, caplog):
    ledger = TokenLedger("openai/gpt-oss-120b", str(ledger_path))

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


def test_prompt_library_loads_the_real_config():
    prompts = PromptLibrary()

    assert prompts.themes
    assert "{themes}" not in prompts.system_prompt
    assert prompts.summary_prompt


@pytest.mark.parametrize("themes", ['"Facilities"', "[]", '[""]', "[1]"])
def test_prompt_library_rejects_bad_themes(tmp_path, themes):
    with pytest.raises(ValueError):
        PromptLibrary(*write_prompts(tmp_path, themes=themes))


@pytest.mark.parametrize("prompt", ["No placeholder.", "{themes} twice {themes}"])
def test_prompt_library_rejects_bad_placeholder(tmp_path, prompt):
    with pytest.raises(ValueError):
        PromptLibrary(*write_prompts(tmp_path, prompt=prompt))


def test_prompt_library_rejects_empty_summary_prompt(tmp_path):
    with pytest.raises(ValueError):
        PromptLibrary(*write_prompts(tmp_path, summary="  \n"))


def test_find_new_themes(prompts):
    records = [{"theme": "Facilities"}, {"theme": "Coined"}, {"theme": "Coined"}, {"theme": ""}, {}]

    assert prompts.find_new_themes(records, ["Earlier"]) == ["Earlier", "Coined"]
