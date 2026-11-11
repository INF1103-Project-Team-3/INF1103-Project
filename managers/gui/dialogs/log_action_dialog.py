# LogActionDialog: the pop-up that records an action against a theme.

import uuid
from datetime import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from managers.models import Action

from ..widgets.combo_box import ComboBox


# Builds an Action.
class LogActionDialog(QDialog):
    def __init__(self, known_themes: list[str], parent=None, theme: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Log an action")
        self.setMinimumWidth(520)
        self.__action = None

        self.__theme = ComboBox()
        self.__theme.setObjectName("themeBox")
        self.__theme.addItems(known_themes)
        if theme:
            self.__theme.setCurrentText(theme)
        self.__description = QLineEdit()
        self.__description.setObjectName("descriptionEdit")
        self.__description.setPlaceholderText("e.g. Upgraded the library Wi-Fi access points")
        self.__date = QDateEdit(QDate.currentDate())
        self.__date.setObjectName("dateEdit")
        self.__date.setCalendarPopup(True)
        self.__date.setDisplayFormat("yyyy-MM-dd")
        self.__keyword = QLineEdit()
        self.__keyword.setObjectName("keywordEdit")
        self.__keyword.setPlaceholderText("Optional: only measure feedback containing this word")
        self.__error = QLabel("")
        self.__error.setObjectName("errorText")
        self.__error.setWordWrap(True)
        self.__error.hide()
        for field in (self.__theme, self.__description, self.__date, self.__keyword):
            field.setProperty("dialogField", True)
            field.setMinimumHeight(44)

        title = QLabel("Log an action")
        title.setObjectName("dialogTitle")
        hint = QLabel("The result shows \"Too early\" until 14 days have passed.")
        hint.setObjectName("statusLine")
        hint.setWordWrap(True)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save action")
        save.setObjectName("primaryButton")
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(title)
        for label, field in (("Theme", self.__theme), ("What was done?", self.__description),
                             ("Date done", self.__date), ("Keyword (optional)", self.__keyword)):
            layout.addLayout(self.__labelled(label, field))
        layout.addWidget(hint)
        layout.addWidget(self.__error)
        layout.addLayout(buttons)

    # A bold label above its field, as in the wireframe.
    @staticmethod
    def __labelled(text: str, field) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(6)
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        box.addWidget(label)
        box.addWidget(field)
        return box

    # The Action built when Save succeeded, otherwise None.
    @property
    def action(self) -> Action | None:
        return self.__action

    @property
    def error_text(self) -> str:
        return self.__error.text()

    def accept(self) -> None:
        if not self.__description.text().strip():
            self.__show_error("Add a description of what was done.")
            return
        try:
            action = Action(
                action_id=f"act_{uuid.uuid4().hex[:8]}",
                theme=self.__theme.currentText(),
                description=self.__description.text(),
                action_date=self.__date.date().toString("yyyy-MM-dd"),
                keyword=self.__keyword.text() or None,
                logged_at=datetime.now().isoformat(timespec="seconds"),
            )
        except ValueError as error:
            self.__show_error(str(error))
            return
        self.__action = action
        super().accept()

    def __show_error(self, text: str) -> None:
        self.__error.setText(text)
        self.__error.show()
