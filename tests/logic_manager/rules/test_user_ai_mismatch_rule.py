import pytest

from managers.logic_manager import ReviewRule, UserAIMismatchRule
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MEDIUM, MISMATCH, NEGATIVE, NEUTRAL, POSITIVE, UNVERIFIED, FeedbackRecord,
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


def test_is_a_review_rule_that_stops_counting():
    rule = UserAIMismatchRule(ThemeNormaliser())
    assert isinstance(rule, ReviewRule)
    assert rule.excludes


def test_exact_agreement_is_left_alone():
    record = apply_rule(make_checked_record())
    assert not record.needs_review
    assert record.verification == MATCHED
    assert record.counted


def test_a_record_the_ai_failed_on_has_nothing_to_compare():
    record = apply_rule(make_checked_record(ai=None))
    assert not record.needs_review
    assert record.verification == UNVERIFIED
    assert record.counted


@pytest.mark.parametrize("user, ai, agree", [
    (LOW, LOW, True), (MEDIUM, MEDIUM, True), (HIGH, HIGH, True), (CRITICAL, CRITICAL, True),
    # one step apart still agrees
    (LOW, MEDIUM, True), (MEDIUM, LOW, True), (MEDIUM, HIGH, True), (HIGH, MEDIUM, True),
    # two or more steps apart
    (LOW, HIGH, False), (HIGH, LOW, False),
    # only one side says critical, even one step away
    (HIGH, CRITICAL, False), (CRITICAL, HIGH, False), (MEDIUM, CRITICAL, False), (CRITICAL, LOW, False),
])
def test_severity_agreement(user, ai, agree):
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, user), ("Facilities", NEGATIVE, ai)))
    assert record.verification == (MATCHED if agree else MISMATCH)
    assert record.counted == agree


def test_one_step_apart_keeps_the_users_severity_and_the_ais_on_record():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, MEDIUM), ("Facilities", NEGATIVE, HIGH)))
    assert record.severity == MEDIUM
    assert record.ai["severity"] == HIGH


@pytest.mark.parametrize("user_sentiment, ai_sentiment", [(NEGATIVE, NEUTRAL), (POSITIVE, NEGATIVE), (NEUTRAL, POSITIVE)])
def test_any_sentiment_difference_is_a_mismatch(user_sentiment, ai_sentiment):
    record = apply_rule(make_checked_record(("Facilities", user_sentiment, HIGH), ("Facilities", ai_sentiment, HIGH)))
    assert record.verification == MISMATCH
    assert not record.counted


@pytest.mark.parametrize("user_theme, ai_theme", [
    ("wifi", "Facilities"),         # both normalise to the base theme
    ("FACILITIES", "facilities"),   # case
    ("car park", "Car-Park"),       # spacing and punctuation on a new theme
])
def test_themes_are_compared_after_normalising(user_theme, ai_theme):
    record = apply_rule(make_checked_record((user_theme, NEGATIVE, HIGH), (ai_theme, NEGATIVE, HIGH)))
    assert record.verification == MATCHED


@pytest.mark.parametrize("user_theme, ai_theme", [
    ("Facilities", "Assessment"),   # two different base themes
    ("Car Park", "Parking"),        # variants of a new theme stay different labels (7.4)
    ("n/a", "Facilities"),          # one side unclear
    ("Facilities", "other"),        # the other side unclear
    ("n/a", "other"),               # Unclear never matches, even with Unclear
])
def test_different_or_unclear_themes_are_a_mismatch(user_theme, ai_theme):
    record = apply_rule(make_checked_record((user_theme, NEGATIVE, HIGH), (ai_theme, NEGATIVE, HIGH)))
    assert record.verification == MISMATCH
    assert not record.counted


def test_the_users_values_stay_as_the_final_ones_until_reviewed():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, LOW), ("Assessment", POSITIVE, HIGH)))
    assert (record.theme, record.sentiment, record.severity) == ("Facilities", NEGATIVE, LOW)


def test_the_reason_names_only_the_fields_that_conflict():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, HIGH), ("Facilities", NEUTRAL, HIGH)))
    assert record.review_reasons == ["AI disagrees with the user on sentiment (user 'negative', AI 'neutral')"]


def test_the_reason_lists_every_conflict():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, LOW), ("Assessment", POSITIVE, HIGH)))
    assert record.review_reasons == [
        "AI disagrees with the user on theme (user 'Facilities', AI 'Assessment'); "
        "sentiment (user 'negative', AI 'positive'); severity (user 'low', AI 'high')"
    ]


def test_the_ais_summary_is_not_compared():
    record = make_checked_record()
    record.set_ai("Facilities", NEGATIVE, HIGH, "The library wifi keeps dropping.")
    apply_rule(record)
    assert not record.needs_review
    assert record.verification == MATCHED


def test_an_admin_review_resolves_the_mismatch():
    record = apply_rule(make_checked_record(("Facilities", NEGATIVE, LOW), ("Assessment", POSITIVE, HIGH)))
    record.mark_reviewed("Assessment", POSITIVE, HIGH)
    assert not record.needs_review
    assert record.counted


class _SeesEverythingAsOneTheme:
    """Stands in for ThemeNormaliser, to show the rule uses the one it is given."""

    def normalise(self, label):
        return "Same Theme"


def test_uses_the_normaliser_it_was_given():
    record = make_checked_record(("Facilities", NEGATIVE, HIGH), ("Assessment", NEGATIVE, HIGH))
    UserAIMismatchRule(_SeesEverythingAsOneTheme()).apply(record)
    assert record.verification == MATCHED
