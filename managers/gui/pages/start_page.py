# StartPage: choose student feedback or admin login.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..style import restyle
from ..widgets.choice_card import ChoiceCard

WIDTH = 640


class StartPage(QWidget):
    student_chosen = Signal()
    login_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        title = QLabel("FeedbackLens")
        title.setObjectName("startTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Student feedback, sorted and analysed.")
        subtitle.setObjectName("startSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.__student = ChoiceCard("Student", "Share feedback", "No login needed.")
        self.__admin = ChoiceCard("Staff", "Admin login", "Dashboard, feedback, trends and actions.")
        self.__student.clicked.connect(self.student_chosen)
        self.__admin.clicked.connect(self.show_login)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self.__student)
        cards.addWidget(self.__admin)

        self.__login = QFrame()
        self.__login.setObjectName("loginCard")
        label = QLabel("Admin password")
        label.setObjectName("questionLabel")
        self.__password = QLineEdit()
        self.__password.setObjectName("passwordBox")
        self.__password.setEchoMode(QLineEdit.EchoMode.Password)
        self.__password.returnPressed.connect(self.__on_login)
        self.__error = QLabel("Incorrect password. Please try again.")
        self.__error.setObjectName("errorText")
        self.__error.hide()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("largeButton")
        log_in = QPushButton("Log in")
        log_in.setObjectName("bigPrimaryButton")
        cancel.clicked.connect(self.reset)
        log_in.clicked.connect(self.__on_login)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(log_in)
        form = QVBoxLayout(self.__login)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(14)
        form.addWidget(label)
        form.addWidget(self.__password)
        form.addWidget(self.__error)
        form.addLayout(buttons)

        column = QWidget()
        column.setMaximumWidth(WIDTH)
        inner = QVBoxLayout(column)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(28)
        heading = QVBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        inner.addLayout(heading)
        inner.addLayout(cards)
        inner.addWidget(self.__login)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(column, 1)
        row.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 40, 16, 40)
        layout.addStretch()
        layout.addLayout(row)
        layout.addStretch(2)
        self.reset()

    def show_login(self) -> None:
        self.__admin.set_selected(True)
        self.__login.show()
        self.__password.setFocus()

    def show_error(self) -> None:
        self.__error.show()
        self.__set_error(True)
        self.__password.selectAll()
        self.__password.setFocus()

    def reset(self) -> None:
        self.__admin.set_selected(False)
        self.__login.hide()
        self.__error.hide()
        self.__password.clear()
        self.__set_error(False)

    def __on_login(self, *_args) -> None:
        self.login_requested.emit(self.__password.text())

    def __set_error(self, error: bool) -> None:
        self.__password.setProperty("error", error)
        restyle(self.__password)
