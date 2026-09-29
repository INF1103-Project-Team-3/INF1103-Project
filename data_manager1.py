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


class DataManager:
    """
    Data Manager that handles a structured JSON dataset,
    computes reports, maintains state across Docker runs,
    captures inputs from the AI Manager, and provides search functionality.
    """

    def __init__(
        self,
        json_storage_path: str = "/data/feedback_store.json"
    ) -> None:
        self.json_path = Path(json_storage_path)
        self.records: List[Dict[str, Any]] = [] #list to hold feedback records
        self.report: Dict[str, Any] = {} #list to hold the summary report

        # Ensure directory exists inside Docker volume
        self.json_path.parent.mkdir(parents=True, exist_ok=True)

        # Ingest state on startup from JSON storage
        self.load_records() #pulls feedback records from the JSON file into memory
        self.load_report() #pulls summary report data from the JSON file into memory

    def receive_ai_input(self, raw_ai_text: str) -> Union[Dict[str, Any], List[Any]]:
        """
        Receives raw JSON text from the AI Manager, increments a counter based on 
        existing folder contents (e.g., ai_output_1.json, ai_output_2.json), saves it, and returns the object.
        """
        # 1. Clean up potential AI markdown syntax formatting blocks
        cleaned_text = raw_ai_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text.replace("```json", "", 1).rstrip("`").strip()
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text.replace("```", "", 1).rstrip("`").strip()

        # 2. Parse string data into a structured Python object
        try:
            parsed_data = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            logging.error(f"Text structural validation failed on AI output: {e}")
            raise ValueError(f"[Data Manager Error] AI text is not valid JSON: {e}")

        # 3. Scan directory to calculate the next sequential file number
        folder = self.json_path.parent
        next_index = 1
        
        if folder.exists():
            # Find all files matching 'ai_output_*.json'
            existing_files = folder.glob("ai_output_*.json")
            existing_numbers = []
            
            for file in existing_files:
                # Extract the number between 'ai_output_' and '.json'
                try:
                    # file.stem gets 'ai_output_1', splitting by '_' gets ['ai_output', '1']
                    num_part = file.stem.split("_")[-1]
                    existing_numbers.append(int(num_part))
                except (ValueError, IndexError):
                    continue
            
            if existing_numbers:
                next_index = max(existing_numbers) + 1

        # 4. Construct the ultra-short filename (e.g., ai_output_1.json, ai_output_2.json)
        filename = f"ai_output_{next_index}.json"
        file_path = folder / filename

        # 5. Write the payload securely into the Docker container volume file path
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(parsed_data, file, indent=4, ensure_ascii=False)
            logging.info(f"AI operational stream successfully logged to disk -> {file_path}")
        except IOError as e:
            logging.warning(f"Disk write interrupted but operational stream intact: {e}")

        # 6. Instantly hand off the ready object data payload to your Logic Manager loop
        return parsed_data


    def _persist_to_file(self) -> bool:
        """Saves current records and report state into a consolidated JSON file."""
        try:
            payload = {
                "records": self.records,
                "report": self.report
            }
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return True
        except Exception as e:
            logging.error("Failed to write to '%s': %s", self.json_path, e)
            return False

    def load_records(self) -> List[Dict[str, Any]]:
        """Loads records array from JSON store. Handles corrupt files safely."""
        if not self.json_path.exists():
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.records = data.get("records", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logging.error("Corrupt JSON at '%s': %s. Resetting memory.", self.json_path, e)
            self.records = []
        return self.records

    def save_record(self, record: Dict[str, Any]) -> bool:
        """Appends a new feedback record and saves."""
        self.records.append(record)
        return self._persist_to_file()

    def load_report(self) -> Dict[str, Any]:
        """Loads report dictionary from JSON store."""
        if not self.json_path.exists():
            return {}
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.report = data.get("report", {}) if isinstance(data, dict) else {}
        except Exception:
            self.report = {}
        return self.report

    def save_report(self, report_data: Dict[str, Any]) -> bool:
        """Updates and persists report dictionary."""
        self.report = report_data
        return self._persist_to_file()

    def hash_stats(self) -> Dict[str, Any]:
        """Calculates dataset SHA-256 fingerprint and summary statistics."""
        serialized = json.dumps(self.records, sort_keys=True).encode("utf-8")
        dataset_hash = hashlib.sha256(serialized).hexdigest()
        return {
            "total_records": len(self.records),
            "sha256_hash": dataset_hash
        }

    def search_records(self, query_text: str) -> List[Dict[str, Any]]:
        """
        Searches records matching terms against text, sentiment, severity, or topic.
        Example query: 'negative high'
        """
        if not query_text.strip():
            return self.records

        terms = query_text.lower().split()
        results = []

        for record in self.records:
            content = (
                f"{record.get('feedback', '')} "
                f"{record.get('sentiment', '')} "
                f"{record.get('severity', '')} "
                f"{record.get('topic', '')} "
                f"{record.get('summary', '')}"
            ).lower()

            # Record must contain all typed query words (e.g. "negative" AND "high")
            if all(term in content for term in terms):
                results.append(record)

        return results


# =====================================================================
# FUNCTION VERIFICATION TEST
# =====================================================================
if __name__ == "__main__":
    # 1. Initialize your DataManager class pointing to your target folder path
    # If you run this inside Docker, keep it as "/data/feedback_store.json"
    data_manager = DataManager(json_storage_path="./data/feedback_store.json")

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
    print("Feeding raw AI manager output into DataManager...")
    
    try:
        # 3. Call your function to process and log the information
        logic_payload = data_manager.receive_ai_input(simulated_ai_output)
        
        print("\n[SUCCESS] Pipeline completed successfully without crashing!")
        print(f"Data payload returned clean for Logic Manager: {logic_payload}")
        print("\nCheck your directory folder context: Look inside your './data/' directory.")
        print("You will see a freshly minted 'ai_output_<index>.json' file!")

    except Exception as error:
        print(f"\n[FAILURE] Test run threw an error: {error}")


# -------------------------------------------------------------------
# Interactive Terminal Menu Execution
# -------------------------------------------------------------------
# if __name__ == "__main__":
#     # Initialize DataManager pointing strictly to /data
#     dm = DataManager(
#         json_storage_path="/data/feedback_store.json"
#         )

#     if not dm.records:
#         print("\n[WARNING] No records found in /data/feedback_store.json or /data/input.csv.")
#         print("Please place 'input.csv' inside your local './data/' directory.")
#         sys.exit(0)

#     print(f"\nSuccessfully loaded {len(dm.records)} feedback items from storage.")

#     # Terminal Menu Loop
#     while True:
#         choice = input(
#             "\nWould you like to see a (summary) of what is most important, (search) by keyword, or (exit)? "
#         ).strip().lower()

#         if choice in ("summary", "sum", "s"):
#             stats = dm.hash_stats()
#             print("\n==================================================")
#             print("                FEEDBACK SUMMARY                  ")
#             print("==================================================")
#             print(f"Total Stored Records : {stats['total_records']}")
#             print(f"Dataset SHA256 Hash  : {stats['sha256_hash']}")
#             if dm.report:
#                 print(f"Overall Summary      : {dm.report.get('overall_summary', 'N/A')}")
#             else:
#                 print("Overall Summary      : No report compiled yet.")
#             print("==================================================\n")

#         elif choice in ("search", "find", "f", "keyword"):
#             query = input("\nEnter search criteria (e.g. 'negative high', 'pacing', 'low'): ").strip()
#             results = dm.search_records(query)

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