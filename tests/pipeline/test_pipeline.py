from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from unittest.mock import MagicMock

import pytest

from managers.ai_manager import AISummary
from managers.logic_manager import (
    ActionSuggestions,
    AggregationResult,
    ImpactReport,
    TrendReport,
)
from managers.models import (
    CRITICAL,
    NEGATIVE,
    POSITIVE,
    REVIEWED,
    UNVERIFIED,
    Action,
    FeedbackRecord,
)
from managers.pipeline import (
    BaseStep,
    PipelineContext,
    PipelineManager,
    PipelineStep,
)
from managers.pipeline.steps import (
    AIClassificationStep,
    ImpactStep,
    IngestionStep,
    LogicStep,
    PersistenceStep,
    SummaryStep,
)


@dataclass
class FakeDecision:
    feedback_id: str
    action: str
    theme: str = "Facilities"
    sentiment: str = NEGATIVE
    severity: str = CRITICAL


@dataclass
class FakeSession:
    records: list[FeedbackRecord] = field(default_factory=list)
    source_file: str | None = "import.csv"
    decisions: list[FakeDecision] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    themes_to_add: list[str] = field(default_factory=list)   # matches SessionResult (Joel's #81)


def _make_record(fid: str = "FB-001", text: str = "Wi-Fi is broken") -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=fid,
        text=text,
        timestamp="2026-11-10T10:00:00",
        source_file="import.csv",
        user={"theme": "Facilities", "sentiment": NEGATIVE, "severity": CRITICAL},
    )


def _make_mock_data(records: list[FeedbackRecord] | None = None) -> MagicMock:
    data = MagicMock()
    # Like the real DataManager (8.6), the mock returns FeedbackRecord objects
    data.load_records.return_value = list(records or [])
    data.load_pending.return_value = []
    data.load_known_themes.return_value = ["Facilities", "Workload"]
    data.load_previous_run.return_value = None
    data.load_actions.return_value = []
    return data


def _make_mock_logic() -> MagicMock:
    logic = MagicMock()
    logic.validate.side_effect = lambda recs: (recs, [])
    logic.apply_rules.side_effect = lambda recs: recs
    logic.review_queue.return_value = []
    logic.aggregate.return_value = MagicMock(spec=AggregationResult)
    logic.compare_runs.return_value = MagicMock(spec=TrendReport)
    logic.suggest_actions.return_value = ActionSuggestions(
        theme_actions=[{"theme": "Facilities", "suggested_action": "Escalate Wi-Fi issue"}]
    )
    logic.evaluate_actions.return_value = []
    # like the real LogicManager: labels come back as given, and a theme is new
    # unless it is one of the themes the mock data starts with
    logic.normalise_theme.side_effect = lambda label: label
    logic.is_new_theme.side_effect = lambda label: label not in ("Facilities", "Workload")
    return logic



def test_base_step_is_abstract_and_implements_pipeline_step() -> None:
    assert issubclass(BaseStep, PipelineStep)
    with pytest.raises(TypeError):
        BaseStep()  # type: ignore[abstract]


def test_pipeline_manager_stops_when_step_returns_false() -> None:
    class HaltingStep(BaseStep):
        def _run(self, context: PipelineContext) -> bool:
            return False

    class NeverReachedStep(BaseStep):
        called = False

        def _run(self, context: PipelineContext) -> bool:
            NeverReachedStep.called = True
            return True

    pm = PipelineManager()
    pm.register_step(HaltingStep())
    pm.register_step(NeverReachedStep())

    ctx = pm.execute_pipeline()
    assert ctx.halted is True
    assert ctx.ai_stopped is False      # P7: halting the pipeline is not the AI stopping
    assert NeverReachedStep.called is False


def test_ingestion_step_confirms_new_theme_and_updates_logic_and_ai() -> None:
    rec = _make_record("FB-010")
    data = _make_mock_data([rec])
    # read once, after the new theme is saved (Logic, not this list, decides what is new)
    data.load_known_themes.return_value = ["Facilities", "Parking Fees"]
    logic = _make_mock_logic()
    ai = MagicMock()

    session = FakeSession(
        decisions=[
            FakeDecision(
                feedback_id="FB-010",
                action="update",
                theme="Parking Fees",
                sentiment=NEGATIVE,
                severity=CRITICAL,
            )
        ]
    )
    ctx = PipelineContext(session=session)  # type: ignore[arg-type]

    step = IngestionStep(data, logic, ai)
    assert step.execute(ctx) is True

    saved = data.save_records.call_args.args[0]
    assert [(r.feedback_id, r.verification) for r in saved] == [("FB-010", REVIEWED)]
    data.add_known_theme.assert_called_once_with("Parking Fees")
    logic.set_known_themes.assert_called_once_with(["Facilities", "Parking Fees"])
    ai.set_known_themes.assert_called_once_with(["Facilities", "Parking Fees"])


def test_ingestion_step_saves_themes_added_in_settings() -> None:
    data = _make_mock_data()
    # read once, after the new theme is saved (Logic, not this list, decides what is new)
    data.load_known_themes.return_value = ["Facilities", "Parking Fees"]
    logic = _make_mock_logic()
    ai = MagicMock()

    ctx = PipelineContext(session=FakeSession(themes_to_add=["Parking Fees"]))  # type: ignore[arg-type]

    assert IngestionStep(data, logic, ai).execute(ctx) is True

    data.add_known_theme.assert_called_once_with("Parking Fees")
    logic.set_known_themes.assert_called_once_with(["Facilities", "Parking Fees"])
    ai.set_known_themes.assert_called_once_with(["Facilities", "Parking Fees"])


def _summary_context(logic, *, sent: int, classified: int, stopped: bool = False) -> PipelineContext:
    return PipelineContext(records=[_make_record()], result=logic.aggregate.return_value,
                           sent_to_ai=sent, classified_count=classified, ai_stopped=stopped)


def test_summary_step_keeps_last_ai_summary_when_nothing_new_was_sent() -> None:
    """A review-only run (nothing sent to the AI) with the AI working: no Call 2 (D24)
    and no rule-based "AI unavailable" actions, so the last AI summary stays on show."""
    logic = _make_mock_logic()
    ai = MagicMock()
    ctx = _summary_context(logic, sent=0, classified=0)

    assert SummaryStep(ai, logic, ai_ready=True).execute(ctx) is True

    ai.summarise.assert_not_called()
    logic.suggest_actions.assert_not_called()
    assert ctx.summary is None and ctx.fallback_actions is None


@pytest.mark.parametrize("ai_ready, sent, classified, stopped", [
    (False, 0, 0, False),   # no API key or key label
    (True, 3, 0, True),     # Call 1 stopped early
    (True, 2, 0, False),    # entries sent, none could be classified
])
def test_summary_step_uses_rule_based_actions_when_the_ai_is_down(ai_ready, sent, classified, stopped) -> None:
    logic = _make_mock_logic()
    ai = MagicMock()
    ctx = _summary_context(logic, sent=sent, classified=classified, stopped=stopped)

    assert SummaryStep(ai, logic, ai_ready=ai_ready).execute(ctx) is True

    ai.summarise.assert_not_called()
    logic.suggest_actions.assert_called_once()
    assert ctx.summary is None and ctx.fallback_actions is not None


def test_summary_step_uses_rule_based_actions_when_call2_fails() -> None:
    logic = _make_mock_logic()
    ai = MagicMock()
    ai.summarise.return_value = None
    ctx = _summary_context(logic, sent=2, classified=2)

    assert SummaryStep(ai, logic, ai_ready=True).execute(ctx) is True

    ai.summarise.assert_called_once()
    assert ctx.summary is None and ctx.fallback_actions is not None


def test_summary_step_stores_the_ai_summary_when_call2_succeeds() -> None:
    logic = _make_mock_logic()
    ai = MagicMock()
    ctx = _summary_context(logic, sent=2, classified=2)

    assert SummaryStep(ai, logic, ai_ready=True).execute(ctx) is True

    assert ctx.summary is ai.summarise.return_value and ctx.fallback_actions is None
    logic.suggest_actions.assert_not_called()


def test_persistence_step_leaves_the_saved_summary_alone_when_nothing_new() -> None:
    data = _make_mock_data()
    logic = _make_mock_logic()
    ctx = PipelineContext(records=[_make_record()], result=logic.aggregate.return_value,
                          trend=MagicMock(), session=FakeSession(source_file=None))  # type: ignore[arg-type]

    assert PersistenceStep(data).execute(ctx) is True

    saved = [c.args[0] for c in data.save_object.call_args_list]
    assert "summary" not in saved and "fallback_actions" not in saved


def test_full_pipeline_completes_when_ai_is_down() -> None:
    """Action A25: End-to-end run with failing AI continues and produces rule-based fallback."""
    rec = _make_record("FB-999")
    data = _make_mock_data()
    data.load_pending.return_value = [rec]
    logic = _make_mock_logic()

    # Simulate AI outage (stopped=True, 0 records classified)
    ai = MagicMock()
    ai.classify_entries.return_value = ([], [rec], True)

    pm = PipelineManager(data_dir="test_data")
    pm.register_step(IngestionStep(data, logic, ai))
    pm.register_step(AIClassificationStep(ai, data))
    pm.register_step(LogicStep(logic, data))
    pm.register_step(SummaryStep(ai, logic))
    pm.register_step(ImpactStep(logic, data))
    pm.register_step(PersistenceStep(data))

    session = FakeSession(records=[rec], source_file="outage.csv")
    ctx = pm.execute_pipeline(session)  # type: ignore[arg-type]

    assert ctx.ai_stopped is True
    assert ctx.halted is False          # P7: Call 1 stopping does not halt the pipeline
    assert ctx.classified_count == 0
    assert ctx.result is not None
    assert ctx.trend is not None
    assert ctx.summary is None
    assert ctx.fallback_actions is not None
    ai.summarise.assert_not_called()
    data.save_records.assert_called()
    data.save_object.assert_any_call("fallback_actions", ctx.fallback_actions)
    data.append_history.assert_called_once()


def test_persistence_step_clears_fallback_actions_when_ai_summary_succeeds() -> None:
    data = _make_mock_data()
    summary = AISummary(
        overall_summary="Students reported Wi-Fi outages.",
        theme_actions=[{"theme": "Facilities", "suggested_action": "Upgrade routers"}],
        created_at="2026-11-12T12:00:00",
    )
    ctx = PipelineContext(
        records=[_make_record()],
        summary=summary,
        fallback_actions=None,
    )

    step = PersistenceStep(data)
    assert step.execute(ctx) is True

    data.save_object.assert_any_call("summary", summary)
    data.save_object.assert_any_call("fallback_actions", [])


def test_full_run_with_real_data_manager_keeps_saved_records_and_actions(tmp_path) -> None:
    """Uses the real DataManager (not a mock), so a mismatch between what Data returns
    and what the pipeline expects shows up here instead of wiping data/ in the app."""
    from managers.data_manager import DataManager
    from managers.logic_manager import LogicManager

    data = DataManager(str(tmp_path))
    saved = [_make_record(f"FB-{i:03}", f"Comment {i}") for i in range(5)]
    data.save_records(saved)
    from managers.io_manager import RecordBuilder
    data.save_action(RecordBuilder().build_action("Facilities", "Fixed Wi-Fi", "2026-11-01"))

    ai = MagicMock()
    ai.classify_entries.side_effect = lambda recs, stored, on_classified: ([], list(recs), True)

    pm = PipelineManager(data_dir=str(tmp_path))
    logic = LogicManager()
    for step in (IngestionStep(data, logic, ai), AIClassificationStep(ai, data),
                 LogicStep(logic, data), SummaryStep(ai, logic),
                 ImpactStep(logic, data), PersistenceStep(data)):
        pm.register_step(step)

    ctx = pm.execute_pipeline(FakeSession(source_file=None))  # type: ignore[arg-type]

    assert sorted(r.feedback_id for r in data.load_records()) == [r.feedback_id for r in saved]
    assert len(ctx.records) == 5
    assert len(ctx.impacts) == 1


# ---- P1: a review decision's theme goes through Logic before it is stored or confirmed

@pytest.mark.parametrize("label, stored, confirmed", [
    ("wifi", "Facilities", None),            # an alias of a base theme
    ("facilities", "Facilities", None),      # a case variant of a known theme
    ("Unclear", "Unclear", None),            # the AI's "no real theme": never confirmed
    ("other", "Unclear", None),
    ("parking fees", "Parking Fees", "Parking Fees"),   # coined: kept, so confirmed (D16)
])
def test_review_theme_is_normalised_and_only_a_new_theme_is_confirmed(label, stored, confirmed) -> None:
    from managers.logic_manager import LogicManager
    from managers.models import THEMES

    rec = _make_record("FB-020")
    data = _make_mock_data([rec])
    data.load_known_themes.return_value = list(THEMES)
    ai = MagicMock()
    session = FakeSession(decisions=[FakeDecision("FB-020", "update", theme=label)])

    assert IngestionStep(data, LogicManager(), ai).execute(PipelineContext(session=session)) is True

    [saved] = data.save_records.call_args.args[0]
    assert (saved.theme, saved.verification) == (stored, REVIEWED)
    if confirmed is None:
        data.add_known_theme.assert_not_called()
        ai.set_known_themes.assert_not_called()
    else:
        data.add_known_theme.assert_called_once_with(confirmed)


def test_accepting_the_ai_values_on_two_records_confirms_a_coined_theme_once() -> None:
    from managers.logic_manager import LogicManager
    from managers.models import THEMES

    data = _make_mock_data([_make_record("FB-021"), _make_record("FB-022")])
    data.load_known_themes.return_value = list(THEMES)
    session = FakeSession(decisions=[FakeDecision("FB-021", "update", theme="Parking"),
                                     FakeDecision("FB-022", "update", theme="parking")])

    IngestionStep(data, LogicManager(), MagicMock()).execute(PipelineContext(session=session))

    data.add_known_theme.assert_called_once_with("Parking")


def _real_pipeline(data, logic, ai) -> PipelineManager:
    pm = PipelineManager()
    for step in (IngestionStep(data, logic, ai), AIClassificationStep(ai, data),
                 LogicStep(logic, data), SummaryStep(ai, logic),
                 ImpactStep(logic, data), PersistenceStep(data)):
        pm.register_step(step)
    return pm


# ---- P5: after a failed run the GUI sends the same session again; nothing is stored twice

def test_rerunning_a_failed_run_stores_its_records_and_actions_once(tmp_path) -> None:
    from managers.data_manager import DataManager
    from managers.io_manager import RecordBuilder
    from managers.logic_manager import LogicManager

    data = DataManager(str(tmp_path))
    session = FakeSession(records=[_make_record("FB-101"), _make_record("FB-102")],
                          actions=[RecordBuilder().build_action("Facilities", "Fixed Wi-Fi", "2026-11-01")])
    ai = MagicMock()
    ai.classify_entries.side_effect = RuntimeError("network down")
    pm = _real_pipeline(data, LogicManager(), ai)

    with pytest.raises(RuntimeError):
        pm.execute_pipeline(session)  # type: ignore[arg-type]
    ai.classify_entries.side_effect = lambda recs, stored, on_classified: ([], list(recs), True)
    pm.execute_pipeline(session)  # type: ignore[arg-type]

    stored = [r.feedback_id for r in data.load_records() + data.load_pending()]
    assert sorted(stored) == ["FB-101", "FB-102"]
    assert len(data.load_actions()) == 1


# ---- P6: a failed ImpactStep (errors swallowed by design) keeps the last saved impacts

def test_a_failed_impact_step_does_not_erase_the_saved_impacts(tmp_path) -> None:
    from managers.data_manager import DataManager
    from managers.logic_manager import LogicManager

    data = DataManager(str(tmp_path))
    data.save_object("impact_output", [{"action_id": "a1", "verdict": "improved"}])
    logic = LogicManager()
    ai = MagicMock()
    ai.classify_entries.side_effect = lambda recs, stored, on_classified: ([], list(recs), True)
    pm = _real_pipeline(data, logic, ai)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(logic, "evaluate_actions", MagicMock(side_effect=RuntimeError("bad action")))
        pm.execute_pipeline(FakeSession(records=[_make_record("FB-201")]))  # type: ignore[arg-type]

    assert data.load_object("impact_output") == [{"action_id": "a1", "verdict": "improved"}]
    assert [r.feedback_id for r in data.load_records()] == ["FB-201"]     # the run itself was saved


# L1: a previous run with a wrong-typed number is skipped, so the run completes
@pytest.mark.parametrize("field, value", [("priority", None), ("priority", 50.5), ("count", "2")])
def test_logic_step_skips_a_previous_run_with_a_wrong_type(field, value) -> None:
    from managers.logic_manager import LogicManager

    record = _make_record()
    logic = LogicManager()
    previous = logic.aggregate(logic.apply_rules([record])).to_dict()
    previous["themes"][0][field] = value
    data = _make_mock_data([record])
    data.load_previous_run.return_value = {"run_at": "2026-11-10T10:00:00", "source_file": "a.csv",
                                           "result": previous}
    context = PipelineContext(session=FakeSession(), records=[record])

    assert LogicStep(logic, data).execute(context) is True
    assert context.trend.has_previous is False
