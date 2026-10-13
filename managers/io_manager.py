import csv
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import uuid
import textwrap
import pwinput  # third-party: pip install pwinput
import data_manager

logger = logging.getLogger(__name__)

# Every valid feedback entry must have all three of these.
REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"  # e.g. 2026-09-29T10:30:00
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000
PAYLOAD_MIME = "application/json"
PAYLOAD_EXT = ".json"

DATA_DIRECTORY = "data"                      # where the output files are saved
TEST_INPUT_FILE = "test-input.json"          # single entries are saved here
AGGREGATED_FILE = "aggregated_output.json"   # theme table data
SUMMARY_FILE = "summary.json"                # summary of the aggregated data
REVIEW_FILE = "for_review.json"              # for review files
TREND_FILE = "trend_output.json"             # trend data

# Display formatting for the dashboard.
WIDTH = 82
COLUMN_THEME = 22

# Display formatting for theme & trend table.
MERGED_THEME = 24
MERGED_STATUS = 16
MERGED_COUNT = 17
MERGED_SENT = 8
MERGED_URGENT = 6
MERGED_GAP = "   "                            # space before the PRIORITY column
MERGED_PRIORITY = 16
MERGED_WIDTH = (MERGED_THEME + MERGED_STATUS + MERGED_COUNT + MERGED_SENT
                + MERGED_URGENT + len(MERGED_GAP) + MERGED_PRIORITY)

# Review queue display.
REVIEW_LABEL_WIDTH = 16     # "low_confidence" column
REVIEW_SUMMARY_WIDTH = 36   # summary is shortened to this many characters
SEVERITY_LEVELS = ("low", "medium", "high", "critical")
SENTIMENTS = ("negative", "neutral", "positive")

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

    Quitting returns False. 
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
    passed or failed (only rejected rows are listed).

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
    print_rows("Rejected rows:", [f"Row {i}: {error}" for i, error in rejected])

    return entries_to_payload(accepted) if accepted else None


# ---------------------------------------------------------------------------
# File reading / conversion
# ---------------------------------------------------------------------------

def data_path(filename):
    """Full path of a file inside DATA_DIRECTORY.
    """
    return os.path.join(DATA_DIRECTORY, filename)


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


def read_json_rows(path):
    """Load a JSON file of rows. Returns [] if it can't be read, so the
    caller can reprompt instead of crashing."""
    try:
        return data_manager._read_list_strict(Path(path))
    except (ValueError, OSError) as exc:
        logger.warning("Could not read JSON %s: %s", path, exc)
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
    return data_manager._write_json_atomic(Path(json_path), rows)

#---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------
# Single entries are saved to test-input.json (see save_entry).
# File imports are passed as an in-memory JSON file.
 
 
def save_entry(entry, path=None):
    """Add one validated entry to the JSON list in path.

    Creates the file if it doesn't exist yet. Returns True on success.
    """
    path = Path(data_path(TEST_INPUT_FILE))
    entries = data_manager._read_list_strict(path) if path.exists() else []
    entries.append(entry)
    return data_manager._write_json_atomic(path, entries)


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


def print_dashboard_header(agg, summary, review_count, both_count=0):
    """Print the title line with entry counts, then the overall summary: one bullet per sentence."""
    print_block(f"FEEDBACK DASHBOARD    entries: {agg['total_entries']}   "
                f"counted: {agg['counted_entries']}   for review: {review_count}")
    if both_count:
        print_out(f"{both_count} critical entries are in both: counted and for review")
    print_out("=" * WIDTH)

    overall = clean(summary.get("overall_summary", ""))
    if overall:
        print_block("OVERALL")
        for sentence in re.split(r"(?<=\.)\s+", overall):
            print_out(textwrap.fill(sentence, width=WIDTH,
                                    initial_indent="  - ", subsequent_indent="    "))


def build_theme_rows(agg):
    """Return (theme, urgent_count) rows in the same order as the JSON file."""
    rows = []
    for t in agg["themes"]:
        sev = t["severity_counts"]
        urgent = sev["critical"] + sev["high"]
        rows.append((t, urgent))
    return rows


def print_theme_table(rows):
    """Print the theme table from rows made by build_theme_rows."""
    print_block("THEMES")
    print_out(f"{'THEME':<{COLUMN_THEME}}{'COUNT':>5}  {'AVG SENT':>8}  {'HIGH+CRIT':>9}  {'PRIORITY':>8}")
    print_out("-" * WIDTH)
    for t, urgent in rows:
        print_out(f"{t['theme']:<{COLUMN_THEME}}{t['count']:>5}  {t['avg_sentiment']:>8.2f}  "
                  f"{urgent:>9}  {t['priority_score']:>8}")


def print_suggested_actions(summary, rows):
    """Print each theme's suggested action, in the same order as the table."""
    actions = {a["theme"]: a["suggested_action"]
               for a in summary.get("summary_list", [])
               if a["theme"] != "Unclear"}
    if not actions:
        return

    print_block("SUGGESTED ACTIONS")
    print_out("-" * WIDTH)
    for t, _ in rows:
        if t["theme"] in actions:
            print_out(textwrap.fill(clean(actions[t["theme"]]), width=WIDTH,
                                    initial_indent=f"{t['theme']:<{COLUMN_THEME}}",
                                    subsequent_indent=" " * COLUMN_THEME))


def display_dashboard():
    """Display dashboard and review queue."""
    pending = load_review_queue()
    agg = data_manager.load_aggregated_output(
        filename=AGGREGATED_FILE, base_dir=DATA_DIRECTORY
    )

    if agg.get("themes"):
        data_manager.SUMMARY_STORAGE_PATH = Path(data_path(SUMMARY_FILE))
        summary = data_manager.load_summary()

        both = sum(
            1 for r in pending
            if r.get("counted") and review_label(r) == "critical"
        )
        print_dashboard_header(agg, summary, len(pending), both)
        display_themes_and_actions(agg, summary)
    else:
        print_block("No aggregated data yet.")

    print_review_queue(pending)
    offer_review(pending)


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------


def load_trend():
    """Load trend output, or return an empty dictionary."""
    return data_manager.load_trends_output(
        filename=TREND_FILE, base_dir=DATA_DIRECTORY
    ) or {}


def has_trend(trend):
    """Check whether a previous run exists."""
    return bool(trend.get("has_previous"))
 
 
def print_trend_headline(trend):
    """One line comparing the headline numbers with the previous run."""
    run_at = (trend.get("previous_run") or {}).get("run_at", "").replace("T", " ")
    headline = trend["headline"]
    print_block(f"Trend vs previous run ({run_at})")
    print_out(f"Entries: {headline['total_entries']['text']}    "
              f"Negative: {headline['negative_percent']['text']}")
 
 
def merge_theme_rows(rows, trend):
    """Merge current themes with trend rows, prioritising trend order."""
    trend_rows = {r["theme"]: r for r in trend.get("themes", [])}
    current = {t["theme"]: (t, urgent) for t, urgent in rows}

    merged = [
        (name, *current.get(name, (None, None)), trend_row)
        for name, trend_row in trend_rows.items()
    ]

    merged.extend(
        (t["theme"], t, urgent, None)
        for t, urgent in rows
        if t["theme"] not in trend_rows
    )

    return merged
 
 
def print_merged_theme_table(merged):
    """Print themes alongside their trend information."""
    print_block("THEMES")
    print_out(
        f"{'THEME':<{MERGED_THEME}}{'STATUS':<{MERGED_STATUS}}"
        f"{'COUNT':<{MERGED_COUNT}}{'AVG SENT':>{MERGED_SENT}}"
        f"{'H+C':>{MERGED_URGENT}}{MERGED_GAP}PRIORITY"
    )
    print_out("-" * MERGED_WIDTH)

    for name, theme, urgent, trend in merged:
        status = trend["status"] if trend else "-"
        count = (trend["count"]["text"] if trend
                 else str(theme["count"]))
        priority = (trend["priority"]["text"] if trend
                    else str(theme["priority_score"]))
        avg_sent = f"{theme['avg_sentiment']:.2f}" if theme else "-"
        high_crit = str(urgent) if theme else "-"

        print_out(
            f"{name:<{MERGED_THEME}}{status:<{MERGED_STATUS}}"
            f"{count:<{MERGED_COUNT}}{avg_sent:>{MERGED_SENT}}"
            f"{high_crit:>{MERGED_URGENT}}{MERGED_GAP}{priority}"
        )

    print_block("AVG SENT = average sentiment, H+C = high + critical entries")


def display_themes_and_actions(agg, summary):
    """ Print the theme table and suggested actions,
      merging with trend data if available."""
    rows = build_theme_rows(agg)
    trend = load_trend()

    if has_trend(trend):
        print_trend_headline(trend)
        merged = merge_theme_rows(rows, trend)
        print_merged_theme_table(merged)
        rows = [(t, urgent) for _, t, urgent, _ in merged if t]
    else:
        if trend.get("message"):
            print_block(trend["message"])
        print_theme_table(rows)

    print_suggested_actions(summary, rows)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def print_search_results(results):
    """Print each matching record: ID and tags on one line, text wrapped below."""
    print_block(f"Found {len(results)} matching record(s):")
    print_out("-" * WIDTH)
    for record in results:
        tags = " | ".join(
            str(record[key]) for key in ("theme", "sentiment", "severity")
            if record.get(key) not in (None, "")
        )
        print_out(f"{record.get('feedback_id', '?')}   {tags}")
        text = clean(str(record.get("text") or record.get("feedback") or ""))
        print_out(textwrap.fill(text, width=WIDTH,
                                initial_indent="  ", subsequent_indent="  "))
        print_out()


def run_admin_search():
    """Admin flow: Search stored feedback. Prompts until something
    matches or the admin quits."""
    print_block()
    while True:
        query = _prompt("Enter Feedback terms (or 'quit' to cancel): ")
        if query is None:
            print_block("Cancelled.")
            return None

        results = data_manager.search_records(query)
        if results:
            print_search_results(results)
            return None
        print_out(f"  No feedback found matching '{query}'. Try different terms.")


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------
#   update review entry sets agreement and confidence to 1 and leaves the
#   record in the file, so a record with both at 1 counts as reviewed and is
#   hidden. Deleted records are already gone from the file.

def load_review_queue():
    """Records in for_review.json that still need a review.
    """
    data = data_manager._load_review_file(Path(DATA_DIRECTORY) / REVIEW_FILE)
    return [
        r for r in data.get("records", [])
        if isinstance(r, dict)
        and not (r.get("agreement") == 1 and r.get("confidence") == 1)
    ]


def review_label(record):
    """Short reason a record was flagged, read from its review_reason."""
    reasons = str(record.get("review_reason", "")).lower()
    if "critical" in reasons:
        return "critical"
    if "confidence" in reasons:
        return "low_confidence"
    if "agreement" in reasons:
        return "low_agreement"
    return "review"


def print_review_queue(pending):
    """Print one line per record for review."""
    print_block("REVIEW QUEUE")
    print_out("-" * WIDTH)
    if not pending:
        print_out("Nothing waiting for review.")
        return
    for r in pending:
        summary = textwrap.shorten(clean(str(r.get("summary", ""))),
                                   width=REVIEW_SUMMARY_WIDTH, placeholder="...")
        print_out(f"{str(r.get('feedback_id', '?')):<8}"
                  f"{review_label(r):<{REVIEW_LABEL_WIDTH}}"
                  f"{str(r.get('theme', '-')):<{COLUMN_THEME}}{summary}")


def print_review_entry(record, position, total):
    """Show one flagged record in full text."""
    print_block(f"Review {position} of {total}   ID: {record.get('feedback_id', '?')}")
    print_out("-" * WIDTH)
    print_out(textwrap.fill(clean(str(record.get("text", ""))), width=WIDTH,
                            initial_indent="  ", subsequent_indent="  "))
    print_out()
    for field in ("theme", "sentiment", "severity", "confidence", "agreement"):
        print_out(f"  {field.capitalize():<11}: {record.get(field, '-')}")
    reasons = record.get("review_reason") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    if reasons:
        print_out(f"  {'Flagged':<11}: {'; '.join(map(str, reasons))}")


def prompt_review_action():
    """Ask what to do with this record. Returns u, d, s, or None if they quit."""
    def check(choice):
        choice = choice.lower()
        if choice in ("u", "d", "s"):
            return choice, ""
        return None, "enter u (update), d (delete) or s (skip)"

    print_out()
    return prompt_until_valid("  [u]pdate, [d]elete, [s]kip (quit to stop): ", check)


def field_check(options):
    """Validator for one update field. Blank is allowed: keeps the current value."""
    def check(text):
        text = text.strip()
        if options is None or not text:
            return text, ""
        if text.lower() in options:
            return text.lower(), ""
        return None, f"choose one of: {', '.join(options)}"
    return check


def review_update(record):
    """Ask for new theme/severity/sentiment. Enter keeps the current value.
    Keeping all three approves the record as it is and leaves the review queue.
    """
    print_block("Press Enter to keep a value. Keeping all three approves the record as is.")
    changes = {}
    for field, options in (("theme", None),
                           ("severity", SEVERITY_LEVELS),
                           ("sentiment", SENTIMENTS)):
        value = prompt_until_valid(f"  New {field} [{record.get(field, '')}]: ",
                                   field_check(options))
        if value is None:   # quit
            print_block("Update cancelled.")
            return
        changes[field] = value

    if data_manager.update_review_entry(record.get("feedback_id"),
                                         filename=REVIEW_FILE, base_dir=DATA_DIRECTORY,
                                         **changes):
        print_block("Updated. It has been removed from the review queue.")
    else:
        print_block("Could not update this entry.")


def review_delete(record):
    """Confirm, then delete the record from the review file."""
    answer = _prompt("  Delete this feedback permanently? (y/n): ")
    if (answer or "").lower() not in ("y", "yes"):
        print_block("Delete cancelled.")
        return
    if data_manager.delete_review_entry(record.get("feedback_id"),
                                         filename=REVIEW_FILE, base_dir=DATA_DIRECTORY):
        print_block("Deleted.")
    else:
        print_block("Could not delete this entry.")


def run_review_queue(pending):
    """Walk through the pending records: update, delete or skip each one."""
    for position, record in enumerate(pending, start=1):
        print_review_entry(record, position, len(pending))
        action = prompt_review_action()
        if action is None:
            break
        if action == "u":
            review_update(record)
        elif action == "d":
            review_delete(record)

    print_block(f"Review finished. {len(load_review_queue())} still in the queue.")


def offer_review(pending):
    """After the queue is shown, prompt to start reviewing."""
    if not pending:
        return
    answer = _prompt("Review them now? (y/n): ")
    if (answer or "").lower() in ("y", "yes"):
        run_review_queue(pending)


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
    Saves the entry to test-input.json and returns it, or None if they cancelled.
    """
    entry = read_entry()
    if entry is None:
        print_block("Cancelled.")
        return None

    if not save_entry(entry):
        print_block(f"Could not save to '{data_path(TEST_INPUT_FILE)}'.")
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
    """
    print_block()
    while True:
        name = _prompt(f"Enter path of CSV or JSON file (or 'quit' to cancel): ")
        if name is None:
            print_block("Cancelled.")
            return None
        path = data_path(name)

        extension = os.path.splitext(path)[1].lower()
        if extension == ".json":
            rows = read_json_rows(path)
            if rows:  # empty list counts as a failed load, so will reprompt
                break
            print_out(f"  Invalid: could not read '{path}' as JSON (check the path and format).")
        elif extension == ".csv":
            # name.csv -> name.json, saved in the data folder
            json_path = data_path(os.path.splitext(os.path.basename(path))[0] + ".json")
            if convert_csv_to_json(path, json_path):
                print_block(f"Converted to '{json_path}'.")
                rows = read_json_rows(json_path)
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
    elif action == "search":
        return run_admin_search()


def run_role_flow(role):
    """Run the flow for this role. Returns its payload, or None."""
    if role == "admin":
        return run_admin_flow()
    print_block("--- Feedback ---")
    return run_single_entry()

# ---------------------------------------------------------------------------
# Printing notices
# ---------------------------------------------------------------------------

def print_no_unclassified_notice():
    print_block("""
    ➔ NOTICE: No unclassified records detected in cache.
    Nothing new to process. Exiting runtime.
    """)

def print_connection_notice():
    print_block(f"""
    ==========================================================================
    CONNECTING TO API & RUNNING
    ==========================================================================
    """)

def print_compilation_notice():
    print_block(f"""
    ==========================================================================
    COMPILING RESULTS AND AGGREGATING THEMES
    ==========================================================================
    """)

def print_ai_request_notice():
    print_block("===========Requesting summary from AI===============")

def print_goodbye():
    print_block("Thank you for using Feedback Manager. Goodbye.")


def main():
    """Run the session. Returns the payload or None."""
    print_block("=== Feedback Manager ===")
 
    role = prompt_role()
    if role is None:
        print_block("Goodbye.")
        return None
 
    payload = run_role_flow(role)
    return payload
 
 
if __name__ == "__main__":
    main()