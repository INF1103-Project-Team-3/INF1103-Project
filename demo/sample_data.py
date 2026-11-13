# Sample FeedbackRecords for the GUI demo, built from the stress-test files in tests/.

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from managers.logic_manager import LogicManager
from managers.models import SENTIMENTS, SEVERITIES, Action, FeedbackRecord

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


# Stress-test text with the hand labels as the student's values. The first few are
# classified and checked by the real LogicManager; the rest wait for the AI.
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
        records.append(record)
    LogicManager().apply_rules(records[:CHECKED_COUNT])
    return records


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
# Made-up priority per run (None = the theme had no counted entries yet, drawn as a gap).
SAMPLE_PRIORITY = {
    "Assessment": (40, 44, 52, 68),
    "Facilities": (72, 70, 55, 38),
    "Teaching Quality": (30, 28, 31, 29),
    "Well-being": (35, 48, 61, 70),
    "Workload": (42, 45, 50, 58),
    "Administration": (33, 30, 27, 35),
    "Social Environment": (None, None, None, 15),
    "Internship Placement": (25, None, 22, 24),
}
RUN_DAYS_AGO = (35, 28, 25, 14)


# [{"run": 1, "finished_at": "2026-10-01", "theme_counts": {...}, "theme_priority": {...}}, ...], oldest first.
def build_sample_history(today: date | None = None) -> list[dict]:
    today = today or date.today()
    history = []
    for index, days_ago in enumerate(RUN_DAYS_AGO):
        counts = {theme: values[index] for theme, values in SAMPLE_HISTORY.items() if values[index]}
        priority = {theme: values[index] for theme, values in SAMPLE_PRIORITY.items()
                    if values[index] is not None}
        history.append({"run": index + 1,
                        "finished_at": (today - timedelta(days=days_ago)).isoformat(),
                        "theme_counts": counts, "theme_priority": priority})
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
