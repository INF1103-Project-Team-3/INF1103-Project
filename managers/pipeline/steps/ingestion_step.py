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
    description = "saving this session's changes"

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
                    if not self._data.delete_record(decision.feedback_id):
                        logger.warning("Delete of %s removed nothing: no store held it", decision.feedback_id)
                    existing_records.pop(decision.feedback_id, None)
                elif decision.action == ReviewDecision.UPDATE:
                    record = existing_records.get(decision.feedback_id)
                    if record is None:
                        logger.warning("Review skipped: no processed record %s", decision.feedback_id)
                        continue
                    theme = self._normalised(decision.theme)
                    try:
                        record.mark_reviewed(
                            theme,
                            decision.sentiment,
                            decision.severity,
                        )
                    except ValueError as error:   # bad value: skip this decision, keep the run going
                        logger.warning("Review of %s not applied: %s", decision.feedback_id, error)
                        continue
                    new_themes.append(theme)

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

    def _normalised(self, theme):
        """A decision's theme as Logic names it (D6, 7.4 step 1): an alias becomes its
        base theme, an unclear word becomes Unclear. Blank or non-text is passed on
        unchanged, so mark_reviewed rejects it as before."""
        if isinstance(theme, str) and theme.strip():
            return self._logic.normalise_theme(theme)
        return theme

    def _confirm_themes(self, themes: list[str]) -> None:
        """Save each theme Logic says is new, once, then refresh Logic and AI once
        (6, v1.8): data.add_known_theme(t), logic.set_known_themes(...),
        ai.set_known_themes(...). Aliases, known themes and Unclear are never saved."""
        added = []
        for theme in themes:
            name = self._normalised(theme)
            if isinstance(name, str) and name not in added and self._logic.is_new_theme(name):
                self._data.add_known_theme(name)
                added.append(name)
        if added:
            refreshed = self._data.load_known_themes()
            self._logic.set_known_themes(refreshed)
            self._ai.set_known_themes(refreshed)
