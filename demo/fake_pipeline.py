# FakePipeline: stand-in for PipelineManager in the GUI demo.

import time
from datetime import date
from types import SimpleNamespace

from managers.ai_manager import ProgressReporter
from managers.ai_manager.progress_tracker import ProgressTracker
from managers.io_manager import ReviewDecision, SessionResult
from managers.logic_manager import LogicManager

STEP_SECONDS = 0.8
RATE_LIMITED_ID = "st_010"


# Applies the session, fakes the AI, then runs the real LogicManager rules.
class FakePipeline:
    def __init__(self, reporter: ProgressReporter, data, ai_answers: dict[str, tuple[str, str, str]],
                 logic: LogicManager | None = None):
        self.__reporter = reporter
        self.__data = data
        self.__answers = ai_answers
        self.__logic = logic or LogicManager()

    def execute_pipeline(self, session: SessionResult):
        for decision in session.decisions:
            if decision.action == ReviewDecision.DELETE:
                self.__data.delete_record(decision.feedback_id)
            else:
                record = self.__data.get_record(decision.feedback_id)
                if record is not None:
                    record.mark_reviewed(decision.theme, decision.sentiment, decision.severity)
        for action in session.actions:
            self.__data.save_action(action)
        for record in session.records:
            self.__data.add_record(record)

        pending = self.__data.load_pending()
        tracker = ProgressTracker(len(pending))
        progress = tracker.progress
        self.__reporter.on_batch_start("Classifying pending feedback (demo)", ["no API calls"], progress)
        for record in pending:
            request_id = record.feedback_id
            tracker.start_record()
            self.__reporter.on_attempt_start(request_id, 1, 3)
            time.sleep(STEP_SECONDS)
            if request_id == RATE_LIMITED_ID:
                tracker.add_retry()
                self.__reporter.on_attempt_failed(request_id, 1, 3, "429 rate limit")
                self.__reporter.on_wait(2.0, "rate limit")
                time.sleep(2.0)
                self.__reporter.on_attempt_start(request_id, 2, 3)
                time.sleep(STEP_SECONDS)
            user = record.user
            theme, sentiment, severity = self.__answers.get(
                request_id, (user["theme"], user["sentiment"], user["severity"]))
            record.set_ai(theme, sentiment, severity)
            tracker.add_tokens(1400)
            tracker.finish_ok()
            self.__reporter.on_record_ok(request_id, f"{theme} · {sentiment} · {severity}", progress)
        self.__reporter.on_batch_end(progress, None, None)
        self.__logic.apply_rules(self.__data.load_records())
        self.__save_run(pending)
        return SimpleNamespace(records=self.__data.load_records(), stopped=False)

    # A history row with every stored record's totals and priority, as the real history keeps.
    def __save_run(self, records) -> None:
        if not records:
            return
        result = self.__logic.aggregate(self.__data.load_records())
        history = self.__data.load_history()
        self.__data.save_history({"run": len(history) + 1, "finished_at": date.today().isoformat(),
                                  "theme_counts": {stats.theme: stats.count for stats in result.themes},
                                  "theme_priority": {stats.theme: stats.priority for stats in result.themes}})
