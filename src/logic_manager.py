import json
<<<<<<< HEAD
from datetime import datetime
=======
>>>>>>> origin/main
from pathlib import Path
 
# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
MIN_CONFIDENCE = 0.5
<<<<<<< HEAD

# Trend comparison: a theme's priority must move by at least this many points
# between runs to count as Escalating or Easing; smaller moves are Steady.
TREND_THRESHOLD = 5
# Display order for themes in the trend output.
TREND_STATUS_ORDER = ["Escalating", "New", "Easing", "Steady", "Not reported"]

=======
 
>>>>>>> origin/main
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
<<<<<<< HEAD


def write_json(path, data):
    """Writes data to a JSON file, creating the parent folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_json_list(path):
    """Reads a JSON file that holds a list. A missing or empty file gives an
    empty list. A file that exists but isn't valid JSON, or isn't a list,
    raises an error instead of being treated as empty, so history is never
    silently lost."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        data = read_json(path)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} is not valid JSON, so it was left unchanged: {error}")
    if not isinstance(data, list):
        raise ValueError(f"{path.name} should contain a list, so it was left unchanged")
    return data


def append_json(path, new_items, sort_key=None, unique_by=None):
    """Adds new_items (a list) to the list stored in a JSON file, keeping
    everything already there. New items are placed first, then:
      - unique_by (a function returning an item's id): if the same id
        appears more than once, only the first (newest) is kept, so
        re-running a file replaces its earlier entries instead of
        duplicating them
      - sort_key: the combined list is re-sorted with it
    A missing or empty file starts a new list. A file that exists but
    can't be read as a list raises an error instead of being overwritten,
    so the history is never lost. The file is replaced in one step, so a
    crash part-way through can't corrupt it."""
    path = Path(path)
    combined = list(new_items) + read_json_list(path)
    if unique_by:
        seen = set()
        unique = []
        for item in combined:
            item_id = unique_by(item)
            if item_id not in seen:
                seen.add(item_id)
                unique.append(item)
        combined = unique
    if sort_key:
        combined.sort(key=sort_key)
    temp_path = path.with_name(path.name + ".tmp")
    write_json(temp_path, combined)
    temp_path.replace(path)


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


=======

def write_json(path, data):
    """Writes data to a JSON file, creating the parent folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_records(path=INPUT_FILE):
    """Loads the AI's classified feedback from a JSON file. Accepts a plain
    list of records, or a dict with the list under a "records" key. Only
    the overall shape is checked here; each record is checked separately
    by validate_record()."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    data = read_json(path)
    if isinstance(data, dict) and "records" in data: #checks if the data is a dictionary and contains a "records" key, if so, it extracts the list of records from that key
        data = data["records"]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError(f"{path.name} should contain a list of feedback records")
    return data


>>>>>>> origin/main
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
<<<<<<< HEAD
 
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str) and timestamp.strip():
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            problems.append(f"'timestamp' is not a valid ISO date-time, got {timestamp!r}")
=======
>>>>>>> origin/main
    return problems


def split_valid_records(records):
    """Splits records into (valid, invalid). One bad record never stops the
    rest. Each invalid entry keeps the original record and the reasons it
    failed, so it can be inspected or sent back to the AI."""
    valid, invalid = [], []
<<<<<<< HEAD
    seen_ids = set()
    for index, record in enumerate(records):
        problems = validate_record(record)
        if not problems:
            # a repeated id would be counted twice; the first one is kept
            if record["feedback_id"] in seen_ids:
                problems.append(f"duplicate feedback_id '{record['feedback_id']}'")
            seen_ids.add(record["feedback_id"])
=======
    for index, record in enumerate(records):
        problems = validate_record(record)
>>>>>>> origin/main
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


<<<<<<< HEAD
def review_sort_key(record: dict) -> tuple:
    """Triage order: most severe first, then grouped by theme, then by
    feedback_id so the order is stable."""
    return (-SEVERITY_RANK[record["severity"]], record["theme"], record["feedback_id"])


def rank_review_queue(records: list) -> list:
    queue = [r for r in records if r["needs_review"]]
    return sorted(queue, key=review_sort_key)


def theme_priority_score(theme: dict) -> int:  
    """combines severity mix (45 points), average sentiment (20 points), 
    and frequency (35 points) to give a 0-100 continuous priority score 
=======
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
>>>>>>> origin/main
    instead of needing to look at multiple metrics to determine which themes 
    are most urgent. Adjust the weights here to change what counts most."""
    severe_entries = theme["severity_counts"]["high"] + theme["severity_counts"]["critical"] #takes the number of high and critical severity feedbacks for that theme
    severity_ratio = severe_entries / theme["count"] if theme["count"] else 0
    negativity = max(0, -theme["avg_sentiment"])
    frequency_factor = min(theme["count"] / 10, 1.0)
<<<<<<< HEAD
    score = (severity_ratio * 45) + (negativity * 20) + (frequency_factor * 35) #formula can be adjusted to change the weight of each factor, currently severity is weighted highest, then frequency, then negativity.
=======
    score = (severity_ratio * 50) + (negativity * 30) + (frequency_factor * 20) #formula can be adjusted to change the weight of each factor, currently severity is weighted highest, then negativity, then frequency
>>>>>>> origin/main
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
<<<<<<< HEAD
    # most-mentioned first; ties broken by priority, then name, so the order is stable
    theme_list.sort(key=lambda t: (-t["count"], -t["priority_score"], t["theme"]))
=======
    theme_list.sort(key=lambda t: t["count"], reverse=True)  # most-mentioned first
>>>>>>> origin/main
 
    return {
        "total_entries": len(records),
        "counted_entries": len(counted),
        "sentiment_distribution": sentiment_counts,
        "themes": theme_list,
    }


# ---------------------------------------------------------------------------
<<<<<<< HEAD
# Trend comparison (this run vs the previous run)
# ---------------------------------------------------------------------------
def _signed(number: int, unit: str = "") -> str:
    """'+14', '-8' or '0', with an optional unit after the number."""
    return "0" if number == 0 else f"{number:+d}{unit}"


def _compare(previous, current, unit: str = "", change_unit: str = "") -> dict:
    """Builds {"previous", "current", "change", "text"} for one number, where
    text is ready to print, e.g. '36 -> 50 (+14)'. A missing side (None) is
    shown as '-' and has no change."""
    if previous is None or current is None:
        return {
            "previous": previous,
            "current": current,
            "change": None,
            "text": (f"{previous}{unit}" if previous is not None else "-")
                    + " -> " + (f"{current}{unit}" if current is not None else "-"),
        }
    change = current - previous
    return {
        "previous": previous,
        "current": current,
        "change": change,
        "text": f"{previous}{unit} -> {current}{unit} ({_signed(change, change_unit)})",
    }


def _negative_percent(stats: dict) -> int:
    """Whole-number percentage of counted entries with negative sentiment."""
    counted = stats["counted_entries"]
    return round(100 * stats["sentiment_distribution"]["negative"] / counted) if counted else 0


def _theme_status(previous_theme, current_theme) -> str:
    """Escalating / Easing / Steady / New / Not reported, decided only by how
    far the theme's priority score moved (see TREND_THRESHOLD)."""
    if previous_theme is None:
        return "New"
    if current_theme is None:
        return "Not reported"
    change = current_theme["priority_score"] - previous_theme["priority_score"]
    if change >= TREND_THRESHOLD:
        return "Escalating"
    if change <= -TREND_THRESHOLD:
        return "Easing"
    return "Steady"


def compare_runs(current_stats: dict, previous_entry: dict | None) -> dict:
    """Compares this run's stats with the previous run's and returns
    display-ready results, so the dashboard only has to print them.

    previous_entry is the newest entry in aggregated_history.json
    ({"run_at", "source_file", "stats"}), or None on the first run. When
    there is nothing to compare, "has_previous" is False, "message" explains
    why, and the other keys are empty."""
    if previous_entry is None:
        return {
            "has_previous": False,
            "message": "First run - nothing to compare yet.",
            "previous_run": None,
            "headline": {},
            "themes": [],
            "needs_attention": [],
            "getting_better": [],
        }

    previous_stats = previous_entry["stats"]
    current_themes = {t["theme"]: t for t in current_stats["themes"]}
    previous_themes = {t["theme"]: t for t in previous_stats["themes"]}

    rows = []
    for name in current_themes.keys() | previous_themes.keys():
        current, previous = current_themes.get(name), previous_themes.get(name)
        rows.append({
            "theme": name,
            "status": _theme_status(previous, current),
            "count": _compare(previous["count"] if previous else 0,
                              current["count"] if current else 0),
            "priority": _compare(previous["priority_score"] if previous else None,
                                 current["priority_score"] if current else None),
        })
    rows.sort(key=lambda r: (TREND_STATUS_ORDER.index(r["status"]),
                             -(r["priority"]["current"] or 0), r["theme"]))

    return {
        "has_previous": True,
        "message": None,
        "previous_run": {
            "run_at": previous_entry.get("run_at"),
            "source_file": previous_entry.get("source_file"),
        },
        "headline": {
            "total_entries": _compare(previous_stats["total_entries"],
                                      current_stats["total_entries"]),
            "counted_entries": _compare(previous_stats["counted_entries"],
                                        current_stats["counted_entries"]),
            "negative_percent": _compare(_negative_percent(previous_stats),
                                         _negative_percent(current_stats),
                                         unit="%", change_unit=" pts"),
            "status_counts": {status: sum(r["status"] == status for r in rows)
                              for status in TREND_STATUS_ORDER},
        },
        "themes": rows,
        "needs_attention": [r["theme"] for r in rows if r["status"] in ("Escalating", "New")],
        "getting_better": [r["theme"] for r in rows if r["status"] == "Easing"],
    }


# ---------------------------------------------------------------------------
# Test runner: python src/logic_manager.py
# ---------------------------------------------------------------------------
def run_sanity_checks(records, invalid_records, processed_records, review_queue, stats, trend):
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
    if trend["has_previous"]:
        trend_themes = {r["theme"] for r in trend["themes"]}
        assert {t["theme"] for t in stats["themes"]} <= trend_themes, "trend is missing a current theme"
        assert sum(trend["headline"]["status_counts"].values()) == len(trend["themes"]), (
            "trend status counts don't add up"
        )
=======
# Test runner: python src/logic_manager.py
# ---------------------------------------------------------------------------
def run_sanity_checks(processed_records, review_queue, expected_total):
    """Fails loudly if the results are inconsistent."""
    total = len(processed_records)
    counted = sum(r["counted"] for r in processed_records)
    assert total == expected_total, (
        f"Total entries mismatch: total_entries={total}, expected={expected_total}"
    )
    assert counted <= total, f"Counted entries ({counted}) exceed total entries ({total})"
 
>>>>>>> origin/main
    ranks = [SEVERITY_RANK[r["severity"]] for r in review_queue]
    assert ranks == sorted(ranks, reverse=True), "review queue not sorted critical-first"
    for earlier, later in zip(review_queue, review_queue[1:]):
        if earlier["severity"] == later["severity"]:
            assert earlier["theme"] <= later["theme"], "themes not grouped within a severity"


def main():
    records = load_records()
    valid_records, invalid_records = split_valid_records(records)
<<<<<<< HEAD
 
=======

>>>>>>> origin/main
    # always written, so the file never shows results from an older run
    write_json(OUTPUT_DIR / "invalid_records.json", invalid_records)
    if invalid_records:
        print(f"WARNING: {len(invalid_records)} of {len(records)} records failed "
<<<<<<< HEAD
              f"validation and were skipped (see invalid_records.json):")
        for item in invalid_records:
            label = item["feedback_id"] or f"record #{item['index']}"
            print(f"  {label}: {'; '.join(item['problems'])}")
 
    processed_records = [apply_feedback_rules(r) for r in valid_records]
    review_queue = rank_review_queue(processed_records)
    stats = aggregate_themes(processed_records)
    write_json(OUTPUT_DIR / "aggregated_output.json", stats)
    run_at = datetime.now().isoformat(timespec="seconds")

    # for_review.json keeps every run; each record is stamped so runs can be told apart
    append_json(OUTPUT_DIR / "for_review.json", [
        {**record, "run_at": run_at, "source_file": INPUT_FILE.name}
        for record in review_queue
    ], sort_key=review_sort_key, unique_by=lambda record: record["feedback_id"])

    # aggregated_history.json keeps every run's stats, newest first. The trend
    # is worked out BEFORE this run is added, so the newest entry is the previous run.
    history_path = OUTPUT_DIR / "aggregated_history.json"
    history = read_json_list(history_path)
    trend = compare_runs(stats, history[0] if history else None)
    write_json(OUTPUT_DIR / "trend_output.json", trend)
    append_json(history_path, [{"run_at": run_at, "source_file": INPUT_FILE.name, "stats": stats}])

    print(f"Total: {len(processed_records)}, Counted: {stats['counted_entries']}, "
          f"Flagged for review: {len(review_queue)}, Invalid: {len(invalid_records)}")
    if trend["has_previous"]:
        print(f"Trend vs previous run ({trend['previous_run']['run_at']}):")
        print(f"  Entries: {trend['headline']['total_entries']['text']}, "
              f"negative: {trend['headline']['negative_percent']['text']},")
        for row in trend["themes"]:
            print(f"  {row['theme']:<22}{row['status']:<13}"
                  f"count {row['count']['text']:<16}priority {row['priority']['text']}")
    else:
        print(trend["message"])

    run_sanity_checks(records, invalid_records, processed_records, review_queue, stats, trend)
=======
                f"validation and were skipped (see invalid_records.json):")
        for item in invalid_records:
            label = item["feedback_id"] or f"record #{item['index']}"
            print(f"  {label}: {'; '.join(item['problems'])}")
            
    processed_feedbacks = [apply_feedback_rules(r) for r in valid_records] #run through all the feedback and apply the rules to each record
    review_queue = rank_review_queue(processed_feedbacks) #filter out feedback that needs review
    write_json(OUTPUT_DIR / "aggregated_output.json", aggregate_themes(processed_feedbacks)) #write the aggregated output to a json file
    write_json(OUTPUT_DIR / "for_review.json", review_queue)

    counted = sum(r["counted"] for r in processed_feedbacks)
    print(f"Total: {len(processed_feedbacks)}, Counted: {counted}, "
            f"Flagged for review: {len(review_queue)}, Invalid: {len(invalid_records)}")
    
    run_sanity_checks(processed_feedbacks, review_queue, expected_total=len(valid_records))
>>>>>>> origin/main
    print("All assertions passed.")

if __name__ == "__main__":
    main()
  
    



