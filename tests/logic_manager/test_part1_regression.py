"""Checks that the OOP Logic Manager gives the same results as the Part 1 code.

fixtures/part1_baseline.json holds what the Part 1 code produced, with confidence
and agreement set to 1.0 so that only the rules kept in Part 2 apply (D1). The AI
and the user agree on every record here, so the cross-check changes nothing.
"""

import json
from pathlib import Path

import pytest

from managers.logic_manager import AggregationResult, LogicManager
from managers.models import SEVERITIES, FeedbackRecord

BASELINE = json.loads((Path(__file__).parent / "fixtures" / "part1_baseline.json").read_text(encoding="utf-8"))
RUNS = {run["name"]: run for run in BASELINE["runs"]}


def build_record(row):
    record = FeedbackRecord(row["feedback_id"], row["text"], row["timestamp"], None,
                            {"theme": row["theme"], "sentiment": row["sentiment"], "severity": row["severity"]})
    record.set_ai(row["theme"], row["sentiment"], row["severity"])
    return record


def process(run):
    """Validates a run and applies the rules, the way the pipeline's LogicStep does."""
    logic = LogicManager()
    valid, invalid = logic.validate([build_record(row) for row in run["records"]])
    assert invalid == []
    return logic, logic.apply_rules(valid)


def aggregate(run):
    logic, records = process(run)
    return logic.aggregate(records)


@pytest.mark.parametrize("run", BASELINE["runs"], ids=lambda run: run["name"])
def test_review_queue_matches_part_1(run):
    logic, records = process(run)
    assert [record.feedback_id for record in logic.review_queue(records)] == run["review_queue"]


@pytest.mark.parametrize("run", BASELINE["runs"], ids=lambda run: run["name"])
def test_totals_match_part_1(run):
    result = aggregate(run)
    assert result.total_entries == run["total_entries"]
    assert result.counted_entries == run["counted_entries"]
    assert result.sentiment_counts == run["sentiment_counts"]
    assert result.negative_percent == run["negative_percent"]


@pytest.mark.parametrize("run", BASELINE["runs"], ids=lambda run: run["name"])
def test_every_themes_numbers_and_order_match_part_1(run):
    actual = [
        {"theme": stats.theme, "count": stats.count, "severity_counts": stats.severity_counts,
         "avg_sentiment": stats.avg_sentiment, "priority_score": stats.priority}
        for stats in aggregate(run).themes
    ]
    assert actual == run["themes"]


@pytest.mark.parametrize("trend", BASELINE["trends"], ids=lambda t: f"{t['current']}-vs-{t['previous']}")
def test_trend_report_matches_part_1(trend):
    logic = LogicManager()
    previous = AggregationResult.from_dict({**trend["previous_run"], "result": aggregate(RUNS[trend["previous"]]).to_dict()})
    report = logic.compare_runs(aggregate(RUNS[trend["current"]]), previous)
    assert report.to_dict() == trend["expected"]


def test_first_run_message_matches_part_1():
    report = LogicManager().compare_runs(aggregate(RUNS["test_output"]), None)
    assert report.to_dict() == BASELINE["first_run_expected"]


def test_the_baseline_covers_every_trend_status():
    statuses = {row["status"] for trend in BASELINE["trends"] for row in trend["expected"]["themes"]}
    assert statuses == {"Escalating", "New", "Easing", "Steady", "Not reported"}


# Part 1's run_sanity_checks, which ran only when its file was run by hand
@pytest.mark.parametrize("run", BASELINE["runs"], ids=lambda run: run["name"])
def test_results_are_consistent(run):
    logic, records = process(run)
    result = logic.aggregate(records)
    queue = logic.review_queue(records)

    assert sum(record.counted for record in records) == result.counted_entries <= len(records)
    assert sum(stats.count for stats in result.themes) == result.counted_entries
    assert sum(result.sentiment_counts.values()) == result.counted_entries
    ranks = [SEVERITIES.index(record.severity) for record in queue]
    assert ranks == sorted(ranks, reverse=True)
    for earlier, later in zip(queue, queue[1:]):
        if earlier.severity == later.severity:
            assert earlier.theme <= later.theme
