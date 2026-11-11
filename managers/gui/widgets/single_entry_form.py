# SingleEntryForm: the admin's form for typing in one entry (Add feedback, Single entry tab).

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout

from managers.io_manager import EntryValidator, RecordBuilder
from managers.models import SENTIMENTS, SEVERITIES

from .card import Card
from .combo_box import ComboBox

OTHER = "Other…"
SOURCE = "admin entry"


# Checks the entry with I/O's EntryValidator, builds it with RecordBuilder, emits record_added.
class SingleEntryForm(Card):
    record_added = Signal(object)

    def __init__(self, validator: EntryValidator, builder: RecordBuilder, parent=None):
        super().__init__(padding=20, spacing=14, parent=parent)
        self.__validator = validator
        self.__builder = builder

        self.__text = QPlainTextEdit()
        self.__text.setObjectName("entryTextBox")
        self.__text.setPlaceholderText("The feedback, as the student wrote it…")
        self.__text.setMinimumHeight(110)
        self.__theme = ComboBox()
        self.__theme.setObjectName("entryTheme")
        self.__theme.setPlaceholderText("Choose…")
        self.__theme.currentTextChanged.connect(self.__on_theme_changed)
        self.__other = QLineEdit()
        self.__other.setObjectName("entryOtherTheme")
        self.__other.setPlaceholderText("Type the new theme")
        self.__other.hide()
        self.__sentiment = self.__choices("entrySentiment", SENTIMENTS)
        self.__severity = self.__choices("entrySeverity", SEVERITIES)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for column, (label, field) in enumerate((("Theme", self.__theme), ("Sentiment", self.__sentiment),
                                                 ("Severity", self.__severity))):
            name = QLabel(label)
            name.setObjectName("fieldLabel")
            grid.addWidget(name, 0, column)
            grid.addWidget(field, 1, column)
            grid.setColumnStretch(column, 1)
        grid.addWidget(self.__other, 2, 0)

        text_label = QLabel("Feedback")
        text_label.setObjectName("fieldLabel")
        self.__error = QLabel("")
        self.__error.setObjectName("errorText")
        self.__error.setWordWrap(True)
        self.__error.hide()
        self.__done = QLabel("")
        self.__done.setObjectName("statusLine")
        add = QPushButton("Add to queue")
        add.setObjectName("primaryButton")
        add.clicked.connect(self.submit)
        buttons = QHBoxLayout()
        buttons.addWidget(self.__done, 1)
        buttons.addWidget(add)

        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(text_label)
        column.addWidget(self.__text)
        self.body.addLayout(column)
        self.body.addLayout(grid)
        self.body.addWidget(self.__error)
        self.body.addLayout(buttons)
        self.set_themes([])

    # Known themes plus "Other…", keeping the current choice when it is still listed.
    def set_themes(self, themes: list[str]) -> None:
        current = self.__theme.currentText()
        self.__theme.blockSignals(True)
        self.__theme.clear()
        self.__theme.addItems([*themes, OTHER])
        self.__theme.setCurrentIndex(self.__theme.findText(current) if current in themes else -1)
        self.__theme.blockSignals(False)
        self.__on_theme_changed(self.__theme.currentText())

    def submit(self, *_args) -> None:
        theme = self.__other.text() if self.__theme.currentText() == OTHER else self.__theme.currentText()
        raw = {"text": self.__text.toPlainText(), "theme": theme,
               "sentiment": self.__sentiment.currentText(), "severity": self.__severity.currentText()}
        entry, error = self.__validator.validate(raw)
        if error:
            self.__error.setText(f"Can't add this entry: {error}.")
            self.__error.show()
            return
        record = self.__builder.build(entry, source_file=SOURCE)
        self.record_added.emit(record)
        self.__done.setText(f"Added {record.feedback_id} ({entry['theme']}) to the queue.")
        self.__text.clear()
        self.__other.clear()
        self.__error.hide()

    def __on_theme_changed(self, text: str) -> None:
        self.__other.setVisible(text == OTHER)

    @staticmethod
    def __choices(name: str, values) -> ComboBox:
        box = ComboBox()
        box.setObjectName(name)
        box.addItems(list(values))
        box.setPlaceholderText("Choose…")
        box.setCurrentIndex(-1)
        return box
