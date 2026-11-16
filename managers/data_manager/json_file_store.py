import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from .file_store import FileStore


class JsonFileStore(FileStore):
    """Concrete implementation for JSON persistence with safe corruption fallback."""

    def __init__(self, quarantine_corrupt: bool = True) -> None:
        """quarantine_corrupt: True for the app's own files: a corrupt one is moved
        aside before returning empty, so the next save cannot overwrite what was in
        it, and one that cannot be opened returns empty. False for a user's import
        file: it is never renamed, and an OSError is raised for the caller to report."""
        self._quarantine_corrupt = quarantine_corrupt

    def load(self, path: Path) -> Any:
        if not path.exists() or path.stat().st_size == 0:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            if self._quarantine_corrupt:
                self._move_aside(path, e)
            else:
                logging.error("Corrupt JSON at '%s': %s. Returning empty store safely.", path, e)
            return {}
        except OSError as e:
            # an import file raises, so read_rows can say why it was not read
            if not self._quarantine_corrupt:
                raise
            # an app file is left where it is: its content may be fine, only unreadable now
            logging.error("Could not open '%s': %s. Returning empty store safely.", path, e)
            return {}

    def save(self, path: Path, data: Any) -> bool:
        return self._write_atomic(path, data)

    @staticmethod
    def _move_aside(path: Path, error: Exception) -> None:
        """Renames a corrupt file to <name>.corrupt-<timestamp>, never over an earlier copy."""
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        target = path.with_name(f"{path.name}.corrupt-{stamp}")
        n = 1
        while target.exists():
            target = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
            n += 1
        try:
            path.replace(target)
            logging.error("Corrupt JSON at '%s': %s. Moved to '%s'; starting empty.",
                          path, error, target.name)
        except OSError as move_error:
            logging.error("Corrupt JSON at '%s': %s. Could not move it aside (%s); "
                          "the next save will replace it.", path, error, move_error)
