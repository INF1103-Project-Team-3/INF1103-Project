# ProgressSignals: the Qt signals a QtProgressReporter emits.

from PySide6.QtCore import QObject, Signal


# One signal per ProgressReporter event.
class ProgressSignals(QObject):
    batch_started = Signal(str, int)
    attempt_started = Signal(str, int, int)
    attempt_failed = Signal(str, int, int, str)
    waiting = Signal(float, str)
    record_ok = Signal(str, str, int, int)
    record_failed = Signal(str, str, int, int)
    batch_stopped = Signal(str, int, int)
    batch_finished = Signal(int, int, int, object, object)
