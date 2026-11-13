import pytest

from managers.logic_manager import NewThemeRule
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import HIGH, NEGATIVE, UNCLEAR_THEME, UNVERIFIED, FeedbackRecord


def make_checked_record(theme):
    record = FeedbackRecord("fb_001", "Parking costs too much.", "2026-09-17T08:03:00", None,
                            {"theme": theme, "sentiment": NEGATIVE, "severity": HIGH})
    record.set_final(theme, NEGATIVE, HIGH, UNVERIFIED)
    return record


def test_flags_a_new_theme_and_stops_counting_it():
    record = make_checked_record("Parking Fees")
    NewThemeRule(ThemeNormaliser()).apply(record)
    assert record.review_reasons == ["New theme 'Parking Fees': confirm it or change it."]
    assert not record.counted


def test_leaves_a_base_theme_alone():
    record = make_checked_record("Facilities")
    NewThemeRule(ThemeNormaliser()).apply(record)
    assert not record.needs_review
    assert record.counted


def test_leaves_a_confirmed_theme_alone():
    record = make_checked_record("Parking Fees")
    NewThemeRule(ThemeNormaliser(["Parking Fees"])).apply(record)
    assert not record.needs_review


def test_leaves_unclear_to_the_unclear_rule():
    record = make_checked_record(UNCLEAR_THEME)
    NewThemeRule(ThemeNormaliser()).apply(record)
    assert not record.needs_review
