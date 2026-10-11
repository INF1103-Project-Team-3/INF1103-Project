import json
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

def read_json(path): #reads a json file
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data): #writes a json file, creating the parent directory if it doesn't exist
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_records(path=INPUT_FILE): #loads the AI's classified feedback from a JSON file. Accepts either a plain list of records, or a dict with the list under a "records" key.
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    data = read_json(path)
    if isinstance(data, dict) and "records" in data: #checks if the data is a dictionary and contains a "records" key, if so, it extracts the list of records from that key
        data = data["records"]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError(f"{path.name} should contain a list of feedback records")
    return data

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
    return problems

def split_valid_records(records):
    """Splits records into (valid, invalid). One bad record never stops the
    rest. Each invalid entry keeps the original record and the reasons it
    failed, so it can be inspected or sent back to the AI."""
    valid, invalid = [], []
    for index, record in enumerate(records):
        problems = validate_record(record)
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

def _clean_label(label: str) -> str: #Lowercases, turns hyphens/underscores/punctuation into spaces and collapses repeated spaces so 'Well-being', 'well_being' and'  WELL  being ' all become 'well being' before lookup.
    cleaned = "".join(ch if ch.isalnum() else " " for ch in label.lower())
    return " ".join(cleaned.split())

def _build_alias_lookup(by_canonical: dict) -> dict: #flattens the grouped dictionary above into {alias: canonical}. Raises if one alias is listed under two themes, since the second one would otherwise silently overwrite the first and be very hard to spot.
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

def normalise_theme(theme: str) -> str: #maps similar theme labels to a canonical name, so that the same underlying issue doesn't get split into separate buckets just because the AI phrased it differently. A label with no known alias is returned unchanged, so new themes still show up instead of being silently forced into a wrong bucket."
    return THEME_ALIASES.get(_clean_label(theme), theme.strip())


def apply_feedback_rules(record): #checks if feedback is critical and if confidence is below threshold
    review = []
    theme = normalise_theme(record.get("theme", "Unclear")) #normalises the theme of the feedback, if no theme is provided, it defaults to "Unclear"
    severity = record.get("severity", "low") #set default severity to low if not provided
    confidence = record.get("confidence", 0.0) #set default confidence to 0.0 if not provided
    agreement = record.get("agreement", 1.0) #set default agreement to 1.0 if not provided

    if severity == "critical": #checking if feedback is critical
        review.append("Critical severity")
    if confidence < MIN_CONFIDENCE: #checking if feedback is below confidence threshold
        review.append(f"Confidence {confidence:.2f} is below threshold {MIN_CONFIDENCE}.")
    if agreement < 1.0: #checking if feedback has low agreement
        review.append(f"Agreement {agreement:.2f} - AI outputs did not fully agree.")
    return {
        **record,
        "theme": theme, #update theme to default if missing or normalised if provided
        "severity": severity, #update severity to default if missing
        "confidence": confidence, #update confidence to default if missing
        "agreement": agreement, #update agreement to default if missing
        "counted": confidence >= MIN_CONFIDENCE and agreement >= 1.0, #feedback will be counted if confidence is above threshold 
        "needs_review": len(review) > 0,  #feedback needs reviews if there are any review notes
        "review_reason": review   
    }

def review_feedbacks(records): #this function is not currently used in the main block, but can be used in dashboard to generate a list of feedback that needs review
    for_review = []
    for record in records:
        if record["needs_review"]: #check if feedback needs review
            reasons = ", ".join(record["review_reason"]) #formatting the review reason
            for_review.append(
                f"Feedback ID {record['feedback_id']} needs review: {reasons}" #adding the feedback ID and reason to the for_review list
            )
    return for_review

def rank_review_queue(records: list) -> list: #sort themes by urgency, then theme, then feedback_id. This is so that the most urgent feedback is at the top of the list, and feedback of the same theme is grouped together for easier review.
    queue = [r for r in records if r["needs_review"]]
    return sorted(
        queue,
        key=lambda r: (-SEVERITY_RANK[r["severity"]], r["theme"], r["feedback_id"]),
    )

def theme_priority_score(theme: dict) -> int:  #combines severity mix, average sentiment, and frequency to give a 0-100 continuous priority score instead of needing to look at multiple metrics to determine which themes are most urgent. 
    severe_entries = theme["severity_counts"]["high"] + theme["severity_counts"]["critical"] #takes the number of high and critical severity feedbacks for that theme
    severity_ratio = severe_entries / theme["count"] if theme["count"] else 0
    negativity = max(0, -theme["avg_sentiment"])
    frequency_factor = min(theme["count"] / 10, 1.0)
 
    score = (severity_ratio * 50) + (negativity * 30) + (frequency_factor * 20) #formula can be adjusted to change the weight of each factor, currently severity is weighted highest, then negativity, then frequency
    return round(score)

def aggregate_themes(records):
    themes = {} #intializing list to store different themes
    counted = [r for r in records if r['counted']] #filter out low confidence feedback
    sentiment_counts = { #initializing sentiment counts
        "positive": 0,
        "neutral": 0,
        "negative": 0
    }
    severity_counts = { #initializing severity counts
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0
    }
    for record in counted: #loops through counted records only
        sentiment = record["sentiment"]
        severity = record["severity"]
        
        match sentiment: #total sentiment counter, score is 1 if positive, 0 if neutral, -1 if negative
            case "positive":
                sentiment_counts["positive"] += 1; score = 1 
            case "neutral":
                sentiment_counts["neutral"] += 1; score = 0
            case "negative":
                sentiment_counts["negative"] += 1; score = -1
        match severity: #total severity counter
            case "critical":
                severity_counts["critical"] += 1
            case "high":
                severity_counts["high"] += 1
            case "medium":
                severity_counts["medium"] += 1
            case "low":
                severity_counts["low"] += 1
        theme = themes.setdefault(normalise_theme(record["theme"]),{ #splitting up feedback by theme, so each theme has its own counters, general sentiment, and a list of all the feedback that falls under that theme
            "theme": normalise_theme(record["theme"]),
            "count": 0,
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "sentiment_sum": 0,
            "feedbacks": [],
        })
        theme["count"] += 1
        theme["severity_counts"][severity] += 1
        theme["sentiment_sum"] += score
        theme["feedbacks"].append({"severity": severity, "summary": record["summary"]})

    theme_list = []
    for theme in themes.values(): #loops through each theme and calculates the average sentiment score for that theme
        theme["avg_sentiment"] = round(theme["sentiment_sum"] / theme["count"],2) #calculating the average sentiment score for each theme, rounded to 2 decimal places
        theme["priority_score"] = theme_priority_score(theme)
        theme["examples"] = sorted(theme["feedbacks"], key=lambda x: SEVERITY_RANK[x["severity"]], reverse=True) #sorting the feedbacks by severity 
        del theme["sentiment_sum"]  # Remove the temporary sentiment sum
        del theme["feedbacks"]  # Remove the temporary feedbacks list
        theme_list.append(theme)
    theme_list.sort(key=lambda t: t["count"], reverse=True) #most mentioned themes will be at the top of the list
    return {
        "total_entries": len(records),
        "counted_entries": len(counted),
        "sentiment_distribution": sentiment_counts,
        "themes": theme_list,
    }
    # return sentiment_counts,severity_counts,themes

def run_sanity_checks(processed_records, review_queue, expected_total):
    """Fails loudly if the results are inconsistent."""
    total = len(processed_records)
    counted = sum(r["counted"] for r in processed_records)
    assert total == expected_total, (
        f"Total entries mismatch: total_entries={total}, expected={expected_total}"
    )
    assert counted <= total, f"Counted entries ({counted}) exceed total entries ({total})"
 
    ranks = [SEVERITY_RANK[r["severity"]] for r in review_queue]
    assert ranks == sorted(ranks, reverse=True), "review queue not sorted critical-first"
    for earlier, later in zip(review_queue, review_queue[1:]):
        if earlier["severity"] == later["severity"]:
            assert earlier["theme"] <= later["theme"], "themes not grouped within a severity"

if __name__ == "__main__":
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
            
    processed_feedbacks = [apply_feedback_rules(r) for r in valid_records] #run through all the feedback and apply the rules to each record
    review_queue = rank_review_queue(processed_feedbacks) #filter out feedback that needs review
    write_json(OUTPUT_DIR / "aggregated_output.json", aggregate_themes(processed_feedbacks)) #write the aggregated output to a json file
    write_json(OUTPUT_DIR / "for_review.json", review_queue)
    counted = sum(r["counted"] for r in processed_feedbacks)
    print(f"Total: {len(processed_feedbacks)}, Counted: {counted}, "
          f"Flagged for review: {len(review_queue)}, Invalid: {len(invalid_records)}")
 
    run_sanity_checks(processed_feedbacks, review_queue, expected_total=len(valid_records))
    print("All assertions passed.")
  
    



