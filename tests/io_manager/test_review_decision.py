"""ReviewDecision and SessionResult: what an input session hands to the pipeline."""
import dataclasses

import pytest

from managers.io_manager.review_decision import ReviewDecision
from managers.io_manager.session_result import SessionResult


def test_update_takes_the_three_labels_and_ignores_anything_else():
    # record.ai may also carry the AI's summary
    decision = ReviewDecision.update("fb_1", {"theme": "Workload", "sentiment": "negative",
                                              "severity": "low", "summary": "ignored"})
    assert decision == ReviewDecision("fb_1", ReviewDecision.UPDATE, "Workload", "negative", "low")


def test_delete_carries_no_labels():
    assert ReviewDecision.delete("fb_1") == ReviewDecision("fb_1", ReviewDecision.DELETE)


def test_a_decision_cannot_be_changed_once_made():
    with pytest.raises(dataclasses.FrozenInstanceError):
        ReviewDecision.delete("fb_1").feedback_id = "fb_2"


def test_session_result_knows_when_it_is_empty_and_what_was_decided():
    session = SessionResult()
    assert session.is_empty()
    session.decisions.append(ReviewDecision.delete("fb_1"))
    assert not session.is_empty()
    assert session.decided_ids() == {"fb_1"}
