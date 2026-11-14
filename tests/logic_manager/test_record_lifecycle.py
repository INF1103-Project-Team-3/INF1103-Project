"""Follows records across several runs. Each run reloads them from JSON and starts
a new LogicManager, as the app will, so nothing carries over in memory."""

import json

from managers.logic_manager import LogicManager
from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MISMATCH, NEGATIVE, REVIEWED, THEMES, UNVERIFIED, FeedbackRecord,
)


def make_record(feedback_id, theme="Facilities", severity=HIGH):
    return FeedbackRecord(feedback_id, "The library wifi keeps dropping.", "2026-09-17T08:03:00", None,
                          {"theme": theme, "sentiment": NEGATIVE, "severity": severity})


def run(records, known_themes=THEMES):
    """One run: validate, apply the rules and aggregate, then save and reload the records."""
    logic = LogicManager(known_themes=known_themes)
    valid, invalid = logic.validate(records)
    assert invalid == []
    logic.apply_rules(valid)
    result = logic.aggregate(valid)
    queue = [record.feedback_id for record in logic.review_queue(valid)]
    saved = json.loads(json.dumps([record.to_dict() for record in valid]))
    return [FeedbackRecord.from_dict(data) for data in saved], result, queue


def test_ai_outage_then_a_disagreement_then_an_admin_review():
    # the AI is down: the user's values are used and the record is counted
    [record], result, queue = run([make_record("fb_001", severity=LOW)])
    assert record.verification == UNVERIFIED
    assert result.get("Facilities").count == 1
    assert queue == []

    # the AI is back and disagrees: the record leaves the statistics for review
    record.set_ai("Assessment", NEGATIVE, HIGH)
    [record], result, queue = run([record])
    assert record.verification == MISMATCH
    assert result.counted_entries == 0
    assert queue == ["fb_001"]

    # nobody has reviewed it yet: the next run still holds it back
    [record], result, queue = run([record])
    assert record.verification == MISMATCH
    assert queue == ["fb_001"]

    # an admin decides: the record is counted under the admin's theme
    record.mark_reviewed("Assessment", NEGATIVE, HIGH)
    [record], result, queue = run([record])
    assert record.verification == REVIEWED
    assert result.get("Assessment").count == 1
    assert result.get("Facilities") is None
    assert queue == []

    # later runs keep the admin's decision
    [record], result, queue = run([record])
    assert (record.verification, record.theme) == (REVIEWED, "Assessment")
    assert result.get("Assessment").count == 1


def test_confirming_a_new_theme_counts_every_record_waiting_on_it():
    records, result, queue = run([make_record("fb_001", "parking fees"), make_record("fb_002", "Parking-Fees")])
    assert result.pending_themes == {"Parking Fees": 2}
    assert result.counted_entries == 0
    assert queue == ["fb_001", "fb_002"]

    # the admin keeps the theme on one record, which confirms it for both
    records[0].mark_reviewed("Parking Fees", NEGATIVE, HIGH)
    records, result, queue = run(records, known_themes=[*THEMES, "Parking Fees"])
    assert result.pending_themes == {}
    assert result.get("Parking Fees").count == 2
    assert queue == []


def test_changing_a_new_theme_to_an_existing_one_clears_it_from_pending():
    records, result, _ = run([make_record("fb_001", "parking fees")])
    assert result.pending_themes == {"Parking Fees": 1}

    records[0].mark_reviewed("Facilities", NEGATIVE, HIGH)
    _, result, queue = run(records)
    assert result.pending_themes == {}
    assert result.get("Facilities").count == 1
    assert queue == []


def test_critical_feedback_stays_counted_and_in_the_queue_until_reviewed():
    [record], result, queue = run([make_record("fb_001", severity=CRITICAL)])
    assert result.counted_entries == 1
    assert queue == ["fb_001"]

    # the AI agrees on a later run: still critical, so still needs a person
    record.set_ai("Facilities", NEGATIVE, CRITICAL)
    [record], result, queue = run([record])
    assert record.verification == MATCHED
    assert result.counted_entries == 1
    assert queue == ["fb_001"]

    record.mark_reviewed("Facilities", NEGATIVE, CRITICAL)
    _, result, queue = run([record])
    assert result.counted_entries == 1
    assert queue == []
