import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class DataManager:
    """
    Manages persistent feedback records and aggregate report summaries across Docker runs.
    """

    def __init__(self, storage_path: str = "/app/data/feedback_store.json") -> None:
        """
        Initialize the DataManager and automatically load existing state on startup.
        """
        self.storage_path = Path(storage_path)
        self.records: List[Dict[str, Any]] = []
        self.report: Dict[str, Any] = {}

        # Ensure directory exists in Docker volume
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Automatically load existing memory on startup
        self.load_records()
        self.load_report()

    def _read_file_safely(self) -> Dict[str, Any]:
        """
        Private helper to read and parse the persistent JSON storage safely.
        Handles missing or corrupt files without crashing.
        """
        if not self.storage_path.exists():
            logging.warning(f"Storage file '{self.storage_path}' not found. Initializing empty dataset.")
            return {"records": [], "report": {}}

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {
                        "records": data.get("records", []),
                        "report": data.get("report", {})
                    }
                else:
                    logging.error(f"File '{self.storage_path}' is invalid root JSON. Resetting.")
                    return {"records": [], "report": {}}

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logging.error(f"Corrupted storage file at '{self.storage_path}': {e}. Recovering with empty state.")
            return {"records": [], "report": {}}
        except Exception as e:
            logging.error(f"Unexpected error loading '{self.storage_path}': {e}. Recovering with empty state.")
            return {"records": [], "report": {}}

    def _persist_to_file(self) -> bool:
        """Private helper to save both records and report state back to disk."""
        try:
            payload = {
                "records": self.records,
                "report": self.report
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logging.info(f"Successfully saved state to '{self.storage_path}'.")
            return True
        except Exception as e:
            logging.error(f"Failed to write state to '{self.storage_path}': {e}")
            return False

    def load_records(self) -> List[Dict[str, Any]]:
        """
        Loads all feedback records from disk on startup or invocation.
        """
        data = self._read_file_safely()
        self.records = data["records"]
        logging.info(f"Loaded {len(self.records)} feedback records from storage.")
        return self.records

    def save_record(self, record: Dict[str, Any]) -> bool:
        """
        Appends a new feedback record (e.g., fb_001) and saves to persistent storage.
        """
        self.records.append(record)
        return self._persist_to_file()

    def load_report(self) -> Dict[str, Any]:
        """
        Loads the report dictionary from disk.
        """
        data = self._read_file_safely()
        self.report = data["report"]
        logging.info("Successfully loaded report summary.")
        return self.report

    def save_report(self, report_data: Dict[str, Any]) -> bool:
        """
        Updates and persists the overall summary report and theme metrics.
        """
        self.report = report_data
        return self._persist_to_file()

    def hash_stats(self) -> Dict[str, Any]:
        """
        Generates statistical metrics and a SHA-256 fingerprint signature across records.
        """
        total_records = len(self.records)
        
        # Serialize records deterministically to compute SHA-256 hash
        serialized_records = json.dumps(self.records, sort_keys=True).encode("utf-8")
        dataset_hash = hashlib.sha256(serialized_records).hexdigest()

        # Compute theme distribution counts
        theme_counts: Dict[str, int] = {}
        for r in self.records:
            theme = r.get("theme", "Uncategorized")
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

        stats = {
            "total_records": total_records,
            "theme_distribution": theme_counts,
            "sha256_hash": dataset_hash
        }
        return stats

    def filter_records(self, **query: Any) -> List[Dict[str, Any]]:
        """
        Queries stored records matching key-value criteria.
        Example: manager.filter_records(theme="Pacing", severity="medium")
        """
        results = []
        for record in self.records:
            match = all(record.get(key) == value for key, value in query.items())
            if match:
                results.append(record)
        return results


# -------------------------------------------------------------------
# Direct Execution Demo
# -------------------------------------------------------------------
if __name__ == "__main__":
    dm = DataManager(storage_path="data/feedback_store.json")

    # 1. Add sample feedback record matching your JSON schema
    sample_record = {
        "feedback_id": "fb_001",
        "text": "The lecture slides moved way too fast today.",
        "timestamp": "2026-09-15T10:32:00",
        "theme": "Pacing",
        "sentiment": "negative",
        "severity": "medium",
        "summary": "Student struggles to keep up with fast-paced slides.",
        "confidence": 0.92,
        "needs_review": False,
        "review_reasons": [],
        "counted": True
    }
    dm.save_record(sample_record)

    # 2. Compute hash stats
    stats = dm.hash_stats()

    # 3. Save matching report section
    sample_report = {
        "stats_key": stats["sha256_hash"],
        "overall_summary": "Most concerns relate to lecture pacing and assessment clarity.",
        "theme_actions": [{"theme": "Pacing", "suggested_action": "Slow down slide progression."}],
        "themes": [
            {
                "theme": "Pacing",
                "count": 1,
                "avg_sentiment": -0.75,
                "severity_counts": {"low": 0, "medium": 1, "high": 0, "critical": 0},
                "priority": True
            }
        ]
    }
    dm.save_report(sample_report)

    # 4. Filter records test
    pacing_issues = dm.filter_records(theme="Pacing", severity="medium")
    print(f"\nFiltered Pacing Records Found: {len(pacing_issues)}")
    print(f"Dataset SHA-256 Hash: {stats['sha256_hash']}")