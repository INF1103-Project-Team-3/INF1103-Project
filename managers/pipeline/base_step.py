from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING

from .pipeline_step import PipelineStep

if TYPE_CHECKING:
    from .pipeline_context import PipelineContext

logger = logging.getLogger(__name__)


class BaseStep(PipelineStep):
    # True: an error stops the run (nothing half-finished is saved).
    # Steps whose failure must not block saving the run (Summary, Impact) set this to False (D20).
    stop_on_error = True

    def execute(self, context: PipelineContext) -> bool:
        step_name = self.__class__.__name__
        logger.info("Starting %s", step_name)
        try:
            should_continue = self._run(context)
            logger.info("Finished %s (continue=%s)", step_name, should_continue)
            return should_continue
        except Exception:
            logger.exception("Error executing %s", step_name)
            if self.stop_on_error:
                raise
            return True     # carry on to the next step

    @abstractmethod
    def _run(self, context: PipelineContext) -> bool:
        """Internal step logic implemented by subclasses."""
