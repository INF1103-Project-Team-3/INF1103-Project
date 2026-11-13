from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from managers.models import TIMESTAMP_FORMAT
from ..base_step import BaseStep

if TYPE_CHECKING:
    from managers.data_manager import DataManager
    from ..pipeline_context import PipelineContext


class PersistenceStep(BaseStep):
    def __init__(self, data: DataManager) -> None:
        self._data = data

    def _run(self, context: PipelineContext) -> bool:
        self._data.save_records(context.records)
        self._data.save_invalid(context.invalid_records)
        self._data.save_review_queue(context.review_queue)

        if context.result is not None:
            self._data.save_object("aggregated_output", context.result)
            source_file = context.session.source_file if context.session else None
            run_at = datetime.now().strftime(TIMESTAMP_FORMAT)
            self._data.append_history(run_at, source_file, context.result)

        if context.trend is not None:
            self._data.save_object("trend_output", context.trend)

        if context.summary is not None:
            self._data.save_object("summary", context.summary)
            # Clear fallback actions when Call 2 succeeds
            self._data.save_object("fallback_actions", [])
        elif context.fallback_actions is not None:
            self._data.save_object("fallback_actions", context.fallback_actions)

        self._data.save_object("impact_output", context.impacts)
        return True
