from datetime import datetime
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