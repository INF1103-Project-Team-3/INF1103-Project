import pytest

from managers.logic_manager.priority_scorer import PriorityScorer
from managers.models import CRITICAL, HIGH, LOW, MEDIUM


@pytest.fixture
def scorer():
    return PriorityScorer()


@pytest.mark.parametrize("count, severity_counts, avg_sentiment, expected", [
    # 4/10 severe * 45 + 0.3 * 20 + 10/10 * 35 = 18 + 6 + 35
    (10, {HIGH: 2, CRITICAL: 2, LOW: 6}, -0.3, 59),
    # 4/4 severe * 45 + 0.5 * 20 + 4/10 * 35 = 45 + 10 + 14
    (4, {HIGH: 4}, -0.5, 69),
    # nothing severe, positive: only frequency counts, 2/10 * 35
    (2, {LOW: 1, MEDIUM: 1}, 1.0, 7),
])
def test_scores_match_the_formula(scorer, count, severity_counts, avg_sentiment, expected):
    assert scorer.score(count, severity_counts, avg_sentiment) == expected


def test_worst_case_scores_100(scorer):
    assert scorer.score(10, {CRITICAL: 10}, -1.0) == 100


def test_no_entries_scores_0(scorer):
    assert scorer.score(0, {}, 0.0) == 0


def test_frequency_stops_counting_at_10_entries(scorer):
    assert scorer.score(10, {HIGH: 5}, -1.0) == scorer.score(40, {HIGH: 20}, -1.0)


def test_positive_sentiment_never_raises_the_score(scorer):
    assert scorer.score(5, {LOW: 5}, 1.0) == scorer.score(5, {LOW: 5}, 0.0)


def test_rounds_half_to_even_like_part_1(scorer):
    # 2/4 * 45 + 0 + 4/10 * 35 = 36.5, which Python's round() makes 36
    assert scorer.score(4, {HIGH: 2, LOW: 2}, 0.0) == 36
