from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline_context import PipelineContext


class PipelineStep(ABC):
    @abstractmethod
    def execute(self, context: PipelineContext) -> bool:
        """Execute the pipeline step and return True if the pipeline should continue."""
