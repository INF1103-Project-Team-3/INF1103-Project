# QtFeedbackView: I/O's FeedbackView for the GUI; each method shows its data on an existing page.

from PySide6.QtWidgets import QMessageBox

from managers.io_manager import FeedbackView

MESSAGE_MS = 8000


# Call from the UI thread only. Pages are switched inside the admin area; if no admin is
# logged in, the page is updated and appears after login (it never skips the login).
class QtFeedbackView(FeedbackView):
    def __init__(self, window, dashboard, feedback, add_feedback):
        self.__window = window
        self.__dashboard = dashboard
        self.__feedback = feedback
        self.__add_feedback = add_feedback
        self.__notice = None

    # The last notice box shown, or None.
    @property
    def notice_box(self) -> QMessageBox | None:
        return self.__notice

    def show_message(self, message: str) -> None:
        self.__window.statusBar().showMessage(message, MESSAGE_MS)

    # A warning box that doesn't block the caller, plus the status bar.
    def show_notice(self, notice: str) -> None:
        if self.__notice is not None:
            self.__notice.close()
        self.__notice = QMessageBox(QMessageBox.Icon.Warning, "Notice", notice, parent=self.__window)
        self.__notice.open()
        self.__window.statusBar().showMessage(notice, MESSAGE_MS)

    def show_dashboard(self, result, trend, summary, queue) -> None:
        self.__window.show_page(self.__dashboard.title)
        self.__dashboard.show_values(result, trend, summary, queue)

    def show_search_results(self, records) -> None:
        self.__window.show_page(self.__feedback.title)
        self.__feedback.show_records(records)
        count = len(records)
        self.show_message(f"{count} {'entry' if count == 1 else 'entries'} found")

    def show_review_entry(self, record, position: int, total: int) -> None:
        self.__window.show_page(self.__feedback.title)
        self.__feedback.show_review_entry(record)
        self.show_message(f"Reviewing {position} of {total}: {record.feedback_id}")

    def show_rejected_rows(self, rejected) -> None:
        self.__window.show_page(self.__add_feedback.title)
        self.__add_feedback.show_import_tab()
        self.__add_feedback.import_panel.show_rejected(rejected)
