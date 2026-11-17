from itertools import count

import pytest

from managers.logic_manager.action_advisor import ActionAdvisor
from managers.logic_manager.theme_aggregator import ThemeAggregator
from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import CRITICAL, HIGH, LOW, MATCHED, NEGATIVE, POSITIVE, FeedbackRecord

WIFI = "Check Wi-Fi coverage and reliability in the areas students mention with IT services."
PRINTERS = "Ask IT to service the printers and publish how to report a faulty one."


_ids = count(1)


def make_record(text, theme="Facilities", sentiment=NEGATIVE, severity=HIGH):
    record = FeedbackRecord(f"fb_{next(_ids):03d}", text, "2026-10-10T10:00:00", None,
                            {"theme": theme, "sentiment": sentiment, "severity": severity})
    record.set_final(theme, sentiment, severity, MATCHED)
    return record


def suggest(records):
    result = ThemeAggregator(ThemeNormaliser()).aggregate(records)
    return {a["theme"]: a["suggested_action"] for a in ActionAdvisor().suggest(result, records).theme_actions}


def test_one_action_per_theme_in_the_results_order():
    # Workload has the most entries, so it comes first although it is last alphabetically
    records = [make_record("Three deadlines in one week.", theme="Workload"),
               make_record("Another deadline clash.", theme="Workload"),
               make_record("The wifi keeps dropping.")]
    result = ThemeAggregator(ThemeNormaliser()).aggregate(records)
    assert ActionAdvisor().suggest(result, records).theme_actions == [
        {"theme": "Workload",
         "suggested_action": "Check the assessment calendar for clashing deadlines and spread them out where possible."},
        {"theme": "Facilities", "suggested_action": WIFI},
    ]


def test_a_theme_with_only_praise_is_kept_up():
    records = [make_record("Tutorials are great.", theme="Teaching Quality", sentiment=POSITIVE, severity=LOW)]
    assert suggest(records)["Teaching Quality"] == "Keep doing what students praise about Teaching Quality."


def test_the_rule_most_negative_entries_mention_wins():
    records = [
        make_record("The PRINTERS jam all the time."),
        make_record("Printers in block B are broken... again"),
        make_record("The wifi drops."),
        make_record("The wifi is great now!", sentiment=POSITIVE),     # praise is not a problem
        make_record("Free wifiplus vouchers ran out."),                # not the whole word
    ]
    assert suggest(records)["Facilities"] == PRINTERS


def test_critical_feedback_goes_to_the_right_team_first():
    records = [make_record("I feel overwhelmed and can't cope.", theme="Well-being", severity=CRITICAL),
               make_record("Exam marking is unfair.", theme="Assessment", severity=CRITICAL),
               make_record("Marking is so slow.", theme="Assessment", severity=CRITICAL)]
    actions = suggest(records)
    assert actions["Well-being"] == ("First pass the 1 critical report to student counselling for immediate "
                                     "follow-up. Promote counselling and well-being support, especially around "
                                     "exams and deadlines.")
    assert actions["Assessment"].startswith("First pass the 2 critical reports to student welfare for immediate")


@pytest.mark.parametrize("theme, expected", [
    ("Facilities", "Pass the facilities problems to estates and IT, with the locations students mention."),
    ("Parking Fees", "Look into the 1 negative entry about Parking Fees and decide who should own it."),
])
def test_without_a_matching_keyword_the_theme_gets_a_general_action(theme, expected):
    assert suggest([make_record("This really needs sorting out.", theme=theme)])[theme] == expected


def test_only_counted_records_are_read():
    excluded = make_record("The wifi keeps dropping.")
    excluded.add_review_reason("Not counted", excludes=True)
    records = [make_record("The library is lovely.", sentiment=POSITIVE, severity=LOW), excluded]
    assert suggest(records)["Facilities"] == "Keep doing what students praise about Facilities."
