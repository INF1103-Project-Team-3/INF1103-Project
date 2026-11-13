# SettingsPage: known themes, Add theme (queued for the next run) and the read-only system status.

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from managers.io_manager import ThemeValidator
from managers.models import THEMES, UNCLEAR_THEME

from ..widgets.card import Card
from ..widgets.pill import Pill
from .base_page import BasePage

AI_STATUS = {True: "ready", False: "not configured (no API key)", None: "not reported"}
THEME_COLUMNS = 3


# Emits theme_added(theme) for MainWindow to queue in the SessionResult; the pipeline saves
# it (add_known_theme, then Logic and the AI) on the next run. Nothing is removed or renamed.
class SettingsPage(BasePage):
    theme_added = Signal(str)

    def __init__(self, data, theme_validator: ThemeValidator, ai_ready: bool | None = None, parent=None):
        super().__init__("Settings", "Themes everyone can pick, and how the system is doing.", parent)
        self.__data = data
        self.__validator = theme_validator
        self.__ai_ready = ai_ready
        self.__queued = []

        self.__themes_card = Card("Known themes", padding=20, spacing=10)
        self.__themes_body = self.__box(self.__themes_card)
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        self.__new_theme = QLineEdit()
        self.__new_theme.setObjectName("newThemeBox")
        self.__new_theme.setPlaceholderText("New theme name, e.g. Parking Fees")
        self.__new_theme.returnPressed.connect(self.add_theme)
        add = QPushButton("Add theme")
        add.setObjectName("primaryButton")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self.add_theme)
        add_row.addWidget(self.__new_theme, 1)
        add_row.addWidget(add)
        self.__feedback = QLabel("")
        self.__feedback.setObjectName("statusLine")
        self.__feedback.setWordWrap(True)
        note = QLabel("A new theme is saved when you next press Process, then students can pick it and "
                      "the AI uses it. Themes can't be removed or renamed here.")
        note.setObjectName("smallNote")
        note.setWordWrap(True)
        self.__themes_card.body.addLayout(add_row)
        self.__themes_card.body.addWidget(self.__feedback)
        self.__themes_card.body.addWidget(note)

        self.__status_card = Card("System status (read only)", padding=20, spacing=10)
        self.__status_body = self.__box(self.__status_card)
        self.content_layout.addWidget(self.__themes_card)
        self.content_layout.addWidget(self.__status_card)
        self.content_layout.addStretch()

    # Themes queued in this session (MainWindow keeps the list and clears it after a run).
    def set_queued(self, themes: list[str]) -> None:
        self.__queued = list(themes)
        self.refresh()

    def refresh(self) -> None:
        self.show_values(self.__data.load_known_themes(), self.__queued, self.status())

    # Shows the given values (QtFeedbackView.show_settings uses this too).
    def show_values(self, known_themes, themes_to_add, status) -> None:
        body = self.__clear(self.__themes_body)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        for index, theme in enumerate(known_themes):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(QLabel(theme))
            row.addWidget(Pill("base" if theme in THEMES else "added", "neutral" if theme in THEMES else "info"))
            row.addStretch()
            grid.addLayout(row, index // THEME_COLUMNS, index % THEME_COLUMNS)
        body.addLayout(grid)
        if themes_to_add:
            waiting = QHBoxLayout()
            waiting.setSpacing(6)
            waiting.addWidget(QLabel("Saved on the next run:"))
            for theme in themes_to_add:
                waiting.addWidget(Pill(theme, "caution"))
            waiting.addStretch()
            body.addLayout(waiting)

        status_body = self.__clear(self.__status_body)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        for row, (label, value) in enumerate(status.items()):
            name = QLabel(label)
            name.setObjectName("fieldName")
            grid.addWidget(name, row, 0)
            grid.addWidget(QLabel(str(value)), row, 1)
        grid.setColumnStretch(1, 1)
        status_body.addLayout(grid)

    # Checks the typed theme like the terminal's Settings, then emits theme_added.
    def add_theme(self, *_args) -> None:
        theme, error = self.__validator.check(self.__new_theme.text())
        known = {name.lower() for name in [*self.__data.load_known_themes(), *self.__queued]}
        if error:
            self.__say(f"Can't add it: {error}.")
        elif theme == UNCLEAR_THEME:
            self.__say("That isn't a usable theme name.")
        elif theme.lower() in known:
            self.__say(f"'{theme}' is already a known theme.")
        else:
            self.__new_theme.clear()
            self.theme_added.emit(theme)
            self.__say(f"'{theme}' will be added when you next press Process.")

    # The read-only facts: the terminal's four, plus tokens used today and the data folder (G3, A33).
    def status(self) -> dict[str, str]:
        runs = self.__data.load_history()
        last = runs[-1]["finished_at"] if runs else ""
        return {
            "AI connection": AI_STATUS.get(self.__ai_ready, AI_STATUS[None]),
            "Processed records": str(len(self.__data.load_records())),
            "Waiting for review": str(len(self.__data.load_review_queue())),
            "Last analysis run": last or "never",
            "Tokens used today": self.__tokens_today(),
            "Data folder": self.__data.data_folder or "not reported",
        }

    # Today's (UTC) total across every key, as the AI's token ledger counts it.
    def __tokens_today(self) -> str:
        log = self.__data.load_token_log()
        if log is None:
            return "log unreadable"
        today = datetime.now(timezone.utc).date().isoformat()
        total = sum(sum((key.get("totals") or {}).values()) for key in (log.get(today) or {}).values()
                    if isinstance(key, dict))
        return f"{total:,} (local estimate)"

    def __say(self, text: str) -> None:
        self.__feedback.setText(text)

    @staticmethod
    def __box(card: Card) -> QVBoxLayout:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        card.body.addWidget(holder)
        return layout

    @classmethod
    def __clear(cls, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout() is not None:
                cls.__clear(item.layout())
                item.layout().deleteLater()
        return layout
