from test_data.sample_ai_output import SAMPLE_RECORDS

MIN_CONFIDENCE = 0.5
total_entries = 0
counted_entries = 0

def apply_record_rules(record): #checks if feedback is critical and if confidence is below threshold
    review = []
    if record["severity"] == "critical": #checking if feedback is critical
        review.append("Critical severity")
    if record["confidence"] < MIN_CONFIDENCE: #checking if feedback is below confidence threshold
        review.append(f"Confidence {record['confidence']:.2f} is below threshold {MIN_CONFIDENCE}.")
    return {
        **record,
        "counted": record["confidence"] >= MIN_CONFIDENCE, #feedback will be counted if confidence is above threshold 
        "needs_review": len(review) > 0,  #feedback needs reviews if there are any review notes
        "review_reason": review   
    }

def review_records(records): #to collate all feedback that needs review and their reasons
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
        theme["examples"] = sorted(theme["feedbacks"], key=lambda x: x["severity"], reverse=True) #sorting the feedbacks by severity 
        del theme["sentiment_sum"]  # Remove the temporary sentiment sum
        del theme["feedbacks"]  # Remove the temporary feedbacks list
        theme_list.append(theme)
    return {
        "total_entries": len(records),
        "counted_entries": len(counted),
        "sentiment_distribution": sentiment_counts,
        "themes": theme_list,
    }
    # return sentiment_counts,severity_counts,themes

processed_records = [apply_record_rules(record) for record in SAMPLE_RECORDS]
total_entries = len(processed_records)                                   
counted_entries = len([r for r in processed_records if r["counted"]]) 
for_review = review_records(processed_records)
aggregated_sentiment = aggregate_themes(processed_records)
# print("Aggregated Sentiment Counts:", aggregated_sentiment[0])
# print("Aggregated Severity Counts:", aggregated_sentiment[1])


# print(for_review)
# print(f"Total entries processed: {total_entries}")
# print(f"Entries counted (confidence >= {MIN_CONFIDENCE}): {counted_entries}")


#make an output function to output only json file for 2nd ai call
#flag out if agreement is 0.33 or 0.67