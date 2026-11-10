# ChoiceCard: a big clickable card on the start page ("Share feedback", "Admin login").

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ..style import restyle


# A small heading (kicker), a title and one line of text. Emits clicked().
class ChoiceCard(QFrame):
    clicked = Signal()

    def __init__(self, kicker: str, title: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("choiceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)
        self.setAccessibleName(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        for content, name in ((kicker.upper(), "choiceKicker"), (title, "choiceTitle"), (text, "choiceText")):
            label = QLabel(content)
            label.setObjectName(name)
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        margin = 23 if selected else 24
        self.layout().setContentsMargins(margin, margin, margin, margin)
        restyle(self)
        for child in self.findChildren(QLabel):
            restyle(child)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
