import json

from managers.data_manager import JsonFileStore


def test_valid_file_loads(tmp_path):
    path = tmp_path / "actions.json"
    path.write_text(json.dumps({"records": [1]}), encoding="utf-8")
    assert JsonFileStore().load(path) == {"records": [1]}


def test_missing_or_empty_file_loads_as_empty(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert JsonFileStore().load(tmp_path / "missing.json") == {}
    assert JsonFileStore().load(empty) == {}
    assert empty.exists()


def test_corrupt_file_is_moved_aside_with_its_content(tmp_path):
    path = tmp_path / "actions.json"
    path.write_text('{"records": [ {"action_id": "a1"', encoding="utf-8")
    assert JsonFileStore().load(path) == {}
    assert not path.exists()
    [moved] = tmp_path.glob("actions.json.corrupt-*")
    assert moved.read_text(encoding="utf-8") == '{"records": [ {"action_id": "a1"'


def test_undecodable_file_is_moved_aside(tmp_path):
    path = tmp_path / "actions.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    assert JsonFileStore().load(path) == {}
    assert len(list(tmp_path.glob("actions.json.corrupt-*"))) == 1


def test_a_second_corrupt_copy_does_not_replace_the_first(tmp_path):
    path = tmp_path / "actions.json"
    store = JsonFileStore()
    path.write_text("first{", encoding="utf-8")
    store.load(path)
    path.write_text("second{", encoding="utf-8")
    store.load(path)
    kept = sorted(p.read_text(encoding="utf-8") for p in tmp_path.glob("actions.json.corrupt-*"))
    assert kept == ["first{", "second{"]


def test_store_without_quarantine_leaves_a_corrupt_file_in_place(tmp_path):
    path = tmp_path / "upload.json"
    path.write_text("{not json", encoding="utf-8")
    assert JsonFileStore(quarantine_corrupt=False).load(path) == {}
    assert path.read_text(encoding="utf-8") == "{not json"
    assert list(tmp_path.glob("*.corrupt-*")) == []


# F5: an unopenable app file loads empty; an import file still raises, so read_rows can say why (I1)
def test_unopenable_file_loads_empty_for_app_data_and_raises_for_imports(tmp_path):
    import pytest
    folder = tmp_path / "actions.json"
    folder.mkdir()
    assert JsonFileStore().load(folder) == {}
    assert folder.is_dir()
    with pytest.raises(OSError):
        JsonFileStore(quarantine_corrupt=False).load(folder)
