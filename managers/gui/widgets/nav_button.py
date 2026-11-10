# NavButton: one sidebar link, with an optional badge on the right.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from ..style import restyle
from .pill import Pill


# A checkable button whose name and badge are labels, so the badge can be a Pill.
class NavButton(QPushButton):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(name)

        self.__name = QLabel(name)
        self.__name.setObjectName("navText")
        self.__badge = Pill()
        self.__badge.hide()
        for label in (self.__name, self.__badge):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(8)
        layout.addWidget(self.__name)
        layout.addStretch()
        layout.addWidget(self.__badge)
        self.toggled.connect(self.__on_toggled)

    @property
    def name(self) -> str:
        return self.__name.text()

    @property
    def badge_text(self) -> str:
        return self.__badge.text()

    # Empty text hides the badge.
    def set_badge(self, text: str, kind: str = "warn") -> None:
        self.__badge.setText(text)
        self.__badge.set_kind(kind)
        self.__badge.setVisible(bool(text))

    def __on_toggled(self, checked: bool) -> None:
        self.__name.setProperty("active", checked)
        restyle(self.__name)
