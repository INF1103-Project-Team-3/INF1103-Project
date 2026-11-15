# DataReader: the GUI's read-only view of DataManager, turning its plain dicts into objects.

import logging

from managers.ai_manager import AISummary
from managers.logic_manager import ActionSuggestions, AggregationResult, ImpactReport, TrendReport
from managers.models import Action, FeedbackRecord


# Wraps DataManager for the pages. Never writes: changes go through the pipeline.
# Accepts records and actions as objects (Data since #82) or as plain dicts.
class DataReader:
    def __init__(self, data):
        self.__data = data

    def load_records(self) -> list[FeedbackRecord]:
        return self.__records(self.__data.load_records())

    def load_pending(self) -> list[FeedbackRecord]:
        return self.__records(self.__data.load_pending())

    def load_review_queue(self) -> list[FeedbackRecord]:
        return self.__records(self.__data.load_review_queue())

    def search_records(self, query: str) -> list[FeedbackRecord]:
        return self.__records(self.__data.search_records(query))

    # The AI's token log, read only (G3): {} if none yet, None if unreadable.
    def load_token_log(self) -> dict | None:
        return self.__data.load_token_log()

    @property
    def data_folder(self) -> str:
        return str(getattr(self.__data, "data_dir", "") or "")

    def load_known_themes(self) -> list[str]:
        return list(self.__data.load_known_themes())

    def load_actions(self) -> list[Action]:
        actions = []
        for entry in self.__data.load_actions():
            try:
                actions.append(entry if isinstance(entry, Action) else Action.from_dict(entry))
            except (KeyError, ValueError, TypeError) as error:
                logging.warning("Skipped a corrupt action: %r", error)
        return actions

    # Part 2 runs, oldest first, in the shape the charts read: {"run": 1, "finished_at": "2026-11-10",
    # "theme_counts": {...}, "theme_priority": {...}}. Part 1 entries are skipped.
    def load_history(self) -> list[dict]:
        runs = []
        for entry in reversed(self.__data.load_history()):
            try:
                result = AggregationResult.from_dict(entry)
            except ValueError:
                continue
            runs.append({"run": len(runs) + 1, "finished_at": (result.run_at or "")[:10],
                         "theme_counts": {stats.theme: stats.count for stats in result.themes},
                         "theme_priority": {stats.theme: stats.priority for stats in result.themes}})
        return runs

    # Part 2 runs as AggregationResults, oldest first (same order as load_history), for compare_runs.
    def load_runs(self) -> list[AggregationResult]:
        runs = []
        for entry in reversed(self.__data.load_history()):
            try:
                runs.append(AggregationResult.from_dict(entry))
            except ValueError:
                continue
        return runs

    # The latest run's statistics, or None before the first run.
    def load_result(self) -> AggregationResult | None:
        return self.__object("aggregated_output", AggregationResult.from_dict)

    def load_trend(self) -> TrendReport | None:
        return self.__object("trend_output", TrendReport.from_dict)

    # The last AI summary that succeeded (Call 2 failing keeps the old one).
    def load_summary(self) -> AISummary | None:
        return self.__object("summary", AISummary.from_dict)

    # Rule-based actions saved when the AI's summary was skipped or failed (D21); the
    # pipeline saves [] when the summary succeeds, which reads as None here.
    def load_fallback_actions(self) -> ActionSuggestions | None:
        return self.__object("fallback_actions", ActionSuggestions.from_dict)

    def load_impacts(self) -> list[ImpactReport]:
        reports = []
        for entry in self.__data.load_object("impact_output") or []:
            try:
                reports.append(ImpactReport.from_dict(entry))
            except (KeyError, ValueError, TypeError) as error:
                logging.warning("Skipped an impact report that could not be read: %r", error)
        return reports

    def __object(self, name: str, build):
        entry = self.__data.load_object(name)
        if not entry:
            return None
        try:
            return build(entry)
        except (KeyError, ValueError, TypeError) as error:
            logging.warning("Could not read %s: %r", name, error)
            return None

    @staticmethod
    def __records(entries) -> list[FeedbackRecord]:
        records = []
        for entry in entries:
            try:
                records.append(entry if isinstance(entry, FeedbackRecord) else FeedbackRecord.from_dict(entry))
            except (KeyError, TypeError) as error:
                logging.warning("Skipped a record Data could not rebuild: %r", error)
        return records
