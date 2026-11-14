"""FeedbackImporter and its CsvImporter and JsonImporter subclasses.

Rows come from FakeData.read_rows(), so no real file is ever opened.
"""
from datetime import datetime

import pytest

from managers.io_manager.csv_importer import CsvImporter
from managers.io_manager.entry_validator import EntryValidator
from managers.io_manager.feedback_importer import FeedbackImporter
from managers.io_manager.json_importer import JsonImporter
from managers.io_manager.record_builder import RecordBuilder
from managers.io_manager.theme_validator import ThemeValidator

GOOD = {"feedback_id": "a1", "text": "Wifi keeps dropping", "timestamp": "2026-10-01T09:00:00",
        "theme": "Facilities", "sentiment": "negative", "severity": "high"}


@pytest.fixture
def importers(data, logic):
    validator = EntryValidator(ThemeValidator(logic))
    builder = RecordBuilder(clock=lambda: datetime(2026, 11, 9))
    return [CsvImporter(data, validator, builder), JsonImporter(data, validator, builder)]


def test_the_base_class_is_abstract(data, logic):
    with pytest.raises(TypeError):
        FeedbackImporter(data, EntryValidator(ThemeValidator(logic)), RecordBuilder())


@pytest.mark.parametrize("path, expected", [("week5.csv", CsvImporter), ("WEEK5.CSV", CsvImporter),
                                            ("data/in.json", JsonImporter), ("notes.txt", None)])
def test_the_right_importer_is_chosen_from_the_file_type(importers, path, expected):
    chosen = FeedbackImporter.select(importers, path)
    assert type(chosen) is expected if expected else chosen is None


def test_import_builds_records_and_reports_rejected_rows(importers, data):
    data.files["uploads/week5.csv"] = [GOOD, {**GOOD, "feedback_id": "a2", "severity": "huge"}]
    result = importers[0].import_file("uploads/week5.csv")
    assert [r.feedback_id for r in result.records] == ["a1"]
    assert result.rejected == [(2, "severity must be one of: low, medium, high, critical")]
    assert result.total == 2
    # only the file's name is kept, not the folder it was in
    assert result.source_file == "week5.csv"
    assert result.records[0].source_file == "week5.csv"


def test_csv_row_with_more_cells_than_the_header_is_rejected(importers, data):
    # csv.DictReader keeps the extra cells under the key None
    data.files["a.csv"] = [{**GOOD, "text": "Wifi drops", None: [" again"]}]
    assert importers[0].import_file("a.csv").rejected == [(1, "row has more cells than the header")]


def test_json_value_that_is_a_list_or_object_is_rejected(importers, data):
    data.files["a.json"] = [{**GOOD, "text": ["a", "list"]}, {**GOOD, "feedback_id": "a2"}]
    result = importers[1].import_file("a.json")
    assert result.rejected == [(1, "field(s) must be plain values, not lists or objects: text")]
    assert [r.feedback_id for r in result.records] == ["a2"]


def test_json_row_that_is_not_an_object_is_rejected(importers, data):
    data.files["a.json"] = ["oops", GOOD]
    assert importers[1].import_file("a.json").rejected == [(1, "row is not an object")]


def test_an_empty_file_is_an_error(importers, data):
    data.files["empty.csv"] = []
    with pytest.raises(ValueError, match="no rows"):
        importers[0].import_file("empty.csv")


def test_a_missing_or_corrupt_file_is_an_error(importers):
    # FakeData raises ValueError like the real Data Manager does
    with pytest.raises(ValueError):
        importers[0].import_file("missing.csv")
