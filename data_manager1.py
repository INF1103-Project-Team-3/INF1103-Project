import csv
import json
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class DataManager:
    """
    Data Manager that converts CSV feedback data into a structured JSON dataset,
    computes reports, maintains state across Docker runs, and provides search functionality.
    """

    def __init__(
        self,
        json_storage_path: str = "/data/feedback_store.json",
        csv_import_path: str = "/data/input.csv",
        force_csv_import: bool = False
    ) -> None:
        self.json_path = Path(json_storage_path)
        self.csv_path = Path(csv_import_path)
        self.records: List[Dict[str, Any]] = []
        self.report: Dict[str, Any] = {}

        # Ensure directory exists inside Docker volume
        self.json_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. First attempt to load existing JSON state
        self.load_records()
        self.load_report()

        # 2. Ingest CSV if no JSON records exist OR if force_csv_import is True
        if (not self.records or force_csv_import) and self.csv_path.exists():
            logging.info(f"Ingesting CSV data from '{self.csv_path}'...")
            self.import_from_csv(self.csv_path)

    def import_from_csv(self, csv_filepath: Path) -> List[Dict[str, Any]]:
        """Reads CSV, converts rows into typed feedback records, and persists to JSON."""
        if not csv_filepath.exists():
            logging.warning(f"CSV file at '{csv_filepath}' does not exist.")
            return []

        imported_records = []
        try:
            with open(csv_filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    reader.fieldnames = [field.strip() for field in reader.fieldnames]

                for row in reader:
                    reasons_raw = str(row.get("review_reasons", "[]")).strip()
                    try:
                        review_reasons = json.loads(reasons_raw.replace("'", '"')) if reasons_raw else []
                    except Exception:
                        review_reasons = [r.strip() for r in reasons_raw.split(",") if r.strip()]

                    try:
                        confidence_val = float(row.get("confidence", 0.0))
                    except (ValueError, TypeError):
                        confidence_val = 0.0

                    record = {
                        "feedback_id": str(row.get("feedback_id", "")).strip(),
                        "feedback": str(row.get("feedback", "")).strip(),
                        "timestamp": str(row.get("timestamp", "")).strip(),
                        "theme": str(row.get("theme", "Uncategorized")).strip(),
                        "sentiment": str(row.get("sentiment", "neutral")).strip(),
                        "severity": str(row.get("severity", "low")).strip(),
                        "summary": str(row.get("summary", "")).strip(),
                        "confidence": confidence_val,
                        "needs_review": str(row.get("needs_review", "")).strip().lower() in ("true", "1", "yes"),
                        "review_reasons": review_reasons,
                        "counted": str(row.get("counted", "")).strip().lower() in ("true", "1", "yes")
                    }
                    imported_records.append(record)

            self.records = imported_records
            self._persist_to_file()
            logging.info(f"Successfully converted and saved {len(imported_records)} records from CSV.")

        except Exception as e:
            logging.error(f"Error importing CSV file '{csv_filepath}': {e}. Recovering with empty dataset.")
            self.records = []

        return self.records

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
            logging.error(f"Failed to write to '{self.json_path}': {e}")
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
            logging.error(f"Corrupt JSON at '{self.json_path}': {e}. Resetting memory.")
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
        Searches records matching terms against text, sentiment, severity, or theme.
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
                f"{record.get('theme', '')} "
                f"{record.get('summary', '')}"
            ).lower()

            # Record must contain all typed query words (e.g. "negative" AND "high")
            if all(term in content for term in terms):
                results.append(record)

        return results


# -------------------------------------------------------------------
# Interactive Terminal Menu Execution
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize DataManager pointing strictly to /data
    dm = DataManager(
        json_storage_path="/data/feedback_store.json",
        csv_import_path="/data/input.csv",
        force_csv_import=False
    )

    if not dm.records:
        print("\n[WARNING] No records found in /data/feedback_store.json or /data/input.csv.")
        print("Please place 'input.csv' inside your local './data/' directory.")
        sys.exit(0)

    print(f"\nSuccessfully loaded {len(dm.records)} feedback items from storage.")

    # Terminal Menu Loop
    while True:
        choice = input(
            "\nWould you like to see a (summary) of what is most important, (search) by keyword, or (exit)? "
        ).strip().lower()

        if choice in ("summary", "sum", "s"):
            stats = dm.hash_stats()
            print("\n==================================================")
            print("                FEEDBACK SUMMARY                  ")
            print("==================================================")
            print(f"Total Stored Records : {stats['total_records']}")
            print(f"Dataset SHA256 Hash  : {stats['sha256_hash']}")
            if dm.report:
                print(f"Overall Summary      : {dm.report.get('overall_summary', 'N/A')}")
            else:
                print("Overall Summary      : No report compiled yet.")
            print("==================================================\n")

        elif choice in ("search", "find", "f", "keyword"):
            query = input("\nEnter search criteria (e.g. 'negative high', 'pacing', 'low'): ").strip()
            results = dm.search_records(query)

            print(f"\nFound {len(results)} matching feedback entry/entries:\n")
            print("-" * 65)
            if results:
                for idx, item in enumerate(results, 1):
                    print(f"Result #{idx}")
                    print(f"  Feedback  : {item.get('feedback') or item.get('summary')}")
                    print(f"  Timestamp : {item.get('timestamp', 'N/A')}")
                    print(f"  Sentiment : {str(item.get('sentiment')).upper()}")
                    print(f"  Severity  : {str(item.get('severity')).upper()}")
                    print(f"  Theme     : {item.get('theme', 'N/A')}")
                    print("-" * 65)
            else:
                print("No records matched your search query.")

        elif choice in ("exit", "quit", "q"):
            print("Exiting application. Goodbye!")
            break

        else:
            print("Invalid input. Please type 'summary', 'search', or 'exit'.")