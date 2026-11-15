from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..base_step import BaseStep

if TYPE_CHECKING:
    from managers.ai_manager import AIManager
    from managers.logic_manager import LogicManager
    from ..pipeline_context import PipelineContext


logger = logging.getLogger(__name__)


class SummaryStep(BaseStep):
    stop_on_error = False   # D20: Call 2 failing is acceptable; the run must still be saved
    description = "the AI summary"

    def __init__(self, ai: AIManager, logic: LogicManager, ai_ready: bool = True) -> None:
        self._ai = ai
        self._logic = logic
        self._ai_ready = ai_ready   # False when the API key or key label is missing

    def _run(self, context: PipelineContext) -> bool:
        if context.result is None:
            return True

        ai_working = self._ai_ready and not context.ai_stopped
        if ai_working and context.sent_to_ai == 0:
            # Nothing new reached the AI (e.g. a review-only run): skip Call 2 to save tokens
            # (D24) and keep the last AI summary, instead of rule-based "AI unavailable" actions
            return True

        ai_summary = None
        # D24: Call 2 only when Call 1 classified something
        if ai_working and context.classified_count > 0:
            try:
                ai_summary = self._ai.summarise(context.result, context.records)
            except Exception:
                logger.exception("Call 2 failed; using the rule-based fallback")

        if ai_summary is not None:
            context.summary = ai_summary
            context.fallback_actions = None
        else:
            # D21: Rule-based fallback only when the AI is down: no key, Call 1 stopped,
            # nothing sent could be classified, or Call 2 failed
            context.summary = None
            context.fallback_actions = self._logic.suggest_actions(context.result, context.records)
        return True
