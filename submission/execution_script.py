"""FeedbackLens execution script: automated tests for the core logic, with no live AI.

What it checks (one section per testing requirement):
  1. Sample AI responses   - the sample replies in submission/ go through the real AI
                             response check and the real Logic rules, end to end
  2. AI response checks    - malformed AI output is rejected and retried, never saved
  3. Record validation     - bad records are set aside with their reasons
  4. Business rules        - user/AI cross-check, critical, unclear and new themes, reviews
  5. Scoring               - the 0-100 priority score and the theme statistics
  6. Routing and trends    - review queue order and run-to-run trend statuses
  7. New Part 2 features   - action impact, rule-based suggested actions, new themes,
                             and keeping the last AI summary when nothing new was sent
  8. Failure cases         - AI down, missing or corrupt files, data kept across runs

No live AI: AI replies come from StubLLMClient below (the sample files or hand-written
replies), so no API key or network is needed. Every file is written to a temporary
folder, so the repo's data/ is never touched.

Run it (from the repo root):
    docker compose run --rm app python submission/execution_script.py
    docker compose run --rm app python submission/execution_script.py sample_ai_output2
Without Docker:  python submission/execution_script.py [sample_module]

The optional argument picks the sample file in submission/ for section 1
(default: sample_ai_output). Exit code 0 means every check passed, 1 means one failed.
"""

import json
import logging
import sys
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

# The script lives in submission/; the project code is one folder up
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # the sample modules

from managers.ai_manager import AIManager, AISummary, LLMClient, ProgressReporter, PromptLibrary
from managers.ai_manager.llm_request_error import LLMRequestError
from managers.ai_manager import request_runner
from managers.ai_manager.request_runner import MAX_ATTEMPTS
from managers.data_manager import DataManager
from managers.io_manager import RecordBuilder, ReviewDecision, SessionResult
from managers.logic_manager import (
    ActionSuggestions, CriticalSeverityRule, ImpactReport, LogicManager, TrendReport,
)
from managers.logic_manager.priority_scorer import PriorityScorer
from managers.models import (
    CRITICAL, HIGH, LOW, MATCHED, MEDIUM, MISMATCH, NEGATIVE, NEUTRAL, PENDING, POSITIVE,
    REVIEWED, SEVERITIES, THEMES, UNCLEAR_THEME, UNVERIFIED, Action, FeedbackRecord,
)
from managers.pipeline import PipelineContext, PipelineManager
from managers.pipeline.steps import (
    AIClassificationStep, ImpactStep, IngestionStep, LogicStep, PersistenceStep, SummaryStep,
)

# Data logs an error for every corrupt file it meets. Section 8 makes corrupt files on
# purpose, so those expected messages are hidden to keep the report readable.
logging.disable(logging.CRITICAL)

SAMPLE_MODULE = "sample_ai_output"   # replaced by the command-line argument, if given
TODAY = date(2026, 11, 1)            # a fixed "today", so the impact checks never drift


# ---------------------------------------------------------------------------
# A tiny test runner: each check is a function registered under its section.
# ---------------------------------------------------------------------------

TESTS = []   # (section, function), in the order they are written


def check(section):
    """Registers the function below it as a check in that section."""
    def register(function):
        TESTS.append((section, function))
        return function
    return register


def expect(condition, message):
    """Fails the current check with message when condition is false."""
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# Stubs and helpers: stand-ins for the live AI, plus quick ways to build records.
# ---------------------------------------------------------------------------

class StubLLMClient(LLMClient):
    """Plays back scripted AI replies instead of calling the API. Each reply is the
    JSON text the model would return, or an LLMRequestError to raise."""

    def __init__(self, replies):
        self.__replies = list(replies)
        self.calls = 0

    @property
    def model(self):
        return "stub-model"

    def send(self, messages, schema_name, schema, token_margin, max_completion_tokens=None):
        self.calls += 1
        reply = self.__replies.pop(0)
        if isinstance(reply, LLMRequestError):
            raise reply
        return reply, 100, 0.0   # (content, tokens used, seconds to wait)


class SilentReporter(ProgressReporter):
    """Shows no progress and never waits, so retries run instantly."""

    def on_batch_start(self, title, details, progress): pass
    def on_attempt_start(self, request_id, attempt, max_attempts): pass
    def on_attempt_failed(self, request_id, attempt, max_attempts, reason): pass
    def on_wait(self, seconds, reason): pass
    def on_record_ok(self, request_id, description, progress): pass
    def on_record_failed(self, request_id, reason, progress): pass
    def on_batch_stopped(self, progress): pass
    def on_batch_end(self, progress, tokens_today, daily_limit): pass


def make_ai(replies):
    """The real AIManager, talking to a StubLLMClient instead of Groq."""
    token_log = {}
    prompts = PromptLibrary("Classify the feedback. Themes: {themes}", "Summarise this run.", list(THEMES))
    client = StubLLMClient(replies)
    ai = AIManager(client, "test-key", prompts, SilentReporter(),
                   lambda: dict(token_log), token_log.update)
    return ai, client


def classify(ai, records):
    """Runs Call 1 (classify_entries) without real waiting: the retry back-off
    sleeps are recorded in waits instead, as the AI Manager's own tests do."""
    waits = []
    real_sleep = request_runner.time.sleep
    request_runner.time.sleep = waits.append
    try:
        classified, pending, stopped = ai.classify_entries(records, [], on_classified=lambda record: None)
    finally:
        request_runner.time.sleep = real_sleep
    return classified, pending, stopped, waits


def ai_reply(theme, sentiment, severity, summary="A short one-line summary."):
    """One well-formed classification reply, as the model sends it."""
    return json.dumps({"theme": theme, "sentiment": sentiment, "severity": severity, "summary": summary})


def make_record(feedback_id, user, ai=None, text="Some feedback text.", when="2026-10-01T10:00:00"):
    """A record with the student's labels (user) and, optionally, the AI's (ai),
    each given as (theme, sentiment, severity)."""
    record = FeedbackRecord(feedback_id, text, when, None,
                            dict(zip(("theme", "sentiment", "severity"), user)))
    if ai is not None:
        record.set_ai(*ai, summary="One-line summary.")
    return record


def run_rules(records, logic=None):
    """Validates the records and runs the rules on the valid ones, like LogicStep."""
    logic = logic or LogicManager()
    valid, _invalid = logic.validate(records)
    return logic.apply_rules(valid)


def build_pipeline(data, logic, ai, ai_ready=True):
    """The six pipeline steps in AppEngine's order, with the AI passed in."""
    pipeline = PipelineManager(data_dir=str(data.data_dir))
    for step in (IngestionStep(data, logic, ai), AIClassificationStep(ai, data), LogicStep(logic, data),
                 SummaryStep(ai, logic, ai_ready=ai_ready), ImpactStep(logic, data), PersistenceStep(data)):
        pipeline.register_step(step)
    return pipeline


def load_samples():
    """The sample AI responses: rows of text plus the labels the AI gave them."""
    module = __import__(SAMPLE_MODULE)
    return module.SAMPLE_RECORDS


# ===========================================================================
# 1. Sample AI responses, end to end (no live API)
# ===========================================================================

@check("1. Sample AI responses (end to end, no live API)")
def sample_replies_pass_the_ai_response_check():
    """Every sample reply passes AIManager's response check and is stored on its record."""
    samples = load_samples()
    replies = [ai_reply(row["theme"], row["sentiment"], row["severity"], row["summary"]) for row in samples]
    ai, _client = make_ai(replies)
    # the student gave the same labels as the AI, so nothing below is a mismatch
    records = [make_record(row["feedback_id"], (row["theme"], row["sentiment"], row["severity"]),
                           text=row["text"], when=row["timestamp"]) for row in samples]
    classified, pending, stopped, _waits = classify(ai, records)
    expect(len(classified) == len(samples) and not pending and not stopped,
           f"{len(classified)} of {len(samples)} classified, {len(pending)} pending, stopped={stopped}")
    expect(all(record.ai["theme"] == row["theme"] for record, row in zip(records, samples)),
           "an AI label was not stored on its record")


@check("1. Sample AI responses (end to end, no live API)")
def sample_run_counts_flags_and_routes_correctly():
    """Sample run: critical rows are flagged but counted, Unclear rows are flagged and left out."""
    samples = load_samples()
    records = [make_record(row["feedback_id"], (row["theme"], row["sentiment"], row["severity"]),
                           ai=(row["theme"], row["sentiment"], row["severity"]),
                           text=row["text"], when=row["timestamp"]) for row in samples]
    logic = LogicManager()
    checked = run_rules(records, logic)
    queue = logic.review_queue(checked)
    result = logic.aggregate(checked)

    critical = [r for r in checked if r.severity == CRITICAL]
    unclear = [r for r in checked if r.theme == UNCLEAR_THEME]
    expect(all(r in queue and r.counted for r in critical), "a critical record was not flagged and counted")
    expect(all(r in queue and not r.counted for r in unclear), "an Unclear record was counted or not flagged")
    expect(result.total_entries == len(samples), f"total_entries {result.total_entries} != {len(samples)}")
    expect(result.counted_entries == len(samples) - len(unclear),
           f"counted {result.counted_entries}, expected {len(samples) - len(unclear)}")
    expect(all(0 <= stats.priority <= 100 for stats in result.themes), "a priority is outside 0-100")


# ===========================================================================
# 2. AI response checks: malformed AI output (failure cases)
# ===========================================================================
# A bad reply is retried up to MAX_ATTEMPTS times; if every attempt is bad, the record
# stays pending (ai = None) and the batch carries on with the next record.

MALFORMED_REPLIES = {
    "text that is not JSON": "Sure! The theme is Facilities.",
    "a missing field": json.dumps({"theme": "Facilities", "sentiment": "negative", "severity": "low"}),
    "an extra field": json.dumps({"theme": "Facilities", "sentiment": "negative", "severity": "low",
                                  "summary": "Wifi drops.", "confidence": 0.9}),
    "a sentiment outside the list": ai_reply("Facilities", "angry", "low"),
    "a severity outside the list": ai_reply("Facilities", "negative", "urgent"),
    "an empty theme": ai_reply("  ", "negative", "low"),
    "a made-up theme over 3 words": ai_reply("Very Long Made Up Theme", "negative", "low"),
    "a summary over 15 words": ai_reply("Facilities", "negative", "low", "word " * 16),
}


def _malformed_check(name, reply):
    def run():
        ai, client = make_ai([reply] * MAX_ATTEMPTS + [ai_reply("Facilities", "negative", "low")])
        bad = make_record("fb_bad", ("Facilities", "negative", "low"))
        good = make_record("fb_good", ("Facilities", "negative", "low"))
        classified, pending, stopped, waits = classify(ai, [bad, good])
        expect(bad.ai is None and bad in pending, "the malformed reply was saved on the record")
        expect(client.calls == MAX_ATTEMPTS + 1, f"expected {MAX_ATTEMPTS} retries, saw {client.calls - 1}")
        expect(classified == [good] and not stopped, "the batch did not carry on to the next record")
        expect(len(waits) >= MAX_ATTEMPTS, "it retried without waiting in between")
    run.__doc__ = f"Rejects {name}: retried, then left pending, and the batch carries on."
    return run


for _name, _reply in MALFORMED_REPLIES.items():
    check("2. AI response checks (malformed AI output)")(_malformed_check(_name, _reply))


@check("2. AI response checks (malformed AI output)")
def a_bad_reply_then_a_good_one_is_accepted():
    """A bad first attempt followed by a valid retry is accepted (retry works)."""
    ai, client = make_ai(["not json", ai_reply("Assessment", "neutral", "medium")])
    record = make_record("fb_1", ("Assessment", "neutral", "medium"))
    classified, _pending, _stopped, _waits = classify(ai, [record])
    expect(classified == [record] and record.ai["theme"] == "Assessment", "the valid retry was not stored")
    expect(client.calls == 2, f"expected 2 attempts, saw {client.calls}")


@check("2. AI response checks (malformed AI output)")
def a_theme_spelling_variant_is_cleaned():
    """A spelling variant of a listed theme ('well being') is stored as the exact label."""
    ai, _client = make_ai([ai_reply("well being", "negative", "low")])
    record = make_record("fb_1", ("Well-being", "negative", "low"))
    classify(ai, [record])
    expect(record.ai["theme"] == "Well-being", f"stored {record.ai['theme']!r}")


@check("2. AI response checks (malformed AI output)")
def a_rejected_api_key_stops_the_batch():
    """A rejected API key stops the batch at once and leaves every record pending."""
    error = LLMRequestError("invalid API key", LLMRequestError.AUTH, retryable=False)
    ai, client = make_ai([error])
    records = [make_record(f"fb_{n}", ("Facilities", "negative", "low")) for n in range(3)]
    classified, pending, stopped, _waits = classify(ai, records)
    expect(stopped and not classified and pending == records, "the batch did not stop with all pending")
    expect(client.calls == 1, "it kept calling the API after the key was rejected")


# ===========================================================================
# 3. Record validation
# ===========================================================================

@check("3. Record validation")
def invalid_records_are_set_aside_with_their_reasons():
    """Bad records are set aside with a reason each; the good records still go through."""
    good = make_record("fb_ok", ("Facilities", "negative", "low"))
    bad_sentiment = make_record("fb_s", ("Facilities", "furious", "low"))
    bad_time = make_record("fb_t", ("Facilities", "negative", "low"), when="yesterday")
    empty_text = make_record("fb_e", ("Facilities", "negative", "low"), text="   ")
    valid, invalid = LogicManager().validate([good, bad_sentiment, bad_time, empty_text, "not a record"])
    expect(valid == [good], f"valid = {[r.feedback_id for r in valid]}")
    reasons = {getattr(record, "feedback_id", "other"): problems for record, problems in invalid}
    expect(any("sentiment" in p for p in reasons["fb_s"]), "no sentiment reason")
    expect(any("timestamp" in p for p in reasons["fb_t"]), "no timestamp reason")
    expect(any("text" in p for p in reasons["fb_e"]), "no text reason")
    expect(len(invalid) == 4, f"{len(invalid)} invalid, expected 4")


@check("3. Record validation")
def a_duplicate_feedback_id_is_rejected():
    """A repeated feedback_id is rejected, so the same entry is never counted twice."""
    first = make_record("fb_1", ("Facilities", "negative", "low"))
    copy = make_record("fb_1", ("Facilities", "negative", "low"))
    valid, invalid = LogicManager().validate([first, copy])
    expect(valid == [first] and invalid[0][0] is copy, "the duplicate was not rejected")
    expect("duplicate" in invalid[0][1][0], f"reason was {invalid[0][1]}")


# ===========================================================================
# 4. Business rules (LogicManager.apply_rules)
# ===========================================================================

@check("4. Business rules")
def agreement_is_matched_and_counted():
    """User and AI agree: verification 'matched', counted, not flagged."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, LOW))])
    expect(record.verification == MATCHED and record.counted and not record.needs_review,
           f"{record.verification}, counted={record.counted}, flagged={record.needs_review}")


@check("4. Business rules")
def no_ai_result_is_unverified_but_still_counted():
    """AI failed on the record: 'unverified', still counted with the student's values (D4)."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, HIGH))])
    expect(record.verification == UNVERIFIED and record.counted, f"{record.verification}, counted={record.counted}")
    expect(record.severity == HIGH, "the student's values were not kept")


@check("4. Business rules")
def a_sentiment_conflict_is_a_mismatch():
    """User says negative, AI says positive: 'mismatch', flagged, not counted until reviewed."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", POSITIVE, LOW))])
    expect(record.verification == MISMATCH and record.needs_review and not record.counted,
           f"{record.verification}, flagged={record.needs_review}, counted={record.counted}")
    expect("sentiment" in record.review_reasons[0], f"reason: {record.review_reasons}")


@check("4. Business rules")
def severity_one_step_apart_still_matches():
    """Severity low vs medium (one step) is close enough to count as agreement."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, MEDIUM))])
    expect(record.verification == MATCHED, record.verification)


@check("4. Business rules")
def severity_two_steps_apart_is_a_mismatch():
    """Severity low vs high (two steps) is a mismatch."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, HIGH))])
    expect(record.verification == MISMATCH, record.verification)


@check("4. Business rules")
def critical_on_one_side_only_is_a_mismatch():
    """Only one side says critical (high vs critical): always a mismatch, never 'close enough'."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, HIGH), ai=("Facilities", NEGATIVE, CRITICAL))])
    expect(record.verification == MISMATCH, record.verification)


@check("4. Business rules")
def a_theme_alias_matches_its_base_theme():
    """The student's 'wifi' and the AI's 'Facilities' agree; the final theme is 'Facilities'."""
    [record] = run_rules([make_record("fb_1", ("wifi", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, LOW))])
    expect(record.verification == MATCHED and record.theme == "Facilities", f"{record.verification}, {record.theme}")


@check("4. Business rules")
def critical_feedback_is_flagged_and_still_counted():
    """Critical severity is always flagged for an admin, and still counted (7.2)."""
    [record] = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, CRITICAL), ai=("Facilities", NEGATIVE, CRITICAL))])
    expect(record.needs_review and record.counted, f"flagged={record.needs_review}, counted={record.counted}")
    expect(record.review_reasons == ["Critical severity"], f"reasons: {record.review_reasons}")


@check("4. Business rules")
def an_unclear_theme_is_flagged_and_not_counted():
    """A theme like 'n/a' becomes 'Unclear': flagged and left out of the statistics."""
    [record] = run_rules([make_record("fb_1", ("n/a", NEUTRAL, LOW), ai=("Facilities", NEUTRAL, LOW))])
    expect(record.theme == UNCLEAR_THEME and record.needs_review and not record.counted,
           f"theme={record.theme}, flagged={record.needs_review}, counted={record.counted}")


@check("4. Business rules")
def an_admin_review_is_final():
    """A reviewed record keeps the admin's values: the rules skip it and it is counted."""
    record = make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", POSITIVE, LOW))
    record.mark_reviewed("Assessment", NEUTRAL, MEDIUM)
    [record] = run_rules([record])
    expect(record.verification == REVIEWED and record.theme == "Assessment" and record.counted,
           f"{record.verification}, {record.theme}, counted={record.counted}")
    expect(not record.needs_review, "the rules flagged a reviewed record again")


@check("4. Business rules")
def the_rules_are_pluggable():
    """Open/Closed: Logic runs any list of ReviewRule objects and rejects anything else."""
    only_critical = LogicManager(rules=[CriticalSeverityRule()])
    [record] = run_rules([make_record("fb_1", ("n/a", NEUTRAL, CRITICAL))], only_critical)
    expect(record.review_reasons == ["Critical severity"], "a rule outside the list was applied")
    try:
        LogicManager(rules=["not a rule"])
    except TypeError:
        return
    raise AssertionError("a non-rule was accepted")


# ===========================================================================
# 5. Scoring and statistics
# ===========================================================================
# priority = share of high+critical x 45 + negativity x 20 + min(count / 10, 1) x 35

@check("5. Scoring")
def priority_score_matches_the_formula():
    """Priority for 2 entries, both negative and high: 1x45 + 1x20 + 0.2x35 = 72."""
    score = PriorityScorer().score(2, {HIGH: 2}, -1.0)
    expect(score == 72, f"got {score}")


@check("5. Scoring")
def priority_score_stays_between_0_and_100():
    """Lowest case (positive, low) scores only frequency; worst case is capped at 100."""
    expect(PriorityScorer().score(10, {LOW: 10}, 1.0) == 35, "10 positive low entries should score 35")
    expect(PriorityScorer().score(50, {CRITICAL: 50}, -1.0) == 100, "the worst case should score 100")
    expect(PriorityScorer().score(0, {}, 0.0) == 0, "no entries should score 0")


@check("5. Scoring")
def theme_statistics_are_correct():
    """Per-theme count, sentiment average, severity counts and priority from real records."""
    records = run_rules([
        make_record("fb_1", ("Facilities", NEGATIVE, CRITICAL), ai=("Facilities", NEGATIVE, CRITICAL)),
        make_record("fb_2", ("Facilities", NEGATIVE, HIGH), ai=("Facilities", NEGATIVE, HIGH)),
        make_record("fb_3", ("Facilities", POSITIVE, LOW), ai=("Facilities", POSITIVE, LOW)),
        make_record("fb_4", ("Assessment", NEUTRAL, LOW), ai=("Assessment", NEUTRAL, LOW)),
    ])
    result = LogicManager().aggregate(records)
    facilities = result.get("Facilities")
    expect(facilities.count == 3 and facilities.avg_sentiment == -0.33, f"{facilities.count}, {facilities.avg_sentiment}")
    expect(facilities.severity_counts[CRITICAL] == 1 and facilities.severity_counts[HIGH] == 1, "severity counts")
    # (2/3) x 45 + 0.33 x 20 + 0.3 x 35 = 30 + 6.6 + 10.5 = 47.1 -> 47
    expect(facilities.priority == 47, f"priority {facilities.priority}")
    expect([s.theme for s in result.themes] == ["Facilities", "Assessment"], "most-mentioned theme is not first")
    expect(result.negative_percent == 50, f"negative_percent {result.negative_percent}")


@check("5. Scoring")
def entries_left_out_are_not_in_the_statistics():
    """A mismatch is in total_entries but not in any theme's count."""
    records = run_rules([
        make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, LOW)),
        make_record("fb_2", ("Facilities", NEGATIVE, LOW), ai=("Facilities", POSITIVE, LOW)),
    ])
    result = LogicManager().aggregate(records)
    expect(result.total_entries == 2 and result.counted_entries == 1,
           f"total {result.total_entries}, counted {result.counted_entries}")


# ===========================================================================
# 6. Routing (review queue) and trends
# ===========================================================================

@check("6. Routing and trends")
def review_queue_puts_critical_first():
    """Review queue order: most severe first, then by theme, then by feedback_id."""
    logic = LogicManager()
    records = run_rules([
        make_record("fb_3", ("Workload", NEGATIVE, LOW), ai=("Workload", POSITIVE, LOW)),        # mismatch, low
        make_record("fb_2", ("Facilities", NEGATIVE, CRITICAL), ai=("Facilities", NEGATIVE, CRITICAL)),
        make_record("fb_1", ("Assessment", NEGATIVE, CRITICAL), ai=("Assessment", NEGATIVE, CRITICAL)),
        make_record("fb_4", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, LOW)),    # not flagged
    ], logic)
    queue = [r.feedback_id for r in logic.review_queue(records)]
    expect(queue == ["fb_1", "fb_2", "fb_3"], f"queue order {queue}")


def _run_result(*theme_rows):
    """An AggregationResult from (theme, count, severity) rows, all negative."""
    records, n = [], 0
    for theme, count, severity in theme_rows:
        for _ in range(count):
            n += 1
            records.append(make_record(f"fb_{n}", (theme, NEGATIVE, severity), ai=(theme, NEGATIVE, severity)))
    return LogicManager().aggregate(run_rules(records))


@check("6. Routing and trends")
def the_first_run_has_nothing_to_compare():
    """With no earlier run, the trend says so instead of inventing changes."""
    trend = LogicManager().compare_runs(_run_result(("Facilities", 2, LOW)), None)
    expect(not trend.has_previous, "the first run claimed a previous run")


@check("6. Routing and trends")
def trend_statuses_follow_the_priority_change():
    """A priority rise of 5+ is Escalating, a fall of 5+ is Easing, new and missing themes are marked."""
    previous = _run_result(("Facilities", 2, LOW), ("Assessment", 2, HIGH), ("Workload", 2, LOW),
                           ("Administration", 2, LOW))
    current = _run_result(("Facilities", 2, HIGH), ("Assessment", 2, LOW), ("Workload", 2, LOW),
                          ("Well-being", 2, LOW))
    trend = LogicManager().compare_runs(current, previous)
    status = {row["theme"]: row["status"] for row in trend.themes}
    expect(status["Facilities"] == TrendReport.ESCALATING, f"Facilities: {status['Facilities']}")
    expect(status["Assessment"] == TrendReport.EASING, f"Assessment: {status['Assessment']}")
    expect(status["Workload"] == TrendReport.STEADY, f"Workload: {status['Workload']}")
    expect(status["Well-being"] == TrendReport.NEW, f"Well-being: {status['Well-being']}")
    expect(status["Administration"] == TrendReport.NOT_REPORTED, f"Administration: {status['Administration']}")


# ===========================================================================
# 7. New Part 2 features
# ===========================================================================

def _impact_records(before_negative, after_negative):
    """Facilities feedback mentioning wifi, spread over the 14 days before and after
    an action dated 2026-10-18 (today is 2026-11-01)."""
    records, n = [], 0
    for days_before in range(before_negative):
        n += 1
        when = (date(2026, 10, 17) - timedelta(days=days_before)).isoformat() + "T10:00:00"
        records.append(make_record(f"fb_{n}", ("Facilities", NEGATIVE, HIGH), ai=("Facilities", NEGATIVE, HIGH),
                                   text="The wifi keeps dropping.", when=when))
    for days_after in range(after_negative):
        n += 1
        when = (date(2026, 10, 19) + timedelta(days=days_after)).isoformat() + "T10:00:00"
        records.append(make_record(f"fb_{n}", ("Facilities", NEGATIVE, HIGH), ai=("Facilities", NEGATIVE, HIGH),
                                   text="The wifi keeps dropping.", when=when))
    return run_rules(records)


def _wifi_action(action_date="2026-10-18"):
    return Action("act_1", "Facilities", "Upgraded library Wi-Fi", action_date, "wifi", "2026-10-18T09:00:00")


@check("7. New features")
def an_action_followed_by_fewer_complaints_is_effective():
    """Action impact: negative feedback fell after the action, so it is 'Effective'."""
    [report] = LogicManager().evaluate_actions([_wifi_action()], _impact_records(8, 1), TODAY)
    expect(report.label == ImpactReport.EFFECTIVE, f"{report.label}: {report.message}")


@check("7. New features")
def an_action_followed_by_more_complaints_is_worse():
    """Action impact: negative feedback rose after the action, so it is 'Worse'."""
    [report] = LogicManager().evaluate_actions([_wifi_action()], _impact_records(1, 8), TODAY)
    expect(report.label == ImpactReport.WORSE, f"{report.label}: {report.message}")


@check("7. New features")
def an_action_with_too_little_data_is_too_early_to_tell():
    """Action impact: dated today, or with too few entries, it is 'Too early to tell'."""
    logic = LogicManager()
    [today] = logic.evaluate_actions([_wifi_action(TODAY.isoformat())], _impact_records(8, 1), TODAY)
    [few] = logic.evaluate_actions([_wifi_action()], _impact_records(1, 1), TODAY)
    expect(today.label == ImpactReport.TOO_EARLY and few.label == ImpactReport.TOO_EARLY,
           f"dated today: {today.label}; two entries: {few.label}")


@check("7. New features")
def rule_based_actions_cover_every_theme():
    """Suggested actions without the AI: critical first, then a keyword match, else 'keep doing it'."""
    logic = LogicManager()
    records = run_rules([
        make_record("fb_1", ("Facilities", NEGATIVE, CRITICAL), ai=("Facilities", NEGATIVE, CRITICAL),
                    text="Exposed wiring near the lab."),
        make_record("fb_2", ("Teaching Quality", NEGATIVE, LOW), ai=("Teaching Quality", NEGATIVE, LOW),
                    text="The lecture pace is far too fast."),
        make_record("fb_3", ("Workload", POSITIVE, LOW), ai=("Workload", POSITIVE, LOW), text="Deadlines are fair."),
    ], logic)
    suggestions = logic.suggest_actions(logic.aggregate(records), records)
    actions = {row["theme"]: row["suggested_action"] for row in suggestions.theme_actions}
    expect(actions["Facilities"].startswith("First pass the 1 critical report"), actions["Facilities"])
    expect("pacing" in actions["Teaching Quality"], actions["Teaching Quality"])
    expect(actions["Workload"] == "Keep doing what students praise about Workload.", actions["Workload"])


@check("7. New features")
def a_new_theme_waits_until_an_admin_confirms_it():
    """A new theme ('parking fees') is flagged and not counted, until an admin confirms it."""
    logic = LogicManager()
    [record] = run_rules([make_record("fb_1", ("parking fees", NEGATIVE, LOW), ai=("Parking Fees", NEGATIVE, LOW))], logic)
    expect(record.theme == "Parking Fees" and record.needs_review and not record.counted,
           f"{record.theme}, flagged={record.needs_review}, counted={record.counted}")
    expect(logic.aggregate([record]).pending_themes == {"Parking Fees": 1}, "not listed as waiting")
    logic.set_known_themes([*THEMES, "Parking Fees"])
    [record] = logic.apply_rules([record])
    expect(record.counted and not record.needs_review, "still not counted after the admin confirmed it")


class _CountingAI:
    """A stand-in AIManager for SummaryStep: counts Call 2 and returns a summary."""
    def __init__(self):
        self.summaries = 0

    def summarise(self, result, records):
        self.summaries += 1
        return AISummary("All fine.", [{"theme": "Facilities", "suggested_action": "Keep going"}])


def _summary_context(sent, classified, stopped=False):
    logic = LogicManager()
    records = run_rules([make_record("fb_1", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, LOW))], logic)
    return logic, PipelineContext(records=records, result=logic.aggregate(records),
                                  sent_to_ai=sent, classified_count=classified, ai_stopped=stopped)


@check("7. New features")
def nothing_new_keeps_the_last_ai_summary():
    """A review-only run with the AI working: no Call 2 and no 'AI unavailable' actions (D24)."""
    logic, context = _summary_context(sent=0, classified=0)
    ai = _CountingAI()
    SummaryStep(ai, logic, ai_ready=True).execute(context)
    expect(ai.summaries == 0 and context.summary is None and context.fallback_actions is None,
           f"Call 2 made {ai.summaries} time(s); fallback={context.fallback_actions}")


@check("7. New features")
def the_ai_down_uses_rule_based_actions():
    """No API key, or Call 1 stopped: rule-based actions are used, labelled 'AI unavailable' (D21)."""
    for ai_ready, stopped in ((False, False), (True, True)):
        logic, context = _summary_context(sent=1, classified=0, stopped=stopped)
        SummaryStep(_CountingAI(), logic, ai_ready=ai_ready).execute(context)
        expect(context.summary is None and isinstance(context.fallback_actions, ActionSuggestions),
               f"ai_ready={ai_ready}, stopped={stopped}: no rule-based actions")


# ===========================================================================
# 8. Failure cases and persistence (real DataManager in a temporary folder)
# ===========================================================================

@check("8. Failure cases")
def missing_files_give_empty_results():
    """A brand-new data folder: every load returns an empty result instead of crashing."""
    with tempfile.TemporaryDirectory() as folder:
        data = DataManager(folder)
        expect(data.load_records() == [] and data.load_pending() == [] and data.load_actions() == [],
               "records, pending or actions not empty")
        expect(data.load_previous_run() is None and data.load_history() == [], "history not empty")
        expect(data.load_known_themes() == list(THEMES), "known themes are not the 8 base themes")


@check("8. Failure cases")
def corrupt_json_files_do_not_crash_the_app():
    """Corrupt JSON in the records, history and known-themes files is handled safely."""
    with tempfile.TemporaryDirectory() as folder:
        for name in ("processed_feedback.json", "aggregated_history.json", "known_themes.json"):
            (Path(folder) / name).write_text("{ this is not json", encoding="utf-8")
        data = DataManager(folder)
        expect(data.load_records() == [], "corrupt records file did not load as empty")
        expect(data.load_previous_run() is None, "corrupt history did not load as 'no previous run'")
        expect(data.load_known_themes() == list(THEMES), "corrupt themes file lost the base themes")


@check("8. Failure cases")
def one_corrupt_record_does_not_lose_the_others():
    """A stored record with fields missing is skipped; the good records still load."""
    with tempfile.TemporaryDirectory() as folder:
        good = run_rules([make_record("fb_good", ("Facilities", NEGATIVE, LOW), ai=("Facilities", NEGATIVE, LOW))])[0]
        payload = {"records": [good.to_dict(), {"feedback_id": "fb_broken"}]}
        (Path(folder) / "processed_feedback.json").write_text(json.dumps(payload), encoding="utf-8")
        records = DataManager(folder).load_records()
        expect([r.feedback_id for r in records] == ["fb_good"], f"loaded {[r.feedback_id for r in records]}")


@check("8. Failure cases")
def a_full_run_with_the_ai_down_still_completes():
    """AI down (rejected key): the whole pipeline still runs, counts the entries and saves the run."""
    with tempfile.TemporaryDirectory() as folder:
        data, logic = DataManager(folder), LogicManager()
        ai, _client = make_ai([LLMRequestError("invalid API key", LLMRequestError.AUTH, retryable=False)])
        builder = RecordBuilder()
        entries = [builder.build({"text": f"The wifi drops in room {n}.", "theme": "Facilities",
                                  "sentiment": NEGATIVE, "severity": LOW}) for n in range(3)]
        context = build_pipeline(data, logic, ai).execute_pipeline(SessionResult(records=entries))
        expect(context.ai_stopped and all(r.verification == UNVERIFIED and r.counted for r in context.records),
               "entries were not unverified and counted")
        expect(isinstance(context.fallback_actions, ActionSuggestions), "no rule-based actions")
        expect(len(data.load_records()) == 3 and data.load_pending() == [], "the run was not saved")
        expect(len(data.load_history()) == 1, "the run is missing from the history")


@check("8. Failure cases")
def saved_records_survive_later_runs():
    """Records stay saved across runs, a review is applied, and nothing is counted twice."""
    with tempfile.TemporaryDirectory() as folder:
        data, logic = DataManager(folder), LogicManager()
        ai, _client = make_ai([ai_reply("Facilities", NEGATIVE, LOW)] * 5)
        pipeline = build_pipeline(data, logic, ai)
        builder = RecordBuilder()
        entries = [builder.build({"text": f"The wifi drops in room {n}.", "theme": "Facilities",
                                  "sentiment": NEGATIVE, "severity": LOW}) for n in range(5)]
        pipeline.execute_pipeline(SessionResult(records=entries))
        decision = ReviewDecision.update(entries[0].feedback_id,
                                         {"theme": "Facilities", "sentiment": NEGATIVE, "severity": HIGH})
        second = pipeline.execute_pipeline(SessionResult(decisions=[decision]))
        stored = {r.feedback_id: r for r in data.load_records()}
        expect(len(stored) == 5, f"{len(stored)} records kept after two runs, expected 5")
        expect(stored[entries[0].feedback_id].verification == REVIEWED, "the review was not saved")
        expect(second.result.total_entries == 5, f"second run counted {second.result.total_entries} entries")


# ---------------------------------------------------------------------------
# Running the checks
# ---------------------------------------------------------------------------

def run_all() -> int:
    """Runs every check, prints a report, and returns how many failed."""
    print("FeedbackLens execution script (no live AI)")
    print(f"Sample AI responses: submission/{SAMPLE_MODULE}.py")
    failed, section = [], None
    for test_section, function in TESTS:
        if test_section != section:
            section = test_section
            print(f"\n{section}")
        description = (function.__doc__ or function.__name__).strip().splitlines()[0]
        try:
            function()
            print(f"  PASS  {description}")
        except Exception as error:   # one failing check must not stop the others
            failed.append(description)
            print(f"  FAIL  {description}")
            reason = str(error) if isinstance(error, AssertionError) else traceback.format_exc().strip().splitlines()[-1]
            print(f"        -> {reason}")
    print(f"\n{len(TESTS) - len(failed)} of {len(TESTS)} checks passed.")
    return len(failed)


def main() -> None:
    global SAMPLE_MODULE
    if len(sys.argv) > 1:
        SAMPLE_MODULE = sys.argv[1].removesuffix(".py")
    try:
        load_samples()
    except (ModuleNotFoundError, AttributeError):
        print(f"Error: submission/{SAMPLE_MODULE}.py not found, or it has no SAMPLE_RECORDS.")
        sys.exit(1)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
