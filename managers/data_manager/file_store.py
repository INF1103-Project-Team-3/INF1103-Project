import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from .storage_backend import StorageBackend

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FileStore(StorageBackend, ABC):
    """Abstract base class handling shared atomic writes and logging."""

    def _write_atomic(self, filepath: Path, data: Any) -> bool:
        temp_path = filepath.with_name(filepath.name + ".tmp")
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(filepath)
            return True
        except OSError as e:
            logging.error("Failed to write atomically to '%s': %s", filepath, e)
            return False

    @abstractmethod
    def load(self, path: Path) -> Any:
        pass

    @abstractmethod
    def save(self, path: Path, data: Any) -> bool:
        pass