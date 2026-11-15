from __future__ import annotations

import pytest

from managers.pipeline import AppEngine, BaseStep, PipelineContext, PipelineManager
from managers.pipeline.steps import IngestionStep


class RecordingView:
    """Collects what AppEngine shows instead of printing it."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def show_message(self, message: str) -> None:
        self.messages.append(message)


class PassingStep(BaseStep):
    description = "the first part"

    def _run(self, context: PipelineContext) -> bool:
        return True


class FailingStep(BaseStep):
    description = "checking the feedback"

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def _run(self, context: PipelineContext) -> bool:
        raise self._error


def engine_with(*steps) -> AppEngine:
    engine = AppEngine()
    pipeline = PipelineManager()
    for step in steps:
        pipeline.register_step(step)
    engine._pipeline = pipeline       # the steps under test instead of the real ones
    return engine


# ---- P3: a step error or Ctrl-C mid-run ends in a plain message, not a traceback

@pytest.mark.parametrize("error", [RuntimeError("disk full"), KeyboardInterrupt()])
def test_a_failed_run_shows_a_plain_message(error):
    view = RecordingView()
    context = engine_with(PassingStep(), FailingStep(error)).execute_run(object(), view)
    assert context is None
    [message] = view.messages
    assert "checking the feedback" in message
    assert "saved" in message
    if isinstance(error, RuntimeError):
        assert "disk full" in message


def test_failure_after_ingestion_says_the_session_was_saved():
    view = RecordingView()
    engine_with(PassingStep(), FailingStep(RuntimeError("x"))).execute_run(object(), view)
    assert "were saved" in view.messages[0]


def test_failure_in_ingestion_says_changes_may_be_lost():
    class BrokenIngestion(IngestionStep):
        def __init__(self) -> None:
            pass

        def _run(self, context: PipelineContext) -> bool:
            raise RuntimeError("x")

    view = RecordingView()
    engine_with(BrokenIngestion()).execute_run(object(), view)
    assert "may not have been saved" in view.messages[0]


def test_a_successful_run_returns_its_context_and_shows_nothing():
    view = RecordingView()
    context = engine_with(PassingStep()).execute_run(object(), view)
    assert isinstance(context, PipelineContext)
    assert view.messages == []


def test_pipeline_reports_the_step_it_is_running():
    seen = []

    class Watching(BaseStep):
        def _run(self, context: PipelineContext) -> bool:
            seen.append(pipeline.current_step)
            return True

    pipeline = PipelineManager()
    step = Watching()
    pipeline.register_step(step)
    assert pipeline.current_step is None
    pipeline.execute_pipeline()
    assert seen == [step]


# ---- P2: a key without its label is "AI down", so Call 1 must not spend tokens

class RecordingClient:
    """Stands in for GroqClient and keeps the key it was given."""
    keys: list = []

    def __init__(self, api_key, model=None):
        RecordingClient.keys.append(api_key)

    @property
    def model(self) -> str:
        return "test-model"


@pytest.mark.parametrize("key, label, sent_key", [
    ("gsk_test", "", None),          # label missing: AI down, the client gets no key
    ("", "my-key", None),            # key missing
    ("gsk_test", "my-key", "gsk_test"),
])
def test_the_client_only_gets_the_key_when_the_ai_is_ready(monkeypatch, tmp_path, key, label, sent_key):
    import managers.pipeline.app_engine as app_engine
    monkeypatch.setattr(app_engine, "ENV_FILE", tmp_path / "missing.env")   # not the real .env
    monkeypatch.setattr(app_engine, "GroqClient", RecordingClient)
    monkeypatch.setenv("GROQ_API_KEY", key)
    monkeypatch.setenv("GROQ_KEY_LABEL", label)
    RecordingClient.keys = []
    AppEngine(str(tmp_path / "data")).bootstrap_system(reporter=None)
    assert RecordingClient.keys == [sent_key]


# ---- P4: logging is set up once by the app; the console shows plain lines, no tracebacks

def test_console_log_lines_are_plain_and_have_no_traceback():
    import logging
    from managers.pipeline.console_log_formatter import ConsoleLogFormatter

    try:
        raise RuntimeError("disk full")
    except RuntimeError:
        import sys
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "Error executing %s", ("LogicStep",),
                                   sys.exc_info())
    line = ConsoleLogFormatter().format(record)
    assert line == "Error: Error executing LogicStep"
    assert record.exc_info is not None      # other handlers still get the full record


def test_logging_is_configured_once_at_warning():
    import logging
    logger = logging.getLogger("p4-test")
    AppEngine.configure_logging(logger)
    AppEngine.configure_logging(logger)
    assert len(logger.handlers) == 1
    assert logger.level == logging.WARNING


# ---- P8: AppEngine keeps its managers private and sets everything in __init__

def test_engine_state_is_private_and_set_in_init():
    engine = AppEngine()
    for name in ("data", "logic", "ai", "pipeline", "ai_ready"):
        assert not hasattr(engine, name)
    assert engine._ai_ready is False


def test_bootstrap_returns_nothing(monkeypatch, tmp_path):
    import managers.pipeline.app_engine as app_engine
    monkeypatch.setattr(app_engine, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setattr(app_engine, "GroqClient", RecordingClient)
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GROQ_KEY_LABEL", "")
    assert AppEngine(str(tmp_path / "data")).bootstrap_system(reporter=None) is None


# ---- I3 (D21): the end-of-run dashboard shows rule-based actions and keeps the last AI summary

class DashboardView:
    def show_dashboard(self, *args) -> None:
        self.args = args


def test_end_of_run_dashboard_shows_rule_based_actions_and_the_saved_summary(tmp_path):
    from managers.ai_manager import AISummary
    from managers.data_manager import DataManager
    from managers.logic_manager import ActionSuggestions

    engine = AppEngine(str(tmp_path / "data"))
    engine._data = DataManager(str(tmp_path / "data"))
    saved = AISummary("Old.", [{"theme": "Facilities", "suggested_action": "AI action."}], "2026-11-01T10:00:00")
    engine._data.save_object("summary", saved)
    context = PipelineContext()
    context.fallback_actions = ActionSuggestions([{"theme": "Facilities", "suggested_action": "Rules."}])
    view = DashboardView()

    engine._show_run_dashboard(context, view)

    assert view.args == (context.result, context.trend, saved, context.review_queue, context.fallback_actions)


def test_end_of_run_dashboard_shows_this_runs_summary(tmp_path):
    from managers.ai_manager import AISummary
    from managers.data_manager import DataManager

    engine = AppEngine(str(tmp_path / "data"))
    engine._data = DataManager(str(tmp_path / "data"))
    context = PipelineContext()
    context.summary = AISummary("New.", [])
    view = DashboardView()

    engine._show_run_dashboard(context, view)

    assert view.args[2] is context.summary
    assert view.args[4] is None
