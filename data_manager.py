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
