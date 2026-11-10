# Sample FeedbackRecords for the GUI demo, built from the stress-test files in tests/.

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from managers.models import CRITICAL, MATCHED, MISMATCH, SENTIMENTS, SEVERITIES, Action, FeedbackRecord

SAMPLES = Path(__file__).resolve().parent.parent / "tests" / "ai_manager_samples"
CHECKED_COUNT = 6


# feedback_id -> the AI's (theme, sentiment, severity) from the saved stress run.
# Reads both layouts: a saved FeedbackRecord ("ai": {...}) and the older flat "ai_theme" fields.
def load_ai_answers() -> dict[str, tuple[str, str, str]]:
    output = json.loads((SAMPLES / "stress-output.json").read_text(encoding="utf-8"))
    answers = {}
    for row in output:
        ai = row.get("ai") or {"theme": row.get("ai_theme"), "sentiment": row.get("ai_sentiment"),
                               "severity": row.get("ai_severity")}
        if all(ai.get(field) for field in ("theme", "sentiment", "severity")):
            answers[row["feedback_id"]] = (ai["theme"], ai["sentiment"].lower(), ai["severity"].lower())
    return answers


# Stress-test text with the hand labels as the student's values.
def build_sample_records() -> list[FeedbackRecord]:
    entries = json.loads((SAMPLES / "stress-input.json").read_text(encoding="utf-8"))
    labels = {row["feedback_id"]: row for row in
              json.loads((SAMPLES / "stress-ans-key.json").read_text(encoding="utf-8"))}
    answers = load_ai_answers()
    records = []
    for index, entry in enumerate(entries):
        label = labels[entry["feedback_id"]]
        user = {"theme": label["theme"],
                "sentiment": _allowed(label["sentiment"].lower(), SENTIMENTS),
                "severity": _allowed(label["severity"].lower(), SEVERITIES)}
        record = FeedbackRecord(entry["feedback_id"], entry["text"], entry["timestamp"],
                                "stress-input.json", user)
        if index < CHECKED_COUNT:
            record.set_ai(*answers[record.feedback_id])
            fake_check(record)
        records.append(record)
    return records


# Rough stand-in for Logic's rules, so the demo has flagged records.
def fake_check(record: FeedbackRecord) -> None:
    user, ai = record.user, record.ai
    gap = abs(SEVERITIES.index(user["severity"]) - SEVERITIES.index(ai["severity"]))
    reasons = []
    if user["theme"].lower() != ai["theme"].lower():
        reasons.append("Theme mismatch")
    if (user["severity"] == CRITICAL) != (ai["severity"] == CRITICAL):
        reasons.append("Critical (one side only)")
    elif gap >= 2:
        reasons.append("Severity gap")
    if user["sentiment"] != ai["sentiment"]:
        reasons.append("Sentiment mismatch")
    record.clear_review()
    record.set_final(user["theme"], user["sentiment"], user["severity"], MISMATCH if reasons else MATCHED)
    for reason in reasons:
        record.add_review_reason(reason, excludes=True)


def _allowed(value: str, allowed: tuple[str, ...]) -> str:
    return value if value in allowed else allowed[1]


SAMPLE_HISTORY = {
    "Assessment": (2, 2, 2, 5),
    "Facilities": (4, 4, 3, 1),
    "Teaching Quality": (3, 3, 3, 3),
    "Well-being": (1, 2, 3, 4),
    "Workload": (1, 1, 2, 2),
    "Administration": (2, 1, 1, 2),
    "Social Environment": (0, 0, 0, 1),
    "Internship Placement": (1, 0, 1, 1),
}
RUN_DAYS_AGO = (35, 28, 25, 14)


# [{"run": 1, "finished_at": "2026-10-01", "theme_counts": {...}}, ...], oldest first.
def build_sample_history(today: date | None = None) -> list[dict]:
    today = today or date.today()
    history = []
    for index, days_ago in enumerate(RUN_DAYS_AGO):
        counts = {theme: values[index] for theme, values in SAMPLE_HISTORY.items()}
        history.append({"run": index + 1,
                        "finished_at": (today - timedelta(days=days_ago)).isoformat(),
                        "theme_counts": counts})
    return history


# Two actions already logged, so the chart has a marker and the list isn't empty.
def build_sample_actions(today: date | None = None) -> list[Action]:
    today = today or date.today()
    logged = datetime.combine(today, datetime.min.time()).isoformat(timespec="seconds")
    return [
        Action("act_demo0001", "Facilities", "Upgraded the library Wi-Fi access points",
               (today - timedelta(days=27)).isoformat(), "wifi", logged),
        Action("act_demo0002", "Assessment", "Published the marking rubric",
               (today - timedelta(days=20)).isoformat(), None, logged),
    ]
