from test_data.sample_ai_output import SAMPLE_RECORDS

MIN_CONFIDENCE = 0.9

def apply_record_rules(record):
    """
    Process a single record.
    For now, this is a simple placeholder that only marks whether
    the record meets the minimum confidence threshold.
    """
    return {
        **record,
        "counted": record["confidence"] >= MIN_CONFIDENCE
    }

processed_records = [apply_record_rules(record) for record in SAMPLE_RECORDS]
print(processed_records)
