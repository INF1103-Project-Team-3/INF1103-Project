# PipelineWorker: runs one pipeline run off the GUI thread.

from PySide6.QtCore import QThread, Signal


# Runs pipeline.execute_pipeline(session) on its own thread.
class PipelineWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline, session, parent=None):
        super().__init__(parent)
        self.__pipeline = pipeline
        self.__session = session

    def run(self) -> None:
        try:
            context = self.__pipeline.execute_pipeline(self.__session)
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.completed.emit(context)
