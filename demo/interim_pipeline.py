# InterimPipeline: a stand-in for Zheng Yi's PipelineManager that runs section 6's steps on the real parts.

import logging
from datetime import date, datetime
from types import SimpleNamespace

from managers.io_manager import ReviewDecision, SessionResult
from managers.logic_manager import AggregationResult
from managers.models import REVIEWED, TIMESTAMP_FORMAT, UNCLEAR_THEME, Action, FeedbackRecord


# Runs ingestion, AI, Logic, summary, impact and persistence. ai=None is an AI-down run.
# clock dates the history entry and today is the impact date (both swappable for seeding).
# Delete this once the real pipeline lands.
class InterimPipeline:
    def __init__(self, data, logic, ai=None, today=date.today, clock=datetime.now):
        self.__data = data
        self.__logic = logic
        self.__ai = ai
        self.__today = today
        self.__clock = clock

    def execute_pipeline(self, session: SessionResult) -> SimpleNamespace:
        stored = self.__load_stored()
        self.__ingest(session, stored)
        classified, stopped = self.__classify(stored)

        valid, invalid = self.__logic.validate(list(stored.values()))
        self.__logic.apply_rules(valid)
        queue = self.__logic.review_queue(valid)
        result = self.__logic.aggregate(valid)
        trend = self.__logic.compare_runs(result, self.__previous_run())

        summary = None
        if self.__ai is not None and classified and not stopped:
            summary = self.__ai.summarise(result, valid)
        impacts = self.__logic.evaluate_actions(self.__load_actions(), valid, self.__today())

        self.__persist(session, valid, invalid, queue, result, trend, summary, impacts)
        return SimpleNamespace(data_dir=str(getattr(self.__data, "data_dir", "")), session=session,
                               records=valid, result=result, trend=trend, summary=summary,
                               impacts=impacts, stopped=stopped)

    # Every stored record by ID: processed ones, then any still pending.
    def __load_stored(self) -> dict[str, FeedbackRecord]:
        stored = {}
        for entry in [*self.__data.load_records(), *self.__data.load_pending()]:
            try:
                record = FeedbackRecord.from_dict(entry)
            except (KeyError, TypeError) as error:
                logging.warning("Skipped a stored record that could not be rebuilt: %r", error)
                continue
            stored.setdefault(record.feedback_id, record)
        return stored

    # Step 2: decisions (an update to an unknown theme confirms it), actions, then new records.
    def __ingest(self, session: SessionResult, stored: dict[str, FeedbackRecord]) -> None:
        for decision in session.decisions:
            if decision.action == ReviewDecision.DELETE:
                self.__data.delete_record(decision.feedback_id)
                stored.pop(decision.feedback_id, None)
                continue
            record = stored.get(decision.feedback_id)
            if record is None:
                logging.warning("Review decision for unknown record %s skipped", decision.feedback_id)
                continue
            self.__confirm_theme(decision.theme)
            record.mark_reviewed(decision.theme, decision.sentiment, decision.severity)
        for action in session.actions:
            self.__data.save_action(action)
        new = [record for record in session.records if record.feedback_id not in stored]
        if new:
            self.__data.add_pending(new)
            stored.update({record.feedback_id: record for record in new})

    def __confirm_theme(self, theme: str) -> None:
        known = self.__data.load_known_themes()
        if theme in known or theme == UNCLEAR_THEME:
            return
        self.__data.add_known_theme(theme)
        known = self.__data.load_known_themes()
        self.__logic.set_known_themes(known)
        if self.__ai is not None:
            self.__ai.set_known_themes(known)

    # Step 3: new and unverified records go to the AI. Returns (classified, stopped).
    def __classify(self, stored: dict[str, FeedbackRecord]) -> tuple[list, bool]:
        to_send = [r for r in stored.values() if r.ai is None and r.verification != REVIEWED]
        if not to_send:
            return [], False
        if self.__ai is None:
            return [], True
        seen = [r for r in stored.values() if r.ai is not None]
        classified, _pending, stopped = self.__ai.classify_entries(to_send, seen, self.__data.update_pending)
        return classified, stopped

    def __previous_run(self) -> AggregationResult | None:
        entry = self.__data.load_previous_run()
        if entry is None:
            return None
        try:
            return AggregationResult.from_dict(entry)
        except ValueError:
            return None

    def __load_actions(self) -> list[Action]:
        actions = []
        for entry in self.__data.load_actions():
            try:
                actions.append(Action.from_dict(entry))
            except (KeyError, ValueError, TypeError) as error:
                logging.warning("Skipped a corrupt action: %r", error)
        return actions

    # Step 7: save everything. Every record is now in the processed file (unverified ones
    # included), so pending is emptied. A failed or skipped summary keeps the last one.
    def __persist(self, session, valid, invalid, queue, result, trend, summary, impacts) -> None:
        data = self.__data
        data.save_records(valid)
        data.save_pending([])
        data.save_invalid([{**record.to_dict(), "problems": problems} for record, problems in invalid])
        data.save_review_queue(queue)
        data.save_object("aggregated_output", result)
        data.save_object("trend_output", trend)
        data.append_history(self.__clock().strftime(TIMESTAMP_FORMAT), session.source_file, result)
        if summary is not None:
            data.save_object("summary", summary)
        data.save_object("impact_output", impacts)
