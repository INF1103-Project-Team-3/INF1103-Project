import csv
import logging
from pathlib import Path
from typing import Any
from .file_store import FileStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class CsvFileStore(FileStore):
    """Concrete implementation for CSV parsing and persistence. Fully implements StorageBackend for LSP[cite: 8]."""

    def load(self, path: Path) -> Any:
        if not path.exists() or path.stat().st_size == 0:
            return []
        rows = []
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
            return rows
        except Exception as e:
            logging.error("Failed to read CSV at '%s': %s", path, e)
            raise ValueError(f"Unreadable CSV file: {e}")

    def save(self, path: Path, data: Any) -> bool:
        """Fully functional save to satisfy LSP since it implements StorageBackend[cite: 8]."""
        if not isinstance(data, list):
            logging.error("CsvFileStore expects a list of dicts to save.")
            return False
        temp_path = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if data and isinstance(data[0], dict):
                fieldnames = list(data[0].keys())
                with open(temp_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(data)
                temp_path.replace(path)
                return True
            return False
        except Exception as e:
            logging.error("Failed to write CSV to '%s': %s", path, e)
            return False