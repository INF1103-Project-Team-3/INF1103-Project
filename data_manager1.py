import json
import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Union, Optional

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
    """Initializes paths and populates memory state from disk."""
    global JSON_STORAGE_PATH, SUMMARY_STORAGE_PATH
    
    JSON_STORAGE_PATH = Path(storage_path)
    JSON_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_STORAGE_PATH = Path("/data/summary.json")

    # Load existing feedback records and summary state
    load_feedback_records()
    load_summary()

# ==========================================
# CORE FUNCTIONAL LOGIC
# ==========================================

import json
import logging
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)

def update_summary_fields(
    root_updates: Optional[Dict[str, Any]] = None,
    item_updates: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    filename: str = "summary.json",
    base_dir: str = "/data"
) -> bool:
    """
    Updates root-level fields and/or specific objects in summary_list within summary.json.

    :param root_updates: Dict of root keys to update (e.g. {"status": "healthy", "overall_summary": "New summary"})
    :param item_updates: Dict or List[Dict] with target summary_id and fields to update 
                        (e.g. {"summary_id": "sum_001", "summary": "Updated text", "topic": "Docker"})
    :param filename: Name of the JSON file (defaults to "summary.json")
    :param base_dir: Path to storage directory (defaults to "/data")
    """
    filepath = Path(base_dir) / filename

    # 1. Load existing data from file
    data: Dict[str, Any] = {}
    if filepath.exists() and filepath.stat().st_size > 0:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logging.error("Failed to read '%s': %s", filepath, e)
            return False

    # 2. Update Top-Level Root Fields
    if root_updates and isinstance(root_updates, dict):
        for key, value in root_updates.items():
            data[key] = value

    # 3. Update Item(s) inside summary_list by summary_id
    if item_updates:
        updates_list = [item_updates] if isinstance(item_updates, dict) else item_updates

        if "summary_list" not in data or not isinstance(data["summary_list"], list):
            data["summary_list"] = []

        summary_list = data["summary_list"]

        for update_payload in updates_list:
            if not isinstance(update_payload, dict):
                continue

            target_id = update_payload.get("summary_id")
            if not target_id:
                logging.warning("Skipping update item missing 'summary_id'.")
                continue

            # Find matching record in summary_list
            matched_item = next(
                (item for item in summary_list if item.get("summary_id") == target_id),
                None
            )

            if matched_item:
                # Update provided fields for matching summary_id
                for k, v in update_payload.items():
                    matched_item[k] = v
            else:
                # If summary_id doesn't exist yet, append it as a new record
                summary_list.append(update_payload)

    # 4. Automatically refresh timestamp
    data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # 5. Save updated dictionary back to summary.json
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info("Successfully updated fields in '%s'.", filepath)
        return True
    except Exception as e:
        logging.error("Failed to write to '%s': %s", filepath, e)
        return False

def load_or_create_feedback_before_ai(
    filename: str = "feedback_before_ai.json", 
    base_dir: str = "/data"
) -> Dict[str, Any]:
    """Loads existing feedback_before_ai.json or creates a new empty one."""
    filepath = Path(base_dir) / filename

    if filepath.exists() and filepath.stat().st_size > 0:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "records" in data:
                    return data
                elif isinstance(data, list):
                    return {"records": data}
        except Exception as e:
            logging.warning("Failed to load '%s': %s. Re-creating.", filepath, e)

    # File does not exist or is empty -> create directory and empty structure
    filepath.parent.mkdir(parents=True, exist_ok=True)
    empty_store = {"records": []}

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(empty_store, f, indent=2, ensure_ascii=False)

    return empty_store


def save_to_feedback_before_ai(
    incoming_data: Union[Dict[str, Any], List[Dict[str, Any]]], 
    filename: str = "feedback_before_ai.json",
    base_dir: str = "/data"
) -> bool:
    """Appends single dictionary OR multiple dictionaries at once."""
    store = load_or_create_feedback_before_ai(filename, base_dir)

    if "records" not in store or not isinstance(store["records"], list):
        store["records"] = []

    if isinstance(incoming_data, dict):
        store["records"].append(incoming_data)
    elif isinstance(incoming_data, list):
        store["records"].extend(incoming_data)
    else:
        return False

    filepath = Path(base_dir) / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    
    return True

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


def save_feedback_dict(feedback_dict: Dict[str, Any]) -> bool:
    """
    Receives a single feedback dictionary or a list of feedback dictionaries,
    appends them to global memory, and persists them into /data/feedback_store.json.
    """
    global records_store

    # 1. Ensure records_store is populated before appending
    if not records_store:
        load_feedback_records()

    # 2. Append incoming feedback (handles both a single dict or a list of dicts)
    if isinstance(feedback_dict, dict):
        records_store.append(feedback_dict)
    elif isinstance(feedback_dict, list):
        records_store.extend(feedback_dict)
    else:
        logging.error("Invalid data type passed. Expected dict or list of dicts.")
        return False

    # 3. Persist updated memory state to disk (/data/feedback_store.json)
    success = _persist_to_file()
    if success:
        logging.info("Feedback dictionary successfully converted to JSON and stored.")
    return success

def _persist_to_file() -> bool:
    """Saves current global feedback records into feedback_store.json."""
    try:
        payload = {
            "records": records_store
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
    """Saves the current global summary_store state into /data/summary.json."""
    try:
        # Ensure target directory exists
        SUMMARY_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with open(SUMMARY_STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(summary_store, f, indent=2, ensure_ascii=False)
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
    """Updates global summary state (dictionary) and persists directly to /data/summary.json."""
    global summary_store
    
    if not isinstance(summary_data, dict):
        logging.error("Invalid summary data passed. Expected dict.")
        return False

    # Initialize memory if empty
    if not summary_store:
        load_summary()

    # Merge incoming dictionary into global summary memory
    summary_store.update(summary_data)

    # Delegate file writing strictly to helper function
    return _persist_summary_to_file()
    
def search_records(query_text: str) -> List[Dict[str, Any]]:
    """Searches feedback records matching query terms."""
    if not query_text.strip():
        return records_store

    terms = query_text.lower().split()
    results = []

    for record in records_store:
        content = (
            f"{record.get('feedback', '')} "
            f"{record.get('text', '')} "
            f"{record.get('sentiment', '')} "
            f"{record.get('severity', '')} "
            f"{record.get('topic', '')} "
            f"{record.get('theme', '')} "
            f"{record.get('summary', '')}"
        ).lower()

        if all(term in content for term in terms):
            results.append(record)

    return results

    def save_dict_to_json(data_dict: Dict[str, Any], filepath: str = "/data/summary.json") -> bool:
        """
        Receives a dictionary and saves/updates it to a JSON file.
        Creates the directory and file if they do not exist.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)  # Auto-create folders if missing

        # Load existing data if file exists, otherwise start with empty dict
        existing_data = {}
        if path.exists() and path.stat().st_size > 0:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = {}

        # Merge new dictionary fields into existing data
        existing_data.update(data_dict)

        # Write merged dictionary back to JSON
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)

        return True


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

    # Don't hard-exit if records_store is empty so you can still add records!
    if not records_store:
        print("\n[NOTICE] No records found in /data/feedback_store.json. You can start adding new entries!")
    else:
        print(f"\nSuccessfully loaded {len(records_store)} feedback items from storage.")

    while True:
        choice = input(
            "\nOptions: (summary), (search), (add) feedback, (update) summary fields, or (exit): "
        ).strip().lower()

        # --------------------------------------------------
        # 1. VIEW SUMMARY
        # --------------------------------------------------
        if choice in ("summary", "sum", "s"):
            load_summary()

            print("\n==================================================")
            print("                FEEDBACK SUMMARY                  ")
            print("==================================================")
            print(f"Total Stored Records : {len(records_store)}")
            if summary_store:
                print("\nCurrent Summary Content:")
                print(json.dumps(summary_store, indent=2))
            else:
                print("Overall Summary      : No summary compiled yet.")
            print("==================================================\n")

        # --------------------------------------------------
        # 2. SEARCH RECORDS
        # --------------------------------------------------
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

        # --------------------------------------------------
        # 3. ADD NEW FEEDBACK DICTIONARY
        # --------------------------------------------------
        elif choice in ("add", "a", "new"):
            print("\n--- Add New Feedback Dictionary ---")
            fb_text = input("Enter feedback text: ").strip()
            fb_topic = input("Enter topic/theme (e.g., Docker, UI): ").strip() or "General"
            fb_sentiment = input("Enter sentiment (positive/neutral/negative): ").strip().lower() or "neutral"
            fb_severity = input("Enter severity (low/medium/high): ").strip().lower() or "low"

            new_feedback_dict = {
                "feedback_id": f"fb_{len(records_store) + 1:03d}",
                "feedback": fb_text,
                "topic": fb_topic,
                "sentiment": fb_sentiment,
                "severity": fb_severity,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            success = save_feedback_dict(new_feedback_dict)
            if success:
                print(f"Successfully added and saved feedback into /data/feedback_store.json!")
                print(f"Current Record Count: {len(records_store)}")
            else:
                print("Failed to save feedback.")

        # --------------------------------------------------
        # 4. UPDATE EXISTING SUMMARY FIELDS ONLY
        # --------------------------------------------------
        elif choice in ("update", "u", "edit"):
            load_summary()
            if not summary_store:
                print("\n[WARNING] No summary found to update. Run load_summary() or initialize summary.json first.")
                continue

            print("\n--- Update Summary Fields ---")
            print("1. Update Root Field (e.g. overall_summary, status, total_records)")
            print("2. Update Field Inside summary_list (e.g. topic or summary for sum_001, sum_002)")
            
            sub_choice = input("Select update target (1 or 2): ").strip()

            if sub_choice == "1":
                root_keys = [k for k in summary_store.keys() if k != "summary_list"]
                print(f"\nExisting Root Fields: {root_keys}")
                field = input("Enter field name to update: ").strip()

                if field in root_keys:
                    val = input(f"Enter new value for '{field}': ").strip()
                    if val.isdigit():
                        val = int(val)
                    
                    summary_store[field] = val
                    summary_store["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    if _persist_summary_to_file():
                        print(f"Successfully updated root field '{field}'!")
                else:
                    print(f"Invalid field. Choose from existing keys: {root_keys}")

            elif sub_choice == "2":
                summary_list = summary_store.get("summary_list", [])
                if not summary_list:
                    print("No summary_list items found in summary.json.")
                    continue

                print("\nAvailable Summary Entries:")
                for item in summary_list:
                    print(f"  - ID: {item.get('summary_id')} | Topic: '{item.get('topic')}' | Summary: '{item.get('summary')}'")

                target_id = input("\nEnter summary_id to modify (e.g., sum_001): ").strip()
                target_item = next((item for item in summary_list if item.get("summary_id") == target_id), None)

                if target_item:
                    print(f"Existing fields for {target_id}: {list(target_item.keys())}")
                    field = input("Enter field to update (e.g. topic, summary, status): ").strip()

                    if field in target_item:
                        new_val = input(f"Enter new value for '{field}': ").strip()
                        target_item[field] = new_val
                        summary_store["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

                        if _persist_summary_to_file():
                            print(f"Successfully updated '{field}' for '{target_id}' in /data/summary.json!")
                    else:
                        print(f"Field '{field}' does not exist on {target_id}.")
                else:
                    print(f"Summary ID '{target_id}' not found.")

        # --------------------------------------------------
        # 5. EXIT
        # --------------------------------------------------
        elif choice in ("exit", "quit", "q"):
            print("Exiting application. Goodbye!")
            break

        else:
            print("Invalid input. Type 'summary', 'search', 'add', 'update', or 'exit'.")