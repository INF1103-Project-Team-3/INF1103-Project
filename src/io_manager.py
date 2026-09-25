
from datetime import datetime
import logging
from typing import Final
import uuid

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

def _now():
    """Current time in TIMESTAMP_FORMAT."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def _generate_id():
    """ID for typed entries, e.g. 'fb_3f9a1c2e'."""
    return f"fb_{uuid.uuid4().hex[:8]}"


def validate_entry(raw):
    """Validate one raw row.

    Returns (clean_entry, "") on success or (None, reason) on failure.
    """
    if not isinstance(raw, dict):
        return None, "row is not an object"

    missing = [
        f for f in REQUIRED_FIELDS
        if raw.get(f) is None or not str(raw[f]).strip()
    ]
    if missing:
        return None, f"missing field(s): {', '.join(missing)}"

    entry = {f: str(raw[f]).strip() for f in REQUIRED_FIELDS}

    if not letter_validation(entry["text"]):
        return None, "text contains no letters"
    if len(entry["text"]) > MAX_TEXT_LENGTH:
        return None, f"text longer than {MAX_TEXT_LENGTH} characters"
    try:
        datetime.strptime(entry["timestamp"], TIMESTAMP_FORMAT)
    except ValueError:
        return None, f"timestamp must look like {TIMESTAMP_FORMAT}"

    return entry, ""