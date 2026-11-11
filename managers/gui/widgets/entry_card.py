# EntryCard: one feedback entry in the Feedback page's list.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ..style import restyle
from .pill import Pill
from .record_tags import is_critical, record_tags, short_date

PREVIEW_CHARS = 110


# Tags, the first lines of the text and a meta line. Emits clicked(feedback_id).
class EntryCard(QFrame):
    clicked = Signal(str)

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setObjectName("entryCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.__feedback_id = record.feedback_id
        self.setProperty("critical", is_critical(record) and record.needs_review)
        self.setProperty("selected", False)

        tags = QHBoxLayout()
        tags.setSpacing(6)
        for text, kind in record_tags(record):
            tags.addWidget(Pill(text, kind))
        tags.addStretch()

        # The AI's one-liner when there is one (D18), otherwise the student's text.
        shown = (record.ai or {}).get("summary") or record.text
        preview = shown[:PREVIEW_CHARS].rstrip() + ("…" if len(shown) > PREVIEW_CHARS else "")
        text = QLabel(preview)
        text.setObjectName("entryText")
        text.setWordWrap(True)
        meta = QLabel(self.__meta_line(record))
        meta.setObjectName("entryMeta")
        meta.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addLayout(tags)
        layout.addWidget(text)
        layout.addWidget(meta)

    @property
    def feedback_id(self) -> str:
        return self.__feedback_id

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        margin = 11 if selected else 12
        self.layout().setContentsMargins(margin, margin, margin, margin)
        restyle(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.__feedback_id)
        super().mousePressEvent(event)

    @staticmethod
    def __meta_line(record) -> str:
        ai = record.ai or {}
        if record.needs_review and ai.get("theme") and ai["theme"] != record.user["theme"]:
            return f"{record.feedback_id} · Student: {record.user['theme']} · AI: {ai['theme']}"
        theme = record.theme or record.user["theme"]
        return f"{record.feedback_id} · {theme} · {short_date(record.timestamp)}"
