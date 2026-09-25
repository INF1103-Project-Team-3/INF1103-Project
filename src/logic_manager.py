from test_data.sample_ai_output import SAMPLE_RECORDS

MIN_CONFIDENCE = 0.9
total_entries = 0
counted_entries = 0

def apply_record_rules(record):
    """
    Process a single record.
    For now, this is a simple placeholder that only marks whether
    the record meets the minimum confidence threshold.
    """
    global total_entries, counted_entries
    review = []
    total_entries += 1
    if record["severity"] == "critical": #checking if feedback is critical
        review.append("Critical severity")
    if record["confidence"] < MIN_CONFIDENCE: #checking if feedback is below confidence threshold
        review.append(f"Confidence {record['confidence']:.2f} is below threshold {MIN_CONFIDENCE}.")
    else:
        counted_entries += 1
    return {
        **record,
        "counted": record["confidence"] >= MIN_CONFIDENCE, #feedback will be counted if confidence is above threshold 
        "needs_review": len(review) > 0,  #feedback needs reviews if there are any review notes
        "review_reason": review   
    }


processed_records = [apply_record_rules(record) for record in SAMPLE_RECORDS]
print(processed_records)
print(f"Total entries processed: {total_entries}")
print(f"Entries counted (confidence >= {MIN_CONFIDENCE}): {counted_entries}")
