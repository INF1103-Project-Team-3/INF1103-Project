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
    for record in records: #loops through counted records only
        sentiment = record["sentiment"]
        severity = record["severity"]
        match sentiment:
            case "positive":
                sentiment_counts["positive"] += 1
            case "neutral":
                sentiment_counts["neutral"] += 1
            case "negative":
                sentiment_counts["negative"] += 1
        match severity:
            case "critical":
                severity_counts["critical"] += 1
            case "high":
                severity_counts["high"] += 1
            case "medium":
                severity_counts["medium"] += 1
            case "low":
                severity_counts["low"] += 1
    return sentiment_counts,severity_counts

processed_records = [apply_record_rules(record) for record in SAMPLE_RECORDS]
total_entries = len(processed_records)                                   
counted_entries = len([r for r in processed_records if r["counted"]]) 
for_review = review_records(processed_records)
aggregated_sentiment = aggregate_themes(processed_records)
print("Aggregated Sentiment Counts:", aggregated_sentiment[0])
print("Aggregated Severity Counts:", aggregated_sentiment[1])
# print(for_review)
# print(f"Total entries processed: {total_entries}")
# print(f"Entries counted (confidence >= {MIN_CONFIDENCE}): {counted_entries}")
