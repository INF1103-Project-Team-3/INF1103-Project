# MainWindow: the admin window (sidebar, pages, background runs).

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from managers.io_manager import (
    EntryValidator, PasswordValidator, RecordBuilder, ReviewDecision, SessionResult, ThemeValidator,
)

from .pages.add_feedback_page import AddFeedbackPage
from .pages.dashboard_page import DashboardPage
from .pages.feedback_page import FeedbackPage
from .pages.settings_page import SettingsPage
from .pages.start_page import StartPage
from .pages.student_form_page import StudentFormPage
from .pages.trends_page import TrendsPage
from .pipeline_worker import PipelineWorker
from .qt_feedback_view import QtFeedbackView
from .qt_progress_reporter import QtProgressReporter
from .style import STYLE, Style
from .widgets.sidebar import Sidebar

DASHBOARD, ADD_FEEDBACK, FEEDBACK, TRENDS = "Dashboard", "Add feedback", "Feedback", "Trends & actions"
SETTINGS = "Settings"


# Holds the sidebar and pages, and runs the pipeline on a PipelineWorker.
# validators is I/O's EntryValidator; with no PasswordValidator, admin login is off.
# ai_ready (True/False, or None if not known) is shown in Settings' system status.
class MainWindow(QMainWindow):
    def __init__(self, pipeline, data, logic, validators: EntryValidator, importers,
                 reporter: QtProgressReporter, password: PasswordValidator | None = None,
                 ai_ready: bool | None = None):
        super().__init__()
        self.__pipeline = pipeline
        self.__data = data
        self.__logic = logic
        self.__validators = validators
        self.__importers = importers
        self.__password = password
        self.__builder = RecordBuilder()
        self.__source_file = None
        self.__worker = None
        self.__decisions = []
        self.__actions = []
        self.__new_records = []
        self.__sent_records = []
        self.__sent_decisions = []
        self.__sent_actions = []
        self.__sent_themes = []
        self.__themes_to_add = []
        self.__close_after_run = False
        self.__run_ok = False

        self.setWindowTitle("FeedbackLens")
        # Opens maximized: AppEngine just calls show(), which keeps this state.
        self.setWindowState(Qt.WindowState.WindowMaximized)
        # Fusion and a light palette for the whole app, so Windows dark mode can't darken any box.
        app = QApplication.instance()
        app.setStyle("Fusion")
        app.setPalette(Style.light_palette())
        self.setPalette(Style.light_palette())
        self.setFont(Style.app_font())
        self.setStyleSheet(STYLE)
        self.__dashboard = DashboardPage(data, ai_ready)
        self.__add_feedback = AddFeedbackPage(data, reporter.signals, validators, self.__builder, importers)
        self.__feedback = FeedbackPage(data, logic)
        self.__trends = TrendsPage(data, logic)
        self.__settings = SettingsPage(data, ThemeValidator(logic), ai_ready)
        self.__pages = {DASHBOARD: self.__dashboard, ADD_FEEDBACK: self.__add_feedback,
                        FEEDBACK: self.__feedback, TRENDS: self.__trends, SETTINGS: self.__settings}

        self.__stack = QStackedWidget()
        for page in self.__pages.values():
            self.__stack.addWidget(page)
        self.__sidebar = Sidebar(list(self.__pages))
        self.__sidebar.page_selected.connect(self.show_page)

        self.__sidebar.logout_requested.connect(self.log_out)

        admin = QWidget()
        layout = QHBoxLayout(admin)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.__sidebar)
        layout.addWidget(self.__stack, 1)

        self.__start = StartPage()
        if password is None or not password.is_configured:
            self.__start.disable_login("Admin login is disabled: no admin password is configured.")
        self.__student = StudentFormPage(data.load_known_themes(), validators, self.__builder)
        self.__start.student_chosen.connect(self.show_student_form)
        self.__start.login_requested.connect(self.__on_login)
        self.__student.back_requested.connect(self.show_start)
        self.__student.feedback_submitted.connect(self.__queue_record)
        self.__screens = QStackedWidget()
        for screen in (self.__start, self.__student, admin):
            self.__screens.addWidget(screen)
        self.__admin = admin
        self.setCentralWidget(self.__screens)

        self.__add_feedback.run_requested.connect(self.run_pipeline)
        self.__dashboard.run_requested.connect(self.run_pipeline)
        self.__add_feedback.record_added.connect(self.__queue_record)
        self.__add_feedback.import_ready.connect(self.__on_import)
        self.__feedback.decision_made.connect(self.__on_decision)
        self.__feedback.undo_requested.connect(self.__undo_decision)
        self.__feedback.save_requested.connect(self.__save_changes)
        self.__feedback.discard_requested.connect(self.__discard_decisions)
        self.__trends.action_logged.connect(self.__on_action_logged)
        self.__settings.theme_added.connect(self.__queue_theme)

        self.__view = QtFeedbackView(self, self.__dashboard, self.__feedback, self.__add_feedback,
                                     self.__settings)

        self.__refresh_all()
        self.show_page(DASHBOARD)
        self.show_start()

    # I/O's FeedbackView for this window, for AppEngine and I/O classes to show results with.
    @property
    def view(self) -> QtFeedbackView:
        return self.__view

    def show_start(self) -> None:
        self.__start.reset()
        self.__screens.setCurrentWidget(self.__start)
        self.statusBar().hide()

    def show_student_form(self) -> None:
        self.__student.set_themes(self.__themes())
        self.__student.reset()
        self.__screens.setCurrentWidget(self.__student)
        self.statusBar().hide()

    def show_admin(self) -> None:
        self.__refresh_all()
        self.show_page(DASHBOARD)
        self.__screens.setCurrentWidget(self.__admin)
        self.statusBar().show()

    def log_out(self) -> None:
        self.show_start()

    def show_page(self, name: str) -> None:
        page = self.__pages[name]
        page.refresh()
        self.__stack.setCurrentWidget(page)
        self.__sidebar.select(name)

    # Starts one run on a PipelineWorker. Returns False if one is already running.
    # show_progress opens Add feedback, where the run's progress is shown.
    def run_pipeline(self, session=None, show_progress: bool = True) -> bool:
        if self.__worker is not None:
            return False
        if session is None:
            session = self.__build_session()
        self.__worker = PipelineWorker(self.__pipeline, session)
        self.__worker.completed.connect(self.__on_run_completed)
        self.__worker.failed.connect(self.__on_run_failed)
        self.__worker.finished.connect(self.__on_worker_finished)
        self.__run_ok = False
        self.__add_feedback.set_busy(True)
        self.__feedback.set_busy(True)
        self.__sidebar.set_badge(ADD_FEEDBACK, "● running", "running")
        if show_progress:
            self.show_page(ADD_FEEDBACK)
        self.__worker.start()
        return True

    # Save changes on the Feedback page: the same run as Process, but the admin stays on Feedback.
    def __save_changes(self) -> None:
        if self.run_pipeline(show_progress=False):
            self.statusBar().showMessage("Saving changes… (progress on Add feedback)")

    # A user's close is blocked during a run, and asks first while anything is still queued (G1).
    def closeEvent(self, event) -> None:
        if self.__worker is not None:
            QMessageBox.information(self, "Run in progress",
                                    "Please wait for the current run to finish before closing.")
            event.ignore()
            return
        if event.spontaneous() and not self.may_close():
            event.ignore()
            return
        super().closeEvent(event)

    # True if nothing is queued or the admin chose Close anyway; Process and close starts a run
    # and closes the window once it succeeds.
    def may_close(self) -> bool:
        unsaved = self.unsaved_summary()
        if not unsaved:
            return True
        choice = self._ask_unsaved(unsaved)
        if choice == "close":
            return True
        if choice == "process":
            self.__close_after_run = self.run_pipeline()
        return False

    # "2 entries and 1 review decision", or "" when nothing is waiting for Process.
    def unsaved_summary(self) -> str:
        counts = ((len(self.__new_records), "entry", "entries"),
                  (len(self.__decisions), "review decision", "review decisions"),
                  (len(self.__actions), "action", "actions"),
                  (len(self.__themes_to_add), "new theme", "new themes"))
        parts = [f"{n} {one if n == 1 else many}" for n, one, many in counts if n]
        if len(parts) <= 1:
            return "".join(parts)
        return ", ".join(parts[:-1]) + f" and {parts[-1]}"

    # Asks what to do with unsaved work: "process", "close" or "cancel".
    def _ask_unsaved(self, unsaved: str) -> str:
        box = QMessageBox(QMessageBox.Icon.Warning, "Unsaved changes",
                          f"Not saved yet: {unsaved}. If you close now, they're lost.", parent=self)
        process = box.addButton("Process and close", QMessageBox.ButtonRole.AcceptRole)
        close = box.addButton("Close anyway", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.exec()
        return {process: "process", close: "close"}.get(box.clickedButton(), "cancel")

    # What a run is sent is remembered, so only that is cleared when it ends: work queued
    # while it runs (the other pages stay usable) waits for the next run (G1).
    def __build_session(self) -> SessionResult:
        self.__sent_records = list(self.__new_records)
        self.__sent_decisions = list(self.__decisions)
        self.__sent_actions = list(self.__actions)
        self.__sent_themes = list(self.__themes_to_add)
        return SessionResult(records=list(self.__sent_records), source_file=self.__source_file,
                             decisions=list(self.__sent_decisions), actions=list(self.__sent_actions),
                             themes_to_add=list(self.__sent_themes))

    def __on_login(self, password: str) -> None:
        accepted = self.__password is not None and self.__password.check(password)[0]
        if accepted:
            self.show_admin()
        else:
            self.__start.show_error()

    # A student's entry or an admin's typed entry, saved on the next run.
    def __queue_record(self, record) -> None:
        if any(r.feedback_id == record.feedback_id for r in self.__new_records):
            return
        self.__new_records.append(record)
        self.__update_queue()

    # Undo on the Feedback page: drops the queued decision for that record.
    def __undo_decision(self, feedback_id: str) -> None:
        self.__decisions = [d for d in self.__decisions if d.feedback_id != feedback_id]
        self.__update_queue()
        self.statusBar().showMessage(f"{feedback_id}: change undone", 8000)

    # Discard all on the Feedback page: drops every queued decision (nothing was saved yet).
    def __discard_decisions(self) -> None:
        count = len(self.__decisions)
        self.__decisions.clear()
        self.__update_queue()
        self.statusBar().showMessage(f"{count} {'change' if count == 1 else 'changes'} discarded", 8000)

    # Known themes plus the ones queued in Settings: the run saves those before Logic checks
    # entries, so an entry using one is counted under it.
    def __themes(self) -> list[str]:
        known = self.__data.load_known_themes()
        return known + [theme for theme in self.__queued_themes() if theme not in known]

    # Themes the next run will confirm: those added in Settings, then those a queued review
    # decision keeps as a new theme (GUI-E, 7.4: a variant can be folded into one at once).
    def __queued_themes(self) -> list[str]:
        themes = list(self.__themes_to_add)
        for decision in self.__decisions:
            if (decision.action == ReviewDecision.UPDATE and isinstance(decision.theme, str)
                    and decision.theme.strip() and self.__logic.is_new_theme(decision.theme)):
                name = self.__logic.normalise_theme(decision.theme)
                if name not in themes:
                    themes.append(name)
        return themes

    # A theme added in Settings, saved by the pipeline on the next run; the theme pickers offer it
    # straight away.
    def __queue_theme(self, theme: str) -> None:
        self.__themes_to_add.append(theme)
        self.__settings.set_queued(self.__themes_to_add)
        self.__update_queue()
        self.statusBar().showMessage(f"Theme '{theme}' added (saved on the next run)", 8000)

    # Everything queued for the next run counts towards Process: entries, decisions,
    # actions and new themes. The Feedback page's save bar shows the decisions, and the
    # entries the same run would send to the AI.
    def __update_queue(self) -> None:
        changes = len(self.__decisions) + len(self.__actions) + len(self.__themes_to_add)
        self.__add_feedback.set_new_count(len(self.__new_records), changes)
        self.__dashboard.set_queued(len(self.__new_records))
        themes = self.__queued_themes()
        for page in (self.__add_feedback, self.__feedback, self.__trends):
            page.set_queued_themes(themes)
        waiting = self.__add_feedback.waiting_for_ai() + len(self.__new_records)
        self.__feedback.set_queued(self.__decisions, waiting)

    # An imported file's new records; the run records the file as its source.
    def __on_import(self, result) -> None:
        before = len(self.__new_records)
        for record in result.records:
            self.__queue_record(record)
        added = len(self.__new_records) - before
        self.__source_file = result.source_file
        message = f"{added} {'entry' if added == 1 else 'entries'} from {result.source_file} queued"
        if added < len(result.records):
            message += f" ({len(result.records) - added} already queued)"
        self.statusBar().showMessage(message, 8000)

    # A later decision for the same record replaces the earlier one.
    def __on_decision(self, decision: ReviewDecision) -> None:
        self.__decisions = [d for d in self.__decisions if d.feedback_id != decision.feedback_id]
        self.__decisions.append(decision)
        self.__update_queue()
        if decision.action == ReviewDecision.DELETE:
            what = "delete"
        else:
            what = " / ".join((decision.theme, decision.sentiment, decision.severity))
        self.statusBar().showMessage(f"{decision.feedback_id}: {what} (saved when you press Save changes)", 8000)

    def __on_action_logged(self, action) -> None:
        self.__actions.append(action)
        self.__update_queue()
        self.statusBar().showMessage(f"Action logged for {action.theme} (saved on the next run)", 8000)

    def __on_run_completed(self, context) -> None:
        self.__run_ok = True
        sent = {record.feedback_id for record in self.__sent_records}
        self.__new_records = [r for r in self.__new_records if r.feedback_id not in sent]
        self.__decisions = [d for d in self.__decisions if not any(d is s for s in self.__sent_decisions)]
        self.__actions = [a for a in self.__actions if not any(a is s for s in self.__sent_actions)]
        self.__themes_to_add = [t for t in self.__themes_to_add if t not in self.__sent_themes]
        self.__sent_records, self.__sent_decisions, self.__sent_actions, self.__sent_themes = [], [], [], []
        if not self.__new_records:
            self.__source_file = None
        self.__settings.set_queued(self.__themes_to_add)
        self.__update_queue()
        self.__trends.forget_unsaved(self.__actions)
        message = "Run finished."
        if context.ai_stopped:
            left = context.sent_to_ai - context.classified_count
            message = (f"Run finished, but the AI stopped: {left} "
                       f"{'entry' if left == 1 else 'entries'} left for the next run.")
        self.__add_feedback.progress_panel.show_message(message)
        self.statusBar().showMessage(message.rstrip("."), 8000)

    def __on_run_failed(self, message: str) -> None:
        self.__add_feedback.progress_panel.show_message(f"Run failed: {message}")
        QMessageBox.warning(self, "Run failed", message)

    def __on_worker_finished(self) -> None:
        self.__worker.wait()
        self.__worker.deleteLater()
        self.__worker = None
        self.__add_feedback.set_busy(False)
        self.__feedback.set_busy(False)
        self.__sidebar.set_badge(ADD_FEEDBACK, "")
        self.__refresh_all()
        # Process and close: close only if the run saved everything; after a failure, stay open.
        if self.__close_after_run:
            self.__close_after_run = False
            if self.__run_ok:
                self.close()

    def __refresh_all(self) -> None:
        for page in self.__pages.values():
            page.refresh()
        count = self.__feedback.review_count()
        self.__sidebar.set_badge(FEEDBACK, f"{count} to review" if count else "", "warn")
