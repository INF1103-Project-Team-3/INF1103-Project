
import csv
from datetime import datetime
import json
import pwinput
import logging
import uuid
import os

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000
ADMIN_PASSWORD = "123456"


def print_out(message=""):
    """The only place print() is called."""
    print(message)


def prompt_role():
    """Ask whether the user is a user or an admin.

    Returns "admin" only after the correct password is entered.
    Returns "user" for the regular single-entry flow, or None on quit.
    Re-prompts on anything other than "user" or "admin".
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
    """Ask an admin to choose: single entry, JSON import, or CSV-to-JSON conversion.

    Returns "entry", "json", "csv", or None on quit.
    """
    while True:
        choice = _prompt("Single entry, JSON import, or CSV to JSON import? (entry/json/csv): ")
        if choice is None:
            return None

        choice = choice.lower()
        if choice in ("entry", "json", "csv"):
            return choice

        print_out("Invalid option. Please enter 'entry', 'json', or 'csv'.")


def authenticate_admin():
    """Prompt for the admin password. Returns True/False. No retry cap
    beyond what prompt_until_valid enforces (none, per your last change).
    """
    def check(password):
        return (True, "") if password == ADMIN_PASSWORD else (None, "wrong password")

    return prompt_until_valid("Admin password: ", check, hide_input=True) is True


def _prompt(message, hide_input=False):
    """
    Returns the stripped answer, or None on quit, Ctrl+C or EOF.
    An empty string means the user just pressed Enter.
    """
    read_input = (lambda m: pwinput.pwinput(m, mask="*")) if hide_input else input
    try:
        answer = read_input(message)
    except (EOFError, KeyboardInterrupt):
        print_out()
        return None
    if hide_input:
        return answer
    answer = answer.strip()
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
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        logger.warning("Could not read CSV %s: %s", path, exc)
        return []


def convert_csv_to_json(csv_path, json_path):
    """Convert a CSV file to a JSON file.
    Returns True on success, False if the CSV can't be read or the
    JSON can't be written.
    """
    rows = read_csv(csv_path)
    if not rows:
        return False

    # DictReader stores extra cells under a None key; drop those.
    rows = [{k: v for k, v in row.items() if k is not None} for row in rows]

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("Could not write JSON %s: %s", json_path, exc)
        return False
    return True





def prompt_until_valid(message, validator,hide_input=False):
    """Prompt until validator(answer) -> (value, error) succeeds.
    Returns value or None on quit.
    """
    while True:
        answer = _prompt(message, hide_input=hide_input)
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


def validate_files(rows):
    """Validate a batch of raw rows.
 
    Returns (accepted, rejected):
      - accepted: list of clean entry dicts
      - rejected: list of (row_number, reason) tuples, 1-indexed
    """
    accepted, rejected = [], []
    for i, raw in enumerate(rows, start=1):
        entry, error = validate_entry(raw)
        if error:
            rejected.append((i, error))
        else:
            accepted.append(entry)
    return accepted, rejected


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


def run_admin_convert():
    """Admin sub-flow: convert a CSV file into a JSON file next to it."""
    while True:
        csv_path = _prompt("Path to a CSV file, or 'quit' to cancel: ")
        if csv_path is None:
            print_out("Cancelled.")
            return

        json_path = os.path.splitext(csv_path)[0] + ".json"
        if convert_csv_to_json(csv_path, json_path):
            print_out(f"Converted to '{json_path}'. Use the 'json' option to import it.")
            return
        print_out(f"  Invalid: could not convert '{csv_path}' (check the path and format).")


def run_admin_files_json():
    """Admin sub-flow: bulk-import a JSON file of feedback rows.
    Reprompts for the path until a file loads or the user quits.
    """
    while True:
        path = _prompt("Path to a JSON file, or 'quit' to cancel: ")
        if path is None:
            print_out("Cancelled.")
            return

        rows = read_json(path)
        if rows:
            break
        print_out(f"  Invalid: could not read '{path}' as JSON (check the path and format).")

    accepted, rejected = validate_files(rows)

    print_out(f"\nValidated {len(accepted)} of {len(rows)} row(s).")
    if accepted:
        print_out("Accepted rows:")
        for entry in accepted:
            print_out(f"  {entry}")
    if rejected:
        print_out("Rejected rows:")
        for i, error in rejected:
            print_out(f"  Row {i}: {error}")



def run_admin_flow():
    """Admin workflow: single entry, JSON import, or CSV-to-JSON conversion."""
    print_out("\n--- Admin ---")
    action = prompt_admin_action()
    if action is None:
        print_out("Cancelled.")
        return
    if action == "json":
        run_admin_files_json()
    elif action == "csv":
        run_admin_convert()
    else:
        run_admin_single_entry()


def main():
    print_out("=== Feedback Manager ===")
    
    role = prompt_role()
    if role is None:
        print_out("Goodbye.")
        return
 
    if role == "admin":
        run_admin_flow()
    else:
        run_user_flow()
 
    print_out("Thank you for using Feedback Manager. Goodbye.")
 
 
if __name__ == "__main__":
    main()