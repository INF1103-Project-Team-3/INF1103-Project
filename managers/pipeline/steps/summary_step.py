from __future__ import annotations

from typing import TYPE_CHECKING

from ..base_step import BaseStep

if TYPE_CHECKING:
    from managers.ai_manager import AIManager
    from managers.logic_manager import LogicManager
    from ..pipeline_context import PipelineContext


class SummaryStep(BaseStep):
    def __init__(self, ai: AIManager, logic: LogicManager) -> None:
        self._ai = ai
        self._logic = logic

    def _run(self, context: PipelineContext) -> bool:
        if context.result is None:
            return True

        ai_summary = None
        # D24: Skip Call 2 when Call 1 stopped early or classified nothing
        if not context.stopped and context.classified_count > 0:
            ai_summary = self._ai.summarise(context.result, context.records)

        if ai_summary is not None:
            context.summary = ai_summary
            context.fallback_actions = None
        else:
            # D21: Rule-based keyword fallback whenever Call 2 is skipped or fails
            context.summary = None
            context.fallback_actions = self._logic.suggest_actions(
                context.result,
                context.records,
            )
        return True
