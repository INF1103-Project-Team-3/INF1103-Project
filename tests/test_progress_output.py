import io
import json
import threading

import pytest

import ai_manager
from ai_manager import AIManager, BACKOFF_BASE_S, MAX_ATTEMPTS
from batch_progress import BatchProgress
from console_progress_reporter import CLEAR_LINE, ConsoleProgressReporter
from llm_request_error import LLMRequestError
from progress_reporter import ProgressReporter
from prompt_library import PromptLibrary
from recording_progress_reporter import RecordingProgressReporter
from stub_llm_client import StubLLMClient
from token_ledger import TokenLedger

ENTRY = {"feedback_id": "fb_001", "text": "The slides move too fast.", "timestamp": "2026-09-15T10:32:00"}
STATS = {"themes": [{"theme": "Facilities"}]}
GOOD = json.dumps({"theme": "Facilities", "alternative_themes": [], "sentiment": "negative", "severity": "high"})
GOOD_SUMMARY = json.dumps({"overall_summary": "All.",
                           "theme_actions": [{"theme": "Facilities", "suggested_action": "Fix."}]})


def fake_clock(*times):
    """Return a clock that gives these times in order, then keeps the last one."""
    remaining = list(times)
    return lambda: remaining.pop(0) if len(remaining) > 1 else remaining[0]


@pytest.fixture
def prompts(tmp_path):
    paths = (tmp_path / "themes.json", tmp_path / "prompt.txt", tmp_path / "summary.txt")
    for path, content in zip(paths, ('["Facilities"]', "Themes: {themes}", "Summarise.")):
        path.write_text(content, encoding="utf-8")
    return PromptLibrary(*[str(path) for path in paths])


@pytest.fixture
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr(ai_manager.time, "sleep", waits.append)
    return waits


def build_manager(client, prompts, tmp_path, reporter):
    return AIManager(client, "main", prompts, reporter, str(tmp_path / "ledger.json"))


def discard(record):
    pass


# Interface
def test_progress_reporter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        ProgressReporter()


@pytest.mark.parametrize("reporter_class", [RecordingProgressReporter, ConsoleProgressReporter])
def test_reporters_substitute_for_the_interface(reporter_class, prompts, tmp_path, sleeps):
    reporter = reporter_class(io.StringIO()) if reporter_class is ConsoleProgressReporter else reporter_class()
    manager = build_manager(StubLLMClient([GOOD, GOOD_SUMMARY]), prompts, tmp_path, reporter)

    assert isinstance(reporter, ProgressReporter)
    assert manager.classify_entries([ENTRY], [], discard)[0][0]["ai_theme"] == "Facilities"
    assert manager.summarise(STATS) is not None


# Events from AIManager
def test_events_for_a_record_that_succeeds_first_time(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient([GOOD]), prompts, tmp_path, reporter).classify_entries([ENTRY], [], discard)

    assert reporter.events == [
        ("batch_start", "Classifying 1 records", ["stub-model", "1 sample each", "key: main"]),
        ("attempt_start", "fb_001", 1, MAX_ATTEMPTS),
        ("wait", 0.5, "rate limit"),
        ("record_ok", "fb_001", "Facilities / negative / high"),
        ("batch_end", 100, None),
    ]


def test_events_for_retries(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()
    server_error = LLMRequestError("server error (HTTP 500)", LLMRequestError.SERVER, True)
    client = StubLLMClient(["not json", server_error, GOOD])

    build_manager(client, prompts, tmp_path, reporter).classify_entries([ENTRY], [], discard)

    retries = [event for event in reporter.events if event[0] in ("attempt_failed", "wait")]
    assert retries == [
        ("attempt_failed", "fb_001", 1, MAX_ATTEMPTS, "invalid output"),
        ("wait", BACKOFF_BASE_S, "backoff"),
        ("attempt_failed", "fb_001", 2, MAX_ATTEMPTS, "server error (HTTP 500)"),
        ("wait", BACKOFF_BASE_S**2, "backoff"),
        ("wait", 0.5, "rate limit"),
    ]


def test_events_when_every_attempt_fails(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient(["not json"] * MAX_ATTEMPTS), prompts, tmp_path, reporter).classify_entries([ENTRY], [], discard)

    assert reporter.names.count("attempt_failed") == MAX_ATTEMPTS - 1
    assert ("record_failed", "fb_001", f"no valid output after {MAX_ATTEMPTS} attempts: invalid output") in reporter.events
    assert "record_ok" not in reporter.names
    assert reporter.names[-1] == "batch_end"


def test_events_when_a_failure_cannot_be_retried(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)

    build_manager(StubLLMClient([rejected]), prompts, tmp_path, reporter).classify_entries([ENTRY], [], discard)

    assert ("record_failed", "fb_001", "key rejected (HTTP 401)") in reporter.events
    assert ("batch_stopped", "key rejected (HTTP 401)", "fb_001") in reporter.events
    assert "attempt_failed" not in reporter.names
    assert "wait" not in reporter.names


def test_stop_comes_after_the_failed_record_and_before_the_batch_end(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)

    build_manager(StubLLMClient([rejected]), prompts, tmp_path, reporter).classify_entries([ENTRY], [], discard)

    assert reporter.names[-3:] == ["record_failed", "batch_stopped", "batch_end"]


def test_invalid_output_does_not_report_a_stop(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient(["not json"] * MAX_ATTEMPTS), prompts, tmp_path, reporter).classify_entries([ENTRY], [], discard)

    assert "batch_stopped" not in reporter.names


def test_summary_is_a_batch_of_one_that_reports_retries(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient(["not json", GOOD_SUMMARY]), prompts, tmp_path, reporter).summarise(STATS)

    assert reporter.events[0] == ("batch_start", "Summarising this run", ["stub-model", "key: main"])
    assert ("record_ok", "summary", "1 retry") in reporter.events
    assert reporter.names[-1] == "batch_end"


def test_failed_summary_ends_its_batch(prompts, tmp_path, sleeps):
    reporter = RecordingProgressReporter()

    result = build_manager(StubLLMClient(["not json"] * MAX_ATTEMPTS), prompts, tmp_path, reporter).summarise(STATS)

    assert result is None
    assert reporter.names[-2:] == ["record_failed", "batch_end"]


def test_ai_manager_never_prints(prompts, tmp_path, sleeps, capsys):
    client = StubLLMClient(["not json", GOOD, GOOD_SUMMARY])
    manager = build_manager(client, prompts, tmp_path, RecordingProgressReporter())

    manager.classify_entries([ENTRY], [], discard)
    manager.summarise(STATS)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# BatchProgress
def test_batch_progress_counts():
    progress = BatchProgress(3)

    progress.finish_ok()
    progress.finish_failed("fb_002")

    assert (progress.total, progress.done, progress.ok, progress.failed) == (3, 2, 1, 1)
    assert progress.pending_ids == ["fb_002"]


def test_eta_is_unknown_until_a_record_finishes():
    assert BatchProgress(3).eta_seconds is None


def test_eta_is_average_per_finished_record_times_records_left():
    progress = BatchProgress(4, fake_clock(100, 110, 130))

    progress.finish_ok()  # at 110
    assert progress.eta_seconds == pytest.approx(30)
    progress.finish_failed("fb_002")  # at 130
    assert progress.eta_seconds == pytest.approx(30)


def test_record_counters_reset_but_batch_tokens_do_not():
    progress = BatchProgress(2)

    progress.start_record()
    progress.add_tokens(100)
    progress.add_retry()
    assert (progress.record_tokens, progress.record_retries) == (100, 1)

    progress.start_record()
    progress.add_tokens(50)
    assert (progress.record_tokens, progress.record_retries) == (50, 0)
    assert progress.tokens == 150


def test_stopping_records_the_reason_and_the_untried_ids():
    progress = BatchProgress(3)
    assert progress.stopped is False

    progress.finish_failed("fb_001")
    progress.stop("connection lost", "fb_001")
    progress.leave_pending(["fb_002", "fb_003"])

    assert progress.stopped is True
    assert (progress.stop_reason, progress.stopped_after) == ("connection lost", "fb_001")
    assert progress.pending_ids == ["fb_001", "fb_002", "fb_003"]
    assert progress.done == 1


# TokenLedger's total for the done line
def test_today_total(tmp_path):
    ledger = TokenLedger("some-model", str(tmp_path / "ledger.json"))

    assert ledger.today_total("main") == 0
    ledger.record("main", "fb_001", 100)
    ledger.record("main", "fb_002", 50)
    ledger.record("other", "fb_003", 7)
    assert ledger.today_total("main") == 150


def test_today_total_is_none_when_the_ledger_is_corrupt(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{corrupt", encoding="utf-8")

    assert TokenLedger("some-model", str(path)).today_total("main") is None


def test_daily_limit():
    assert TokenLedger("openai/gpt-oss-120b", "unused").daily_limit == 200_000
    assert TokenLedger("some-model", "unused").daily_limit is None


# ConsoleProgressReporter, plain lines
def test_plain_output_for_a_batch():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    progress = BatchProgress(2, fake_clock(0, 0, 0, 243))

    reporter.on_batch_start("Classifying 2 records", ["model", "1 sample each", "key: main"], progress)
    reporter.on_attempt_start("fb_001", 1, 3)
    reporter.on_attempt_failed("fb_001", 1, 3, "invalid output")
    reporter.on_wait(11.3, "rate limit")
    reporter.on_wait(0.5, "rate limit")
    progress.start_record()
    progress.add_tokens(1702)
    progress.finish_failed("fb_001")
    reporter.on_record_failed("fb_001", "no valid output after 3 attempts: invalid output", progress)
    reporter.on_batch_end(progress, 61_200, 200_000)

    lines = stream.getvalue().splitlines()
    assert lines[0] == "[AI] Classifying 2 records | model | 1 sample each | key: main"
    assert lines[1] == "  retry fb_001  attempt 1/3: invalid output"
    assert lines[2] == "  wait  rate limit: 11.3s"
    assert lines[3] == "  FAIL  fb_001  left pending: no valid output after 3 attempts: invalid output"
    assert lines[4].startswith("[##########..........] 1/2  50%  ETA ")
    assert lines[4].endswith("ok 0  failed 1")
    assert lines[5] == "[AI] Done in 4m 03s: 0 ok, 1 pending (fb_001) | 1,702 tokens | today 61,200 / 200,000 (local estimate)"
    assert len(lines) == 6


def test_plain_output_has_no_control_characters_or_thread():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    progress = BatchProgress(1)

    reporter.on_batch_start("Title", [], progress)
    assert not [thread for thread in threading.enumerate() if thread.name == "ai-progress-timer"]
    reporter.on_attempt_start("fb_001", 1, 3)
    progress.finish_ok()
    reporter.on_record_ok("fb_001", "Facilities / negative / high", progress)
    reporter.on_batch_end(progress, None, None)

    assert "\r" not in stream.getvalue()
    assert "\x1b" not in stream.getvalue()


def test_ok_line_gives_description_time_and_tokens():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    progress = BatchProgress(1, fake_clock(0, 10, 11.8))

    reporter.on_batch_start("Title", [], progress)
    progress.start_record()
    progress.add_tokens(1702)
    progress.finish_ok()
    reporter.on_record_ok("fb_001", "Facilities / negative / high", progress)

    assert "  ok    fb_001  Facilities / negative / high   1.8s  1,702 tokens\n" in stream.getvalue()


def test_stop_line_and_done_line_for_a_stopped_batch():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    progress = BatchProgress(4)

    reporter.on_batch_start("Title", [], progress)
    progress.finish_ok()
    progress.finish_failed("fb_002")
    progress.stop("connection lost", "fb_002")
    progress.leave_pending(["fb_003", "fb_004"])
    reporter.on_batch_stopped(progress)
    reporter.on_batch_end(progress, None, None)

    lines = stream.getvalue().splitlines()
    assert lines[1] == "  STOP  connection lost after fb_002: 2 records left pending"
    assert lines[2].endswith("1 ok, 3 pending (fb_002, fb_003, fb_004) | 0 tokens")


@pytest.mark.parametrize("tokens_today, limit, ending", [
    (61_200, None, "| 0 tokens | today 61,200 (local estimate)"),
    (None, 200_000, "| 0 tokens"),
])
def test_done_line_without_a_limit_or_a_readable_ledger(tokens_today, limit, ending):
    stream = io.StringIO()
    progress = BatchProgress(1)
    reporter = ConsoleProgressReporter(stream)

    reporter.on_batch_start("Title", [], progress)
    reporter.on_batch_end(progress, tokens_today, limit)

    assert stream.getvalue().splitlines()[-1].endswith(ending)


# ConsoleProgressReporter, live bar
def test_live_output_redraws_the_bar_and_shows_the_attempt():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream, live=True)
    progress = BatchProgress(2)

    reporter.on_batch_start("Title", [], progress)
    reporter.on_attempt_start("fb_001", 2, 3)
    reporter.on_batch_end(progress, None, None)

    assert CLEAR_LINE in stream.getvalue()
    assert "ETA --" in stream.getvalue()
    assert "| fb_001 attempt 2/3 0s" in stream.getvalue()


def test_live_timer_thread_stops_cleanly():
    reporter = ConsoleProgressReporter(io.StringIO(), live=True)
    progress = BatchProgress(1)

    reporter.on_batch_start("Title", [], progress)
    assert [thread for thread in threading.enumerate() if thread.name == "ai-progress-timer"]

    reporter.on_batch_end(progress, None, None)
    assert not [thread for thread in threading.enumerate() if thread.name == "ai-progress-timer"]


def test_output_does_not_contain_the_api_key(prompts, tmp_path, sleeps):
    stream = io.StringIO()
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)
    manager = build_manager(StubLLMClient([rejected]), prompts, tmp_path, ConsoleProgressReporter(stream))

    manager.classify_entries([ENTRY], [], discard)

    assert "key rejected (HTTP 401)" in stream.getvalue()
    assert "Bearer" not in stream.getvalue()
