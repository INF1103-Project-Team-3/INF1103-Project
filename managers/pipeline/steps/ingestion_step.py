from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from managers.io_manager import ReviewDecision
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

        if session is not None:
            # Themes to confirm: new themes from Settings, plus any a review keeps (D16)
            new_themes = list(session.themes_to_add)

            for decision in session.decisions:
                if decision.action == ReviewDecision.DELETE:
                    self._data.delete_record(decision.feedback_id)
                    existing_records.pop(decision.feedback_id, None)
                elif decision.action == ReviewDecision.UPDATE:
                    record = existing_records.get(decision.feedback_id)
                    if record is None:
                        logger.warning("Review skipped: no processed record %s", decision.feedback_id)
                        continue
                    try:
                        record.mark_reviewed(
                            decision.theme,
                            decision.sentiment,
                            decision.severity,
                        )
                    except ValueError as error:   # bad value: skip this decision, keep the run going
                        logger.warning("Review of %s not applied: %s", decision.feedback_id, error)
                        continue
                    if decision.theme:
                        new_themes.append(decision.theme)

            self._confirm_themes(new_themes)

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

    def _confirm_themes(self, themes: list[str]) -> None:
        """Save each theme not yet known, then refresh Logic and AI once (6, v1.8):
        data.add_known_theme(t), logic.set_known_themes(...), ai.set_known_themes(...)."""
        known = set(self._data.load_known_themes())
        added = False
        for theme in themes:
            if theme not in known:
                self._data.add_known_theme(theme)
                known.add(theme)
                added = True
        if added:
            refreshed = self._data.load_known_themes()
            self._logic.set_known_themes(refreshed)
            self._ai.set_known_themes(refreshed)
