"""RecordBuilder: creates FeedbackRecords and Actions with generated IDs and times."""
import re
from datetime import datetime

import pytest

from managers.io_manager.record_builder import RecordBuilder
from managers.models import PENDING

FIXED_TIME = datetime(2026, 11, 9, 14, 30, 5)
LABELS = {"theme": "Workload", "sentiment": "negative", "severity": "high"}


@pytest.fixture
def builder():
    return RecordBuilder(clock=lambda: FIXED_TIME)


def test_typed_feedback_gets_a_new_id_and_the_current_time(builder):
    record = builder.build({"text": "Too many deadlines"}, LABELS)
    assert re.fullmatch(r"fb_[0-9a-f]{8}", record.feedback_id)
    assert record.timestamp == "2026-11-09T14:30:05"
    assert record.source_file is None
    assert record.user == LABELS


def test_each_record_gets_a_different_id(builder):
    ids = {builder.build({"text": "x"}, LABELS).feedback_id for _ in range(50)}
    assert len(ids) == 50


def test_imported_row_keeps_its_own_id_and_timestamp(builder):
    entry = {"feedback_id": "a1", "text": "Wifi drops", "timestamp": "2026-10-01T09:00:00", **LABELS}
    record = builder.build(entry, source_file="week5.csv")
    assert (record.feedback_id, record.timestamp, record.source_file) == (
        "a1", "2026-10-01T09:00:00", "week5.csv")
    assert record.user == LABELS                # taken from the entry when user is not given


def test_only_the_input_sides_fields_are_filled(builder):
    record = builder.build({"text": "x"}, LABELS)
    # the AI, Logic and the pipeline fill these in later
    assert record.ai is None
    assert (record.theme, record.sentiment, record.severity) == (None, None, None)
    assert record.verification == PENDING


def test_action_gets_a_new_id_and_logged_time(builder):
    action = builder.build_action("Facilities", "Upgraded the wifi", "2026-09-30", "wifi")
    assert re.fullmatch(r"act_[0-9a-f]{8}", action.action_id)
    assert action.logged_at == "2026-11-09T14:30:05"
    assert action.keyword == "wifi"


def test_blank_keyword_means_measure_the_whole_theme(builder):
    assert builder.build_action("Facilities", "Upgraded the wifi", "2026-09-30", "").keyword is None


def test_invalid_action_is_refused_by_the_action_itself(builder):
    with pytest.raises(ValueError):
        builder.build_action("Facilities", "Upgraded the wifi", "2026-02-30")
