# Add feedback's Single entry and Import file tabs, and how MainWindow queues what they produce.

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QPushButton  # noqa: E402

from demo.fake_data_manager import FakeDataManager  # noqa: E402
from demo.sample_data import build_sample_records  # noqa: E402
from managers.gui.widgets.import_panel import ImportPanel  # noqa: E402
from managers.gui.widgets.single_entry_form import OTHER, SingleEntryForm  # noqa: E402
from managers.io_manager import (  # noqa: E402
    CsvImporter, EntryValidator, JsonImporter, RecordBuilder, ThemeValidator,
)
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import THEMES  # noqa: E402

HEADER = "feedback_id,text,timestamp,theme,sentiment,severity\n"


def button(widget, text):
    return [b for b in widget.findChildren(QPushButton) if b.text().startswith(text)][0]


def validator():
    return EntryValidator(ThemeValidator(LogicManager()))


def single_form(qtbot):
    form = SingleEntryForm(validator(), RecordBuilder())
    form.set_themes(list(THEMES))
    qtbot.addWidget(form)
    return form


def fill(form, text, theme, sentiment="negative", severity="medium", other=""):
    form.findChild(QPlainTextEdit, "entryTextBox").setPlainText(text)
    if theme == OTHER:
        form.theme_picker.type_other(other)
    else:
        form.theme_picker.choose(theme)
    for name, value in (("entrySentiment", sentiment), ("entrySeverity", severity)):
        box = [w for w in form.findChildren(object) if w.objectName() == name][0]
        box.setCurrentText(value)


def test_single_entry_rejects_an_incomplete_entry(qtbot):
    form = single_form(qtbot)
    with qtbot.assertNotEmitted(form.record_added):
        button(form, "Add to queue").click()
    assert "missing field(s): text" in form.findChild(QLabel, "errorText").text()


def test_single_entry_builds_a_record(qtbot):
    form = single_form(qtbot)
    fill(form, "The lab printers jam every week", "Facilities")
    with qtbot.waitSignal(form.record_added, timeout=1000) as blocker:
        button(form, "Add to queue").click()
    record = blocker.args[0]
    assert record.user == {"theme": "Facilities", "sentiment": "negative", "severity": "medium"}
    assert record.source_file == "admin entry" and record.ai is None


def test_other_theme_goes_through_the_theme_validator(qtbot):
    form = single_form(qtbot)
    fill(form, "Parking costs too much", OTHER, other="  parking fees ")
    assert form.findChild(QLineEdit, "entryThemeOther").isVisibleTo(form)
    with qtbot.waitSignal(form.record_added, timeout=1000) as blocker:
        button(form, "Add to queue").click()
    assert blocker.args[0].user["theme"] == "Parking Fees"


def import_panel(qtbot, data):
    check, builder = validator(), RecordBuilder()
    panel = ImportPanel([CsvImporter(data, check, builder), JsonImporter(data, check, builder)], data)
    qtbot.addWidget(panel)
    return panel


def test_import_previews_rejected_rows_and_skips_saved_ids(qtbot, tmp_path):
    data = FakeDataManager(build_sample_records())
    saved_id = data.load_records()[0].feedback_id
    path = tmp_path / "week6.csv"
    path.write_text(HEADER
                    + "new_001,Wifi drops in the lab,2026-11-10T09:00:00,Facilities,negative,medium\n"
                    + "new_002,No severity here,2026-11-10T09:05:00,Workload,negative,\n"
                    + f"{saved_id},Already in the store,2026-11-10T09:10:00,Facilities,negative,low\n",
                    encoding="utf-8")
    panel = import_panel(qtbot, data)
    panel.load_file(str(path))
    summary = panel.findChild(QLabel, "cardTitle").text()
    assert "week6.csv: 3 rows" in summary and "1 ready" in summary
    assert "1 rejected" in summary and "1 already saved" in summary
    assert "Row 2: missing field(s): severity" in panel.findChild(QLabel, "reasonList").text()
    with qtbot.waitSignal(panel.import_ready, timeout=1000) as blocker:
        button(panel, "Add 1 entry").click()
    result = blocker.args[0]
    assert [r.feedback_id for r in result.records] == ["new_001"] and result.source_file == "week6.csv"


def test_import_explains_an_unsupported_file(qtbot, tmp_path):
    panel = import_panel(qtbot, FakeDataManager([]))
    panel.load_file(str(tmp_path / "notes.txt"))
    assert "Only .csv and .json" in panel.findChild(QLabel, "errorText").text()
    assert not button(panel, "Add to queue").isEnabled()


def test_main_window_sends_imported_entries_with_their_source_file(qtbot, tmp_path):
    from demo.fake_pipeline import FakePipeline
    from demo.sample_data import load_ai_answers
    from managers.gui import MainWindow, QtProgressReporter
    data = FakeDataManager(build_sample_records())
    reporter = QtProgressReporter()
    check, builder = validator(), RecordBuilder()
    window = MainWindow(FakePipeline(reporter, data, load_ai_answers()), data, LogicManager(), check,
                        [CsvImporter(data, check, builder)], reporter)
    qtbot.addWidget(window)
    path = tmp_path / "week6.csv"
    path.write_text(HEADER + "new_001,Wifi drops in the lab,2026-11-10T09:00:00,Facilities,negative,medium\n",
                    encoding="utf-8")
    page = [w for w in window.findChildren(ImportPanel)][0]
    page.load_file(str(path))
    button(page, "Add 1 entry").click()
    session = window._MainWindow__build_session()
    assert [r.feedback_id for r in session.records] == ["new_001"] and session.source_file == "week6.csv"
