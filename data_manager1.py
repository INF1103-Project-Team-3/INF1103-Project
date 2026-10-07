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
# MODULE STATE & CONFIGURATION
# ==========================================
JSON_STORAGE_PATH = Path(os.getenv("JSON_STORAGE_PATH", "/data/feedback_store.json"))
SUMMARY_STORAGE_PATH = Path(os.getenv("SUMMARY_STORAGE_PATH", "/data/summary.json"))

# Global states to hold current information in memory
records_store: List[Dict[str, Any]] = [] 
summary_store: Dict[str, Any] = {}


def init_manager(storage_path: str = "/data/feedback_store.json") -> None:
    """Initializes paths, folders, and populates the global memory stores."""
    global JSON_STORAGE_PATH, SUMMARY_STORAGE_PATH

    JSON_STORAGE_PATH = Path(storage_path)
    JSON_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_STORAGE_PATH = Path("/data/summary.json")

    # Load existing disk datasets into memory state on boot
    load_feedback_records()
    load_summary()


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
        logging.error("Text structural validation failed on AI output: %s", e)
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
        logging.info("AI operational stream successfully logged to disk -> %s", file_path)
    except IOError as e:
        logging.warning("Disk write interrupted but operational stream intact: %s", e)

    return parsed_data

def _persist_to_file() -> bool:
    """Saves the current global records and summary state into feedback_store.json."""
    try:
        payload = {
            "records": records_store,
            "summary": summary_store
        }
        with open(JSON_STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error("Failed to write to '%s': %s", JSON_STORAGE_PATH, e)
        return False

def load_feedback_records() -> List[Dict[str, Any]]:
    """Loads feedback records array from JSON store into global memory."""
    global records_store
    if not JSON_STORAGE_PATH.exists():
        records_store = []
        return []

    try:
        with open(JSON_STORAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

            # Handle Dict Root: {"records": [...]}
            if isinstance(data, dict):
                records_store = data.get("records", []) or data.get("feedback_store", [])
            # Handle List Root: [...]
            elif isinstance(data, list):
                records_store = data
            else:
                records_store = []

        logging.info("Loaded %d record(s) from '%s'", len(records_store), JSON_STORAGE_PATH)

    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.error("Corrupt JSON at '%s': %s. Resetting memory.", JSON_STORAGE_PATH, e)
        records_store = []

    return records_store

def save_feedback_record(record: Dict[str, Any]) -> bool:
    """Appends a new feedback record to global state and saves."""
    records_store.append(record)
    return _persist_to_file()


def _persist_summary_to_file() -> bool:
    """Saves the current global summary state into the flat JSON file."""
    try:
        # Ensure target directory exists
        SUMMARY_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with open(SUMMARY_STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(summary_store, f, indent=2)
        return True
    except Exception as e:
        logging.error("Failed to write summary to '%s': %s", SUMMARY_STORAGE_PATH, e)
        return False


def load_summary() -> Dict[str, Any]:
    """Loads summary dictionary from /data/summary.json into global memory."""
    global summary_store
    if not SUMMARY_STORAGE_PATH.exists():
        summary_store = {}
        return summary_store

    try:
        with open(SUMMARY_STORAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            summary_store = data if isinstance(data, dict) else {}
        logging.info("Loaded summary from '%s'", SUMMARY_STORAGE_PATH)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.error("Corrupt summary JSON at '%s': %s", SUMMARY_STORAGE_PATH, e)
        summary_store = {}

    return summary_store

def save_summary(summary_data: Dict[str, Any]) -> bool:
    """Updates summary state and persists directly to /data/summary.json."""
    global summary_store
    if isinstance(summary_data, dict):
        summary_store.update(summary_data)
    else:
        summary_store = summary_data

    try:
        SUMMARY_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SUMMARY_STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(summary_store, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error("Failed to save summary to '%s': %s", SUMMARY_STORAGE_PATH, e)
        return False
    
def search_records(query_text: str) -> List[Dict[str, Any]]:
    """Searches active global memory records matching query terms."""
    if not query_text.strip():
        return records_store

    terms = query_text.lower().split()
    results = []

    for record in records_store:
        content = (
            f"{record.get('text', '')} "
            f"{record.get('feedback', '')} "
            f"{record.get('sentiment', '')} "
            f"{record.get('severity', '')} "
            f"{record.get('theme', '')} "
            f"{record.get('topic', '')} "
            f"{record.get('summary', '')}"
        ).lower()

        if all(term in content for term in terms):
            results.append(record)

    return results



# # =====================================================================
# # FUNCTION VERIFICATION TEST
# # =====================================================================
# if __name__ == "__main__":
#     # ===================================================================
#     # Pipeline Verification Test
#     # ===================================================================
    
#     # 1. Initialize your DataManager path config pointing to your target folder path
#     # If you run this inside Docker, change it back to "/data/feedback_store.json"
#     init_manager(storage_path="./data/feedback_store.json")

#     # 2. Simulate raw markdown text received from your AI Manager call
#     simulated_ai_output = """
#     ```json
#     {
#         "status": "success",
#         "timestamp": "2026-09-29T09:23:00Z",
#         "insights": {
#             "summary": "Users are reporting system performance speed improvements on build 2.4.",
#             "primary_sentiment": "positive",
#             "action_required": false
#         }

#     }
#     ```
#     """

#     print("--- Starting Pipeline Verification Test ---")
#     print("Feeding raw AI manager output into standalone function...")
    
#     try:
#         # 3. Call your functional conversion block to process and log the information
#         logic_payload = receive_ai_input(simulated_ai_output)
        
#         print("\n[SUCCESS] Pipeline completed successfully without crashing!")
#         print(f"Data payload returned clean for Logic Manager: {logic_payload}")
#         print("\nCheck your directory folder context: Look inside your './data/' directory.")
#         print("You will see a freshly minted 'ai_output_<index>.json' file!")

#     except Exception as error:
#         print(f"\n[FAILURE] Test run threw an error: {error}")


# ==========================================
# CLI TERMINAL MENU
# ==========================================

if __name__ == "__main__":
    init_manager("/data/feedback_store.json")

    if not records_store:
        print("\n[WARNING] No records found in /data/feedback_store.json.")
        sys.exit(0)

    print(f"\nSuccessfully loaded {len(records_store)} feedback items from storage.")

    while True:
        choice = input(
            "\nWould you like to see a (summary) of what is most important, (search) by keyword, or (exit)? "
        ).strip().lower()

        if choice in ("summary", "sum", "s"):
            print("\n==================================================")
            print("                FEEDBACK SUMMARY                  ")
            print("==================================================")
            print(f"Total Stored Records : {len(records_store)}")
            if summary_store:
                print(f"Overall Summary      : {summary_store.get('overall_summary', 'N/A')}")
                print(f"Status               : {summary_store.get('status', 'N/A')}")
            else:
                print("Overall Summary      : No summary compiled yet.")
            print("==================================================\n")

        elif choice in ("search", "find", "f", "keyword"):
            query = input("\nEnter search criteria (e.g. 'negative high', 'pacing'): ").strip()
            results = search_records(query)

            print(f"\nFound {len(results)} matching feedback entry/entries:\n")
            print("-" * 65)
            if results:
                for idx, item in enumerate(results, 1):
                    print(f"Result #{idx}")
                    print(f"  Feedback  : {item.get('feedback') or item.get('text') or item.get('summary')}")
                    print(f"  Timestamp : {item.get('timestamp', 'N/A')}")
                    print(f"  Sentiment : {str(item.get('sentiment')).upper()}")
                    print(f"  Severity  : {str(item.get('severity')).upper()}")
                    print(f"  Topic     : {item.get('topic') or item.get('theme', 'N/A')}")
                    print("-" * 65)
            else:
                print("No records matched your search query.")

        elif choice in ("exit", "quit", "q"):
            print("Exiting application. Goodbye!")
            break

        else:
            print("Invalid input. Please type 'summary', 'search', or 'exit'.")

