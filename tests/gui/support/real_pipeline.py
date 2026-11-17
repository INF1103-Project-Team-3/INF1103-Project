# Builds Zheng Yi's real PipelineManager the way AppEngine does, for GUI tests on real Data.

from managers.pipeline import PipelineManager
from managers.pipeline.steps import (
    AIClassificationStep, ImpactStep, IngestionStep, LogicStep, PersistenceStep, SummaryStep,
)


# The six steps in AppEngine's order, with the AI passed in (usually a StubAI).
def build_pipeline(data, logic, ai) -> PipelineManager:
    pipeline = PipelineManager(data_dir=str(data.data_dir))
    for step in (IngestionStep(data, logic, ai), AIClassificationStep(ai, data), LogicStep(logic, data),
                 SummaryStep(ai, logic), ImpactStep(logic, data), PersistenceStep(data)):
        pipeline.register_step(step)
    return pipeline
