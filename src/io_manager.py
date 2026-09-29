import csv
from datetime import datetime
import json
import logging
import os
import uuid

import pwinput  # third-party: pip install pwinput

logger = logging.getLogger(__name__)

# Every valid feedback entry must have all three of these.
REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"  # e.g. 2026-09-29T10:30:00
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000

# Hardcoded password.
ADMIN_PASSWORD = "123456"


def print_out(message=""):
    """The only place print() is called, so output is easy to redirect later."""
    print(message)


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

def _prompt(message, hidden=False):
    """Ask for input. Returns the answer, or None if the user quits.

    Quit means typing q/quit, or pressing Ctrl+C.

    With hidden=True (passwords), input shows as '*' and is returned as-is:
    Use Ctrl+C cancels there.
    """
    reader = (lambda m: pwinput.pwinput(m, mask="*")) if hidden else input
    try:
        answer = reader(message)
    except (EOFError, KeyboardInterrupt):
        print_out()  # move to a fresh line after ^C
        return None
    if hidden:
        return answer
    answer = answer.strip()
    if answer.lower() in QUIT_COMMANDS: 
        return None
    return answer


def prompt_until_valid(message, validator, hidden=False):
    """Keep asking until validator(answer) -> (value, error) has no error.

    Returns the validated value, or None if the user quits.
    There is no retry limit.
    """
    while True:
        answer = _prompt(message, hidden=hidden)
        if answer is None:
            return None
        value, error = validator(answer)
        if not error:
            return value
        print_out(f"  Invalid: {error}")


def authenticate_admin():
    """Ask for the admin password (masked). Returns True only if it matches.

    Quitting (Ctrl+C / Ctrl+D) returns False. Wrong guesses re-prompts.
    """
    def check(password):
        return (True, "") if password == ADMIN_PASSWORD else (None, "wrong password")

    return prompt_until_valid("Admin password: ", check, hidden=True) is True


def prompt_role():
    """Ask if the person is a 'user' or an 'admin'.

    Returns "user", "admin", or None if they
    quit or cancel.
    """
    def check(choice):
        choice = choice.strip().lower()
        if choice in ("user", "admin"):
            return choice, ""
        return None, "please enter 'user' or 'admin'"

    role = prompt_until_valid("Are you a user or admin? (user/admin): ", check)
    if role is None:
        return None

    if role == "admin":
        return "admin" if authenticate_admin() else None
    return "user"


def prompt_admin_action():
    """Ask the admin what to do: 'entry', 'json' or 'csv'.

    Returns the chosen word, or None if they quit.
    """
    while True:
        choice = _prompt("Single entry, JSON import, or convert CSV to JSON? (entry/json/csv): ")
        if choice is None:
            return None

        choice = choice.lower()  # _prompt already stripped whitespace
        if choice in ("entry", "json", "csv"):
            return choice

        print_out("Invalid option. Please enter 'entry', 'json', or 'csv'.")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def letter_validation(text):
    """True if text has at least one letter. Rejects things like '123' or '!!!'."""
    return any(c.isalpha() for c in text)


def _now():
    """Current time as a string in TIMESTAMP_FORMAT."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def generate_id():
    """Short random ID for typed entries, e.g. 'fb_3f9a1c2e'."""
    return f"fb_{uuid.uuid4().hex[:8]}"


def validate_entry(raw):
    """Check one raw row and clean it up.

    Returns (clean_entry, "") if it's valid, or (None, reason) if not.
    """
    # JSON rows can be anything (strings, numbers, lists), so check the type first.
    if not isinstance(raw, dict):
        return None, "row is not an object"

    # A field counts as missing if it's absent, None, or only whitespace.
    missing = [
        f for f in REQUIRED_FIELDS
        if raw.get(f) is None or not str(raw[f]).strip()
    ]
    if missing:
        return None, f"missing field(s): {', '.join(missing)}"

    # Keep only the required fields, as trimmed strings (extra columns are dropped).
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


def validate_files(rows):
    """Validate all rows in that file.

    Returns (accepted, rejected):
      accepted: list of clean entry dicts
      rejected: list of (row_number, reason), numbered from 1
    """
    accepted, rejected = [], []
    for i, raw in enumerate(rows, start=1):
        entry, error = validate_entry(raw)
        if error:
            rejected.append((i, error))
        else:
            accepted.append(entry)
    return accepted, rejected


def print_rows(title, rows):
    """Print a titled, indented list. Prints nothing if the list is empty."""
    if rows:
        print_out(title)
        for row in rows:
            print_out(f"  {row}")
 
 
def validate_and_report(rows):
    """Validate rows from a JSON file (or a converted CSV) and print what
    passed or failed.
 
    Returns the accepted rows as a payload, or None if none were valid.
    """
    accepted, rejected = validate_files(rows)
 
    print_out(f"\nValidated {len(accepted)} of {len(rows)} row(s).")
    print_rows("Accepted rows:", accepted)
    print_rows("Rejected rows:", [f"Row {i}: {error}" for i, error in rejected])
 
    return entries_to_payload(accepted) if accepted else None


# ---------------------------------------------------------------------------
# File reading / conversion
# ---------------------------------------------------------------------------

def read_json(path):
    """Load a JSON file that holds a list of rows. Returns [] on any problem."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Could not read JSON %s: %s", path, exc)
        return []
    # The top level must be a list; a single object or string isn't a batch.
    if not isinstance(data, list):
        logger.warning("JSON %s must contain a list of entries", path)
        return []
    return data


def read_csv(path):
    """Load a CSV file as a list of dicts (first row = column names).
    Returns [] on any problem.
    """
    try:
        # utf-8-sig ignores the invisible BOM that Excel adds, which would
        # otherwise corrupt the first column name.
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        logger.warning("Could not read CSV %s: %s", path, exc)
        return []


def convert_csv_to_json(csv_path, json_path):
    """Convert a CSV file into a JSON file (a list of objects).

    Returns True on success, False if the CSV can't be read or the JSON
    can't be written. Overwrites json_path if it already exists.
    """
    rows = read_csv(csv_path)
    if not rows:  # unreadable, or only a header row
        return False

    # If a row has more cells than the header, DictReader files the extras
    # under a None key. Drop them.
    rows = [{k: v for k, v in row.items() if k is not None} for row in rows]

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("Could not write JSON %s: %s", json_path, exc)
        return False
    return True
#---------------------------------------------------------------------------

 
# Payloads
# ---------------------------------------------------------------------------
# Single entries are passed as a JSON string. File imports are passed as an
# in-memory JSON file: (filename, content_bytes, mime_type).
PAYLOAD_MIME = "application/json"
PAYLOAD_EXT = ".json"
 
 
def entry_to_payload(entry):
    """One validated entry -> JSON string.
 
    """
    return json.dumps(entry, ensure_ascii=False, indent=2)
 
 
def entries_to_payload(entries):
    """A list of validated entries -> file (filename, bytes, mime_type).
 
    Named like 'feedback_20260929_143000.json'. The file holds a JSON array.
    Only accepted rows go in; rejected rows never reach the payload.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    content = json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")
    return (f"feedback_{stamp}{PAYLOAD_EXT}", content, PAYLOAD_MIME)


# ---------------------------------------------------------------------------

# Flows
# ---------------------------------------------------------------------------

def read_entry():
    """Ask for one piece of feedback. Returns an entry dict, or None if they quit."""
    def check(text):
        # ID and timestamp are generated on each attempt, then the whole
        # entry goes through the same validation as imported rows.
        return validate_entry({
            "feedback_id": generate_id(),
            "text": text,
            "timestamp": _now(),
        })

    return prompt_until_valid("Enter feedback (quit to cancel): ", check)


def submit_single_entry():
    """Collect one entry, printing 'Cancelled.' if they quit. Returns the entry or None."""
    entry = read_entry()
    if entry is None:
        print_out("Cancelled.")
        return None
    return entry


def run_single_entry(is_admin=False):
    """Collect one feedback entry and confirm it (user or admin).
 
    Returns the entry as a payload, or None if they cancelled.
    """
    entry = read_entry()
    if entry is None:
        print_out("Cancelled.")
        return None
 
    if is_admin:
        print_out(f"Entry ID: {entry['feedback_id']}")
    else:
        print_out("Thank you! Your response has been saved.")
    print_out(f"  {entry}")
    return entry_to_payload(entry)


def run_admin_files_json():
    """Admin flow: import a JSON file. Keeps asking for a path until a file
    loads or the admin quits.
 
    Returns the accepted rows as a payload, or None.
    """
    while True:
        path = _prompt("Path to a JSON file, or 'quit' to cancel: ")
        if path is None:
            print_out("Cancelled.")
            return None
 
        rows = read_json(path)
        if rows:  # empty list counts as a failed load, so we reprompt
            break
        print_out(f"  Invalid: could not read '{path}' as JSON (check the path and format).")
 
    return validate_and_report(rows)


def run_admin_convert():
    """Admin flow: convert a CSV into a JSON file saved next to it, then
    validate the converted rows the same way as a JSON import.
 
    Returns the accepted rows as a payload, or None.
    """
    while True:
        csv_path = _prompt("Path to a CSV file, or 'quit' to cancel: ")
        if csv_path is None:
            print_out("Cancelled.")
            return None
 
        # data.csv -> data.json, in the same folder
        json_path = os.path.splitext(csv_path)[0] + ".json"
        if convert_csv_to_json(csv_path, json_path):
            break
        print_out(f"  Invalid: could not convert '{csv_path}' (check the path and format).")
 
    print_out(f"Converted to '{json_path}'.")
    return validate_and_report(read_json(json_path))


def run_admin_flow():
    """Admin workflow: run whichever action the admin picks."""
    print_out("\n--- Admin ---")
    action = prompt_admin_action()
    if action is None:
        print_out("Cancelled.")
        return
    if action == "json":
        return run_admin_files_json()
    elif action == "csv":
        return run_admin_convert()
    else:  # "entry"
        return run_single_entry(is_admin=True)

def run_role_flow(role):
    """Run the flow for this role. Returns its payload, or None."""
    if role == "admin":
        return run_admin_flow()
    print_out("\n--- Feedback ---")
    return run_single_entry()

def main():
    """Run the session. Returns the payload (nothing is printed for it), or None."""
    print_out("=== Feedback Manager ===")
 
    role = prompt_role()
    if role is None:
        print_out("Goodbye.")
        return None
 
    payload = run_role_flow(role)
    print_out("Thank you for using Feedback Manager. Goodbye.")
    return payload
 
 
if __name__ == "__main__":
    main()