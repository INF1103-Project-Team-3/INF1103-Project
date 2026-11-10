"""Call 2's input: Part 1's payload shape built from the run's records (D18),
with the size limit (D19). No live API: the payload is read from the task."""

import json
from pathlib import Path

import pytest

from managers.ai_manager.summary_input import MAX_INPUT_CHARS, MAX_TEXT_CHARS, SummaryInput
from managers.ai_manager.summary_task import SummaryTask
from managers.logic_manager import LogicManager
from managers.models import FeedbackRecord, MATCHED, UNVERIFIED

CONFIG_DIR = Path(__file__).resolve().parents[2] / "managers" / "config"
SEVERITY_COUNTS = {"low": 0, "medium": 0, "high": 0, "critical": 0}


def theme_stats(theme, count=1, avg_sentiment=-1.0):
    return {
        "theme": theme, "count": count, "severity_counts": SEVERITY_COUNTS,
        "sentiment_counts": {"positive": 0, "neutral": 0, "negative": count},
        "avg_sentiment": avg_sentiment, "priority": 3, "unverified": 0,
    }


def stats(*themes):
    return {
        "total_entries": 9, "counted_entries": 7, "negative_percent": 71, "unverified_count": 1,
        "sentiment_counts": {"positive": 1, "neutral": 1, "negative": 5},
        "themes": list(themes), "pending_themes": {"Parking": 2},
    }


def record(feedback_id, theme, severity, summary="One line.", text="Raw text.", counted=True):
    """A record as Logic leaves it. summary=None gives one whose call 1 failed (ai is None)."""
    built = FeedbackRecord(feedback_id, text, "2026-11-09T10:00:00", None,
                           {"theme": theme, "sentiment": "negative", "severity": severity})
    if summary is not None:
        built.set_ai(theme, "negative", severity, summary)
    if counted:
        built.set_final(theme, "negative", severity, MATCHED if summary is not None else UNVERIFIED)
    return built


def payload(stats_dict, records, max_input_chars=None):
    task = SummaryTask(stats_dict, records, "Summarise.", max_input_chars)
    return json.loads(task.build_messages()[1]["content"])


def examples(built, theme_index=0):
    return built["themes"][theme_index]["examples"]


def padded(label):
    """A one-liner long enough that dropping it frees more room than the
    examples_shown and examples_total fields take, so one drop is enough."""
    return f"{label} " + "x" * 80


def labels(built, theme_index=0):
    return [example["summary"].split()[0] for example in examples(built, theme_index)]


# SummaryInput on its own
def test_summary_input_payload_and_theme_names_are_copies():
    built = SummaryInput(stats(theme_stats("Facilities"), theme_stats("Workload")), [record("fb_1", "Facilities", "high")])

    built.payload["themes"].clear()
    built.theme_names.clear()

    assert len(built.payload["themes"]) == 2
    assert built.theme_names == ["Facilities", "Workload"]


def test_summary_task_sends_what_summary_input_builds():
    records = [record("fb_1", "Facilities", "high", "Lift.")]

    assert payload(stats(theme_stats("Facilities")), records) == SummaryInput(stats(theme_stats("Facilities")), records, None).payload


# Part 1's shape
def test_payload_has_part_1_shape_and_leaves_out_undescribed_fields():
    built = payload(stats(theme_stats("Facilities")), [record("fb_1", "Facilities", "high")])

    assert list(built) == ["total_entries", "counted_entries", "sentiment_distribution", "themes"]
    assert built["sentiment_distribution"] == {"positive": 1, "neutral": 1, "negative": 5}
    assert list(built["themes"][0]) == ["theme", "count", "severity_counts", "avg_sentiment", "examples"]
    assert "priority" not in json.dumps(built)
    assert "Parking" not in json.dumps(built)  # pending themes are not counted, so not summarised


def test_theme_order_follows_the_result():
    built = payload(stats(theme_stats("Workload", 3), theme_stats("Facilities")), [])

    assert [theme["theme"] for theme in built["themes"]] == ["Workload", "Facilities"]


def test_every_number_comes_from_the_result_unchanged():
    facilities = theme_stats("Facilities", 4, avg_sentiment=-0.25)
    built = payload(stats(facilities), [])

    assert built["total_entries"] == 9
    assert built["counted_entries"] == 7
    assert built["themes"][0]["count"] == 4
    assert built["themes"][0]["avg_sentiment"] == -0.25
    assert built["themes"][0]["severity_counts"] == SEVERITY_COUNTS


# Examples
def test_examples_are_the_one_liners_with_final_severity_most_severe_first():
    records = [
        record("fb_1", "Facilities", "low", "Bin overflowing."),
        record("fb_2", "Facilities", "critical", "Railing loose."),
        record("fb_3", "Facilities", "high", "Lift broken."),
        record("fb_4", "Facilities", "high", "Aircon broken."),
    ]

    assert examples(payload(stats(theme_stats("Facilities", 4)), records)) == [
        {"severity": "critical", "summary": "Railing loose."},
        {"severity": "high", "summary": "Lift broken."},  # equal severities keep the records' order
        {"severity": "high", "summary": "Aircon broken."},
        {"severity": "low", "summary": "Bin overflowing."},
    ]


def test_examples_use_final_values_not_the_ai_ones():
    # The user said high, the AI medium; Logic keeps the user's (7.1), and the
    # example must match the theme's severity_counts, which count the final value.
    built_record = FeedbackRecord("fb_1", "Text.", "t", None, {"theme": "Facilities", "sentiment": "negative", "severity": "high"})
    built_record.set_ai("Catering", "negative", "medium", "Canteen queue long.")
    built_record.set_final("Facilities", "negative", "high", MATCHED)

    assert examples(payload(stats(theme_stats("Facilities")), [built_record])) == [
        {"severity": "high", "summary": "Canteen queue long."}
    ]


def test_examples_are_grouped_under_their_own_theme():
    records = [record("fb_1", "Facilities", "high", "Lift."), record("fb_2", "Workload", "medium", "Deadlines.")]
    built = payload(stats(theme_stats("Workload"), theme_stats("Facilities")), records)

    assert examples(built, 0) == [{"severity": "medium", "summary": "Deadlines."}]
    assert examples(built, 1) == [{"severity": "high", "summary": "Lift."}]


def test_uncounted_records_give_no_example():
    records = [record("fb_1", "Facilities", "high", "Counted."), record("fb_2", "Facilities", "high", "Held.", counted=False)]
    held_for_review = record("fb_3", "Facilities", "high", "Mismatch.")
    held_for_review.add_review_reason("mismatch", excludes=True)

    assert examples(payload(stats(theme_stats("Facilities")), [*records, held_for_review])) == [
        {"severity": "high", "summary": "Counted."}
    ]


def test_theme_with_no_records_passed_gets_no_examples():
    assert examples(payload(stats(theme_stats("Facilities")), [])) == []


# No one-liner: raw text in its place
def test_record_with_no_ai_sends_its_raw_text():
    built = payload(stats(theme_stats("Facilities")), [record("fb_1", "Facilities", "high", summary=None, text="The lift is broken.")])

    assert examples(built) == [{"severity": "high", "summary": "The lift is broken."}]


def test_record_saved_before_call_1_wrote_one_liners_sends_its_raw_text():
    old = record("fb_1", "Facilities", "high", summary=None, text="Saved before D18.", counted=False)
    old.set_ai("Facilities", "negative", "high")  # no summary, as on records from before this change
    old.set_final("Facilities", "negative", "high", MATCHED)

    assert examples(payload(stats(theme_stats("Facilities")), [old])) == [{"severity": "high", "summary": "Saved before D18."}]


@pytest.mark.parametrize("length, sent", [(MAX_TEXT_CHARS - 1, MAX_TEXT_CHARS - 1), (MAX_TEXT_CHARS, MAX_TEXT_CHARS),
                                          (MAX_TEXT_CHARS + 1, MAX_TEXT_CHARS), (2000, MAX_TEXT_CHARS)])
def test_raw_text_is_cut_to_the_limit(length, sent):
    text = "a" * length
    built = payload(stats(theme_stats("Facilities")), [record("fb_1", "Facilities", "high", summary=None, text=text)])

    assert examples(built)[0]["summary"] == "a" * sent


def test_one_liners_are_never_cut():
    one_liner = "word " * 15
    built = payload(stats(theme_stats("Facilities")), [record("fb_1", "Facilities", "high", one_liner, text="x" * 2000)])

    assert examples(built)[0]["summary"] == one_liner


def test_one_liners_and_raw_text_mix_in_one_theme():
    records = [record("fb_1", "Facilities", "high", "Lift broken."),
               record("fb_2", "Facilities", "critical", summary=None, text="Railing is loose near the makerspace.")]

    assert examples(payload(stats(theme_stats("Facilities", 2)), records)) == [
        {"severity": "critical", "summary": "Railing is loose near the makerspace."},
        {"severity": "high", "summary": "Lift broken."},
    ]


# Size limit (D19)
def test_no_limit_sends_every_example():
    records = [record(f"fb_{index}", "Facilities", "low", "word " * 15) for index in range(500)]

    built = payload(stats(theme_stats("Facilities", 500)), records, None)

    assert len(examples(built)) == 500
    assert "examples_shown" not in built


def test_default_limit_is_the_measured_value_and_is_applied():
    assert MAX_INPUT_CHARS == 8_000
    records = [record(f"fb_{index}", "Facilities", "low", "word " * 15) for index in range(500)]

    task = SummaryTask(stats(theme_stats("Facilities", 500)), records, "Summarise.")  # no limit passed
    built = json.loads(task.build_messages()[1]["content"])

    assert len(json.dumps(built)) <= MAX_INPUT_CHARS
    assert built["examples_shown"] < built["examples_total"] == 500


def test_reference_sized_run_fits_the_default_limit_untrimmed():
    # 20 counted one-liners across 7 themes, like the live reference run (3,616 chars).
    records = [record(f"fb_{index}", theme, "high", "word " * 12)
               for index, theme in enumerate(["Facilities", "Assessment", "Workload", "Well-being"] * 5)]
    themes = [theme_stats(theme, 5) for theme in ("Facilities", "Assessment", "Workload", "Well-being")]

    built = payload(stats(*themes), records, MAX_INPUT_CHARS)

    assert "examples_shown" not in built
    assert sum(len(theme["examples"]) for theme in built["themes"]) == 20


def test_payload_within_the_limit_is_unchanged():
    records = [record("fb_1", "Facilities", "high", "Lift.")]
    unlimited = payload(stats(theme_stats("Facilities")), records)

    assert payload(stats(theme_stats("Facilities")), records, len(json.dumps(unlimited))) == unlimited


def test_trimming_drops_the_least_severe_first_and_reports_it():
    records = [record("fb_1", "Facilities", "critical", padded("Railing.")), record("fb_2", "Facilities", "low", padded("Bin.")),
               record("fb_3", "Facilities", "high", padded("Lift."))]
    full = payload(stats(theme_stats("Facilities", 3)), records)

    built = payload(stats(theme_stats("Facilities", 3)), records, len(json.dumps(full)))
    assert "examples_shown" not in built
    built = payload(stats(theme_stats("Facilities", 3)), records, len(json.dumps(full)) - 1)

    assert labels(built) == ["Railing.", "Lift."]
    assert (built["examples_shown"], built["examples_total"]) == (2, 3)
    assert len(json.dumps(built)) <= len(json.dumps(full)) - 1
    assert built["themes"][0]["count"] == 3  # counts still cover every entry


def test_shown_and_total_fields_count_towards_the_limit():
    # Dropping "Bin." frees fewer characters than the two fields then take, so
    # the payload is still too long and a second example has to go.
    records = [record("fb_1", "Facilities", "critical", "Railing."), record("fb_2", "Facilities", "low", "Bin."),
               record("fb_3", "Facilities", "high", "Lift.")]
    full = payload(stats(theme_stats("Facilities", 3)), records)

    built = payload(stats(theme_stats("Facilities", 3)), records, len(json.dumps(full)) - 1)

    assert labels(built) == ["Railing."]
    assert len(json.dumps(built)) <= len(json.dumps(full)) - 1


def test_trimming_takes_from_the_largest_theme_among_equal_severities():
    records = [*[record(f"fb_w{index}", "Workload", "low", padded(f"Work {index}.")) for index in range(3)],
               *[record(f"fb_f{index}", "Facilities", "low", padded(f"Fac {index}.")) for index in range(2)]]
    themes = (theme_stats("Workload", 3), theme_stats("Facilities", 2))
    full = payload(stats(*themes), records)

    built = payload(stats(*themes), records, len(json.dumps(full)) - 1)

    assert labels(built, 0) == ["Work", "Work"]
    assert len(examples(built, 1)) == 2


def test_trimming_prefers_a_lower_severity_over_a_larger_theme():
    records = [*[record(f"fb_w{index}", "Workload", "high", padded(f"Work {index}.")) for index in range(3)],
               record("fb_f0", "Facilities", "high", padded("Fac high.")), record("fb_f1", "Facilities", "low", padded("Fac low."))]
    themes = (theme_stats("Workload", 3), theme_stats("Facilities", 2))
    full = payload(stats(*themes), records)

    built = payload(stats(*themes), records, len(json.dumps(full)) - 1)

    assert len(examples(built, 0)) == 3
    assert labels(built, 1) == ["Fac"]


def test_equal_themes_lose_from_the_first_listed():
    records = [record("fb_w", "Workload", "low", padded("W.")), record("fb_w2", "Workload", "low", padded("W2.")),
               record("fb_f", "Facilities", "low", padded("F.")), record("fb_f2", "Facilities", "low", padded("F2."))]
    themes = (theme_stats("Workload", 2), theme_stats("Facilities", 2))
    full = payload(stats(*themes), records)

    built = payload(stats(*themes), records, len(json.dumps(full)) - 1)

    assert (len(examples(built, 0)), len(examples(built, 1))) == (1, 2)


def test_every_theme_keeps_one_example_even_over_the_limit():
    records = [record(f"fb_{theme}_{index}", theme, "low", f"{theme} {index}.")
               for theme in ("Workload", "Facilities") for index in range(3)]
    themes = (theme_stats("Workload", 3), theme_stats("Facilities", 3))

    built = payload(stats(*themes), records, 10)

    assert (len(examples(built, 0)), len(examples(built, 1))) == (1, 1)
    assert (built["examples_shown"], built["examples_total"]) == (2, 6)


def test_trimming_keeps_critical_examples_while_lower_ones_remain():
    records = [*[record(f"fb_c{index}", "Well-being", "critical", f"Critical {index}.") for index in range(2)],
               *[record(f"fb_l{index}", "Well-being", "low", f"Low {index}.") for index in range(20)]]
    full = payload(stats(theme_stats("Well-being", 22)), records)
    limit = len(json.dumps(full)) // 2

    built = payload(stats(theme_stats("Well-being", 22)), records, limit)

    kept = [example["severity"] for example in examples(built)]
    assert kept[:2] == ["critical", "critical"]
    assert len(json.dumps(built)) <= limit


# The real Logic Manager's result, end to end
def test_real_aggregation_result_builds_a_consistent_payload():
    records = [
        record("fb_1", "Facilities", "high", "Lift broken."),
        record("fb_2", "Facilities", "low", "Bin full."),
        record("fb_3", "Workload", "critical", summary=None, text="I cannot cope with these deadlines."),
        record("fb_4", "Facilities", "medium", "Printers slow.", counted=False),  # Logic checks it below
    ]
    logic = LogicManager()
    logic.apply_rules(records)
    result = logic.aggregate(records)

    built = payload(result.to_dict(), records)

    assert built["total_entries"] == 4
    assert built["counted_entries"] == sum(theme["count"] for theme in built["themes"])
    for theme in built["themes"]:
        # one example per counted record, and the same severities as the counts
        assert len(theme["examples"]) == theme["count"]
        severities = [example["severity"] for example in theme["examples"]]
        assert {severity: severities.count(severity) for severity in theme["severity_counts"]} == theme["severity_counts"]


# The real prompt describes every field the payload can carry
def test_real_summary_prompt_describes_every_payload_field():
    prompt = (CONFIG_DIR / "summary_prompt.txt").read_text(encoding="utf-8")

    for field in ["total_entries", "counted_entries", "sentiment_distribution", "themes", "count",
                  "severity_counts", "avg_sentiment", "examples", "examples_shown", "examples_total"]:
        assert field in prompt, field
