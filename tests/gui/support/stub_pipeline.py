# StubPipeline: a pipeline for MainWindow tests that records each session and saves nothing.

from types import SimpleNamespace


# execute_pipeline(session) keeps the session and returns the given context, or an empty one
# with the fields MainWindow reads after a run.
class StubPipeline:
    def __init__(self, context=None):
        self.sessions = []
        self.__context = context

    def execute_pipeline(self, session):
        self.sessions.append(session)
        if self.__context is not None:
            return self.__context
        return SimpleNamespace(records=[], halted=False, ai_stopped=False, sent_to_ai=0, classified_count=0)
