import json

from numpy import rint

MIN_CONFIDENCE = 0.5
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3} #for sorting feedback by severity


def apply_feedback_rules(record): #checks if feedback is critical and if confidence is below threshold
    review = []
    if record["severity"] == "critical": #checking if feedback is critical
        review.append("Critical severity")
    if record["confidence"] < MIN_CONFIDENCE: #checking if feedback is below confidence threshold
        review.append(f"Confidence {record['confidence']:.2f} is below threshold {MIN_CONFIDENCE}.")
    if record["agreement"] < 1.0: #checking if feedback has low agreement
        review.append(f"Agreement {record['agreement']:.2f} - AI outputs did not fully agree.")
    return {
        **record,
        "counted": record["confidence"] >= MIN_CONFIDENCE and record["agreement"] >= 1.0, #feedback will be counted if confidence is above threshold 
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
        theme = themes.setdefault(record["theme"],{ #splitting up feedback by theme, so each theme has its own counters, general sentiment, and a list of all the feedback that falls under that theme
            "theme": record["theme"],
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
    aggregated_sentiment = aggregate_themes(processed_feedbacks)
    with open("aggregated_output.json", "w") as f:
        json.dump(aggregated_sentiment, f, indent=2)

    review_queue = [r for r in processed_feedbacks if r["needs_review"]] #filter out feedback that needs review
    with open("for_review.json", "w") as f: #write the feedback that needs review to a json file
        json.dump(review_queue, f, indent=2) 
    print(f"Total: {total_entries}, Counted: {counted_entries}, Flagged for review: {len(review_queue)}")
    # print(f"Total entries processed: {total_entries}")
    # print(f"Entries counted (confidence >= {MIN_CONFIDENCE}): {counted_entries}")


#make an output function to output only json file for 2nd ai call (done)
#flag out if agreement is 0.33 or 0.67 (done)
#make a function to read json file, so dont need to import dictionary.
#separate into smaller functions

