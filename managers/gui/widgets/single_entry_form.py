# SingleEntryForm: the admin's form for typing in one entry (Add feedback, Single entry tab).

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from managers.io_manager import EntryValidator, RecordBuilder
from managers.models import SENTIMENTS, SEVERITIES

from .card import Card
from .combo_box import ComboBox
from .theme_picker import OTHER, ThemePicker  # noqa: F401  (OTHER re-exported for callers)

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
        self.__theme = ThemePicker("entryTheme")
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
            grid.addWidget(field, 1, column, Qt.AlignmentFlag.AlignTop)
            grid.setColumnStretch(column, 1)

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

    @property
    def theme_picker(self) -> ThemePicker:
        return self.__theme

    def set_themes(self, themes: list[str]) -> None:
        self.__theme.set_themes(themes)

    def submit(self, *_args) -> None:
        raw = {"text": self.__text.toPlainText(), "theme": self.__theme.theme(),
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
        if self.__theme.is_other():
            self.__theme.clear()
        self.__error.hide()

    @staticmethod
    def __choices(name: str, values) -> ComboBox:
        box = ComboBox()
        box.setObjectName(name)
        box.addItems(list(values))
        box.setPlaceholderText("Choose…")
        box.setCurrentIndex(-1)
        return box
