# Card: the white rounded box every page section sits in.

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..style import restyle


# A white box with a 1px border.
class Card(QFrame):
    def __init__(self, title: str = "", padding: int = 20, spacing: int = 14, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.__layout = QVBoxLayout(self)
        self.__layout.setContentsMargins(padding, padding, padding, padding)
        self.__layout.setSpacing(spacing)
        self.__header = QHBoxLayout()
        self.__header.setSpacing(8)
        if title:
            heading = QLabel(title)
            heading.setObjectName("cardTitle")
            self.__header.addWidget(heading)
            self.__header.addStretch()
            self.__layout.addLayout(self.__header)

    @property
    def body(self) -> QVBoxLayout:
        return self.__layout

    @property
    def header_layout(self) -> QHBoxLayout:
        return self.__header

    # "" for a plain card, "critical" for the light orange one.
    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        restyle(self)
        for child in self.findChildren(QWidget):
            restyle(child)
