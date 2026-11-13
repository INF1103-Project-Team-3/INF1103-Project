from __future__ import annotations

from typing import TYPE_CHECKING

from managers.logic_manager import AggregationResult
from ..base_step import BaseStep

if TYPE_CHECKING:
    from managers.data_manager import DataManager
    from managers.logic_manager import LogicManager
    from ..pipeline_context import PipelineContext


class LogicStep(BaseStep):
    def __init__(self, logic: LogicManager, data: DataManager) -> None:
        self._logic = logic
        self._data = data

    def _run(self, context: PipelineContext) -> bool:
        valid, invalid = self._logic.validate(context.records)
        checked = self._logic.apply_rules(valid)
        queue = self._logic.review_queue(checked)
        result = self._logic.aggregate(checked)

        previous_raw = self._data.load_previous_run()
        previous = None
        if previous_raw is not None:
            try:
                previous = AggregationResult.from_dict(previous_raw)
            except ValueError:
                previous = None

        trend = self._logic.compare_runs(result, previous)

        context.records = checked
        context.invalid_records = invalid
        context.review_queue = queue
        context.result = result
        context.trend = trend
        return True
