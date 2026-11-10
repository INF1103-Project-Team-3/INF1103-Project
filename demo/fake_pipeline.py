# FakePipeline: stand-in for PipelineManager in the GUI demo.

import time
from datetime import date
from types import SimpleNamespace

from managers.ai_manager import BatchProgress, ProgressReporter

from .sample_data import fake_check

STEP_SECONDS = 0.8
RATE_LIMITED_ID = "st_010"


class FakePipeline:
    def __init__(self, reporter: ProgressReporter, data, ai_answers: dict[str, tuple[str, str, str]]):
        self.__reporter = reporter
        self.__data = data
        self.__answers = ai_answers

    def execute_pipeline(self, session):
        for decision in session.decisions:
            if decision.action == "delete":
                self.__data.delete_record(decision.feedback_id)
            else:
                record = self.__data.get_record(decision.feedback_id)
                if record is not None:
                    record.mark_reviewed(*decision.values)
        for action in session.actions:
            self.__data.save_action(action)
        for record in session.records:
            self.__data.add_record(record)

        pending = self.__data.load_pending()
        progress = BatchProgress(len(pending))
        self.__reporter.on_batch_start("Classifying pending feedback (demo)", ["no API calls"], progress)
        for record in pending:
            request_id = record.feedback_id
            progress.start_record()
            self.__reporter.on_attempt_start(request_id, 1, 3)
            time.sleep(STEP_SECONDS)
            if request_id == RATE_LIMITED_ID:
                progress.add_retry()
                self.__reporter.on_attempt_failed(request_id, 1, 3, "429 rate limit")
                self.__reporter.on_wait(2.0, "rate limit")
                time.sleep(2.0)
                self.__reporter.on_attempt_start(request_id, 2, 3)
                time.sleep(STEP_SECONDS)
            user = record.user
            theme, sentiment, severity = self.__answers.get(
                request_id, (user["theme"], user["sentiment"], user["severity"]))
            record.set_ai(theme, sentiment, severity)
            fake_check(record)
            progress.add_tokens(1400)
            progress.finish_ok()
            self.__reporter.on_record_ok(request_id, f"{theme} · {sentiment} · {severity}", progress)
        self.__reporter.on_batch_end(progress, None, None)
        self.__save_run(pending)
        return SimpleNamespace(records=self.__data.load_records(), stopped=False)

    def __save_run(self, records) -> None:
        if not records:
            return
        counts = {}
        for record in records:
            theme = record.theme or record.ai["theme"]
            counts[theme] = counts.get(theme, 0) + 1
        history = self.__data.load_history()
        self.__data.save_history({"run": len(history) + 1, "finished_at": date.today().isoformat(),
                                  "theme_counts": counts})
