import pytest

from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MISMATCH, NEGATIVE, PENDING, REVIEWED,
    FeedbackRecord, Serializable,
)

USER = {"theme": "Facilities", "sentiment": NEGATIVE, "severity": HIGH}


def make_record():
    return FeedbackRecord("fb_001", "The library wifi keeps dropping.", "2026-11-04T09:30:00", None, USER)


def test_new_record_is_pending_and_not_counted():
    record = make_record()
    assert record.verification == PENDING
    assert record.ai is None
    assert record.theme is None
    assert not record.counted
    assert not record.needs_review


def test_is_serializable():
    assert isinstance(make_record(), Serializable)


def test_user_values_cannot_be_changed_from_outside():
    values = dict(USER)
    record = FeedbackRecord("fb_001", "text", "2026-11-04T09:30:00", None, values)
    values["severity"] = LOW
    record.user["severity"] = LOW
    assert record.user["severity"] == HIGH


def test_fields_are_read_only():
    with pytest.raises(AttributeError):
        make_record().counted = True


def test_set_ai_stores_the_ai_values():
    record = make_record()
    record.set_ai("Wi-Fi", NEGATIVE, CRITICAL)
    assert record.ai == {"theme": "Wi-Fi", "sentiment": NEGATIVE, "severity": CRITICAL}


def test_set_ai_stores_a_summary_when_given():
    record = make_record()
    record.set_ai("Wi-Fi", NEGATIVE, CRITICAL, "Library wifi keeps dropping.")
    assert record.ai["summary"] == "Library wifi keeps dropping."


@pytest.mark.parametrize("summary", ["", "   ", 1])
def test_a_bad_summary_is_rejected_and_stores_nothing(summary):
    record = make_record()
    with pytest.raises(ValueError):
        record.set_ai("Wi-Fi", NEGATIVE, CRITICAL, summary)
    assert record.ai is None


def test_round_trip_keeps_the_summary():
    record = make_record()
    record.set_ai("Wi-Fi", NEGATIVE, CRITICAL, "Library wifi keeps dropping.")
    assert FeedbackRecord.from_dict(record.to_dict()).ai["summary"] == "Library wifi keeps dropping."


@pytest.mark.parametrize("theme, sentiment, severity", [
    ("", NEGATIVE, HIGH),
    ("Facilities", "angry", HIGH),
    ("Facilities", NEGATIVE, "urgent"),
])
def test_bad_values_are_rejected(theme, sentiment, severity):
    record = make_record()
    with pytest.raises(ValueError):
        record.set_ai(theme, sentiment, severity)
    with pytest.raises(ValueError):
        record.set_final(theme, sentiment, severity, MATCHED)
    with pytest.raises(ValueError):
        record.mark_reviewed(theme, sentiment, severity)


def test_set_final_counts_the_record():
    record = make_record()
    record.set_final("Facilities", NEGATIVE, HIGH, MATCHED)
    assert (record.theme, record.verification, record.counted) == ("Facilities", MATCHED, True)


@pytest.mark.parametrize("verification", [PENDING, REVIEWED, "approved"])
def test_set_final_rejects_other_verification_values(verification):
    with pytest.raises(ValueError):
        make_record().set_final("Facilities", NEGATIVE, HIGH, verification)


def test_excluding_reason_stops_counting():
    record = make_record()
    record.set_final("Facilities", NEGATIVE, HIGH, MISMATCH)
    record.add_review_reason("AI disagrees on sentiment", excludes=True)
    assert record.needs_review
    assert not record.counted


def test_non_excluding_reason_flags_but_still_counts():
    record = make_record()
    record.set_final("Facilities", NEGATIVE, CRITICAL, MATCHED)
    record.add_review_reason("Critical severity", excludes=False)
    assert record.needs_review
    assert record.counted


def test_clear_review_removes_reasons_and_exclusion():
    record = make_record()
    record.set_final("Facilities", NEGATIVE, HIGH, MATCHED)
    record.add_review_reason("Unclear theme", excludes=True)
    record.clear_review()
    assert record.review_reasons == []
    assert record.counted


def test_mark_reviewed_uses_admin_values_and_counts():
    record = make_record()
    record.set_final("Facilities", NEGATIVE, HIGH, MISMATCH)
    record.add_review_reason("AI disagrees on theme", excludes=True)
    record.mark_reviewed("Administration", NEGATIVE, LOW)
    assert (record.theme, record.severity, record.verification) == ("Administration", LOW, REVIEWED)
    assert record.review_reasons == []
    assert record.counted


def test_round_trip_keeps_every_field():
    record = make_record()
    record.set_ai("Wi-Fi", NEGATIVE, HIGH)
    record.set_final("Facilities", NEGATIVE, HIGH, MISMATCH)
    record.add_review_reason("AI theme differs", excludes=True)
    copy = FeedbackRecord.from_dict(record.to_dict())
    assert copy.to_dict() == record.to_dict()
    assert not copy.counted


def test_from_dict_with_only_creation_fields_gives_a_pending_record():
    record = FeedbackRecord.from_dict({
        "feedback_id": "fb_002",
        "text": "Too many deadlines this week.",
        "timestamp": "2026-11-04T10:00:00",
        "user": USER,
    })
    assert record.verification == PENDING
    assert record.source_file is None
    assert not record.counted


def test_from_dict_missing_required_key_raises():
    with pytest.raises(KeyError):
        FeedbackRecord.from_dict({"feedback_id": "fb_003"})
