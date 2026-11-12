import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from managers.gui.pipeline_worker import PipelineWorker  # noqa: E402


class StubPipeline:
    def __init__(self, error=None):
        self.error = error
        self.sessions = []

    def execute_pipeline(self, session):
        self.sessions.append(session)
        if self.error:
            raise self.error
        return "context"


def test_completed_carries_the_context(qtbot):
    pipeline = StubPipeline()
    worker = PipelineWorker(pipeline, session="session")
    with qtbot.waitSignal(worker.completed, timeout=2000) as blocker:
        worker.start()
    worker.wait()
    assert blocker.args == ["context"]
    assert pipeline.sessions == ["session"]


def test_failed_reports_the_error_instead_of_crashing(qtbot):
    worker = PipelineWorker(StubPipeline(ValueError("bad data")), session=None)
    with qtbot.waitSignal(worker.failed, timeout=2000) as blocker:
        worker.start()
    worker.wait()
    assert blocker.args == ["ValueError: bad data"]
