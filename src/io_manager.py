import csv
from datetime import datetime
import json
import logging
import os
import re
import uuid
import textwrap
import pwinput  # third-party: pip install pwinput

logger = logging.getLogger(__name__)

# Every valid feedback entry must have all three of these.
REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"  # e.g. 2026-09-29T10:30:00
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000
PAYLOAD_MIME = "application/json"
PAYLOAD_EXT = ".json"

TEST_INPUT_FILE = "test-input.json"          # single entries are saved here
AGGREGATED_FILE = "aggregated_output.json"   # theme table data
SUMMARY_FILE = "summary-output.json"         # overall + suggested actions data

# Display formatting for the dashboard.
WIDTH = 68
COLUMN_THEME = 22
PRIORITY_THRESHOLD = 3      # A theme is PRIORITY if it has any high/critical entry

# Hardcoded password.
ADMIN_PASSWORD = "123456"

# Admin menu: number -> action name used by run_admin_flow.
ADMIN_MENU = {
    "1": ("entry", "Feedback Entry"),
    "2": ("import", "CSV or JSON import"),
    "3": ("dashboard", "Dashboard"),
    "4": ("search", "Search Feedback"),
}


def print_out(message=""):
    """Making it easy for Output to be redirected later."""
    print(message)


def print_block(*lines):
    """Print one blank line, then each line given.

    Every block of output (headings, results, reports, goodbyes) are seperated by a line.
    """
    print_out()
    for line in lines:
        print_out(line)


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

def _prompt(message, hidden=False):
    """Ask for input. Returns the answer, or None if the user quits.

    Quit means typing q/quit.

    With hidden=True (passwords), input shows as '*':
    """
    reader = (lambda m: pwinput.pwinput(m, mask="*")) if hidden else input
    try:
        answer = reader(message)
    except (EOFError, KeyboardInterrupt):
        print_out()
        return None
    if hidden:
        return answer
    answer = answer.strip()
    if answer.lower() in QUIT_COMMANDS: # quit
        return None
    return answer


def prompt_until_valid(message, validator, hidden=False):
    """Keep asking until validator(answer) has no error.

    Returns the validated value, or None if the user quits.
    Will keep prompting until a valid value is entered.
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

    Quitting (typing 'q' or 'quit') returns False. 
    Wrong guesses keep prompting until a valid value is entered
    """
    def check(password):
        return (True, "") if password == ADMIN_PASSWORD else (None, "wrong password")

    return prompt_until_valid("Admin password: ", check, hidden=True) is True


def prompt_role():
    """Ask if the person is a user or an admin.

    Returns user, admin, or None if they
    quit or cancel.
    """
    def check(choice):
        choice = choice.lower()
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
    """Show the admin menu and ask what to do.

    Returns the chosen action (entry, import, dashboard, search), or None
    if they quit.
    """
    menu_lines = [f"{number}. {label}" for number, (_, label) in ADMIN_MENU.items()]
    while True:
        print_block(*menu_lines)
        choice = _prompt(f"Choose an option (1-{len(ADMIN_MENU)}): ")
        if choice is None:
            return None

        if choice in ADMIN_MENU:
            return ADMIN_MENU[choice][0]

        print_out(f"Invalid option. Please enter a number from 1 to {len(ADMIN_MENU)}.")


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
    """Check each raw row and clean it.

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


def print_rows(title, rows):
    """Print a titled, indented list. Prints nothing if the list is empty."""
    if rows:
        print_block(title, *[f"  {row}" for row in rows])
 
 
def validate_and_report(rows):
    """Validate rows from a JSON file or the converted CSV and print what
    passed or failed.

    Returns the accepted rows as a payload, or None if none were valid.
    """
    accepted, rejected = [], []  # rejected: list of (row_number, reason)
    for i, raw in enumerate(rows, start=1):
        entry, error = validate_entry(raw)
        if error:
            rejected.append((i, error))
        else:
            accepted.append(entry)

    print_block(f"Validated {len(accepted)} of {len(rows)} row(s).")
    print_rows("Accepted rows:", accepted)
    print_rows("Rejected rows:", [f"Row {i}: {error}" for i, error in rejected])

    return entries_to_payload(accepted) if accepted else None


# ---------------------------------------------------------------------------
# File reading / conversion
# ---------------------------------------------------------------------------

def read_json(path):
    """Load a JSON file that holds a list of rows. """
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


def write_json(path, data):
    """Write data to path as JSON, creating the file if it doesn't exist.

    Returns True on success, False if the file can't be written.
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("Could not write JSON %s: %s", path, exc)
        return False
    return True


def read_csv(path):
    """Load a CSV file as a list of dicts (first row = column names).
    """
    try:
        # utf-8-sig ignores the invisible BOM, which would corrupt the first column name.
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

    # If a row has more cells than the header, they sit under a None key (saved as "null"). validate_entry ignores them.
    return write_json(json_path, rows)
#---------------------------------------------------------------------------

 
# Payloads
# ---------------------------------------------------------------------------
# Single entries are saved to test-input.json (see save_entry).
# File imports are passed as an in-memory JSON file.
 
 
def save_entry(entry, path=TEST_INPUT_FILE):
    """Add one validated entry to the JSON list in path.

    Creates the file if it doesn't exist yet. Returns True on success.
    """
    entries = read_json(path) if os.path.exists(path) else []
    entries.append(entry)
    return write_json(path, entries)
 
 
def entries_to_payload(entries):
    """A list of validated entries: file(filename, bytes, mime_type).
 
    The file holds a JSON array.
    Only accepted rows go in; rejected rows to be rejected.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    content = json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")
    return (f"feedback_{stamp}{PAYLOAD_EXT}", content, PAYLOAD_MIME)


# ---------------------------------------------------------------------------

# Dashboard 
# ---------------------------------------------------------------------------


def clean(text):
    """Replace characters that some terminals can't print."""
    return (text.replace("\u2011", "-")     # non-breaking hyphen
                .replace("\u2019", "'")     # curly apostrophe
                .replace("\u2013", "-")
                .replace("\u2014", "-"))


def load_dashboard_data(path):
    """Load a JSON file; return None if missing or unreadable."""
    if not os.path.exists(path):
        print_block(f"{path} not found.")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print_block(f"Could not read {path}.")
        return None


def print_dashboard_header(agg, summary):
    """Print the title line with entry counts, then the overall summary
    (one bullet per sentence)."""
    print_block(f"FEEDBACK DASHBOARD    entries: {agg['total_entries']}   "
                f"counted: {agg['counted_entries']}  ")
    print_out("=" * WIDTH)

    overall = clean(summary.get("overall_summary", ""))
    if overall:
        print_block("OVERALL")
        for sentence in re.split(r"(?<=\.)\s+", overall):
            print_out(textwrap.fill(sentence, width=WIDTH,
                                    initial_indent="  - ", subsequent_indent="    "))


def build_theme_rows(agg):
    """Return (theme, urgent_count, is_priority) rows: priority first, then by count."""
    rows = []
    for t in agg["themes"]:
        sev = t["severity_counts"]
        urgent = sev["critical"] + sev["high"]
        is_priority = sev["critical"] > 0 or urgent >= PRIORITY_THRESHOLD
        rows.append((t, urgent, is_priority))
    rows.sort(key=lambda r: (not r[2], -r[0]["count"]))
    return rows


def print_theme_table(rows):
    """Print the theme table from rows made by build_theme_rows."""
    print_block("THEMES")
    print_out(f"{'THEME':<{COLUMN_THEME}}{'COUNT':>5}  {'AVG SENT':>8}  {'HIGH+CRIT':>9}  PRIORITY")
    print_out("-" * WIDTH)
    for t, urgent, is_priority in rows:
        print_out(f"{t['theme']:<{COLUMN_THEME}}{t['count']:>5}  {t['avg_sentiment']:>8.2f}  "
                  f"{urgent:>9}  {'YES' if is_priority else 'no'}")


def print_suggested_actions(summary, rows):
    """Print each theme's suggested action, in the same order as the table."""
    actions = {a["theme"]: a["suggested_action"]
               for a in summary.get("theme_actions", [])
               if a["theme"] != "Unclear"}
    if not actions:
        return

    print_block("SUGGESTED ACTIONS")
    print_out("-" * WIDTH)
    for t, _, _ in rows:
        if t["theme"] in actions:
            print_out(textwrap.fill(clean(actions[t["theme"]]), width=WIDTH,
                                    initial_indent=f"{t['theme']:<{COLUMN_THEME}}",
                                    subsequent_indent=" " * COLUMN_THEME))


def display_dashboard():
    """Load the output files and print the dashboard."""
    agg = load_dashboard_data(AGGREGATED_FILE)
    if agg is None:
        return
    summary = load_dashboard_data(SUMMARY_FILE) or {}

    rows = build_theme_rows(agg)
    print_dashboard_header(agg, summary)
    print_theme_table(rows)
    print_suggested_actions(summary, rows)


# ---------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------

def read_entry():
    """Ask for one piece of feedback. Returns an entry dict, or None if they quit."""
    def check(text):
        # ID and timestamp are generated on each attempt, then the whole
        # entry goes through the same validation.
        return validate_entry({
            "feedback_id": generate_id(),
            "text": text,
            "timestamp": _now(),
        })

    return prompt_until_valid("Enter feedback (quit to cancel): ", check)


def run_single_entry(is_admin=False):
    """Collect one feedback entry and confirm if they are user or admin.
 
    Saves the entry to test-input.json and returns it, or None if they
    cancelled or it could not be saved.
    """
    entry = read_entry()
    if entry is None:
        print_block("Cancelled.")
        return None

    if not save_entry(entry):
        print_block(f"Could not save to '{TEST_INPUT_FILE}'.")
        return None
 
    if is_admin:
        print_block(f"Entry ID: {entry['feedback_id']}")
    else:
        print_block("Thank you! Your response has been saved.")
    print_out(f"  {entry}")
    return entry


def run_admin_import():
    """Admin flow: import a JSON or CSV file. The file type is picked from
    the extension. Keeps asking for a path until a file loads or the admin quits.

    A CSV is converted to a JSON file (name.csv -> name.json) before
    validating. Returns the accepted rows as a payload, or None.
    """
    print_block()
    while True:
        path = _prompt("Path to a CSV or JSON file, or 'quit' to cancel: ")
        if path is None:
            print_block("Cancelled.")
            return None

        extension = os.path.splitext(path)[1].lower()
        if extension == ".json":
            rows = read_json(path)
            if rows:  # empty list counts as a failed load, so will reprompt
                break
            print_out(f"  Invalid: could not read '{path}' as JSON (check the path and format).")
        elif extension == ".csv":
            # name.csv -> name.json, in the same folder
            json_path = os.path.splitext(path)[0] + ".json"
            if convert_csv_to_json(path, json_path):
                print_block(f"Converted to '{json_path}'.")
                rows = read_json(json_path)
                break
            print_out(f"  Invalid: could not convert '{path}' (check the path and format).")
        else:
            print_out("  Invalid: file must end in .csv or .json.")

    return validate_and_report(rows)


def run_admin_flow():
    """Admin workflow: run whichever action the admin picks."""
    print_block("--- Admin ---")
    action = prompt_admin_action()
    if action is None:
        print_block("Cancelled.")
        return
    if action == "entry":
        return run_single_entry(is_admin=True)
    elif action == "import":
        return run_admin_import()
    elif action == "dashboard":
        return display_dashboard()
    else:  # "search"
        return 


def run_role_flow(role):
    """Run the flow for this role. Returns its payload, or None."""
    if role == "admin":
        return run_admin_flow()
    print_block("--- Feedback ---")
    return run_single_entry()


def main():
    """Run the session. Returns the payload or None."""
    print_block("=== Feedback Manager ===")
 
    role = prompt_role()
    if role is None:
        print_block("Goodbye.")
        return None
 
    payload = run_role_flow(role)
    print_block("Thank you for using Feedback Manager. Goodbye.")
    return payload
 
 
if __name__ == "__main__":
    main()