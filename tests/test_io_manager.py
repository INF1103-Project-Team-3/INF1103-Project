from src import io_manager 


def test_print_out(capsys):
    io_manager.print_out("Hello")
    captured = capsys.readouterr()

    assert captured.out == "Hello\n"


def test_letter_validation():
    assert io_manager.letter_validation("Hello") is True
    assert io_manager.letter_validation("123") is False
    assert io_manager.letter_validation("!!!") is False
    assert io_manager.letter_validation("Hello123") is True


def test_prompt_normal_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Hello")

    result = io_manager._prompt("Enter something: ")

    assert result == "Hello"


def test_prompt_quit(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "quit")

    result = io_manager._prompt("Enter something: ")

    assert result is None