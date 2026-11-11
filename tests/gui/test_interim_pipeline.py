# InterimPipeline and DataReader on a real DataManager in a temp folder, with a stub AI.
# Importing managers.gui loads PySide6, so these skip where Qt isn't installed (Docker CI).

from datetime import date

import pytest

pytest.importorskip("PySide6")

from demo.interim_pipeline import InterimPipeline  # noqa: E402
from managers.ai_manager import AISummary  # noqa: E402
from managers.data_manager import DataManager  # noqa: E402
from managers.gui.data_reader import DataReader  # noqa: E402
from managers.io_manager import RecordBuilder, ReviewDecision, SessionResult  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import MATCHED, REVIEWED, UNVERIFIED  # noqa: E402


# Agrees with the user on every record, or fails them all when down.
class StubAI:
    def __init__(self, down=False):
        self.down = down
        self.themes = None
        self.summaries = 0

    def classify_entries(self, records, stored_records, on_classified):
        if self.down:
            return [], list(records), True
        for record in records:
            user = record.user
            record.set_ai(user["theme"], user["sentiment"], user["severity"], "one-liner")
            on_classified(record)
        return list(records), [], False

    def summarise(self, result, records):
        self.summaries += 1
        return AISummary("All fine.", [])

    def set_known_themes(self, themes):
        self.themes = list(themes)


def record(text, theme="Facilities", sentiment="negative", severity="medium"):
    return RecordBuilder().build({"text": text, "theme": theme, "sentiment": sentiment, "severity": severity})


def setup(tmp_path, ai=None):
    data = DataManager(str(tmp_path / "data"))
    logic = LogicManager()
    return data, InterimPipeline(data, logic, ai, today=lambda: date(2026, 11, 11))


def test_new_records_are_classified_checked_and_saved(tmp_path):
    ai = StubAI()
    data, pipeline = setup(tmp_path, ai)
    context = pipeline.execute_pipeline(SessionResult(records=[record("Wifi drops"), record("Lab is cold")]))
    saved = DataReader(data).load_records()
    assert {r.verification for r in saved} == {MATCHED}
    assert not data.load_pending()
    assert context.result.counted_entries == 2 and not context.stopped
    assert ai.summaries == 1 and data.load_object("summary")["overall_summary"] == "All fine."
    assert len(DataReader(data).load_history()) == 1


def test_ai_down_keeps_users_values_and_retries_next_run(tmp_path):
    data, pipeline = setup(tmp_path, StubAI(down=True))
    context = pipeline.execute_pipeline(SessionResult(records=[record("Wifi drops")]))
    assert context.stopped and context.summary is None
    assert DataReader(data).load_records()[0].verification == UNVERIFIED

    ai = StubAI()
    InterimPipeline(data, LogicManager(), ai).execute_pipeline(SessionResult())
    assert DataReader(data).load_records()[0].verification == MATCHED


def test_no_ai_at_all_still_saves_the_run(tmp_path):
    data, pipeline = setup(tmp_path, ai=None)
    context = pipeline.execute_pipeline(SessionResult(records=[record("Wifi drops")]))
    assert context.stopped and context.result.counted_entries == 1
    assert data.load_object("aggregated_output") is not None


def test_review_decisions_update_delete_and_confirm_a_new_theme(tmp_path):
    ai = StubAI()
    data, pipeline = setup(tmp_path, ai)
    keep, drop = record("Parking costs too much", theme="Parking Fees"), record("Spam spam")
    pipeline.execute_pipeline(SessionResult(records=[keep, drop]))
    flagged = DataReader(data).load_review_queue()
    assert [r.feedback_id for r in flagged] == [keep.feedback_id]

    confirm = ReviewDecision.update(keep.feedback_id, keep.user)
    pipeline.execute_pipeline(SessionResult(decisions=[confirm, ReviewDecision.delete(drop.feedback_id)]))
    saved = {r.feedback_id: r for r in DataReader(data).load_records()}
    assert saved[keep.feedback_id].verification == REVIEWED and saved[keep.feedback_id].counted
    assert drop.feedback_id not in saved
    assert "Parking Fees" in data.load_known_themes() and "Parking Fees" in ai.themes
    assert not DataReader(data).load_review_queue()


def test_logged_action_is_saved_and_evaluated(tmp_path):
    data, pipeline = setup(tmp_path, StubAI())
    action = RecordBuilder().build_action("Facilities", "Fixed the wifi", "2026-11-01", "wifi")
    context = pipeline.execute_pipeline(SessionResult(records=[record("Wifi drops")], actions=[action]))
    assert [a.action_id for a in DataReader(data).load_actions()] == [action.action_id]
    assert len(context.impacts) == 1 and data.load_object("impact_output")


def test_data_reader_skips_part1_history_and_corrupt_records(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    data.json_store.save(data.data_dir / "aggregated_history.json", [{"run_at": "x", "stats": {}}])
    data.save_records([{"feedback_id": "fb_bad"}])
    reader = DataReader(data)
    assert reader.load_history() == [] and reader.load_records() == []


def test_unverified_records_leave_the_pending_file_after_a_run(tmp_path):
    data, pipeline = setup(tmp_path, StubAI(down=True))
    pipeline.execute_pipeline(SessionResult(records=[record("Wifi drops"), record("Lab is cold")]))
    assert not data.load_pending()
    assert {r.verification for r in DataReader(data).load_records()} == {UNVERIFIED}
