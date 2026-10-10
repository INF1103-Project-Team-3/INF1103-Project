import json

MIN_CONFIDENCE = 0.5
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3} #for sorting feedback by severity
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

def _clean_label(label: str) -> str: #Lowercases, turns hyphens/underscores/punctuation into spaces and collapses repeated spaces so 'Well-being', 'well_being' and'  WELL  being ' all become 'well being' before lookup.
    cleaned = "".join(ch if ch.isalnum() else " " for ch in label.lower())
    return " ".join(cleaned.split())

def _build_alias_lookup(by_canonical: dict) -> dict:
    """Flattens the grouped dictionary above into {alias: canonical}.
    Raises if one alias is listed under two themes, since the second one
    would otherwise silently overwrite the first and be very hard to spot."""
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
    """Maps near-duplicate theme labels onto one canonical name, so the
    same underlying issue doesn't get split into separate, smaller theme
    buckets just because the AI phrased it differently. A label with no
    known alias (e.g. a genuinely new theme) is returned unchanged, so
    new themes still show up instead of being silently forced into a
    wrong bucket."""
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

if __name__ == "__main__":
    from test_data.sample_ai_output import SAMPLE_RECORDS
    processed_feedbacks = [apply_feedback_rules(record) for record in SAMPLE_RECORDS] #run through all the feedback and apply the rules to each record
    total_entries = len(processed_feedbacks)                                   
    counted_entries = len([r for r in processed_feedbacks if r["counted"]]) 
    # for_review = review_feedbacks(processed_feedbacks) 
    print(processed_feedbacks)
    aggregated_sentiment = aggregate_themes(processed_feedbacks)
    with open("aggregated_output.json", "w") as f:
        json.dump(aggregated_sentiment, f, indent=2)

    review_queue = [r for r in processed_feedbacks if r["needs_review"]] #filter out feedback that needs review
    with open("for_review.json", "w") as f: #write the feedback that needs review to a json file
        json.dump(review_queue, f, indent=2) 
    print(f"Total: {total_entries}, Counted: {counted_entries}, Flagged for review: {len(review_queue)}")
    # print(f"Total entries processed: {total_entries}")
    # print(f"Entries counted (confidence >= {MIN_CONFIDENCE}): {counted_entries}")



#make a function to read json file, so dont need to import dictionary.
#separate into smaller functions

