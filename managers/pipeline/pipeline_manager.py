from __future__ import annotations

from typing import TYPE_CHECKING

from .pipeline_context import PipelineContext

if TYPE_CHECKING:
    from managers.io_manager import SessionResult
    from .pipeline_step import PipelineStep


class PipelineManager:
    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self._steps: list[PipelineStep] = []
        self._current_step: PipelineStep | None = None

    @property
    def current_step(self) -> PipelineStep | None:
        """The step running now, or the one that raised if a run failed; None after a run ends."""
        return self._current_step

    def register_step(self, step: PipelineStep) -> None:
        self._steps.append(step)

    def execute_pipeline(self, session: SessionResult | None = None) -> PipelineContext:
        context = PipelineContext(data_dir=self._data_dir, session=session)
        for step in self._steps:
            self._current_step = step
            if not step.execute(context):
                context.halted = True
                break
        self._current_step = None
        return context
