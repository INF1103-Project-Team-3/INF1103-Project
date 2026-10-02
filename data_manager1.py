import csv
import json
import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Union

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# MODULE STATE & CONFIGURATION (Replaces __init__)
# ==========================================
JSON_STORAGE_PATH = Path(os.getenv("JSON_STORAGE_PATH", "/data/feedback_store.json"))

# Global states to hold current information in memory
records_store: List[Dict[str, Any]] = [] 
report_store: Dict[str, Any] = {} 

def init_manager(storage_path: str = "/data/feedback_store.json") -> None:
    """Initializes paths, folders, and populates the global memory stores."""
    global JSON_STORAGE_PATH, records_store, report_store
    
    JSON_STORAGE_PATH = Path(storage_path)
    JSON_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Ingest state on initialization
    records_store = load_records()
    report_store = load_report()


# ==========================================
# CORE FUNCTIONAL LOGIC
# ==========================================

def receive_ai_input(raw_ai_text: str) -> Union[Dict[str, Any], List[Any]]:
    """Receives raw JSON text from the AI Manager and logs it sequentially."""
    cleaned_text = raw_ai_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text.replace("```json", "", 1).rstrip("`").strip()
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text.replace("```", "", 1).rstrip("`").strip()

    try:
        parsed_data = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logging.error(f"Text structural validation failed on AI output: {e}")
        raise ValueError(f"[Data Manager Error] AI text is not valid JSON: {e}")

    folder = JSON_STORAGE_PATH.parent
    next_index = 1
    
    if folder.exists():
        existing_files = folder.glob("ai_output_*.json")
        existing_numbers = []
        
        for file in existing_files:
            try:
                num_part = file.stem.split("_")[-1]
                existing_numbers.append(int(num_part))
            except (ValueError, IndexError):
                continue
        
        if existing_numbers:
            next_index = max(existing_numbers) + 1

    filename = f"ai_output_{next_index}.json"
    file_path = folder / filename

    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(parsed_data, file, indent=4, ensure_ascii=False)
        logging.info(f"AI operational stream successfully logged to disk -> {file_path}")
    except IOError as e:
        logging.warning(f"Disk write interrupted but operational stream intact: {e}")

    return parsed_data


def _persist_to_file() -> bool:
    """Saves the current global records and report state into the flat JSON file."""
    try:
        payload = {
            "records": records_store,
            "report": report_store
        }
        with open(JSON_STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception as e:
        logging.error("Failed to write to '%s': %s", JSON_STORAGE_PATH, e)
        return False


def load_records() -> List[Dict[str, Any]]:
    """Loads records array from JSON store into global memory."""
    global records_store
    if not JSON_STORAGE_PATH.exists():
        return []
    try:
        with open(JSON_STORAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            records_store = data.get("records", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.error("Corrupt JSON at '%s': %s. Resetting memory.", JSON_STORAGE_PATH, e)
        records_store = []
    return records_store


def save_record(record: Dict[str, Any]) -> bool:
    """Appends a new feedback record to global state and saves."""
    records_store.append(record)
    return _persist_to_file()


def load_report() -> Dict[str, Any]:
    """Loads report dictionary from JSON store into global memory."""
    global report_store
    if not JSON_STORAGE_PATH.exists():
        return {}
    try:
        with open(JSON_STORAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            report_store = data.get("report", {}) if isinstance(data, dict) else {}
    except Exception:
        report_store = {}
    return report_store


def save_report(report_data: Dict[str, Any]) -> bool:
    """Updates global report dictionary and persists state."""
    global report_store
    report_store = report_data
    return _persist_to_file()


def search_records(query_text: str) -> List[Dict[str, Any]]:
    """Searches active global memory records matching input criteria terms."""
    if not query_text.strip():
        return records_store

    terms = query_text.lower().split()
    results = []

    for record in records_store:
        content = (
            f"{record.get('feedback', '')} "
            f"{record.get('sentiment', '')} "
            f"{record.get('severity', '')} "
            f"{record.get('topic', '')} "
            f"{record.get('summary', '')}"
        ).lower()

        if all(term in content for term in terms):
            results.append(record)

    return results



# =====================================================================
# FUNCTION VERIFICATION TEST
# =====================================================================
if __name__ == "__main__":
    # ===================================================================
    # Pipeline Verification Test
    # ===================================================================
    
    # 1. Initialize your DataManager path config pointing to your target folder path
    # If you run this inside Docker, change it back to "/data/feedback_store.json"
    init_manager(storage_path="./data/feedback_store.json")

    # 2. Simulate raw markdown text received from your AI Manager call
    simulated_ai_output = """
    ```json
    {
        "status": "success",
        "timestamp": "2026-09-29T09:23:00Z",
        "insights": {
            "summary": "Users are reporting system performance speed improvements on build 2.4.",
            "primary_sentiment": "positive",
            "action_required": false
        }
    }
    ```
    """

    print("--- Starting Pipeline Verification Test ---")
    print("Feeding raw AI manager output into standalone function...")
    
    try:
        # 3. Call your functional conversion block to process and log the information
        logic_payload = receive_ai_input(simulated_ai_output)
        
        print("\n[SUCCESS] Pipeline completed successfully without crashing!")
        print(f"Data payload returned clean for Logic Manager: {logic_payload}")
        print("\nCheck your directory folder context: Look inside your './data/' directory.")
        print("You will see a freshly minted 'ai_output_<index>.json' file!")

    except Exception as error:
        print(f"\n[FAILURE] Test run threw an error: {error}")


# # -------------------------------------------------------------------
# # Interactive Terminal Menu Execution
# # -------------------------------------------------------------------
# if __name__ == "__main__":
#     # Initialize data storage mapping strictly to local folder or /data path
#     init_manager(storage_path="./data/feedback_store.json")

#     if not records_store:
#         print("\n[WARNING] No records found in feedback_store.json or input.csv.")
#         print("Please place 'input.csv' inside your local './data/' directory.")
#         sys.exit(0)

#     print(f"\nSuccessfully loaded {len(records_store)} feedback items from storage.")

#     # Terminal Menu Loop
#     while True:
#         choice = input(
#             "\nWould you like to see a (summary) of what is most important, (search) by keyword, or (exit)? "
#         ).strip().lower()

#         if choice in ("summary", "sum", "s"):
#             print("\n==================================================")
#             print("                FEEDBACK SUMMARY                  ")
#             print("==================================================")
#             print(f"Total Stored Records : {len(records_store)}")
#             if report_store:
#                 print(f"Overall Summary      : {report_store.get('overall_summary', 'N/A')}")
#             else:
#                 print("Overall Summary      : No report compiled yet.")
#             print("==================================================\n")

#         elif choice in ("search", "find", "f", "keyword"):
#             query = input("\nEnter search criteria (e.g. 'negative high', 'pacing', 'low'): ").strip()
#             results = search_records(query)

#             print(f"\nFound {len(results)} matching feedback entry/entries:\n")
#             print("-" * 65)
#             if results:
#                 for idx, item in enumerate(results, 1):
#                     print(f"Result #{idx}")
#                     print(f"  Feedback  : {item.get('feedback') or item.get('summary')}")
#                     print(f"  Timestamp : {item.get('timestamp', 'N/A')}")
#                     print(f"  Sentiment : {str(item.get('sentiment')).upper()}")
#                     print(f"  Severity  : {str(item.get('severity')).upper()}")
#                     print(f"  Topic     : {item.get('topic', 'N/A')}")
#                     print("-" * 65)
#             else:
#                 print("No records matched your search query.")

#         elif choice in ("exit", "quit", "q"):
#             print("Exiting application. Goodbye!")
#             break

#         else:
#             print("Invalid input. Please type 'summary', 'search', or 'exit'.")
