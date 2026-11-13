import json
import logging
from pathlib import Path
from typing import Any
from .file_store import FileStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class JsonFileStore(FileStore):
    """Concrete implementation for JSON persistence with safe corruption fallback."""

    def load(self, path: Path) -> Any:
        if not path.exists() or path.stat().st_size == 0:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logging.error("Corrupt JSON at '%s': %s. Returning empty store safely.", path, e)
            return {}

    def save(self, path: Path, data: Any) -> bool:
        return self._write_atomic(path, data)