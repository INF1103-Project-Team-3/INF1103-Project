import io
import json
import threading
from types import SimpleNamespace

import pytest

from managers.ai_manager import (
    AIManager, BatchProgress, ConsoleProgressReporter, ProgressReporter, PromptLibrary, ai_manager as ai_manager_module
)
from managers.ai_manager.progress_tracker import ProgressTracker
from managers.ai_manager.ai_manager import BACKOFF_BASE_S, MAX_ATTEMPTS
from managers.ai_manager.console_progress_reporter import CLEAR_LINE
from managers.ai_manager.llm_request_error import LLMRequestError
from managers.ai_manager.token_ledger import TokenLedger
from managers.models import FeedbackRecord
from in_memory_token_log import InMemoryTokenLog
from recording_progress_reporter import RecordingProgressReporter
from stub_llm_client import StubLLMClient

USER = {"theme": "Assessment", "sentiment": "neutral", "severity": "low"}
RESULT = SimpleNamespace(to_dict=lambda: {  # stands in for AggregationResult
    "total_entries": 1, "counted_entries": 1, "sentiment_counts": {"positive": 0, "neutral": 0, "negative": 1},
    "themes": [{"theme": "Facilities", "count": 1, "severity_counts": {"low": 0, "medium": 0, "high": 1, "critical": 0},
                "avg_sentiment": -1.0}],
})
GOOD = json.dumps({"theme": "Facilities", "sentiment": "negative", "severity": "high", "summary": "Lift broken."})
GOOD_SUMMARY = json.dumps({"overall_summary": "All.",
                           "theme_actions": [{"theme": "Facilities", "suggested_action": "Fix."}]})


def fake_clock(*times):
    """Return a clock that gives these times in order, then keeps the last one."""
    remaining = list(times)
    return lambda: remaining.pop(0) if len(remaining) > 1 else remaining[0]


@pytest.fixture
def prompts():
    return PromptLibrary("Themes: {themes}", "Summarise.", ["Facilities"])


@pytest.fixture
def entry():
    return FeedbackRecord("fb_001", "The slides move too fast.", "2026-09-15T10:32:00", None, USER)


@pytest.fixture
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr(ai_manager_module.time, "sleep", waits.append)
    return waits


def build_manager(client, prompts, reporter):
    token_log = InMemoryTokenLog()
    return AIManager(client, "main", prompts, reporter, token_log.load, token_log.save)


def discard(record):
    pass


# Interface
def test_progress_reporter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        ProgressReporter()


@pytest.mark.parametrize("reporter_class", [RecordingProgressReporter, ConsoleProgressReporter])
def test_reporters_substitute_for_the_interface(reporter_class, prompts, sleeps, entry):
    reporter = reporter_class(io.StringIO()) if reporter_class is ConsoleProgressReporter else reporter_class()
    manager = build_manager(StubLLMClient([GOOD, GOOD_SUMMARY]), prompts, reporter)

    assert isinstance(reporter, ProgressReporter)
    assert manager.classify_entries([entry], [], discard)[0][0].ai["theme"] == "Facilities"
    assert manager.summarise(RESULT, []) is not None


# Events from AIManager
def test_events_for_a_record_that_succeeds_first_time(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient([GOOD]), prompts, reporter).classify_entries([entry], [], discard)

    assert reporter.events == [
        ("batch_start", "Classifying 1 records", ["stub-model", "1 sample each", "key: main"]),
        ("attempt_start", "fb_001", 1, MAX_ATTEMPTS),
        ("wait", 0.5, "rate limit"),
        ("record_ok", "fb_001", "Facilities / negative / high"),
        ("batch_end", 100, None),
    ]


def test_events_for_retries(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()
    server_error = LLMRequestError("server error (HTTP 500)", LLMRequestError.SERVER, True)
    client = StubLLMClient(["not json", server_error, GOOD])

    build_manager(client, prompts, reporter).classify_entries([entry], [], discard)

    retries = [event for event in reporter.events if event[0] in ("attempt_failed", "wait")]
    assert retries == [
        ("attempt_failed", "fb_001", 1, MAX_ATTEMPTS, "invalid output"),
        ("wait", BACKOFF_BASE_S, "backoff"),
        ("attempt_failed", "fb_001", 2, MAX_ATTEMPTS, "server error (HTTP 500)"),
        ("wait", BACKOFF_BASE_S**2, "backoff"),
        ("wait", 0.5, "rate limit"),
    ]


def test_events_when_every_attempt_fails(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient(["not json"] * MAX_ATTEMPTS), prompts, reporter).classify_entries([entry], [], discard)

    assert reporter.names.count("attempt_failed") == MAX_ATTEMPTS - 1
    assert ("record_failed", "fb_001", f"no valid output after {MAX_ATTEMPTS} attempts: invalid output") in reporter.events
    assert "record_ok" not in reporter.names
    assert reporter.names[-1] == "batch_end"


def test_events_when_a_failure_cannot_be_retried(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)

    build_manager(StubLLMClient([rejected]), prompts, reporter).classify_entries([entry], [], discard)

    assert ("record_failed", "fb_001", "key rejected (HTTP 401)") in reporter.events
    assert ("batch_stopped", "key rejected (HTTP 401)", "fb_001") in reporter.events
    assert "attempt_failed" not in reporter.names
    assert "wait" not in reporter.names


def test_stop_comes_after_the_failed_record_and_before_the_batch_end(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)

    build_manager(StubLLMClient([rejected]), prompts, reporter).classify_entries([entry], [], discard)

    assert reporter.names[-3:] == ["record_failed", "batch_stopped", "batch_end"]


def test_invalid_output_does_not_report_a_stop(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient(["not json"] * MAX_ATTEMPTS), prompts, reporter).classify_entries([entry], [], discard)

    assert "batch_stopped" not in reporter.names


def test_summary_is_a_batch_of_one_that_reports_retries(prompts, sleeps):
    reporter = RecordingProgressReporter()

    build_manager(StubLLMClient(["not json", GOOD_SUMMARY]), prompts, reporter).summarise(RESULT, [])

    assert reporter.events[0] == ("batch_start", "Summarising this run", ["stub-model", "key: main"])
    assert ("record_ok", "summary", "1 retry") in reporter.events
    assert reporter.names[-1] == "batch_end"


def test_failed_summary_ends_its_batch(prompts, sleeps):
    reporter = RecordingProgressReporter()

    result = build_manager(StubLLMClient(["not json"] * MAX_ATTEMPTS), prompts, reporter).summarise(RESULT, [])

    assert result is None
    assert reporter.names[-2:] == ["record_failed", "batch_end"]


def test_ai_manager_never_prints(prompts, sleeps, capsys, entry):
    client = StubLLMClient(["not json", GOOD, GOOD_SUMMARY])
    manager = build_manager(client, prompts, RecordingProgressReporter())

    manager.classify_entries([entry], [], discard)
    manager.summarise(RESULT, [])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# ProgressTracker and its read-only BatchProgress view
def test_batch_progress_counts():
    tracker = ProgressTracker(3)
    progress = tracker.progress

    tracker.finish_ok()
    tracker.finish_failed("fb_002")

    assert (progress.total, progress.done, progress.ok, progress.failed) == (3, 2, 1, 1)
    assert progress.pending_ids == ["fb_002"]


def test_batch_progress_is_a_live_read_only_view():
    tracker = ProgressTracker(2)
    progress = tracker.progress

    tracker.finish_ok()  # the view shows the tracker's current counts
    assert (progress.done, progress.ok) == (1, 1)
    for mutator in ("start_record", "add_tokens", "add_retry", "finish_ok", "finish_failed", "stop", "leave_pending"):
        assert not hasattr(progress, mutator), mutator
    with pytest.raises(AttributeError):
        progress.ok = 5


def test_reporters_get_the_read_only_view(prompts, sleeps, entry):
    reporter = RecordingProgressReporter()
    build_manager(StubLLMClient([GOOD]), prompts, reporter).classify_entries([entry], [], discard)

    assert isinstance(reporter.last_progress, BatchProgress)
    assert not isinstance(reporter.last_progress, ProgressTracker)


def test_eta_is_unknown_until_a_record_finishes():
    assert ProgressTracker(3).progress.eta_seconds is None


def test_eta_is_average_per_finished_record_times_records_left():
    tracker = ProgressTracker(4, fake_clock(100, 110, 130))
    progress = tracker.progress

    tracker.finish_ok()  # at 110
    assert progress.eta_seconds == pytest.approx(30)
    tracker.finish_failed("fb_002")  # at 130
    assert progress.eta_seconds == pytest.approx(30)


def test_record_counters_reset_but_batch_tokens_do_not():
    tracker = ProgressTracker(2)
    progress = tracker.progress

    tracker.start_record()
    tracker.add_tokens(100)
    tracker.add_retry()
    assert (progress.record_tokens, progress.record_retries) == (100, 1)

    tracker.start_record()
    tracker.add_tokens(50)
    assert (progress.record_tokens, progress.record_retries) == (50, 0)
    assert progress.tokens == 150


def test_stopping_records_the_reason_and_the_untried_ids():
    tracker = ProgressTracker(3)
    progress = tracker.progress
    assert progress.stopped is False

    tracker.finish_failed("fb_001")
    tracker.stop("connection lost", "fb_001")
    tracker.leave_pending(["fb_002", "fb_003"])

    assert progress.stopped is True
    assert (progress.stop_reason, progress.stopped_after) == ("connection lost", "fb_001")
    assert progress.pending_ids == ["fb_001", "fb_002", "fb_003"]
    assert progress.done == 1


# TokenLedger's total for the done line
def test_today_total():
    token_log = InMemoryTokenLog()
    ledger = TokenLedger("some-model", token_log.load, token_log.save)

    assert ledger.today_total("main") == 0
    ledger.record("main", "fb_001", 100)
    ledger.record("main", "fb_002", 50)
    ledger.record("other", "fb_003", 7)
    assert ledger.today_total("main") == 150


def test_today_total_is_none_when_the_ledger_is_corrupt():
    token_log = InMemoryTokenLog()
    token_log.corrupt = True

    assert TokenLedger("some-model", token_log.load, token_log.save).today_total("main") is None


def test_daily_limit():
    assert TokenLedger("openai/gpt-oss-120b", None, None).daily_limit == 200_000
    assert TokenLedger("some-model", None, None).daily_limit is None


# ConsoleProgressReporter, plain lines
def test_plain_output_for_a_batch():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    tracker = ProgressTracker(2, fake_clock(0, 0, 0, 243))
    progress = tracker.progress

    reporter.on_batch_start("Classifying 2 records", ["model", "1 sample each", "key: main"], progress)
    reporter.on_attempt_start("fb_001", 1, 3)
    reporter.on_attempt_failed("fb_001", 1, 3, "invalid output")
    reporter.on_wait(11.3, "rate limit")
    reporter.on_wait(0.5, "rate limit")
    tracker.start_record()
    tracker.add_tokens(1702)
    tracker.finish_failed("fb_001")
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
    tracker = ProgressTracker(1)
    progress = tracker.progress

    reporter.on_batch_start("Title", [], progress)
    assert not [thread for thread in threading.enumerate() if thread.name == "ai-progress-timer"]
    reporter.on_attempt_start("fb_001", 1, 3)
    tracker.finish_ok()
    reporter.on_record_ok("fb_001", "Facilities / negative / high", progress)
    reporter.on_batch_end(progress, None, None)

    assert "\r" not in stream.getvalue()
    assert "\x1b" not in stream.getvalue()


def test_ok_line_gives_description_time_and_tokens():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    tracker = ProgressTracker(1, fake_clock(0, 10, 11.8))
    progress = tracker.progress

    reporter.on_batch_start("Title", [], progress)
    tracker.start_record()
    tracker.add_tokens(1702)
    tracker.finish_ok()
    reporter.on_record_ok("fb_001", "Facilities / negative / high", progress)

    assert "  ok    fb_001  Facilities / negative / high   1.8s  1,702 tokens\n" in stream.getvalue()


def test_stop_line_and_done_line_for_a_stopped_batch():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream)
    tracker = ProgressTracker(4)
    progress = tracker.progress

    reporter.on_batch_start("Title", [], progress)
    tracker.finish_ok()
    tracker.finish_failed("fb_002")
    tracker.stop("connection lost", "fb_002")
    tracker.leave_pending(["fb_003", "fb_004"])
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
    tracker = ProgressTracker(1)
    progress = tracker.progress
    reporter = ConsoleProgressReporter(stream)

    reporter.on_batch_start("Title", [], progress)
    reporter.on_batch_end(progress, tokens_today, limit)

    assert stream.getvalue().splitlines()[-1].endswith(ending)


# ConsoleProgressReporter, live bar
def test_live_output_redraws_the_bar_and_shows_the_attempt():
    stream = io.StringIO()
    reporter = ConsoleProgressReporter(stream, live=True)
    tracker = ProgressTracker(2)
    progress = tracker.progress

    reporter.on_batch_start("Title", [], progress)
    reporter.on_attempt_start("fb_001", 2, 3)
    reporter.on_batch_end(progress, None, None)

    assert CLEAR_LINE in stream.getvalue()
    assert "ETA --" in stream.getvalue()
    assert "| fb_001 attempt 2/3 0s" in stream.getvalue()


def test_live_timer_thread_stops_cleanly():
    reporter = ConsoleProgressReporter(io.StringIO(), live=True)
    tracker = ProgressTracker(1)
    progress = tracker.progress

    reporter.on_batch_start("Title", [], progress)
    assert [thread for thread in threading.enumerate() if thread.name == "ai-progress-timer"]

    reporter.on_batch_end(progress, None, None)
    assert not [thread for thread in threading.enumerate() if thread.name == "ai-progress-timer"]


def test_output_does_not_contain_the_api_key(prompts, sleeps, entry):
    stream = io.StringIO()
    rejected = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)
    manager = build_manager(StubLLMClient([rejected]), prompts, ConsoleProgressReporter(stream))

    manager.classify_entries([entry], [], discard)

    assert "key rejected (HTTP 401)" in stream.getvalue()
    assert "Bearer" not in stream.getvalue()
