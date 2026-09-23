import csv
import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class DataManager:
    """
    Data Manager that converts CSV feedback data into a structured JSON dataset,
    computes reports, and maintains state across Docker runs.
    """

    def __init__(
        self,
        json_storage_path: str = "/app/data/feedback_store.json",
        csv_import_path: str = "/app/data/input.csv",
        force_csv_import: bool = False  # Added force_csv_import parameter
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
        """
        Reads a CSV file, parses data types (booleans, floats, lists),
        and converts rows into the feedback record JSON format.
        """
        if not csv_filepath.exists():
            logging.warning(f"CSV file at '{csv_filepath}' does not exist.")
            return []

        imported_records = []
        try:
            with open(csv_filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                
                # Strip spaces or BOM artifacts from column headers
                if reader.fieldnames:
                    reader.fieldnames = [field.strip() for field in reader.fieldnames]

                for row in reader:
                    # Parse review reasons list safely
                    reasons_raw = str(row.get("review_reasons", "[]")).strip()
                    try:
                        review_reasons = json.loads(reasons_raw.replace("'", '"')) if reasons_raw else []
                    except Exception:
                        review_reasons = [r.strip() for r in reasons_raw.split(",") if r.strip()]

                    # Parse float confidence safely
                    try:
                        confidence_val = float(row.get("confidence", 0.0))
                    except (ValueError, TypeError):
                        confidence_val = 0.0

                    # Map flat CSV row into typed JSON record
                    record = {
                        "feedback ID": str(row.get("feedback ID", "")).strip(),
                        "user ID": str(row.get("user ID", "")).strip(),
                        "feedback": str(row.get("feedback", "")).strip(),
                        "timestamp": str(row.get("timestamp", "")).strip(),
                        "topic": str(row.get("topic", "Uncategorized")).strip(),
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

    def filter_records(self, **query: Any) -> List[Dict[str, Any]]:
        """Queries stored records matching key-value criteria."""
        results = []
        for record in self.records:
            match = all(record.get(k) == v for k, v in query.items())
            if match:
                results.append(record)
        return results


# -------------------------------------------------------------------
# Execution Block
# -------------------------------------------------------------------
if __name__ == "__main__":
    logging.info("--- Starting DataManager Test Execution ---")

    # Force CSV import so input.csv converts directly to JSON
    dm = DataManager(
        json_storage_path="/app/data/feedback_store.json",
        csv_import_path="/app/data/input.csv",
        force_csv_import=True
    )

    # 1. Print records count to verify CSV loaded
    print(f"\n[DEBUG] Total Records Loaded: {len(dm.records)}")

    # 2. Compute and print dataset hash stats
    stats = dm.hash_stats()
    print(f"[DEBUG] SHA256 Fingerprint: {stats['sha256_hash']}")

    # 3. Save calculated report state into JSON
    sample_report = {
        "stats_key": stats["sha256_hash"],
        "overall_summary": "Processed feedback records from CSV import.",
        "total_imported": len(dm.records)
    }
    dm.save_report(sample_report)

    logging.info("--- Execution Complete. Check /app/data/feedback_store.json ---")