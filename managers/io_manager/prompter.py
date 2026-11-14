from __future__ import annotations

from typing import Callable

from .feedback_view import FeedbackView
from .input_validator import InputValidator


class Prompter:
    """Asks the person for typed input and returns None if they quit.

    Quitting means typing q or quit (or pressing Ctrl-D / Ctrl-C). I never
    print anything myself: the questions go through the reader, and error
    messages go through the view. The readers are constructor parameters so a
    test can feed in scripted answers instead of a keyboard.
    """

    QUIT_COMMANDS = ("q", "quit")
    YES_ANSWERS = ("y", "yes")

    def __init__(self, view: FeedbackView, reader: Callable[[str], str] = input,
                 secret_reader: Callable[[str], str] | None = None):
        self._view = view
        self._reader = reader
        self._secret_reader = secret_reader or self._default_secret_reader()

    @staticmethod
    def _default_secret_reader() -> Callable[[str], str]:
        """Hidden input that shows '*' if pwinput is installed, else getpass (no echo)."""
        try:
            import pwinput
            return lambda message: pwinput.pwinput(message, mask="*")
        except ImportError:
            import getpass
            return getpass.getpass

    def ask(self, message: str, hidden: bool = False) -> str | None:
        """One answer, or None if the person quit. hidden=True is for passwords."""
        reader = self._secret_reader if hidden else self._reader
        try:
            answer = reader(message)
        except (EOFError, KeyboardInterrupt):
            return None
        if hidden:
            return answer             # a password could legitimately be "q", so never treat it as quit
        answer = answer.strip()
        return None if answer.lower() in self.QUIT_COMMANDS else answer

    def ask_until_valid(self, message: str, validator: InputValidator,
                        hidden: bool = False):
        """Keep asking until the validator accepts. Returns its value, or None if they quit."""
        while True:
            answer = self.ask(message, hidden=hidden)
            if answer is None:
                return None
            value, error = validator.check(answer)    # works for any InputValidator
            if not error:
                return value
            self._view.show_message(f"  Invalid: {error}")

    def confirm(self, message: str) -> bool:
        """True only if the person answered yes."""
        return (self.ask(message) or "").lower() in self.YES_ANSWERS
