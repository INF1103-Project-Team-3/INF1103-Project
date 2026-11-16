import json

import pytest

from managers.data_manager import DataManager
from managers.models import NEGATIVE, HIGH, REVIEWED, THEMES, Action, FeedbackRecord

USER = {"theme": "Facilities", "sentiment": NEGATIVE, "severity": HIGH}


def record(feedback_id, text="The library wifi keeps dropping."):
    return FeedbackRecord(feedback_id, text, "2026-11-04T09:30:00", None, USER)


def action(action_id):
    return Action(action_id, "Facilities", "Fixed the wifi", "2026-11-01", None, "2026-11-02T10:00:00")


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


# ---- D1: a corrupt store file is kept, not overwritten by the next save

@pytest.mark.parametrize("filename, save", [
    ("actions.json", lambda data: data.save_action(action("a2"))),
    # the pipeline loads the saved records before it saves them again (IngestionStep)
    ("processed_feedback.json",
     lambda data: data.save_records(data.load_records() + [record("fb_002")])),
    ("feedback_before_ai.json", lambda data: data.add_pending([record("fb_002")])),
    ("aggregated_history.json", lambda data: data.append_history("2026-11-04T10:00:00", None, {})),
    ("known_themes.json", lambda data: data.add_known_theme("Parking")),
])
def test_corrupt_store_file_survives_the_next_save(tmp_path, filename, save):
    data = DataManager(str(tmp_path))
    write(tmp_path / filename, '{"records": [ {"feedback_id": "fb_001"')
    save(data)
    [moved] = tmp_path.glob(f"{filename}.corrupt-*")
    assert moved.read_text(encoding="utf-8") == '{"records": [ {"feedback_id": "fb_001"'
    assert json.loads((tmp_path / filename).read_text(encoding="utf-8"))


def test_corrupt_import_file_is_left_in_place(tmp_path):
    data = DataManager(str(tmp_path / "data"))
    upload = tmp_path / "upload.json"
    write(upload, "{not json")
    assert data.read_rows(upload) == [{}]
    assert upload.read_text(encoding="utf-8") == "{not json"
    assert list(tmp_path.rglob("*.corrupt-*")) == []


# ---- D2: an entry with the wrong container types is skipped, not a crash

@pytest.mark.parametrize("field, value", [
    ("user", None), ("user", ["ab"]), ("ai", 5), ("ai", "x"), ("review_reasons", 5),
])
def test_record_entry_with_wrong_container_is_skipped(tmp_path, field, value):
    good = record("fb_001").to_dict()
    bad = {**record("fb_002").to_dict(), field: value}
    write(tmp_path / "processed_feedback.json", {"records": [good, bad]})
    assert [r.feedback_id for r in DataManager(str(tmp_path)).load_records()] == ["fb_001"]


# ---- D3: known_themes.json of the wrong shape gives the base themes

@pytest.mark.parametrize("content", [
    {"themes": None}, {"themes": "Parking"}, {"themes": 5}, None, "Parking", 5,
])
def test_known_themes_of_the_wrong_shape_give_base_themes(tmp_path, content):
    write(tmp_path / "known_themes.json", content)
    assert DataManager(str(tmp_path)).load_known_themes() == list(THEMES)


@pytest.mark.parametrize("content", [
    ["Parking", 5, "", "   ", None], {"themes": ["Parking", 5, "", "   ", None]},
])
def test_known_themes_drop_bad_items_only(tmp_path, content):
    write(tmp_path / "known_themes.json", content)
    assert DataManager(str(tmp_path)).load_known_themes() == list(THEMES) + ["Parking"]


@pytest.mark.parametrize("content", [{"themes": None}, {"themes": "Parking"}, None, 5])
def test_add_known_theme_over_the_wrong_shape(tmp_path, content):
    write(tmp_path / "known_themes.json", content)
    data = DataManager(str(tmp_path))
    assert data.add_known_theme("Canteen")
    assert data.load_known_themes() == list(THEMES) + ["Canteen"]


# ---- D4: an Excel CSV with a byte-order mark reads like any other

def test_csv_with_bom_reads_its_first_column(tmp_path):
    upload = tmp_path / "upload.csv"
    upload.write_bytes("feedback_id,text\r\nfb_001,Wifi drops\r\n".encode("utf-8-sig"))
    rows = DataManager(str(tmp_path / "data")).read_rows(upload)
    assert rows == [{"feedback_id": "fb_001", "text": "Wifi drops"}]


# ---- D5: a reviewed record with no "counted" key is still counted

def test_reviewed_record_without_counted_key_is_counted(tmp_path):
    reviewed = record("fb_001")
    reviewed.mark_reviewed("Facilities", NEGATIVE, HIGH)
    entry = reviewed.to_dict()
    del entry["counted"]
    write(tmp_path / "processed_feedback.json", {"records": [entry]})
    [loaded] = DataManager(str(tmp_path)).load_records()
    assert loaded.verification == REVIEWED and loaded.counted


# ---- P5: a re-run after a failed run does not store the same IDs twice

def test_add_pending_skips_ids_already_pending_or_processed(tmp_path):
    data = DataManager(str(tmp_path))
    data.add_pending([record("fb_001"), record("fb_002")])
    data.update_pending(record("fb_002"))           # classified: moved to processed
    data.add_pending([record("fb_001"), record("fb_002"), record("fb_003")])
    assert [r.feedback_id for r in data.load_pending()] == ["fb_001", "fb_003"]
    assert [r.feedback_id for r in data.load_records()] == ["fb_002"]


def test_save_action_skips_an_action_id_already_stored(tmp_path):
    data = DataManager(str(tmp_path))
    data.save_action(action("a1"))
    data.save_action(action("a1"))
    data.save_action(action("a2"))
    assert [a.action_id for a in data.load_actions()] == ["a1", "a2"]


# ---- I1: read_rows raises ValueError for a file it cannot read, as its contract says
def test_read_rows_of_a_missing_file_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        DataManager(str(tmp_path / "data")).read_rows(tmp_path / "missing.csv")


@pytest.mark.parametrize("name", ["folder.json", "folder.csv"])
def test_read_rows_of_a_folder_raises_value_error(tmp_path, name):
    (tmp_path / name).mkdir()
    with pytest.raises(ValueError):
        DataManager(str(tmp_path / "data")).read_rows(tmp_path / name)


# ---- F2: search matches what a record says, not the names of its fields

def test_search_matches_values_not_field_names_or_empty_values(tmp_path):
    data = DataManager(str(tmp_path))
    data.save_records([record("fb_001", "The lift is broken.")])
    for query in ("theme", "sentiment", "severity", "summary", "none", "null", "true", "false"):
        assert data.search_records(query) == [], query


def test_search_matches_id_text_summary_and_labels(tmp_path):
    data = DataManager(str(tmp_path))
    saved = record("fb_001", "The lift is broken.")
    saved.set_ai("Facilities", NEGATIVE, HIGH, "Elevator out of service.")
    saved.mark_reviewed("Parking", NEGATIVE, HIGH)
    data.save_records([saved])
    for query in ("fb_001", "LIFT", "elevator", "facilities", "negative", "high", "parking", "lift facilities"):
        assert [r.feedback_id for r in data.search_records(query)] == ["fb_001"], query


# ---- F5: an app data file that cannot be opened loads empty instead of crashing (DR 8.6)

def test_app_file_that_cannot_be_opened_loads_empty_and_stays_put(tmp_path):
    (tmp_path / "processed_feedback.json").mkdir()
    data = DataManager(str(tmp_path))
    assert data.load_records() == []
    assert (tmp_path / "processed_feedback.json").is_dir()


def test_token_log_that_cannot_be_opened_reads_as_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(DataManager, "_token_log_path", lambda self: tmp_path)
    assert DataManager(str(tmp_path / "data")).load_token_log() is None


# ---- F10: the CSV store saves an empty list like the JSON store (LSP, DR 8.6)

def test_csv_store_saves_an_empty_list(tmp_path):
    from managers.data_manager.csv_file_store import CsvFileStore
    path = tmp_path / "out.csv"
    path.write_text("a\n1\n", encoding="utf-8")
    assert CsvFileStore().save(path, []) is True
    assert CsvFileStore().load(path) == []


# ---- F11: delete_record says whether anything was removed (DR 8.6: -> bool)

def test_delete_record_is_true_only_when_a_store_held_the_id(tmp_path):
    data = DataManager(str(tmp_path))
    assert data.delete_record("fb_x") is False
    data.save_records([record("fb_001")])
    assert data.delete_record("fb_x") is False
    assert data.delete_record("fb_001") is True
    assert data.load_records() == []
