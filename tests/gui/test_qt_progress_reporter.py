import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from managers.ai_manager import BatchProgress, ProgressReporter  # noqa: E402
from managers.gui import QtProgressReporter  # noqa: E402


def test_is_a_progress_reporter(qtbot):
    assert isinstance(QtProgressReporter(), ProgressReporter)


def test_record_ok_emits_counts_not_the_progress_object(qtbot):
    reporter = QtProgressReporter()
    progress = BatchProgress(total=3)
    progress.start_record()
    progress.finish_ok()
    with qtbot.waitSignal(reporter.signals.record_ok, timeout=1000) as blocker:
        reporter.on_record_ok("st_001", "Facilities · negative · high", progress)
    assert blocker.args == ["st_001", "Facilities · negative · high", 1, 3]


def test_batch_end_allows_unknown_token_count(qtbot):
    reporter = QtProgressReporter()
    progress = BatchProgress(total=2)
    with qtbot.waitSignal(reporter.signals.batch_finished, timeout=1000) as blocker:
        reporter.on_batch_end(progress, None, None)
    assert blocker.args == [0, 0, 2, None, None]


def test_wait_emits_seconds_and_reason(qtbot):
    reporter = QtProgressReporter()
    with qtbot.waitSignal(reporter.signals.waiting, timeout=1000) as blocker:
        reporter.on_wait(2, "rate limit")
    assert blocker.args == [2.0, "rate limit"]
