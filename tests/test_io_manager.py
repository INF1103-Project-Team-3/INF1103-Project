from datetime import datetime
import io
import json
from src import io_manager 

# Test print_out()
def test_print_out(capsys):
    io_manager.print_out("Hello")
    captured = capsys.readouterr()

    assert captured.out == "Hello\n"

# Test letter_validation()
def test_letter_validation():
    assert io_manager.letter_validation("Hello") is True
    assert io_manager.letter_validation("123") is False
    assert io_manager.letter_validation("!!!") is False
    assert io_manager.letter_validation("Hello123") is True

# Test _prompt()

def test_prompt_normal_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Hello")

    result = io_manager._prompt("Enter something: ")

    assert result == "Hello"


def test_prompt_quit(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "quit")

    result = io_manager._prompt("Enter something: ")

    assert result is None

# Test _now()

def test_now_returns_correct_format():
    timestamp = io_manager._now()

    # Should not raise an exception
    datetime.strptime(timestamp, io_manager.TIMESTAMP_FORMAT)


#  Test generate_id()

def test_generate_id_format():
    fb_id = io_manager.generate_id()

    assert fb_id.startswith("fb_")
    assert len(fb_id) == 11  # "fb_" + 8 characters


def test_generate_id_is_unique():
    id1 = io_manager.generate_id()
    id2 = io_manager.generate_id()

    assert id1 != id2

# Test validate_entry() 

def test_validate_entry_valid():
    entry = {
        "feedback_id": "fb_12345678",
        "text": "Great service!",
        "timestamp": "2026-09-25T10:30:00",
    }

    cleaned, error = io_manager.validate_entry(entry)

    assert error == ""
    assert cleaned == entry


def test_validate_entry_not_dict():
    cleaned, error = io_manager.validate_entry("hello")

    assert cleaned is None
    assert error == "row is not an object"


def test_validate_entry_missing_field():
    entry = {
        "feedback_id": "fb_12345678",
        "text": "Great service!"
    }

    cleaned, error = io_manager.validate_entry(entry)

    assert cleaned is None
    assert "missing field(s): timestamp" in error


def test_validate_entry_no_letters():
    entry = {
        "feedback_id": "fb_12345678",
        "text": "12345!!!",
        "timestamp": "2026-09-25T10:30:00",
    }

    cleaned, error = io_manager.validate_entry(entry)

    assert cleaned is None
    assert error == "text contains no letters"


def test_validate_entry_text_too_long():
    entry = {
        "feedback_id": "fb_12345678",
        "text": "a" * (io_manager.MAX_TEXT_LENGTH + 1),
        "timestamp": "2026-09-25T10:30:00",
    }

    cleaned, error = io_manager.validate_entry(entry)

    assert cleaned is None
    assert "text longer than" in error


def test_validate_entry_bad_timestamp():
    entry = {
        "feedback_id": "fb_12345678",
        "text": "Good",
        "timestamp": "25/09/2026",
    }

    cleaned, error = io_manager.validate_entry(entry)

    assert cleaned is None
    assert "timestamp must look like" in error

#  Test read_json() 

def test_read_json_valid(tmp_path):
    data = [
        {
            "feedback_id": "fb_12345678",
            "text": "Good",
            "timestamp": "2026-09-25T10:30:00",
        }
    ]

    file = tmp_path / "data.json"
    file.write_text(json.dumps(data), encoding="utf-8")

    assert io_manager.read_json(file) == data


def test_read_json_invalid_json(tmp_path):
    file = tmp_path / "bad.json"
    file.write_text("{invalid json", encoding="utf-8")

    assert io_manager.read_json(file) == []


def test_read_json_not_list(tmp_path):
    file = tmp_path / "dict.json"
    file.write_text(json.dumps({"hello": "world"}), encoding="utf-8")

    assert io_manager.read_json(file) == []


