from __future__ import annotations

from typing import TYPE_CHECKING

from managers.models import PENDING, UNVERIFIED
from ..base_step import BaseStep

if TYPE_CHECKING:
    from managers.ai_manager import AIManager
    from managers.data_manager import DataManager
    from ..pipeline_context import PipelineContext


class AIClassificationStep(BaseStep):
    def __init__(self, ai: AIManager, data: DataManager) -> None:
        self._ai = ai
        self._data = data

    def _run(self, context: PipelineContext) -> bool:
        to_classify = [
            r for r in context.records
            if r.ai is None and r.verification in (PENDING, UNVERIFIED)   # rule 6: constants, not strings
        ]
        stored_records = [r for r in context.records if r.ai is not None]

        if not to_classify:
            context.classified_count = 0
            return True

        classified, _pending, stopped = self._ai.classify_entries(
            to_classify,
            stored_records,
            on_classified=self._data.update_pending,
        )
        context.classified_count = len(classified)
        context.stopped = stopped
        # D20 / C36: Always continue to LogicStep even if AI is down or classified nothing
        return True
