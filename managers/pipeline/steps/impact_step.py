from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from managers.models import Action
from ..base_step import BaseStep

if TYPE_CHECKING:
    from managers.data_manager import DataManager
    from managers.logic_manager import LogicManager
    from ..pipeline_context import PipelineContext


class ImpactStep(BaseStep):
    stop_on_error = False   # impact is extra; a failure here must not block saving the run

    def __init__(self, logic: LogicManager, data: DataManager) -> None:
        self._logic = logic
        self._data = data

    def _run(self, context: PipelineContext) -> bool:
        actions = self._rebuild_all(self._data.load_actions(), Action)
        context.impacts = self._logic.evaluate_actions(
            actions,
            context.records,
            date.today(),
        )
        return True
