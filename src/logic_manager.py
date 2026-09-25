from test_data.sample_ai_output import SAMPLE_RECORDS

MIN_CONFIDENCE = 0.5
total_entries = 0
counted_entries = 0
# for_review = []

def apply_record_rules(record): #checks if feedback is critical and if confidence is below threshold
    global total_entries, counted_entries
    review = []
    total_entries += 1
    if record["severity"] == "critical": #checking if feedback is critical
        review.append("Critical severity")
    if record["confidence"] < MIN_CONFIDENCE: #checking if feedback is below confidence threshold
        review.append(f"Confidence {record['confidence']:.2f} is below threshold {MIN_CONFIDENCE}.")
    else:
        counted_entries += 1 #if feedback is above threshold, it will be counted
    return {
        **record,
        "counted": record["confidence"] >= MIN_CONFIDENCE, #feedback will be counted if confidence is above threshold 
        "needs_review": len(review) > 0,  #feedback needs reviews if there are any review notes
        "review_reason": review   
    }

# def review_records(records):
#     global for_review
#     for record in records:
#         if apply_record_rules(record)["needs_review"] is True: #check if feedback needs review
#             reason = apply_record_rules(record)["review_reason"].strip("[]").replace("'", "") #formatting the review reason
#             for_review.append(f"Feedback ID {record['feedback_id']} needs review: {reason}") #adding the feedback ID and reason to the for_review list
#     return for_review

def review_records(records):
    for_review = []

    for record in records:
        result = apply_record_rules(record)

        if result["needs_review"]:
            reasons = result["review_reason"]
            reason_text = ", ".join(reasons)
            for_review.append(
                f"Feedback ID {record['feedback_id']} needs review: {reason_text}"
            )
    return for_review

processed_records = [apply_record_rules(record) for record in SAMPLE_RECORDS]
for_review = review_records(SAMPLE_RECORDS)
print(for_review)
print(f"Total entries processed: {total_entries}")
print(f"Entries counted (confidence >= {MIN_CONFIDENCE}): {counted_entries}")
