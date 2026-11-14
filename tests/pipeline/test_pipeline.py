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
    assert ctx.stopped is True
    assert NeverReachedStep.called is False


def test_ingestion_step_confirms_new_theme_and_updates_logic_and_ai() -> None:
    rec = _make_record("FB-010")
    data = _make_mock_data([rec])
    data.load_known_themes.side_effect = [
        ["Facilities"],
        ["Facilities", "Parking Fees"],
    ]
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
    data.load_known_themes.side_effect = [
        ["Facilities"],
        ["Facilities", "Parking Fees"],
    ]
    logic = _make_mock_logic()
    ai = MagicMock()

    ctx = PipelineContext(session=FakeSession(themes_to_add=["Parking Fees"]))  # type: ignore[arg-type]

    assert IngestionStep(data, logic, ai).execute(ctx) is True

    data.add_known_theme.assert_called_once_with("Parking Fees")
    logic.set_known_themes.assert_called_once_with(["Facilities", "Parking Fees"])
    ai.set_known_themes.assert_called_once_with(["Facilities", "Parking Fees"])


def test_summary_step_skips_call2_when_nothing_classified_and_uses_fallback() -> None:
    data = _make_mock_data()
    logic = _make_mock_logic()
    ai = MagicMock()

    ctx = PipelineContext(
        records=[_make_record()],
        result=logic.aggregate.return_value,
        classified_count=0,
        stopped=False,
    )

    step = SummaryStep(ai, logic)
    assert step.execute(ctx) is True

    # D24: Call 2 must not be invoked when classified_count == 0
    ai.summarise.assert_not_called()
    # D21: Keyword fallback actions generated instead
    logic.suggest_actions.assert_called_once()
    assert ctx.summary is None
    assert ctx.fallback_actions is not None


def test_full_pipeline_completes_when_ai_is_down() -> None:
    """Action A25: End-to-end run with failing AI continues and produces rule-based fallback."""
    rec = _make_record("FB-999")
    data = _make_mock_data()
    data.load_pending.return_value = [rec.to_dict()]   # real Data returns dicts
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

    assert ctx.stopped is True
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
