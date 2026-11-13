# FakeDataManager: in-memory stand-in for DataManager, for the GUI demo and tests.

import csv
import json
import threading
from datetime import date
from pathlib import Path

from managers.logic_manager import LogicManager
from managers.models import CRITICAL, THEMES, Action, FeedbackRecord


class FakeDataManager:
    def __init__(self, records: list[FeedbackRecord], actions: list[Action] | None = None,
                 history: list[dict] | None = None):
        self.__records = {r.feedback_id: r for r in records}
        self.__actions = list(actions or [])
        self.__history = list(history or [])
        self.__lock = threading.Lock()

    # Every record the AI has seen (pending ones are listed by load_pending).
    def load_records(self) -> list[FeedbackRecord]:
        with self.__lock:
            return [r for r in self.__records.values() if r.ai is not None]

    def load_pending(self) -> list[FeedbackRecord]:
        with self.__lock:
            return [r for r in self.__records.values() if r.ai is None]

    # Flagged records, critical first.
    def load_review_queue(self) -> list[FeedbackRecord]:
        flagged = [r for r in self.load_records() if r.needs_review]
        return sorted(flagged, key=lambda r: not any("Critical" in reason for reason in r.review_reasons)
                      and (r.ai or {}).get("severity") != CRITICAL)

    def search_records(self, query: str) -> list[FeedbackRecord]:
        terms = query.lower().split()
        found = []
        for record in self.load_records():
            haystack = " ".join([record.text, record.user.get("theme", ""),
                                 (record.ai or {}).get("theme", ""), record.theme or ""]).lower()
            if all(term in haystack for term in terms):
                found.append(record)
        return found

    def load_known_themes(self) -> list[str]:
        return list(THEMES)

    def load_actions(self) -> list[Action]:
        with self.__lock:
            return list(self.__actions)

    def load_history(self) -> list[dict]:
        with self.__lock:
            return [dict(run) for run in self.__history]

    # What DataReader gives the dashboard and charts, worked out live from the sample records.
    def load_result(self):
        return LogicManager().aggregate(self.load_records())

    def load_trend(self):
        return None

    def load_summary(self):
        return None

    def load_impacts(self):
        return LogicManager().evaluate_actions(self.load_actions(), self.load_records(), date.today())

    def add_record(self, record: FeedbackRecord) -> None:
        with self.__lock:
            self.__records[record.feedback_id] = record

    def save_history(self, run: dict) -> None:
        with self.__lock:
            self.__history.append(run)

    def delete_record(self, feedback_id: str) -> None:
        with self.__lock:
            self.__records.pop(feedback_id, None)

    def get_record(self, feedback_id: str) -> FeedbackRecord | None:
        with self.__lock:
            return self.__records.get(feedback_id)

    # An import file's rows, as DataManager.read_rows gives them.
    def read_rows(self, path) -> list[dict]:
        path = Path(path)
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                return list(csv.DictReader(handle))
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["records"] if isinstance(data, dict) and "records" in data else list(data)

    def save_action(self, action: Action) -> None:
        with self.__lock:
            self.__actions.append(action)
