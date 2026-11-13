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

    def __init__(self, ai: AIManager, logic: LogicManager) -> None:
        self._ai = ai
        self._logic = logic

    def _run(self, context: PipelineContext) -> bool:
        if context.result is None:
            return True

        ai_summary = None
        # D24: Skip Call 2 when Call 1 stopped early or classified nothing
        if not context.stopped and context.classified_count > 0:
            try:
                ai_summary = self._ai.summarise(context.result, context.records)
            except Exception:
                logger.exception("Call 2 failed; using the rule-based fallback")

        if ai_summary is not None:
            context.summary = ai_summary
            context.fallback_actions = None
        else:
            # D21: Rule-based keyword fallback whenever Call 2 is skipped or fails
            context.summary = None
            context.fallback_actions = self._fallback(context)
        return True

    def _fallback(self, context: PipelineContext):
        # logic.suggest_actions is "not built yet" in v1.9 (A24). Until it lands,
        # keep the last saved summary instead of crashing the run.
        suggest = getattr(self._logic, "suggest_actions", None)
        if suggest is None:
            logger.warning("logic.suggest_actions is not available yet (A24); "
                           "no fallback actions this run")
            return None
        return suggest(context.result, context.records)
