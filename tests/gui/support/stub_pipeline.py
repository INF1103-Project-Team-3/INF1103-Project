# StubPipeline: a pipeline for MainWindow tests that records each session and saves nothing.

from types import SimpleNamespace


# execute_pipeline(session) keeps the session and returns an empty context.
class StubPipeline:
    def __init__(self):
        self.sessions = []

    def execute_pipeline(self, session):
        self.sessions.append(session)
        return SimpleNamespace(records=[], stopped=False)
