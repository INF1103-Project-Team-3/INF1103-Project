
import csv
from datetime import datetime
import json
import logging

import uuid

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
SUPPORTED_EXTENSIONS = (".csv", ".json")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000
ADMIN_PASSWORD = "123456"
STORE_FILE = "feedback_store.json"

def print_out(message=""):
    """The only place print() is called."""
    print(message)

def prompt_role():
    """Ask whether the user is a user or an admin.

    Returns "admin" only after the correct password is entered.
    Returns "user" for the regular single-entry flow, or None on quit.
    """
    choice = _prompt("Are you a user or admin? ")
    if choice is None:
        return None

    choice = choice.strip().lower()
    if choice == "admin":
        return "admin" if authenticate_admin() else None
    return "user"

def prompt_admin_action():
    """Ask an admin to choose: single entry, JSON import, or CSV import.

    Returns "entry", "json", "csv", or None on quit.
    """
    while True:
        choice = _prompt("Single entry, JSON import, or CSV import? (entry/json/csv): ")

        if choice is None:
            return None

        choice = choice.strip().lower()

        if choice == "entry":
            return "entry"
        elif choice == "json":
            return "json"
        elif choice == "csv":
            return "csv"

        print_out("Invalid option. Please enter 'entry', 'json', or 'csv'.")

def authenticate_admin():
    """Prompt for the admin password. Returns True/False. No retry cap
    beyond what _prompt_until_valid enforces (none, per your last change).
    """
    def check(password):
        return (True, "") if password == ADMIN_PASSWORD else (None, "wrong password")

    return prompt_until_valid("Admin password: ", check) is True

def _prompt(message):
    """
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


def generate_id():
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

def read_json(path):
    """Read raw rows from a JSON file (expects a list). Returns [] if bad."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Could not read JSON %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        logger.warning("JSON %s must contain a list of entries", path)
        return []
    return data

def read_csv(path):
    """Read raw rows from a CSV file as dicts. Returns [] if bad."""    
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        logger.warning("Could not read CSV %s: %s", path, exc)
        return []

def prompt_until_valid(message, validator):
    """Prompt until validator(answer) -> (value, error) succeeds.
    Returns value or None on quit.
    """
    while True:
        answer = _prompt(message)
        if answer is None:
            return None
        value, error = validator(answer)
        if not error:
            return value
        print_out(f"  Invalid: {error}")


def read_entry():
    """Prompt for one piece of feedback.

    Returns an entry dict, or None if the user 
    quits or fails validation too many times.
    """
    def check(text):
        return validate_entry({
            "feedback_id": generate_id(),
            "text": text,
            "timestamp": _now(),
        })

    return prompt_until_valid("Enter feedback (quit to cancel): ", check)

def submit_single_entry():
    """Collect one feedback entry. Returns the entry dict, or None on cancel."""
    entry = read_entry()
    if entry is None:
        print_out("Cancelled.")
        return None
    return entry

def run_user_flow():
    """User workflow: a single feedback attempt, then a thank-you message."""
    print_out("\n--- Feedback ---")
    entry = submit_single_entry()
    if entry is None:
        return
    print_out("Thank you! Your response has been saved.")
    print_out(f"  {entry}")

def run_admin_single_entry():
    """Admin sub-flow: submit one feedback entry."""
    entry = submit_single_entry()
    if entry is None:
        return
    print_out(f"Entry ID: {entry['feedback_id']}")
    print_out(f"  {entry}")