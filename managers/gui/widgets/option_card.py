# OptionCard: one answer on the student form (e.g. "Negative", or "High" with a description).

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QRadioButton, QSizePolicy, QVBoxLayout

from ..style import restyle


# A bordered card holding a radio button and an optional description.
class OptionCard(QFrame):
    def __init__(self, value: str, title: str, description: str = "", tone: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("optionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("tone", tone)
        self.setProperty("selected", False)
        self.__value = value
        self.__radio = QRadioButton(title)
        self.__radio.toggled.connect(self.__on_toggled)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        layout.addWidget(self.__radio)
        if description:
            text = QLabel(description)
            text.setObjectName("optionText")
            text.setWordWrap(True)
            text.setContentsMargins(24, 0, 0, 0)
            layout.addWidget(text)
        layout.addStretch()
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(120)

    @property
    def value(self) -> str:
        return self.__value

    @property
    def radio(self) -> QRadioButton:
        return self.__radio

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.__radio.setChecked(True)
        super().mousePressEvent(event)

    def __on_toggled(self, checked: bool) -> None:
        self.setProperty("selected", checked)
        margin = (13, 11) if checked else (14, 12)
        self.layout().setContentsMargins(margin[0], margin[1], margin[0], margin[1])
        restyle(self)
        restyle(self.__radio)
