import sys
import json
import textwrap
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


# ---------------------------------------------------------------------------
# IO Formatting Configurations (Mirrored from io_manager.py)
# ---------------------------------------------------------------------------
WIDTH = 82
COLUMN_THEME = 22

MERGED_THEME = 24
MERGED_STATUS = 16
MERGED_COUNT = 17
MERGED_SENT = 8
MERGED_URGENT = 6
MERGED_GAP = "   "
MERGED_PRIORITY = 16
MERGED_WIDTH = (MERGED_THEME + MERGED_STATUS + MERGED_COUNT + MERGED_SENT
                + MERGED_URGENT + len(MERGED_GAP) + MERGED_PRIORITY)

REVIEW_LABEL_WIDTH = 16
REVIEW_SUMMARY_WIDTH = 36


def clean(text):
    """Replace characters that some terminals can't print."""
    return (text.replace("\u2011", "-")
                .replace("\u2019", "'")
                .replace("\u2013", "-")
                .replace("\u2014", "-"))


def get_review_label(record):
    """Reason a record was flagged, read from its review_reason."""
    reasons = str(record.get("review_reason", "")).lower()
    if "critical" in reasons:
        return "critical"
    if "confidence" in reasons:
        return "low_confidence"
    if "agreement" in reasons:
        return "low_agreement"
    return "review"


def main():
    # ---------------------------------------------------------------------------
    # Dynamic System Argument Import Layer
    # ---------------------------------------------------------------------------
    if len(sys.argv) < 2:
        print(" Error: Missing input module argument.")
        print(" Usage: python execution_script1.py sampled_ai_output")
        sys.exit(1)

    # Read the module string passed in terminal (e.g., "sampled_ai_output")
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

    # 2. Run rule processing engine directly
    print("\n[2/5] Applying thematic rules and filtering thresholds...")
    processed = [logic_manager.apply_feedback_rules(r) for r in valid]
    
    processed_filepath = SCRIPT_DIR / "processed_feedback.json"
    with open(processed_filepath, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

    # 3. Run triage routing engine directly
    print("\n[3/5] Sorting manual review queue (Severity -> Alphabetical Theme)...")
    queue = logic_manager.rank_review_queue(processed)
    
    review_filepath = SCRIPT_DIR / "for_review.json"
    with open(review_filepath, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

    # 4. Run data calculation matrix directly
    print("\n[4/5] Generating theme statistics and analytics summary...")
    stats = logic_manager.aggregate_themes(processed)
    
    aggregated_filepath = SCRIPT_DIR / "aggregated_output.json"
    with open(aggregated_filepath, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    # 5. Run Trend Analytics Matrix
    print("\n[5/5] Calculating trend metrics vs historical context...")
    history_filepath = SCRIPT_DIR / "aggregated_history.json"
    previous_entry = None

    if history_filepath.exists() and history_filepath.stat().st_size > 0:
        try:
            with open(history_filepath, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                if isinstance(history_data, list) and len(history_data) > 0:
                    previous_entry = history_data[0]
        except Exception:
            print("   Historical data trace unreadable. Evaluating as baseline run.")

    trend = logic_manager.compare_runs(stats, previous_entry)
    
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

    updated_history = [current_history_node] + existing_history
    with open(history_filepath, "w", encoding="utf-8") as f:
        json.dump(updated_history, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------------------
    # Structured Screen Display Outputs (Mirrored from io_manager.py Layouts)
    # ---------------------------------------------------------------------------
    print("\n")
    print(f"FEEDBACK DATA DATASET    entries: {stats['total_entries']}   "
          f"counted: {stats['counted_entries']}   for review: {len(queue)}")
    
    both_count = sum(1 for r in queue if r.get("counted") and get_review_label(r) == "critical")
    if both_count:
        print(f"{both_count} critical entries are in both: counted and for review")
    print("=" * WIDTH)

    # Section 1: Historical Trend Headline Numbers
    if trend.get("has_previous"):
        run_timestamp = (trend.get("previous_run") or {}).get("run_at", "").replace("T", " ")
        headline = trend["headline"]
        print(f"\nTrend vs previous run ({run_timestamp})")
        print(f"  Entries: {headline['total_entries']['text']}    "
              f"Negative: {headline['negative_percent']['text']}")

    # Section 2: Themes & Analytics Table View
    print("\nTHEMES")
    if trend.get("has_previous"):
        # Display with Trend comparison columns merge
        print(f"{'THEME':<{MERGED_THEME}}{'STATUS':<{MERGED_STATUS}}"
              f"{'COUNT':<{MERGED_COUNT}}{'AVG SENT':>{MERGED_SENT}}"
              f"{'H+C':>{MERGED_URGENT}}{MERGED_GAP}PRIORITY")
        print("-" * MERGED_WIDTH)

        # Build cross-reference structure
        trend_rows = {r["theme"]: r for r in trend.get("themes", [])}
        current_themes = {t["theme"]: t for t in stats["themes"]}
        all_theme_names = list(trend_rows.keys()) + [n for n in current_themes if n not in trend_rows]

        for name in all_theme_names:
            t = current_themes.get(name)
            tr = trend_rows.get(name)
            
            urgent_val = "-"
            if t:
                sev = t.get("severity_counts", {})
                urgent_val = str(sev.get("critical", 0) + sev.get("high", 0))

            status = tr["status"] if tr else "-"
            count_str = tr["count"]["text"] if tr else (str(t["count"]) if t else "-")
            priority_str = tr["priority"]["text"] if tr else (str(t["priority_score"]) if t else "-")
            avg_sent = f"{t['avg_sentiment']:.2f}" if t else "-"

            print(f"{name:<{MERGED_THEME}}{status:<{MERGED_STATUS}}"
                  f"{count_str:<{MERGED_COUNT}}{avg_sent:>{MERGED_SENT}}"
                  f"{urgent_val:>{MERGED_URGENT}}{MERGED_GAP}{priority_str}")
        print("\nAVG SENT = average sentiment, H+C = high + critical entries")
    else:
        # Fallback Standard Theme View when no history log trace exists
        if trend.get("message"):
            print(f"  {trend['message']}")
        print(f"{'THEME':<{COLUMN_THEME}}{'COUNT':>5}  {'AVG SENT':>8}  {'HIGH+CRIT':>9}  {'PRIORITY':>8}")
        print("-" * WIDTH)
        for t in stats["themes"]:
            sev = t["severity_counts"]
            urgent = sev["critical"] + sev["high"]
            print(f"{t['theme']:<{COLUMN_THEME}}{t['count']:>5}  {t['avg_sentiment']:>8.2f}  "
                  f"{urgent:>9}  {t['priority_score']:>8}")

    # Section 3: Triage Review Queue Logs Block
    print("\nREVIEW QUEUE")
    print("-" * WIDTH)
    if not queue:
        print("Nothing waiting for review.")
    else:
        for r in queue:
            summary_snippet = textwrap.shorten(clean(str(r.get("summary", ""))),
                                               width=REVIEW_SUMMARY_WIDTH, placeholder="...")
            print(f"{str(r.get('feedback_id', '?')):<8}"
                  f"{get_review_label(r):<{REVIEW_LABEL_WIDTH}}"
                  f"{str(r.get('theme', '-')):<{COLUMN_THEME}}{summary_snippet}")
            
    print("\n" + "=" * WIDTH)
    print("JSON files successfully generated")


if __name__ == "__main__":
    main()
