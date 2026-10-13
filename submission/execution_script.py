import sys
import json
from datetime import datetime
from pathlib import Path

# 1. Get the directory where this script sits (root/submission/)
SCRIPT_DIR = Path(__file__).resolve().parent

# 2. Go up one level to get to the project workspace root (root/)
PROJECT_ROOT = SCRIPT_DIR.parent

# 3. Add the project root, managers folder, and execution directory to Python's path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

MANAGERS_DIR = PROJECT_ROOT / "managers"
if str(MANAGERS_DIR) not in sys.path:
    sys.path.append(str(MANAGERS_DIR))

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Import the core logic engine
from managers import logic_manager


def main():
    # ---------------------------------------------------------------------------
    # Dynamic System Argument Import Layer
    # ---------------------------------------------------------------------------
    if len(sys.argv) < 2:
        print(" Error: Missing input module argument.")
        print(" Usage: python execution_script.py sampled_ai_output")
        sys.exit(1)

    # Read the module string passed in terminal (e.g., "sampled_ai_output" or "sample1")
    module_input = sys.argv[1]
    
    # Clean the name in case the user included a file extension by habit
    if module_input.endswith(".py"):
        module_input = module_input[:-3]

    print(f"Loading data via import from module: {module_input}")
    print("=========================================")

    try:
        # Dynamically import the target module package
        imported_module = __import__(module_input)
        
        # Verify the target contains the required global records array variable
        if hasattr(imported_module, "SAMPLE_RECORDS"):
            input_records = imported_module.SAMPLE_RECORDS
        else:
            print(f" Error: Imported module '{module_input}' does not contain 'SAMPLE_RECORDS'.")
            sys.exit(1)
            
    except ModuleNotFoundError:
        print(f" Error: Could not locate or import Python module named '{module_input}.py'.")
        print(f"   Ensure the file sits directly in the '{SCRIPT_DIR.name}/' directory.")
        sys.exit(1)
    except Exception as e:
        print(f" Error during structural module parsing: {e}")
        sys.exit(1)

    # 1. Run validation engine directly
    print(f"\n[1/5] Running record validation on {len(input_records)} items...")
    valid, invalid = logic_manager.split_valid_records(input_records)
    print(f"  -> Valid records extracted: {len(valid)}")
    print(f"  -> Invalid records dropped: {len(invalid)}")

    # 2. Run rule processing engine directly
    print("\n[2/5] Applying thematic rules and filtering thresholds...")
    processed = [logic_manager.apply_feedback_rules(r) for r in valid]
    print(f"  -> Successfully appended rule fields to all {len(processed)} entries.")
    
    # Save Step 2 data to processed_feedback.json
    processed_filepath = SCRIPT_DIR / "processed_feedback.json"
    with open(processed_filepath, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

    # 3. Run triage routing engine directly
    print("\n[3/5] Sorting manual review queue (Severity -> Alphabetical Theme)...")
    queue = logic_manager.rank_review_queue(processed)
    print(f"  -> Items sent to human triage queue: {len(queue)}")
    
    # Save Step 3 data to for_review.json
    review_filepath = SCRIPT_DIR / "for_review.json"
    with open(review_filepath, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

    # 4. Run data calculation matrix directly
    print("\n[4/5] Generating theme statistics and analytics summary...")
    stats = logic_manager.aggregate_themes(processed)
    
    # Save Step 4 data to aggregated_output.json
    aggregated_filepath = SCRIPT_DIR / "aggregated_output.json"
    with open(aggregated_filepath, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------------------
    # 5. Run Trend Analytics Matrix (New Feature Layer)
    # ---------------------------------------------------------------------------
    print("\n[5/5] Calculating trend metrics vs historical context...")
    history_filepath = SCRIPT_DIR / "aggregated_history.json"
    previous_entry = None

    # Load the latest historical run block to cross-reference trends
    if history_filepath.exists() and history_filepath.stat().st_size > 0:
        try:
            with open(history_filepath, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                if isinstance(history_data, list) and len(history_data) > 0:
                    previous_entry = history_data[0]  # Take newest entry from history log
        except Exception:
            print("   Historical data trace unreadable. Evaluating as baseline run.")

    # Call the logic manager's trend comparison function
    trend = logic_manager.compare_runs(stats, previous_entry)
    
    # Save Step 5 data to trend_output.json
    trend_filepath = SCRIPT_DIR / "trend_output.json"
    with open(trend_filepath, "w", encoding="utf-8") as f:
        json.dump(trend, f, indent=2, ensure_ascii=False)

    # Append current execution run data into history log cache for subsequent executions
    run_at = datetime.now().isoformat(timespec="seconds")
    current_history_node = {
        "run_at": run_at,
        "source_file": f"{module_input}.py",
        "stats": stats
    }
    
    existing_history = []
    if history_filepath.exists() and history_filepath.stat().st_size > 0:
        try:
            with open(history_filepath, "r", encoding="utf-8") as f:
                existing_history = json.load(f)
                if not isinstance(existing_history, list):
                    existing_history = []
        except Exception:
            existing_history = []

    # Save tracking history array (newest runs placed first)
    updated_history = [current_history_node] + existing_history
    with open(history_filepath, "w", encoding="utf-8") as f:
        json.dump(updated_history, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------------------
    # Execution Metrics Display Output
    # ---------------------------------------------------------------------------
    print("\n=========================================")
    print("EXECUTION SCRIPT OUTPUT METRICS")
    print("=========================================")
    print(f"Total Parsed Entries: {stats['total_entries']}")
    print(f"Counted Entries     : {stats['counted_entries']}")
    print(f"Sentiment Spread    : {json.dumps(stats['sentiment_distribution'])}")
    print("\nAggregated Themes Found:")
    for theme_data in stats["themes"]:
        print(f"  - {theme_data['theme']:<22} | Count: {theme_data['count']:<3} | Priority Score: {theme_data['priority_score']}")

    print("\n HISTORICAL TREND LOGS")
    print("-----------------------------------------")
    if trend["has_previous"]:
        print(f"Trend vs previous run historical node ({trend['previous_run']['run_at']}):")
        print(f"  Entries Shift  : {trend['headline']['total_entries']['text']}")
        print(f"  Negative Delta : {trend['headline']['negative_percent']['text']}")
        print("\nCategorized Theme Trend Deltas:")
        for row in trend["themes"]:
            print(f"  * {row['theme']:<22} | Status: {row['status']:<13} | Count: {row['count']['text']:<16} | Priority: {row['priority']['text']}")
    else:
        print(f"   {trend['message']}")

    print("\nJSON files successfully generated:")
    print(f"  Processed Feedback : {processed_filepath.name}")
    print(f"  Review Queue       : {review_filepath.name}")
    print(f"  Aggregated_output  : {aggregated_filepath.name}")
    print(f"  Trend Output       : {trend_filepath.name}")

if __name__ == "__main__":
    main()
