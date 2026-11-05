import pytest

from managers.logic_manager import AggregationResult, ThemeStats
from managers.models import CRITICAL, HIGH, LOW, MEDIUM, NEGATIVE, NEUTRAL, POSITIVE, Serializable


def make_stats(theme, negative, neutral, positive, unverified=0):
    count = negative + neutral + positive
    return ThemeStats(theme, count, {LOW: count, MEDIUM: 0, HIGH: 0, CRITICAL: 0},
                      {POSITIVE: positive, NEUTRAL: neutral, NEGATIVE: negative}, 0.0, 50, unverified)


def make_result(**changes):
    values = {
        "themes": [make_stats("Facilities", 3, 1, 0, unverified=1), make_stats("Assessment", 1, 0, 1)],
        "total_entries": 8,
        "pending_themes": {"Parking Fees": 2},
    }
    values.update(changes)
    return AggregationResult(**values)


def test_is_serializable():
    assert isinstance(make_result(), Serializable)


def test_counted_entries_are_the_theme_counts_added_up():
    assert make_result().counted_entries == 6


def test_total_entries_include_records_that_were_not_counted():
    assert make_result().total_entries == 8


def test_sentiment_counts_are_added_up_across_themes():
    assert make_result().sentiment_counts == {POSITIVE: 1, NEUTRAL: 1, NEGATIVE: 4}


def test_negative_percent_is_a_whole_number():
    # 4 of 6 counted entries are negative: 66.7% -> 67
    assert make_result().negative_percent == 67


def test_negative_percent_is_0_when_nothing_is_counted():
    assert make_result(themes=[]).negative_percent == 0


def test_unverified_count_is_added_up_across_themes():
    assert make_result().unverified_count == 1


def test_get_finds_a_theme_or_returns_none():
    result = make_result()
    assert result.get("Assessment").count == 2
    assert result.get("Workload") is None


def test_themes_keep_their_order_and_cannot_be_changed():
    result = make_result()
    assert [stats.theme for stats in result.themes] == ["Facilities", "Assessment"]
    assert isinstance(result.themes, tuple)


def test_pending_themes_default_to_none_and_are_a_copy():
    assert make_result(pending_themes=None).pending_themes == {}
    result = make_result()
    result.pending_themes["Car Park"] = 1
    assert result.pending_themes == {"Parking Fees": 2}


def test_round_trip_gives_an_equal_result():
    result = make_result()
    assert AggregationResult.from_dict(result.to_dict()) == result


def test_to_dict_leaves_the_run_details_to_the_history_entry():
    data = make_result(run_at="2026-11-05T10:00:00").to_dict()
    assert "run_at" not in data
    assert data["counted_entries"] == 6


def test_from_dict_reads_a_history_entry_with_its_run_details():
    entry = {"run_at": "2026-11-05T10:00:00", "source_file": "week1.csv", "result": make_result().to_dict()}
    result = AggregationResult.from_dict(entry)
    assert (result.run_at, result.source_file) == ("2026-11-05T10:00:00", "week1.csv")
    assert result.counted_entries == 6


def test_from_dict_rejects_a_part_1_history_entry():
    part_1_entry = {"run_at": "2026-10-10T17:02:00", "source_file": "test-output.json",
                    "stats": {"total_entries": 25, "themes": []}}
    with pytest.raises(ValueError, match="Part 1"):
        AggregationResult.from_dict(part_1_entry)


@pytest.mark.parametrize("data", [None, [], {}, {"themes": [{"theme": "Facilities"}], "total_entries": 1}])
def test_from_dict_raises_value_error_for_anything_unreadable(data):
    with pytest.raises(ValueError):
        AggregationResult.from_dict(data)
