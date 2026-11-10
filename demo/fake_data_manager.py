# FakeDataManager: in-memory stand-in for DataManager, for the GUI demo and tests.

import threading

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

    def save_action(self, action: Action) -> None:
        with self.__lock:
            self.__actions.append(action)
