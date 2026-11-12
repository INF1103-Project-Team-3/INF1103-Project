# Sidebar: page navigation for the admin window.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QVBoxLayout, QWidget

from .nav_button import NavButton

WIDTH = 260


# One NavButton per page. Emits page_selected(name) when one is clicked.
class Sidebar(QWidget):
    page_selected = Signal(str)
    logout_requested = Signal()

    def __init__(self, page_names: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.__buttons = {}
        self.__group = QButtonGroup(self)
        self.__group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(4)
        app_name = QLabel("FeedbackLens")
        app_name.setObjectName("appName")
        layout.addWidget(app_name)

        for name in page_names:
            button = NavButton(name)
            button.clicked.connect(lambda _checked=False, page=name: self.page_selected.emit(page))
            self.__group.addButton(button)
            self.__buttons[name] = button
            layout.addWidget(button)
        layout.addStretch()
        log_out = NavButton("Log out")
        log_out.setCheckable(False)
        log_out.clicked.connect(self.logout_requested)
        layout.addWidget(log_out)

    # Highlights a page's button without emitting page_selected.
    def select(self, name: str) -> None:
        self.__buttons[name].setChecked(True)

    # Shows a badge on a page's link, e.g. "5 to review"; empty text removes it.
    def set_badge(self, name: str, badge: str, kind: str = "warn") -> None:
        self.__buttons[name].set_badge(badge, kind)

    def badge(self, name: str) -> str:
        return self.__buttons[name].badge_text
