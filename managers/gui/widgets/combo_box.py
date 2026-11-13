# ComboBox: a dropdown whose list follows the style sheet and fits its longest item.

from PySide6.QtWidgets import QComboBox, QListView

POPUP_PADDING = 48


class ComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.setMaxVisibleItems(12)

    def showPopup(self) -> None:
        widest = max((self.fontMetrics().horizontalAdvance(self.itemText(i)) for i in range(self.count())),
                     default=0)
        self.view().setMinimumWidth(max(self.width(), widest + POPUP_PADDING))
        super().showPopup()
