# MainWindow: the admin window (sidebar, pages, background runs).

from types import SimpleNamespace

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from .pages.add_feedback_page import AddFeedbackPage
from .pages.dashboard_page import DashboardPage
from .pages.feedback_page import FeedbackPage
from .pages.start_page import StartPage
from .pages.student_form_page import StudentFormPage
from .pages.trends_page import TrendsPage
from .pipeline_worker import PipelineWorker
from .qt_progress_reporter import QtProgressReporter
from .style import STYLE, app_font, light_palette
from .widgets.sidebar import Sidebar

DASHBOARD, ADD_FEEDBACK, FEEDBACK, TRENDS = "Dashboard", "Add feedback", "Feedback", "Trends & actions"


# Holds the sidebar and pages, and runs the pipeline on a PipelineWorker.
class MainWindow(QMainWindow):
    def __init__(self, pipeline, data, logic, validators, importers, reporter: QtProgressReporter,
                 check_password=None):
        super().__init__()
        self.__pipeline = pipeline
        self.__data = data
        self.__logic = logic
        self.__validators = validators
        self.__importers = importers
        self.__check_password = check_password
        self.__worker = None
        self.__decisions = []
        self.__actions = []
        self.__new_records = []
        self.__sent_records = []

        self.setWindowTitle("FeedbackLens")
        self.setPalette(light_palette())
        self.setFont(app_font())
        self.setStyleSheet(STYLE)
        self.__dashboard = DashboardPage(data)
        self.__add_feedback = AddFeedbackPage(data, reporter.signals)
        self.__feedback = FeedbackPage(data)
        self.__trends = TrendsPage(data)
        self.__pages = {DASHBOARD: self.__dashboard, ADD_FEEDBACK: self.__add_feedback,
                        FEEDBACK: self.__feedback, TRENDS: self.__trends}

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
        self.__student = StudentFormPage(data.load_known_themes())
        self.__start.student_chosen.connect(self.show_student_form)
        self.__start.login_requested.connect(self.__on_login)
        self.__student.back_requested.connect(self.show_start)
        self.__student.feedback_submitted.connect(self.__on_feedback_submitted)
        self.__screens = QStackedWidget()
        for screen in (self.__start, self.__student, admin):
            self.__screens.addWidget(screen)
        self.__admin = admin
        self.setCentralWidget(self.__screens)

        self.__add_feedback.run_requested.connect(self.run_pipeline)
        self.__feedback.decision_made.connect(self.__on_decision)
        self.__trends.action_logged.connect(self.__on_action_logged)

        self.__refresh_all()
        self.show_page(DASHBOARD)
        self.show_start()

    def show_start(self) -> None:
        self.__start.reset()
        self.__screens.setCurrentWidget(self.__start)
        self.statusBar().hide()

    def show_student_form(self) -> None:
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
    def run_pipeline(self, session=None) -> bool:
        if self.__worker is not None:
            return False
        if session is None:
            session = self.__build_session()
        self.__worker = PipelineWorker(self.__pipeline, session)
        self.__worker.completed.connect(self.__on_run_completed)
        self.__worker.failed.connect(self.__on_run_failed)
        self.__worker.finished.connect(self.__on_worker_finished)
        self.__add_feedback.set_busy(True)
        self.__sidebar.set_badge(ADD_FEEDBACK, "● running", "running")
        self.show_page(ADD_FEEDBACK)
        self.__worker.start()
        return True

    def closeEvent(self, event) -> None:
        if self.__worker is not None:
            QMessageBox.information(self, "Run in progress",
                                    "Please wait for the current run to finish before closing.")
            event.ignore()
            return
        super().closeEvent(event)

    def __build_session(self):
        self.__sent_records = list(self.__new_records)
        return SimpleNamespace(records=list(self.__sent_records), source_file=None,
                               decisions=list(self.__decisions), actions=list(self.__actions))

    def __on_login(self, password: str) -> None:
        if self.__check_password is not None and self.__check_password(password):
            self.show_admin()
        else:
            self.__start.show_error()

    def __on_feedback_submitted(self, record) -> None:
        self.__new_records.append(record)
        self.__add_feedback.set_new_count(len(self.__new_records))

    def __on_decision(self, feedback_id: str, action: str, values) -> None:
        self.__decisions.append(SimpleNamespace(feedback_id=feedback_id, action=action, values=values))
        what = "delete" if action == "delete" else " / ".join(values)
        self.statusBar().showMessage(f"{feedback_id}: {what} (saved on the next run)", 8000)

    def __on_action_logged(self, action) -> None:
        self.__actions.append(action)
        self.statusBar().showMessage(f"Action logged for {action.theme} (saved on the next run)", 8000)

    def __on_run_completed(self, context) -> None:
        self.__decisions.clear()
        self.__actions.clear()
        sent = {record.feedback_id for record in self.__sent_records}
        self.__new_records = [r for r in self.__new_records if r.feedback_id not in sent]
        self.__sent_records = []
        self.__add_feedback.set_new_count(len(self.__new_records))
        self.__trends.forget_unsaved()
        self.__add_feedback.progress_panel.show_message("Run finished.")
        self.statusBar().showMessage("Run finished", 8000)

    def __on_run_failed(self, message: str) -> None:
        self.__add_feedback.progress_panel.show_message(f"Run failed: {message}")
        QMessageBox.warning(self, "Run failed", message)

    def __on_worker_finished(self) -> None:
        self.__worker.deleteLater()
        self.__worker = None
        self.__add_feedback.set_busy(False)
        self.__sidebar.set_badge(ADD_FEEDBACK, "")
        self.__refresh_all()

    def __refresh_all(self) -> None:
        for page in self.__pages.values():
            page.refresh()
        count = self.__feedback.review_count()
        self.__sidebar.set_badge(FEEDBACK, f"{count} to review" if count else "", "warn")
