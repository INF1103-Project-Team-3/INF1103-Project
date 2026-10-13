import json
from datetime import datetime
from pathlib import Path
 
# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
MIN_CONFIDENCE = 0.5

# Allowed values. The dict order is the display order (low -> critical).
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SENTIMENT_SCORE = {"positive": 1, "neutral": 0, "negative": -1}
 
# Paths are built from this file's location, so they work from any terminal
# folder. logic_manager.py lives in src/, so two levels up is the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = REPO_ROOT / "config" / "test-output.json"
OUTPUT_DIR = REPO_ROOT / "output"  # scratch results (git-ignored)
 
# Every record from the AI must have these fields, with these types.
REQUIRED_FIELDS = {
    "feedback_id": "string",
    "text": "string",
    "timestamp": "string",
    "theme": "string",
    "sentiment": "string",
    "severity": "string",
    "summary": "string",
    "confidence": "number",
    "agreement": "number",
}
ALLOWED_VALUES = {
    "sentiment": list(SENTIMENT_SCORE),
    "severity": list(SEVERITY_RANK),
}
ZERO_TO_ONE_FIELDS = ("confidence", "agreement")
 

# ---------------------------------------------------------------------------
# Reading and writing JSON files
# ---------------------------------------------------------------------------
def read_json(path):
    """Reads a JSON file and returns its contents (a dict or list)."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    """Writes data to a JSON file, creating the parent folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_records(path: str | Path = INPUT_FILE) -> list:
    """Loads the AI's classified feedback from a JSON file. Accepts a plain
    list of records, or a dict with the list under a "records" key. Only
    the overall shape is checked here; each record is checked separately
    by validate_record()."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    data = read_json(path)
    # the file may be {"records": [...]} instead of a plain list
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    # individual records are checked later by validate_record(), so one bad
    # entry doesn't stop the whole file from loading
    if not isinstance(data, list):
        raise ValueError(f"{path.name} should contain a list of feedback records")
    return data


# ---------------------------------------------------------------------------
# Validating the AI's output
# ---------------------------------------------------------------------------
def _matches_type(value, type_name):
    """True if value is the kind of thing type_name describes."""
    match type_name:
        case "string":
            return isinstance(value, str)
        case "number":
            # bool is a kind of int in Python, so True would otherwise pass
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        case _:
            raise ValueError(f"Unknown type name: {type_name}")

def validate_record(record):
    """Returns a list of problems with one record. An empty list means the
    record is valid: every required field is present, has the right type,
    uses an allowed value, and confidence/agreement are between 0 and 1."""
    if not isinstance(record, dict):
        return ["record is not a JSON object"]
 
    problems = []
    for field, type_name in REQUIRED_FIELDS.items():
        if field not in record:
            problems.append(f"missing field '{field}'")
            continue
        value = record[field]
        if not _matches_type(value, type_name):
            problems.append(
                f"'{field}' should be a {type_name}, got {type(value).__name__}: {value!r}"
            )
        elif type_name == "string" and not value.strip():
            problems.append(f"'{field}' is empty")
        elif field in ALLOWED_VALUES and value not in ALLOWED_VALUES[field]:
            problems.append(
                f"'{field}' must be one of {ALLOWED_VALUES[field]}, got {value!r}"
            )
        elif field in ZERO_TO_ONE_FIELDS and not 0.0 <= value <= 1.0:
            problems.append(f"'{field}' must be between 0.0 and 1.0, got {value}")
 
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str) and timestamp.strip():
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            problems.append(f"'timestamp' is not a valid ISO date-time, got {timestamp!r}")
    return problems


def split_valid_records(records):
    """Splits records into (valid, invalid). One bad record never stops the
    rest. Each invalid entry keeps the original record and the reasons it
    failed, so it can be inspected or sent back to the AI."""
    valid, invalid = [], []
    seen_ids = set()
    for index, record in enumerate(records):
        problems = validate_record(record)
        if not problems:
            # a repeated id would be counted twice; the first one is kept
            if record["feedback_id"] in seen_ids:
                problems.append(f"duplicate feedback_id '{record['feedback_id']}'")
            seen_ids.add(record["feedback_id"])
        if problems:
            invalid.append({
                "index": index,
                "feedback_id": record.get("feedback_id") if isinstance(record, dict) else None,
                "problems": problems,
                "record": record,
            })
        else:
            valid.append(record)
    return valid, invalid


# ---------------------------------------------------------------------------
# Theme normalisation
# ---------------------------------------------------------------------------
# Canonical theme -> alternative labels the AI might produce for it, written
# in lowercase with spaces (see _clean_label). To support a new variant, add
# it to the right list.
THEME_ALIASES_BY_CANONICAL = {
    "Teaching Quality": [
        "teaching quality", "teaching", "teaching style", "teaching methods",
        "lecture quality", "lectures", "lecture delivery", "lecturer",
        "lecturers", "lecture speed", "lecture pace", "pacing", "pace",
        "course pace", "tutorial quality", "tutorials", "instructor quality",
        "instruction quality", "course content", "module content",
        "teaching staff", "professor quality",
    ],
    "Assessment": [
        "assessment", "assessments", "assignments", "assignment",
        "grading", "marking", "marking criteria", "grading criteria",
        "rubric", "rubrics", "exams", "exam", "examinations", "tests",
        "quizzes", "coursework", "group project grading", "academic integrity",
        "plagiarism",
    ],
    "Facilities": [
        "facilities", "facility", "campus facilities", "infrastructure",
        "equipment", "classrooms", "lecture theatre", "lecture theater",
        "labs", "lab", "laboratory", "library", "printing", "printers",
        "wifi", "wi fi", "internet", "air conditioning", "aircon",
        "canteen", "food", "vending machine", "maintenance", "campus safety",
    ],
    "Administration": [
        "administration", "admin", "administrative", "timetable",
        "timetabling", "scheduling", "module registration", "registration",
        "enrolment", "enrollment", "student portal", "portal",
        "booking system", "bookings", "communication", "announcements",
        "bureaucracy", "student services", "fees",
    ],
    "Well-being": [
        "well being", "wellbeing", "wellness", "mental health",
        "stress", "workload", "burnout", "student welfare", "welfare",
        "health", "counselling", "counseling", "mental wellbeing",
        "emotional wellbeing", "work life balance",
    ],
    "Social Environment": [
        "social environment", "social", "campus culture", "culture",
        "harassment", "bullying", "discrimination", "peer relationships",
        "group dynamics", "teamwork", "classmates", "safety",
        "personal safety", "stalking", "inclusion", "diversity",
    ],
    "Internship Placement": [
        "internship placement", "internship", "internships", "placement",
        "placements", "iwsp", "work study", "work integrated learning",
        "industry attachment", "attachment", "industry placement",
    ],
    "Unclear": [
        "unclear", "unknown", "other", "others", "n a", "none", "general",
        "miscellaneous", "misc", "off topic", "no feedback", "spam",
    ],
}


def _clean_label(label: str) -> str: 
    """Lowercases, turns hyphens/underscores/punctuation into spaces and 
    collapses repeated spaces so 'Well-being', 'well_being' and'  WELL  being ' 
    all become 'well being' before lookup."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in label.lower())
    return " ".join(cleaned.split())


def _build_alias_lookup(by_canonical: dict) -> dict: 
    """Flattens the grouped dictionary above into {alias: canonical}. Raises
    if an alias is listed under two themes, since the second would silently
    overwrite the first and be very hard to spot."""
    lookup = {}
    for canonical, aliases in by_canonical.items():
        for alias in [canonical] + aliases:
            key = _clean_label(alias)
            if key in lookup and lookup[key] != canonical:
                raise ValueError(
                    f"Alias '{alias}' is listed under both '{lookup[key]}' and '{canonical}'"
                )
            lookup[key] = canonical
    return lookup


THEME_ALIASES = _build_alias_lookup(THEME_ALIASES_BY_CANONICAL)


def normalise_theme(theme: str) -> str: 
    """Maps similar theme labels to a canonical name, so that the same underlying issue
      doesn't get split into separate buckets just because the AI phrased it differently. 
      A label with no known alias is returned unchanged, so new themes still show up 
      instead of being silently forced into a wrong bucket."""
    return THEME_ALIASES.get(_clean_label(theme), theme.strip())


def apply_feedback_rules(record): 
    """Normalises the theme and adds three fields: needs_review,
    review_reason and counted. The record must already have passed
    validate_record(), so every field is known to be present."""
    review = []
    if record["severity"] == "critical": #checking if feedback is critical
        review.append("Critical severity")
    if record["confidence"] < MIN_CONFIDENCE: #checking if feedback is below confidence threshold
        review.append(f"Confidence {record['confidence']:.2f} is below threshold {MIN_CONFIDENCE}.")
    if record["agreement"] < 1.0: #checking if feedback has low agreement
        review.append(f"Agreement {record['agreement']:.2f} - AI outputs did not fully agree.")
    return {
        **record,
        "theme": normalise_theme(record["theme"]),
        # low-confidence or low-agreement feedback is reviewed, not counted
        "counted": record["confidence"] >= MIN_CONFIDENCE and record["agreement"] >= 1.0,
        "needs_review": len(review) > 0,
        "review_reason": review,
    }


def rank_review_queue(records: list) -> list: 
    """Returns the records needing review in triage order: most severe first,
    then grouped by theme, then by feedback_id so the order is stable."""
    queue = [r for r in records if r["needs_review"]]
    return sorted(
        queue,
        key=lambda r: (-SEVERITY_RANK[r["severity"]], r["theme"], r["feedback_id"]),
    )


def theme_priority_score(theme: dict) -> int:  
    """combines severity mix (50 points), average sentiment (30 points), 
    and frequency (20 points) to give a 0-100 continuous priority score 
    instead of needing to look at multiple metrics to determine which themes 
    are most urgent. Adjust the weights here to change what counts most."""
    severe_entries = theme["severity_counts"]["high"] + theme["severity_counts"]["critical"] #takes the number of high and critical severity feedbacks for that theme
    severity_ratio = severe_entries / theme["count"] if theme["count"] else 0
    negativity = max(0, -theme["avg_sentiment"])
    frequency_factor = min(theme["count"] / 10, 1.0)
    score = (severity_ratio * 50) + (negativity * 30) + (frequency_factor * 20) #formula can be adjusted to change the weight of each factor, currently severity is weighted highest, then negativity, then frequency
    return round(score)


def aggregate_themes(records):
    """Groups the counted records by theme and returns the stats used for the
    report. Expects records that went through apply_feedback_rules()."""
    counted = [r for r in records if r["counted"]]
    sentiment_counts = dict.fromkeys(SENTIMENT_SCORE, 0)
    themes = {}

    for record in counted:
        sentiment_counts[record["sentiment"]] += 1
        theme = themes.setdefault(record["theme"], {
            "theme": record["theme"],
            "count": 0,
            "severity_counts": dict.fromkeys(SEVERITY_RANK, 0),
            "sentiment_sum": 0,
            "feedbacks": [],
        })
        theme["count"] += 1
        theme["severity_counts"][record["severity"]] += 1
        theme["sentiment_sum"] += SENTIMENT_SCORE[record["sentiment"]]
        theme["feedbacks"].append({"severity": record["severity"], "summary": record["summary"]})
 
    # second pass: the averages need each theme's final count
    theme_list = []
    for theme in themes.values():
        theme["avg_sentiment"] = round(theme["sentiment_sum"] / theme["count"], 2)
        theme["priority_score"] = theme_priority_score(theme)
        theme["examples"] = sorted(
            theme["feedbacks"], key=lambda f: SEVERITY_RANK[f["severity"]], reverse=True
        )
        del theme["sentiment_sum"], theme["feedbacks"]
        theme_list.append(theme)
    # most-mentioned first; ties broken by priority, then name, so the order is stable
    theme_list.sort(key=lambda t: (-t["count"], -t["priority_score"], t["theme"]))
 
    return {
        "total_entries": len(records),
        "counted_entries": len(counted),
        "sentiment_distribution": sentiment_counts,
        "themes": theme_list,
    }


# ---------------------------------------------------------------------------
# Test runner: python src/logic_manager.py
# ---------------------------------------------------------------------------
def run_sanity_checks(records, invalid_records, processed_records, review_queue, stats):
    """Fails loudly if the results are inconsistent."""
    counted = sum(r["counted"] for r in processed_records)
 
    assert len(processed_records) + len(invalid_records) == len(records), (
        f"records went missing: {len(processed_records)} valid + "
        f"{len(invalid_records)} invalid != {len(records)} loaded"
    )
    assert counted <= len(processed_records), (
        f"Counted entries ({counted}) exceed valid entries ({len(processed_records)})"
    )
    assert sum(t["count"] for t in stats["themes"]) == counted, "theme counts don't add up"
    assert sum(stats["sentiment_distribution"].values()) == counted, "sentiment counts don't add up"
 
    ranks = [SEVERITY_RANK[r["severity"]] for r in review_queue]
    assert ranks == sorted(ranks, reverse=True), "review queue not sorted critical-first"
    for earlier, later in zip(review_queue, review_queue[1:]):
        if earlier["severity"] == later["severity"]:
            assert earlier["theme"] <= later["theme"], "themes not grouped within a severity"


def main():
    records = load_records()
    valid_records, invalid_records = split_valid_records(records)
 
    # always written, so the file never shows results from an older run
    write_json(OUTPUT_DIR / "invalid_records.json", invalid_records)
    if invalid_records:
        print(f"WARNING: {len(invalid_records)} of {len(records)} records failed "
              f"validation and were skipped (see invalid_records.json):")
        for item in invalid_records:
            label = item["feedback_id"] or f"record #{item['index']}"
            print(f"  {label}: {'; '.join(item['problems'])}")
 
    processed_records = [apply_feedback_rules(r) for r in valid_records]
    review_queue = rank_review_queue(processed_records)
    stats = aggregate_themes(processed_records)
    write_json(OUTPUT_DIR / "aggregated_output.json", stats)
    write_json(OUTPUT_DIR / "for_review.json", review_queue)
 
    print(f"Total: {len(processed_records)}, Counted: {stats['counted_entries']}, "
          f"Flagged for review: {len(review_queue)}, Invalid: {len(invalid_records)}")
 
    run_sanity_checks(records, invalid_records, processed_records, review_queue, stats)
    print("All assertions passed.")

if __name__ == "__main__":
    main()
  
    



