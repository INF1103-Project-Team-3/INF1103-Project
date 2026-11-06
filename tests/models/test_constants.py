from managers.models import SEVERITIES, THEMES, UNCLEAR_THEME


def test_eight_base_themes_and_unclear_is_not_one():
    assert len(THEMES) == 8
    assert UNCLEAR_THEME not in THEMES


def test_severities_ordered_low_to_critical():
    assert SEVERITIES.index("low") < SEVERITIES.index("medium") < SEVERITIES.index("high") < SEVERITIES.index("critical")
