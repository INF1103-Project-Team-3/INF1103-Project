import pytest

from managers.logic_manager import UserAIMismatchRule
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MEDIUM, MISMATCH, NEGATIVE, NEUTRAL, UNVERIFIED, FeedbackRecord,
)


def make_checked_record(user=("Facilities", NEGATIVE, HIGH), ai=("Facilities", NEGATIVE, HIGH)):
    """Final values are the user's, and the record starts as matched, as LogicManager leaves it."""
    theme, sentiment, severity = user
    record = FeedbackRecord("fb_001", "The library wifi keeps dropping.", "2026-09-17T08:03:00", None,
                            {"theme": theme, "sentiment": sentiment, "severity": severity})
    if ai is not None:
        record.set_ai(*ai)
    record.set_final(theme, sentiment, severity, MATCHED if ai is not None else UNVERIFIED)
    return record


def apply_rule(record):
    UserAIMismatchRule(ThemeNormaliser()).apply(record)
    return record


def test_a_record_the_ai_failed_on_has_nothing_to_compare():
    record = apply_rule(make_checked_record(ai=None))
    assert not record.needs_review
    assert record.verification == UNVERIFIED


@pytest.mark.parametrize("user, ai, agree", [
    (CRITICAL, CRITICAL, True),     # same severity
    (LOW, MEDIUM, True),            # one step apart
    (LOW, HIGH, False),             # two steps apart
    (HIGH, CRITICAL, False),        # only the AI says critical
    (CRITICAL, HIGH, False),        # only the user says critical
])
def test_severity_agreement(user, ai, agree):
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, user), ("Facilities", NEGATIVE, ai)))
    assert record.verification == (MATCHED if agree else MISMATCH)
    assert record.counted == agree
    assert record.needs_review != agree


def test_a_sentiment_difference_is_a_mismatch():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, HIGH), ("Facilities", NEUTRAL, HIGH)))
    assert record.verification == MISMATCH


def test_themes_are_compared_after_normalising():
    record = apply_rule(make_checked_record(("wifi", NEGATIVE, HIGH), ("Facilities", NEGATIVE, HIGH)))
    assert record.verification == MATCHED


@pytest.mark.parametrize("user_theme, ai_theme", [
    ("Facilities", "Assessment"),   # two different themes
    ("n/a", "other"),               # Unclear never matches, even with Unclear
])
def test_different_or_unclear_themes_are_a_mismatch(user_theme, ai_theme):
    record = apply_rule(make_checked_record((user_theme, NEGATIVE, HIGH), (ai_theme, NEGATIVE, HIGH)))
    assert record.verification == MISMATCH


def test_the_users_values_stay_as_the_final_ones_until_reviewed():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, LOW), ("Assessment", NEUTRAL, HIGH)))
    assert (record.theme, record.sentiment, record.severity) == ("Facilities", NEGATIVE, LOW)


def test_the_reason_names_every_conflict_and_only_those():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, LOW), ("Assessment", NEGATIVE, HIGH)))
    assert record.review_reasons == [
        "AI disagrees with the user on theme (user 'Facilities', AI 'Assessment'); severity (user 'low', AI 'high')"
    ]


def test_the_ais_summary_is_not_compared():
    record = make_checked_record()
    record.set_ai("Facilities", NEGATIVE, HIGH, "The library wifi keeps dropping.")
    apply_rule(record)
    assert not record.needs_review
    assert record.verification == MATCHED


class _SeesEverythingAsOneTheme:
    """Stands in for ThemeNormaliser, to show the rule uses the one it is given."""

    def normalise(self, label):
        return "Same Theme"


def test_uses_the_normaliser_it_was_given():
    record = make_checked_record(("Facilities", NEGATIVE, HIGH), ("Assessment", NEGATIVE, HIGH))
    UserAIMismatchRule(_SeesEverythingAsOneTheme()).apply(record)
    assert record.verification == MATCHED
