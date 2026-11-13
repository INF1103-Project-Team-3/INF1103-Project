from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..base_step import BaseStep

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from managers.ai_manager import AIManager
    from managers.data_manager import DataManager
    from managers.logic_manager import LogicManager
    from ..pipeline_context import PipelineContext


class IngestionStep(BaseStep):
    def __init__(
        self,
        data: DataManager,
        logic: LogicManager,
        ai: AIManager,
    ) -> None:
        self._data = data
        self._logic = logic
        self._ai = ai

    def _run(self, context: PipelineContext) -> bool:
        session = context.session
        existing_records = {r.feedback_id: r for r in self._data.load_records()}
        known_themes = set(self._data.load_known_themes())
        themes_updated = False

        if session is not None:
            for decision in session.decisions:
                if decision.action == "delete":
                    self._data.delete_record(decision.feedback_id)
                    existing_records.pop(decision.feedback_id, None)
                elif decision.action == "update":
                    record = existing_records.get(decision.feedback_id)
                    if record is None:
                        logger.warning("Review skipped: no processed record %s", decision.feedback_id)
                    else:
                        try:
                            record.mark_reviewed(
                                decision.theme,
                                decision.sentiment,
                                decision.severity,
                            )
                        except ValueError as error:   # bad value: skip this decision, keep the run going
                            logger.warning("Review of %s not applied: %s", decision.feedback_id, error)
                            continue
                        if decision.theme and decision.theme not in known_themes:
                            self._data.add_known_theme(decision.theme)
                            known_themes.add(decision.theme)
                            themes_updated = True

            if themes_updated:
                refreshed_themes = self._data.load_known_themes()
                self._logic.set_known_themes(refreshed_themes)
                self._ai.set_known_themes(refreshed_themes)

            for action in session.actions:
                self._data.save_action(action)

            if session.records:
                self._data.add_pending(session.records)

        if existing_records:
            self._data.save_records(list(existing_records.values()))

        pending = self._data.load_pending()
        processed = self._data.load_records()
        context.records = processed + pending
        return True
