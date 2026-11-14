import pytest

from managers.logic_manager import ThemeStats
from managers.models import CRITICAL, HIGH, LOW, MEDIUM, NEGATIVE, NEUTRAL, POSITIVE, Serializable


def make_stats():
    return ThemeStats("Facilities", 4, {LOW: 1, MEDIUM: 0, HIGH: 2, CRITICAL: 1},
                      {POSITIVE: 0, NEUTRAL: 1, NEGATIVE: 3}, -0.75, 67, 1)


def test_stores_every_field():
    stats = make_stats()
    assert (stats.theme, stats.count, stats.avg_sentiment, stats.priority, stats.unverified) == (
        "Facilities", 4, -0.75, 67, 1)
    assert stats.severity_counts[HIGH] == 2
    assert stats.sentiment_counts[NEGATIVE] == 3


def test_is_serializable():
    assert isinstance(make_stats(), Serializable)


def test_fields_are_read_only():
    with pytest.raises(AttributeError):
        make_stats().priority = 100


def test_counts_cannot_be_changed_from_outside():
    stats = make_stats()
    stats.severity_counts[HIGH] = 99
    assert stats.severity_counts[HIGH] == 2


def test_round_trip_gives_an_equal_object():
    stats = make_stats()
    assert ThemeStats.from_dict(stats.to_dict()) == stats


def test_missing_field_raises_key_error():
    data = make_stats().to_dict()
    del data["priority"]
    with pytest.raises(KeyError):
        ThemeStats.from_dict(data)
