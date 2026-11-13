from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Sequence

from managers.models import UNCLEAR_THEME, FeedbackRecord

from .choice_validator import ChoiceValidator
from .csv_importer import CsvImporter
from .entry_form import EntryForm
from .entry_validator import EntryValidator
from .feedback_importer import FeedbackImporter
from .feedback_view import FeedbackView
from .import_result import ImportResult
from .json_importer import JsonImporter
from .password_validator import PasswordValidator
from .prompter import Prompter
from .record_builder import RecordBuilder
from .review_session import ReviewSession
from .session_result import SessionResult
from .theme_validator import ThemeValidator

if TYPE_CHECKING:
    from managers.data_manager import DataManager
    from managers.logic_manager import LogicManager


class IOManager:
    """The I/O Manager: asks who is using the app, runs the user form or the
    admin menu, and returns everything collected as one SessionResult.

    I never save anything and never call the AI. I only read from Data, and I
    use Logic for one thing: normalising a typed theme (through ThemeValidator).
    Each menu option is a short method that hands the real work to a form, an
    importer, the review session or Data, so this class only decides what
    happens next.

    Class relationships I chose on purpose:
      - Aggregation: the view, prompter and importers are made outside and
        passed in, so they exist without me (a test passes a fake view, and the
        GUI reuses the same importers).
      - Composition: I create the PasswordValidator, the EntryForm and the
        ReviewSession myself; they exist only inside this object.
      - Association: Data and Logic are other managers I use but do not own.
    """

    ROLE_USER = "user"
    ROLE_ADMIN = "admin"
    ROLES = (ROLE_USER, ROLE_ADMIN)

    # notices AppEngine shows through show_notice() in terminal mode, around one
    # pipeline run: nothing collected, about to run, and the end of the program.
    # Progress during the run is the ProgressReporter's job, not the view's.
    NOTICE_NOTHING_NEW = "NOTICE: Nothing new to process. Exiting runtime."
    NOTICE_CONNECTING = "CONNECTING TO API & RUNNING"
    NOTICE_GOODBYE = "Thank you for using Feedback Manager. Goodbye."

    # what Settings shows for the AI connection; AppEngine knows (it reads the
    # API key), I do not, because only AppEngine reads environment variables
    AI_STATUS = {True: "ready", False: "not configured (no API key)", None: "not reported"}

    def __init__(self, view: FeedbackView, prompter: Prompter,
                 importers: Sequence[FeedbackImporter], data: "DataManager",
                 logic: "LogicManager", admin_password: str | None,
                 ai_ready: bool | None = None):
        self._view = view
        self._prompter = prompter
        self._importers = list(importers)
        self._data = data
        # the password comes from AppEngine (read from the environment); it is
        # never written in the source code
        self._password = PasswordValidator(admin_password)
        self._roles = ChoiceValidator(self.ROLES, error="please enter 'user' or 'admin'")
        self._ai_ready = ai_ready
        # one theme validator, shared by the form and Settings, so a typed theme
        # is cleaned up by Logic the same way wherever it is typed
        self._theme_validator = ThemeValidator(logic)
        self._form = EntryForm(prompter, view, data, self._theme_validator, RecordBuilder())
        # a reviewer may press Enter to keep a theme, so this theme validator allows blank
        self._review = ReviewSession(view, prompter, ThemeValidator(logic, allow_blank=True))

        # role -> flow, so the right flow is chosen without an if/else
        self._flows: dict[str, Callable[[], SessionResult | None]] = {
            self.ROLE_USER: self._run_user,
            self.ROLE_ADMIN: self._run_admin,
        }
        # admin menu label -> handler, instead of a long if/elif chain. A dict
        # keeps insertion order, so the menu numbers follow this order. A new
        # option is one method plus one line here (Open/Closed Principle).
        # Each handler returns True only when the admin has finished.
        self._menu: dict[str, Callable[[SessionResult], bool]] = {
            "Feedback Entry": self._add_entry,
            "CSV or JSON import": self._import_file,
            "Dashboard": self._show_dashboard,
            "Search Feedback": self._search,
            "Review flagged feedback": self._review_flagged,
            "Log an action": self._log_action,
            "Settings": self._settings,
            "Finish and run analysis": self._finish,
        }

    @staticmethod
    def create_importers(data: "DataManager", logic: "LogicManager") -> list[FeedbackImporter]:
        """The standard importers (CSV and JSON), ready to pass to the constructor
        or to the GUI. They share one validator and one builder."""
        validator = EntryValidator(ThemeValidator(logic))
        builder = RecordBuilder()
        return [CsvImporter(data, validator, builder), JsonImporter(data, validator, builder)]

    # ---- public API ------------------------------------------------------

    def run_session(self) -> SessionResult | None:
        """Run one session. Returns what was collected, or None if the person
        quit or collected nothing."""
        self._view.show_message("=== Feedback Manager ===")
        role = self._select_role()
        if role is None:
            self._view.show_message("Goodbye.")
            return None
        return self._flows[role]()

    def show_notice(self, notice: str) -> None:
        """Show a status notice (one of the NOTICE_* attributes)."""
        self._view.show_notice(notice)

    # ---- choosing the role -------------------------------------------------

    def _select_role(self) -> str | None:
        """'user' or 'admin'. An admin must log in. None if they quit or fail to log in."""
        role = self._prompter.ask_until_valid(
            "Are you a user or admin? (user/admin): ", self._roles)
        if role == self.ROLE_ADMIN and not self._authenticate():
            return None
        return role

    def _authenticate(self) -> bool:
        if not self._password.is_configured:
            self._view.show_message("Admin login is disabled: no admin password is configured.")
            return False
        # the password check gives True when correct, and None if the admin quits
        return self._prompter.ask_until_valid(
            "Admin password: ", self._password, hidden=True) is True

    # ---- user flow ---------------------------------------------------------

    def _run_user(self) -> SessionResult | None:
        """A user's whole session: give one piece of feedback."""
        self._view.show_message("--- Feedback ---")
        record = self._form.collect_feedback()
        if record is None:
            self._view.show_message("Cancelled.")
            return None
        self._view.show_message("Thank you! Your response has been received.")
        return SessionResult(records=[record])

    # ---- admin flow --------------------------------------------------------

    def _run_admin(self) -> SessionResult | None:
        """Show the menu until the admin finishes or quits. Everything they do
        goes into one SessionResult, returned at the end (None if it is empty)."""
        session = SessionResult()
        handlers = list(self._menu.values())
        menu = "\n".join(f"{n}. {label}" for n, label in enumerate(self._menu, 1))
        choices = ChoiceValidator([str(n) for n in range(1, len(handlers) + 1)],
                                  error=f"please enter a number from 1 to {len(handlers)}")
        self._view.show_message("--- Admin ---")
        while True:
            self._view.show_message(menu)
            choice = self._prompter.ask_until_valid(
                f"Choose an option (1-{len(handlers)}): ", choices)
            if choice is None or handlers[int(choice) - 1](session):
                break
        if session.is_empty():
            self._view.show_message("Cancelled.")
            return None
        return session

    def _add_entry(self, session: SessionResult) -> bool:
        record = self._form.collect_feedback()
        if record is None:
            self._view.show_message("Cancelled.")
        else:
            session.records.append(record)
            self._view.show_message(f"Entry ID: {record.feedback_id}")
        return False

    def _import_file(self, session: SessionResult) -> bool:
        result = self._ask_for_import()
        if result is None:
            self._view.show_message("Cancelled.")
            return False
        self._view.show_message(f"Validated {len(result.records)} of {result.total} row(s).")
        self._view.show_rejected_rows(result.rejected)
        if result.records:
            session.records.extend(result.records)
            session.source_file = result.source_file
        return False

    def _ask_for_import(self) -> ImportResult | None:
        """Keep asking for a file path until one imports, or the admin quits (None)."""
        types = ", ".join(i.extension for i in self._importers)
        while True:
            path = self._prompter.ask("\nEnter path of CSV or JSON file (or 'quit' to cancel): ")
            if path is None:
                return None
            # polymorphism: I never check the file type myself, the importers do
            importer = FeedbackImporter.select(self._importers, path)
            if importer is None:
                self._view.show_message(f"  Invalid: file must end in {types}.")
                continue
            try:
                return importer.import_file(path)
            except ValueError as exc:       # unreadable, corrupt or empty file: ask again
                self._view.show_message(f"  Invalid: could not read '{path}': {exc}")

    def _show_dashboard(self, session: SessionResult) -> bool:
        # imported here, not at the top, so an unfinished Logic or AI module can
        # never stop the whole I/O package from loading
        from managers.ai_manager import AISummary
        from managers.logic_manager import AggregationResult, TrendReport
        queue = self._load_queue()
        self._view.show_dashboard(self._rebuild("aggregated_output", AggregationResult),
                                  self._rebuild("trend_output", TrendReport),
                                  self._rebuild("summary", AISummary), queue)
        # only offer a review if something is still undecided in this session
        waiting = [r for r in queue if r.feedback_id not in session.decided_ids()]
        if waiting and self._prompter.confirm("\nReview them now? (y/n): "):
            session.decisions.extend(self._review.run(queue, session.decided_ids()))
        return False

    def _search(self, session: SessionResult) -> bool:
        while True:
            query = self._prompter.ask("\nEnter feedback terms (or 'quit' to cancel): ")
            if query is None:
                self._view.show_message("Cancelled.")
                return False
            found = self._data.search_records(query)     # searching is Data's job
            if found:
                self._view.show_search_results(found)
                return False
            self._view.show_message(f"  No feedback found matching '{query}'. Try different terms.")

    def _review_flagged(self, session: SessionResult) -> bool:
        session.decisions.extend(self._review.run(self._load_queue(), session.decided_ids()))
        return False

    def _log_action(self, session: SessionResult) -> bool:
        action = self._form.collect_action()
        if action is None:
            self._view.show_message("Cancelled.")
        else:
            session.actions.append(action)
            self._view.show_message(f"Action logged. ID: {action.action_id}")
        return False

    def _settings(self, session: SessionResult) -> bool:
        """Known themes, Add theme and the read-only system status, until Back."""
        options = ChoiceValidator(("1", "2"), error="please enter 1 or 2")
        while True:
            self._view.show_settings(self._data.load_known_themes(),
                                     session.themes_to_add, self._status())
            self._view.show_message("1. Add a theme\n2. Back to the admin menu")
            choice = self._prompter.ask_until_valid("Choose an option (1-2): ", options)
            if choice != "1":                   # Back, or quit
                return False
            self._add_theme(session)

    def _add_theme(self, session: SessionResult) -> None:
        """Queue one new theme. I never save it: the pipeline does, when the
        analysis runs (data.add_known_theme, then logic.set_known_themes)."""
        theme = self._prompter.ask_until_valid(
            "New theme name (quit to cancel): ", self._theme_validator)
        if theme is None:
            self._view.show_message("Cancelled.")
            return
        known = {name.lower() for name in self._data.load_known_themes()}
        known |= {name.lower() for name in session.themes_to_add}
        if theme == UNCLEAR_THEME:              # Logic treats filler words as Unclear
            self._view.show_message("  Invalid: that is not a usable theme name.")
        elif theme.lower() in known:
            self._view.show_message(f"  '{theme}' is already a known theme.")
        else:
            session.themes_to_add.append(theme)
            self._view.show_message(f"  '{theme}' will be added when the analysis runs.")

    def _status(self) -> dict[str, str]:
        """Read-only facts for Settings, using only the Data reads I am allowed."""
        last_run = self._data.load_history(1)
        run_at = str(last_run[0].get("run_at") or "") if last_run else ""
        return {
            "AI connection": self.AI_STATUS.get(self._ai_ready, self.AI_STATUS[None]),
            "Processed records": str(len(self._data.load_records() or [])),
            "Waiting for review": str(len(self._load_queue())),
            "Last analysis run": run_at.replace("T", " ") or "never",
        }

    def _finish(self, session: SessionResult) -> bool:
        return True

    # ---- reading saved results (read only) ---------------------------------

    def _load_queue(self) -> list[FeedbackRecord]:
        """The records currently flagged for review."""
        return list(self._data.load_review_queue() or [])

    def _rebuild(self, name: str, cls: Any) -> Any:
        """Load one saved result from Data and turn the dictionary back into an
        object with its from_dict() (the Serializable contract). Missing data
        gives None. Corrupt data also gives None, so the dashboard shows "no
        data" instead of crashing, and I say so through the view (only the
        view displays anything)."""
        raw = self._data.load_object(name)
        if not raw:
            return None
        try:
            return cls.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            self._view.show_message(f"  Note: the saved {name} could not be read, so it is left out.")
            return None
