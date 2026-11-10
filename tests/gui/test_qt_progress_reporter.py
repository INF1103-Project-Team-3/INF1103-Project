import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from managers.ai_manager import ProgressReporter  # noqa: E402
from managers.ai_manager.progress_tracker import ProgressTracker  # noqa: E402
from managers.gui import QtProgressReporter  # noqa: E402


def test_is_a_progress_reporter(qtbot):
    assert isinstance(QtProgressReporter(), ProgressReporter)


def test_record_ok_emits_counts_not_the_progress_object(qtbot):
    reporter = QtProgressReporter()
    tracker = ProgressTracker(3)
    tracker.start_record()
    tracker.finish_ok()
    progress = tracker.progress
    with qtbot.waitSignal(reporter.signals.record_ok, timeout=1000) as blocker:
        reporter.on_record_ok("st_001", "Facilities · negative · high", progress)
    assert blocker.args == ["st_001", "Facilities · negative · high", 1, 3]


def test_batch_end_allows_unknown_token_count(qtbot):
    reporter = QtProgressReporter()
    progress = ProgressTracker(2).progress
    with qtbot.waitSignal(reporter.signals.batch_finished, timeout=1000) as blocker:
        reporter.on_batch_end(progress, None, None)
    assert blocker.args == [0, 0, 2, None, None]


def test_wait_emits_seconds_and_reason(qtbot):
    reporter = QtProgressReporter()
    with qtbot.waitSignal(reporter.signals.waiting, timeout=1000) as blocker:
        reporter.on_wait(2, "rate limit")
    assert blocker.args == [2.0, "rate limit"]
