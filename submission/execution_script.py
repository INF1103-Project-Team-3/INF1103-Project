import json
import logic_manager
from sample_ai_output import SAMPLE_RECORDS

print("🚀 STARTING DIRECT LOGIC EXECUTION RUN")
print("=========================================")

# 1. Run validation engine directly
print(f"\n[1/4] Running record validation on {len(SAMPLE_RECORDS)} items...")
valid, invalid = logic_manager.split_valid_records(SAMPLE_RECORDS)
print(f"  -> Valid records extracted: {len(valid)}")
print(f"  -> Invalid records dropped: {len(invalid)}")

# 2. Run rule processing engine directly
print("\n[2/4] Applying thematic rules and filtering thresholds...")
processed = [logic_manager.apply_feedback_rules(r) for r in valid]
print(f"  -> Successfully appended rule fields to all {len(processed)} entries.")

# 3. Run triage routing engine directly
print("\n[3/4] Sorting manual review queue (Severity -> Alphabetical Theme)...")
queue = logic_manager.rank_review_queue(processed)
print(f"  -> Items sent to human triage queue: {len(queue)}")
if queue:
    print(f"  -> Top item in triage: ID {queue[0]['feedback_id']} ({queue[0]['severity'].upper()} - {queue[0]['theme']})")

# 4. Run data calculation matrix directly
print("\n[4/4] Generating theme statistics and analytics summary...")
stats = logic_manager.aggregate_themes(processed)

print("\n=========================================")
print("📊 DIRECT EXECUTION OUTPUT METRICS")
print("=========================================")
print(f"Total Parsed Entries: {stats['total_entries']}")
print(f"Counted Entries     : {stats['counted_entries']}")
print(f"Sentiment Spread    : {json.dumps(stats['sentiment_distribution'])}")
print("\nAggregated Themes Found:")
for theme_data in stats["themes"]:
    print(f"  - {theme_data['theme']:<22} | Count: {theme_data['count']:<3} | Priority Score: {theme_data['priority_score']}")

print("\n✅ Execution completed cleanly with zero functional definition layers.")
