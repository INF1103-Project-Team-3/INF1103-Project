# BasePage: what every admin page has in common.

from abc import abstractmethod

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..qt_abc_meta import QtABCMeta


# Abstract admin page: title, header and scrollable content.
class BasePage(QWidget, metaclass=QtABCMeta):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        cls = type(self)
        missing = sorted(name for name in dir(cls)
                         if getattr(getattr(cls, name, None), "__isabstractmethod__", False))
        if missing:
            raise TypeError(f"Can't instantiate abstract class {cls.__name__} "
                            f"without an implementation for: {', '.join(missing)}")
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.__title = title

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        heading_box = QVBoxLayout()
        heading_box.setSpacing(4)
        heading_box.addWidget(heading)
        self.__subtitle = QLabel(subtitle)
        self.__subtitle.setObjectName("pageSubtitle")
        self.__subtitle.setWordWrap(True)
        self.__subtitle.setVisible(bool(subtitle))
        heading_box.addWidget(self.__subtitle)

        self.__header = QHBoxLayout()
        self.__header.setSpacing(12)
        self.__header.addLayout(heading_box, 1)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)
        layout.addLayout(self.__header)
        self.__content = QVBoxLayout()
        self.__content.setSpacing(16)
        layout.addLayout(self.__content, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    @property
    def title(self) -> str:
        return self.__title

    # Where a subclass puts its widgets.
    @property
    def content_layout(self) -> QVBoxLayout:
        return self.__content

    def set_subtitle(self, text: str) -> None:
        self.__subtitle.setText(text)
        self.__subtitle.setVisible(bool(text))

    # Puts a widget (usually the page's main button) at the top right.
    def add_header_widget(self, widget: QWidget) -> None:
        self.__header.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)

    # Reload this page's data (read-only Data calls only).
    @abstractmethod
    def refresh(self) -> None:
        pass
