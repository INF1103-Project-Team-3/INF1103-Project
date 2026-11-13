# DataReader on a real DataManager, filled by the real pipeline (stub AI) in a temp folder.

import pytest

pytest.importorskip("PySide6")

from managers.data_manager import DataManager  # noqa: E402
from managers.gui.data_reader import DataReader  # noqa: E402
from managers.io_manager import RecordBuilder, SessionResult  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import MATCHED, UNVERIFIED  # noqa: E402
from tests.gui.support.real_pipeline import build_pipeline  # noqa: E402
from tests.gui.support.stub_ai import StubAI  # noqa: E402


def record(text, theme="Facilities"):
    return RecordBuilder().build({"text": text, "theme": theme, "sentiment": "negative", "severity": "medium"})


def run(data, ai, **session):
    return build_pipeline(data, LogicManager(), ai).execute_pipeline(SessionResult(**session))


def test_reads_records_summary_and_history_after_a_run(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    run(data, StubAI(), records=[record("Wifi drops"), record("Lab is cold")])
    reader = DataReader(data)
    assert {r.verification for r in reader.load_records()} == {MATCHED}
    assert reader.load_summary().overall_summary == "All fine."
    assert reader.load_result().counted_entries == 2
    assert len(reader.load_history()) == 1 and "Facilities" in reader.load_history()[0]["theme_priority"]
    assert reader.load_fallback_actions() is None


def test_rule_based_actions_are_read_after_an_ai_down_run(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    run(data, StubAI(down=True), records=[record("Wifi drops")])
    reader = DataReader(data)
    assert reader.load_records()[0].verification == UNVERIFIED
    assert reader.load_fallback_actions().theme_actions[0]["theme"] == "Facilities"


def test_logged_action_is_read_back_as_an_action(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    action = RecordBuilder().build_action("Facilities", "Fixed the wifi", "2026-11-01", "wifi")
    run(data, StubAI(), records=[record("Wifi drops")], actions=[action])
    reader = DataReader(data)
    assert [a.action_id for a in reader.load_actions()] == [action.action_id]
    assert len(reader.load_impacts()) == 1


def test_skips_part1_history_and_corrupt_records(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    data.json_store.save(data.data_dir / "aggregated_history.json", [{"run_at": "x", "stats": {}}])
    data.json_store.save(data.data_dir / "processed_feedback.json", {"records": [{"feedback_id": "fb_bad"}]})
    reader = DataReader(data)
    assert reader.load_history() == [] and reader.load_records() == []
