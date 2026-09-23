import csv
import json
import haslib
import logging
from pathlib import Path
from typng import List, Dict, Any, Union

#set up logging so outputs can be captured by Docker logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s -%(message)s')

class DataManager:
    #persistent data manager designed for Docker containers. Manages records, reports, filtering, statistical hashing, and file recovery.
    def __init__(
            self,
            records_path: str ="/app/data/records.json",
            reports_path: str ="/app/data/reports.json",
            storage_format: str ="json"
    ) -> None:
        self.records_path = Path(records_path)
        self.reports_path = Path(reports_path)
        self.storage_format = storage_format.lower().strip()
        self.records: List[Dict[str, Any]] = []

        #Ensure parent directories exits inside the container volue
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_path.parent.mkdir(parents=True, exist_ok=True)

        #Automatically load existing records if the file exists
        self.load_records()

    def load_records(self) -> List[Dict[str, Any]];
        #load all records from disk. Handles missing or corrupted files gracefully without crashing the container.

        if not self.records_path.exists():
            logging.warning(f" File {self.records_path} not found. Initializing empty records array.")
            self.records = []
            return self.records

        try:
            if self.storage_format == "json":
                with open(self.records_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.records = data if isinstance(data, list) else []
            elif self.storage_format == "csv":
                with open(self.records_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    self.records = [dict(row) for row in reader]

            logging.info(f"Loaded {len(self.records)} records from '{self.records_path}'.")
        except (json.JSONDecodeError, csv.Error, UnicodeDecodeError) as e:
            logging.error(f"Corrupted file at'{self.records_path}': {e}. Recovering with empty state.")
            self.records = []
        except Exception as e:
            logging.error(f"Unexpected error loading '{self.records_path}': {e}. Recovering with empty state.")
            self.records = []

        return self.records

    def save_records(self, record: Dict[str, Any]) -> bool:
        # Append a single record and saves the dataset to the persistent volume.

        try:
            self.records.append(record)

            if self.storage_format == "json":
                with open(self.records_path, "w", encoding="utf-8") as f:
                    json.dump(self.records, f, indent=4)
            elif self.storage_format == "csv":
                if self.records:
                    fieldnames = list(self.records[0].keys())
                    with open(self.records_path, "w", encoding="utf-8", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(self.records)
            logging.info(f"Saved record to '{self.records_path}'.")
            return True
        except Exception as e:
            logging.error(f"Failed to save record to '{self.records_path}': {e}")
            return False
        