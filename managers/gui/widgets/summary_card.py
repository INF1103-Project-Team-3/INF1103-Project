# SummaryCard: the AI's overall summary and its suggested actions (or the rule-based ones), each loggable.

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from managers.logic_manager import ActionSuggestions

from .card import Card


# Rule-based actions (D21) replace the AI's when the pipeline saved some; the AI's summary
# and date stay. "Log this action" emits log_action_requested(theme, suggestion).
class SummaryCard(Card):
    log_action_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__("AI summary and suggested actions", padding=20, spacing=10, parent=parent)
        holder = QWidget()
        self.__body = QVBoxLayout(holder)
        self.__body.setContentsMargins(0, 0, 0, 0)
        self.__body.setSpacing(8)
        self.body.addWidget(holder)

    def show_summary(self, summary, fallback) -> None:
        body = self.__clear(self.__body)
        if summary is None:
            body.addWidget(self.__label("No AI summary yet. It is written after a run that classifies new entries.",
                                        "mutedText"))
        else:
            body.addWidget(self.__label(summary.overall_summary))
        if fallback is not None:
            self.__add_actions(body, ActionSuggestions.LABEL, fallback.theme_actions)
            body.addWidget(self.__label(f"Rule-based suggestions from {self.__date(fallback.created_at)}.",
                                        "smallNote"))
        elif summary is not None:
            self.__add_actions(body, "Suggested actions", summary.theme_actions)
        if summary is not None:
            body.addWidget(self.__label(f"Summary written by the AI on {self.__date(summary.created_at)}.",
                                        "smallNote"))

    def __add_actions(self, body, title: str, theme_actions) -> None:
        actions = [a for a in theme_actions if a.get("suggested_action")]
        if not actions:
            return
        body.addWidget(self.__label(title, "fieldLabel"))
        for action in actions:
            theme, text = action.get("theme", ""), action["suggested_action"]
            row = QHBoxLayout()
            log = QPushButton("Log this action")
            log.setObjectName("linkButton")
            log.setCursor(Qt.CursorShape.PointingHandCursor)
            log.clicked.connect(lambda _checked=False, t=theme, d=text: self.log_action_requested.emit(t, d))
            row.addWidget(self.__label(f"<b>{theme}:</b> {text}"), 1)
            row.addWidget(log, 0, Qt.AlignmentFlag.AlignTop)
            body.addLayout(row)

    @staticmethod
    def __label(text: str, name: str = "") -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        if name:
            label.setObjectName(name)
        return label

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

    # "2026-11-11T18:41:29" -> "11 Nov 2026".
    @staticmethod
    def __date(text) -> str:
        try:
            moment = datetime.fromisoformat(str(text))
        except ValueError:
            return str(text or "an unknown date")
        return f"{moment.day} {moment:%b %Y}"
