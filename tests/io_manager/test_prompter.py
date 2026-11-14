"""Prompter: asks for input, re-asks until valid, and treats q/quit as quitting."""
import pytest

from managers.io_manager.choice_validator import ChoiceValidator
from managers.io_manager.password_validator import PasswordValidator
from managers.io_manager.prompter import Prompter
from managers.io_manager.text_validator import TextValidator


def test_answer_is_trimmed(prompter):
    assert prompter(["  hello  "]).ask("Say something: ") == "hello"


@pytest.mark.parametrize("answer", ["q", "quit", "QUIT", " Q "])
def test_quit_commands_return_none(prompter, answer):
    assert prompter([answer]).ask("Name: ") is None


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_ctrl_d_and_ctrl_c_count_as_quitting(screen, error):
    def reader(prompt):
        raise error
    assert Prompter(screen.view, reader).ask("Name: ") is None


def test_a_hidden_answer_of_q_is_a_password_not_quit(prompter):
    # someone's password could really be "q"
    assert prompter(secrets=["q"]).ask("Password: ", hidden=True) == "q"


def test_re_asks_until_valid_and_shows_each_error(prompter, screen):
    ask = prompter(["maybe", "HIGH"])
    assert ask.ask_until_valid("Severity: ", ChoiceValidator(("low", "high"))) == "high"
    assert prompter.script.prompts == ["Severity: ", "Severity: "]
    assert "  Invalid: choose one of: low, high" in screen.lines


def test_quitting_while_re_asking_returns_none(prompter):
    assert prompter(["maybe", "quit"]).ask_until_valid(
        "Severity: ", ChoiceValidator(("low", "high"))) is None


@pytest.mark.parametrize("validator, answer, expected", [
    (ChoiceValidator(("user", "admin")), "Admin", "admin"),
    (TextValidator("text"), " Good lectures ", "Good lectures"),
    (PasswordValidator("pw"), "pw", True),
])
def test_works_with_any_input_validator(prompter, validator, answer, expected):
    # polymorphism: the Prompter never needs to know which validator it was given
    hidden = isinstance(validator, PasswordValidator)
    ask = prompter([] if hidden else [answer], [answer] if hidden else [])
    assert ask.ask_until_valid("> ", validator, hidden=hidden) == expected


@pytest.mark.parametrize("answer, expected", [("y", True), ("YES", True), ("n", False),
                                              ("whatever", False), ("q", False)])
def test_confirm_is_true_only_for_yes(prompter, answer, expected):
    assert prompter([answer]).confirm("Sure? ") is expected
