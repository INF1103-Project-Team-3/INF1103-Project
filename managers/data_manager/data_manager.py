import logging
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .storage_backend import StorageBackend
from .json_file_store import JsonFileStore
from .csv_file_store import CsvFileStore

# Import models and constants from shared package
try:
    from managers.models import THEMES, FeedbackRecord, Action
except ImportError:
    THEMES = (
        "Teaching Quality",
        "Assessment",
        "Facilities",
        "Administration",
        "Well-being",
        "Social Environment",
        "Workload",
        "Internship Placement",
    )
    FeedbackRecord = None  # type: ignore
    Action = None  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _read_list_strict(path: Union[str, Path]) -> List[Any]:
    """Module-level compatibility helper for older I/O tests."""
    store = JsonFileStore()
    data = store.load(Path(path))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "records" in data:
        return data["records"]
    raise ValueError("Expected a list or records container.")


class DataManager:
    """
    Encapsulates all file persistence and returns model objects.
    """

    def __init__(self, data_dir: str = "data", store: Optional[StorageBackend] = None) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.json_store: StorageBackend = store if store else JsonFileStore()

        self._importers = {
            ".csv": CsvFileStore(),
            ".json": self.json_store,
        }

    def _get_path(self, filename: str) -> Path:
        return self.data_dir / filename

    def _to_records(self, raw_list: List[Any]) -> List[Any]:
        """Converts raw dictionaries into FeedbackRecord objects, skipping corrupt entries."""
        if FeedbackRecord is None:
            return raw_list
        records = []
        for item in raw_list:
            if isinstance(item, FeedbackRecord):
                records.append(item)
            elif isinstance(item, dict):
                try:
                    records.append(FeedbackRecord.from_dict(item))
                except (KeyError, ValueError) as e:
                    logging.error("Skipping corrupt FeedbackRecord entry: %s", e)
        return records

    def _to_actions(self, raw_list: List[Any]) -> List[Any]:
        """Converts raw dictionaries into Action objects, skipping corrupt entries."""
        if Action is None:
            return raw_list
        actions = []
        for item in raw_list:
            if isinstance(item, Action):
                actions.append(item)
            elif isinstance(item, dict):
                try:
                    actions.append(Action.from_dict(item))
                except (KeyError, ValueError) as e:
                    logging.error("Skipping corrupt Action entry: %s", e)
        return actions

    def _load_raw_records(self, filename: str) -> List[Dict[str, Any]]:
        """Internal helper to load raw record dicts from a store file."""
        filepath = self._get_path(filename)
        data = self.json_store.load(filepath)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data["records"]
        if isinstance(data, list):
            return data
        return []

    def load_records(self, filename: str = "processed_feedback.json") -> List[Any]:
        raw_list = self._load_raw_records(filename)
        return self._to_records(raw_list)

    def save_records(self, records: List[Any]) -> bool:
        filepath = self._get_path("processed_feedback.json")
        payload = {"records": [r.to_dict() if hasattr(r, "to_dict") else r for r in records]}
        return self.json_store.save(filepath, payload)

    def delete_record(self, feedback_id: str) -> bool:
        success_proc = self._remove_from_store_file(feedback_id, "processed_feedback.json")
        success_rev = self._remove_from_store_file(feedback_id, "for_review.json")
        success_pend = self._remove_from_store_file(feedback_id, "feedback_before_ai.json")
        return success_proc or success_rev or success_pend

    def _remove_from_store_file(self, feedback_id: str, filename: str) -> bool:
        filepath = self._get_path(filename)
        data = self.json_store.load(filepath)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            filtered = [item for item in data["records"] if item.get("feedback_id") != feedback_id]
            data["records"] = filtered
            return self.json_store.save(filepath, data)
        elif isinstance(data, list):
            filtered = [item for item in data if item.get("feedback_id") != feedback_id]
            return self.json_store.save(filepath, filtered)
        return True

    def load_pending(self, filename: str = "feedback_before_ai.json") -> List[Any]:
        raw_list = self._load_raw_records(filename)
        return self._to_records(raw_list)

    def save_pending(self, records: List[Any], filename: str = "feedback_before_ai.json") -> bool:
        filepath = self._get_path(filename)
        payload = {"records": [r.to_dict() if hasattr(r, "to_dict") else r for r in records]}
        return self.json_store.save(filepath, payload)

    def add_pending(self, records: Union[Any, List[Any]]) -> bool:
        current = self._load_raw_records("feedback_before_ai.json")
        incoming = records if isinstance(records, list) else [records]
        current.extend([r.to_dict() if hasattr(r, "to_dict") else r for r in incoming])
        return self.save_pending(current)

    def update_pending(self, record: Any) -> None:
        target_id = record.get("feedback_id") if isinstance(record, dict) else getattr(record, "feedback_id", None)
        if not target_id:
            return

        processed = self._load_raw_records("processed_feedback.json")
        updated = False
        rec_dict = record.to_dict() if hasattr(record, "to_dict") else record

        for idx, item in enumerate(processed):
            if item.get("feedback_id") == target_id:
                processed[idx] = rec_dict
                updated = True
                break
        if not updated:
            processed.append(rec_dict)

        self.json_store.save(self._get_path("processed_feedback.json"), {"records": processed})

        remaining = [
            r for r in self._load_raw_records("feedback_before_ai.json")
            if r.get("feedback_id") != target_id
        ]
        self.save_pending(remaining)

    def search_records(self, query: str) -> List[Any]:
        records = self.load_records("processed_feedback.json")
        if not query.strip():
            return records
        terms = query.lower().split()
        results = []
        for record in records:
            rec_dict = record.to_dict() if hasattr(record, "to_dict") else record
            content = " ".join(str(val) for val in rec_dict.values()).lower()
            if all(term in content for term in terms):
                results.append(record)
        return results

    def save_review_queue(self, records: List[Any]) -> bool:
        filepath = self._get_path("for_review.json")
        payload = {"records": [r.to_dict() if hasattr(r, "to_dict") else r for r in records]}
        return self.json_store.save(filepath, payload)

    def load_review_queue(self) -> List[Any]:
        raw_list = self._load_raw_records("for_review.json")
        return self._to_records(raw_list)

    def save_invalid(self, invalid_records: List[Dict[str, Any]]) -> bool:
        filepath = self._get_path("invalid_records.json")
        return self.json_store.save(filepath, invalid_records)

    def save_object(self, name: str, obj: Any) -> bool:
        filename = f"{name}.json" if not name.endswith(".json") else name
        filepath = self._get_path(filename)
        if isinstance(obj, list):
            payload = [item.to_dict() if hasattr(item, "to_dict") else item for item in obj]
        elif hasattr(obj, "to_dict"):
            payload = obj.to_dict()
        else:
            payload = obj
        return self.json_store.save(filepath, payload)

    def load_object(self, name: str) -> Union[Dict[str, Any], List[Any], None]:
        filename = f"{name}.json" if not name.endswith(".json") else name
        filepath = self._get_path(filename)
        data = self.json_store.load(filepath)
        return data if data else None

    def append_history(self, run_at: str, source_file: Optional[str], result: Any) -> bool:
        filepath = self._get_path("aggregated_history.json")
        history = self.json_store.load(filepath)
        if not isinstance(history, list):
            history = []
        res_dict = result.to_dict() if hasattr(result, "to_dict") else result
        entry = {
            "run_at": run_at,
            "source_file": source_file,
            "result": res_dict,
        }
        history.insert(0, entry)
        return self.json_store.save(filepath, history)

    def load_previous_run(self) -> Optional[Dict[str, Any]]:
        filepath = self._get_path("aggregated_history.json")
        history = self.json_store.load(filepath)
        if isinstance(history, list) and len(history) > 0:
            return history[0]
        return None

    def load_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        filepath = self._get_path("aggregated_history.json")
        history = self.json_store.load(filepath)
        if not isinstance(history, list):
            return []
        if limit is not None:
            return history[:limit]
        return history

    def load_known_themes(self) -> List[str]:
        filepath = self._get_path("known_themes.json")
        data = self.json_store.load(filepath)
        confirmed = []
        if isinstance(data, dict) and "themes" in data:
            confirmed = data["themes"]
        elif isinstance(data, list):
            confirmed = data

        known = list(THEMES)
        for t in confirmed:
            if t not in known:
                known.append(t)
        return known

    def add_known_theme(self, name: str) -> bool:
        filepath = self._get_path("known_themes.json")
        data = self.json_store.load(filepath)

        themes_list = []
        if isinstance(data, dict) and "themes" in data:
            themes_list = data["themes"]
        elif isinstance(data, list):
            themes_list = data

        if name not in themes_list:
            themes_list.append(name)

        payload = {"themes": themes_list}
        return self.json_store.save(filepath, payload)

    def load_actions(self) -> List[Any]:
        raw_list = self._load_raw_records("actions.json")
        return self._to_actions(raw_list)

    def save_action(self, action: Any) -> bool:
        raw_actions = self._load_raw_records("actions.json")
        act_dict = action.to_dict() if hasattr(action, "to_dict") else action
        raw_actions.append(act_dict)
        filepath = self._get_path("actions.json")
        return self.json_store.save(filepath, {"records": raw_actions})

    def read_rows(self, path: Union[str, Path]) -> List[Dict[str, Any]]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Import file not found: {p}")
        ext = p.suffix.lower()
        store = self._importers.get(ext)
        if not store:
            raise ValueError(f"Unsupported file extension for import: {ext}")
        data = store.load(p)
        if isinstance(data, dict) and "records" in data:
            return data["records"]
        if isinstance(data, list):
            return data
        return [data] if isinstance(data, dict) else []

    def _token_log_path(self) -> Path:
        config_dir = Path(__file__).resolve().parents[1] / "config"
        return config_dir / "token-usage-log.json"

    def load_token_log(self) -> Optional[Dict[str, Any]]:
        """Loads token usage log; returns {} if missing/empty, None if corrupt."""
        filepath = self._token_log_path()
        if not filepath.exists() or filepath.stat().st_size == 0:
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logging.error("Corrupt token log at '%s': %s. Returning None safely.", filepath, e)
            return None  # Corrupt file returns None so it is never overwritten

    def load_prompts(self) -> tuple[str, str]:
        """Loads system and summary prompts from config/ with fallback supporting {themes}."""
        config_dir = Path(__file__).resolve().parents[1] / "config"
        prompt_path = config_dir / "system_prompt.txt"
        summary_path = config_dir / "summary_prompt.txt"

        sys_prompt = (
            prompt_path.read_text(encoding="utf-8")
            if prompt_path.exists()
            else "Analyze feedback accurately using known themes: {themes}."
        )
        sum_prompt = (
            summary_path.read_text(encoding="utf-8")
            if summary_path.exists()
            else "Summarize key themes."
        )
        return sys_prompt, sum_prompt

    def save_token_log(self, log: Dict[str, Any]) -> bool:
        filepath = self._token_log_path()
        if not log and filepath.exists() and filepath.stat().st_size > 0:
            logging.warning("Attempted to save empty token log over existing log. Skipped.")
            return False
        temp_path = filepath.with_name(filepath.name + ".tmp")
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
            temp_path.replace(filepath)
            return True
        except OSError as e:
            logging.error("Failed to write token log atomically to '%s': %s", filepath, e)
            return False
