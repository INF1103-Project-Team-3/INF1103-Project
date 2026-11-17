# ThemePicker: a dropdown of the known themes plus "Other…", which opens a text box for a new theme.

from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from .combo_box import ComboBox

OTHER = "Other…"


# theme() gives the chosen theme, the typed one under "Other…", or "" if nothing is chosen.
# It doesn't check the label: the form passes it to I/O's ThemeValidator through EntryValidator.
class ThemePicker(QWidget):
    def __init__(self, name: str, placeholder: str = "Choose…",
                 other_placeholder: str = "Type the new theme", parent=None):
        super().__init__(parent)
        self.__box = ComboBox()
        self.__box.setObjectName(name)
        self.__box.setPlaceholderText(placeholder)
        self.__box.currentTextChanged.connect(self.__on_changed)
        self.__other = QLineEdit()
        self.__other.setObjectName(f"{name}Other")
        self.__other.setPlaceholderText(other_placeholder)
        self.__other.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.__box)
        layout.addWidget(self.__other)
        self.set_themes([])

    # Known themes plus "Other…", keeping the current choice when it is still listed.
    def set_themes(self, themes: list[str]) -> None:
        current = self.__box.currentText()
        self.__box.blockSignals(True)
        self.__box.clear()
        self.__box.addItems([*themes, OTHER])
        index = self.__box.findText(current) if current in [*themes, OTHER] else -1
        self.__box.setCurrentIndex(index)
        self.__box.blockSignals(False)
        self.__on_changed(self.__box.currentText())

    def theme(self) -> str:
        if self.__box.currentText() == OTHER:
            return self.__other.text().strip()
        return self.__box.currentText()

    def choose(self, text: str) -> None:
        self.__box.setCurrentText(text)

    def type_other(self, text: str) -> None:
        self.choose(OTHER)
        self.__other.setText(text)

    def is_other(self) -> bool:
        return self.__box.currentText() == OTHER

    def clear(self) -> None:
        self.__box.setCurrentIndex(-1)
        self.__other.clear()

    def __on_changed(self, text: str) -> None:
        self.__other.setVisible(text == OTHER)
        if text == OTHER:
            self.__other.setFocus()
