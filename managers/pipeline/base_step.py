from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING

from .pipeline_step import PipelineStep

if TYPE_CHECKING:
    from .pipeline_context import PipelineContext

logger = logging.getLogger(__name__)


class BaseStep(PipelineStep):
    def execute(self, context: PipelineContext) -> bool:
        step_name = self.__class__.__name__
        logger.info("Starting %s", step_name)
        try:
            should_continue = self._run(context)
            logger.info("Finished %s (continue=%s)", step_name, should_continue)
            return should_continue
        except Exception:
            logger.exception("Error executing %s", step_name)
            raise

    @abstractmethod
    def _run(self, context: PipelineContext) -> bool:
        """Internal step logic implemented by subclasses."""
