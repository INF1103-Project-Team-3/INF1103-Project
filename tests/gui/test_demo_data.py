# The demo's stand-ins need no Qt, so these run everywhere, including Docker CI.

from managers.ai_manager import ProgressReporter

from demo.fake_data_manager import FakeDataManager
from demo.fake_pipeline import FakePipeline
from demo.sample_data import CHECKED_COUNT, build_sample_records, load_ai_answers


class RecordingReporter(ProgressReporter):
    def __init__(self):
        self.events = []

    def on_batch_start(self, title, details, progress): self.events.append("start")
    def on_attempt_start(self, request_id, attempt, max_attempts): pass
    def on_attempt_failed(self, request_id, attempt, max_attempts, reason): self.events.append("retry")
    def on_wait(self, seconds, reason): self.events.append("wait")
    def on_record_ok(self, request_id, description, progress): self.events.append(request_id)
    def on_record_failed(self, request_id, reason, progress): pass
    def on_batch_stopped(self, progress): pass
    def on_batch_end(self, progress, tokens_today, daily_limit): self.events.append("end")


class Session:
    def __init__(self, decisions=(), actions=()):
        self.records, self.source_file = [], None
        self.decisions, self.actions = list(decisions), list(actions)


def test_sample_records_start_partly_checked():
    data = FakeDataManager(build_sample_records())
    assert len(data.load_records()) == CHECKED_COUNT
    assert len(data.load_pending()) == 12 - CHECKED_COUNT
    assert data.load_review_queue()


def test_fake_run_classifies_every_pending_record(monkeypatch):
    monkeypatch.setattr("demo.fake_pipeline.STEP_SECONDS", 0)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    reporter = RecordingReporter()
    data = FakeDataManager(build_sample_records())
    FakePipeline(reporter, data, load_ai_answers()).execute_pipeline(Session())
    assert not data.load_pending()
    assert reporter.events[0] == "start" and reporter.events[-1] == "end"
    assert "retry" in reporter.events and "wait" in reporter.events


def test_new_student_record_is_added_and_classified(monkeypatch):
    from managers.models import FeedbackRecord
    from demo.sample_data import build_sample_history
    monkeypatch.setattr("demo.fake_pipeline.STEP_SECONDS", 0)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    data = FakeDataManager(build_sample_records(), history=build_sample_history())
    record = FeedbackRecord("fb_test0001", "The library is too cold", "2026-11-05T10:00:00", None,
                            {"theme": "Facilities", "sentiment": "negative", "severity": "low"})
    session = Session()
    session.records = [record]
    FakePipeline(RecordingReporter(), data, load_ai_answers()).execute_pipeline(session)
    assert data.get_record("fb_test0001").ai is not None
    assert len(data.load_history()) == 5
