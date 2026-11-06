from managers.logic_manager import ReviewRule, UnclearThemeRule
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import HIGH, MATCHED, NEGATIVE, UNCLEAR_THEME, UNVERIFIED, FeedbackRecord


def make_checked_record(user_theme, ai_theme=None):
    record = FeedbackRecord("fb_001", "Not sure where this goes.", "2026-09-17T08:03:00", None,
                            {"theme": user_theme, "sentiment": NEGATIVE, "severity": HIGH})
    if ai_theme is not None:
        record.set_ai(ai_theme, NEGATIVE, HIGH)
    record.set_final(user_theme, NEGATIVE, HIGH, MATCHED if ai_theme else UNVERIFIED)
    return record


def make_rule():
    return UnclearThemeRule(ThemeNormaliser())


def test_is_a_review_rule_that_stops_counting():
    rule = make_rule()
    assert isinstance(rule, ReviewRule)
    assert rule.excludes


def test_flags_an_unclear_user_theme_and_stops_counting_it():
    record = make_checked_record("n/a")
    make_rule().apply(record)
    assert record.review_reasons == ["Unclear theme (user said 'n/a') - needs a theme assigned"]
    assert not record.counted


def test_flags_an_unclear_ai_theme():
    record = make_checked_record("Facilities", ai_theme="other")
    make_rule().apply(record)
    assert record.review_reasons == ["Unclear theme (AI said 'other') - needs a theme assigned"]


def test_names_both_sides_when_both_are_unclear():
    record = make_checked_record("misc", ai_theme="spam")
    make_rule().apply(record)
    assert record.review_reasons == ["Unclear theme (user said 'misc'; AI said 'spam') - needs a theme assigned"]


def test_leaves_clear_themes_alone():
    record = make_checked_record("wifi", ai_theme="Facilities")
    make_rule().apply(record)
    assert not record.needs_review
    assert record.counted


def test_a_new_theme_is_not_unclear():
    record = make_checked_record("Parking Fees")
    make_rule().apply(record)
    assert not record.needs_review


class _EverythingIsUnclear:
    """Stands in for ThemeNormaliser, to show the rule uses the one it is given."""

    def normalise(self, label):
        return UNCLEAR_THEME


def test_uses_the_normaliser_it_was_given():
    record = make_checked_record("Facilities")
    UnclearThemeRule(_EverythingIsUnclear()).apply(record)
    assert record.needs_review
