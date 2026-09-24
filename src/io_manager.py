
import logging
from typing import Final

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
SUPPORTED_EXTENSIONS = (".csv", ".json")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
MAX_REPROMPTS: Final = 3
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000

def print_out(message=""):
    """The only place print() is called."""
    print(message)


def _prompt(message):
    """The only place input() is called.

    Returns the stripped answer, or None on quit, Ctrl+C or EOF.
    An empty string means the user just pressed Enter.
    """
    try:
        answer = input(message).strip() 
    except (EOFError, KeyboardInterrupt):
        print_out()
        return None
    if answer.lower() in QUIT_COMMANDS:
        return None
    return answer

def letter_validation(text):
    """If text contains at least one letter, return True (rejects '123' or '!!!')."""
    return any(c.isalpha() for c in text)

