# StudentFormPage: the student's feedback form.

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from managers.io_manager import EntryValidator, RecordBuilder
from managers.models import CRITICAL, SENTIMENTS, SEVERITIES

from ..widgets.option_card import OptionCard

WIDTH = 760
MAX_CHARS = 2000
CHIPS_PER_ROW = 5
SEVERITY_TEXT = {
    "low": "Minor annoyance or a suggestion",
    "medium": "Affects your studies or daily routine",
    "high": "Serious harm to grades, money or progress",
    "critical": "Someone's safety or wellbeing is at risk",
}


# Emits feedback_submitted(record), checked by I/O's EntryValidator and built by RecordBuilder.
class StudentFormPage(QWidget):
    feedback_submitted = Signal(object)
    back_requested = Signal()

    def __init__(self, known_themes: list[str], validator: EntryValidator, builder: RecordBuilder,
                 parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.__themes = list(known_themes)
        self.__validator = validator
        self.__builder = builder

        top = QFrame()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(32, 12, 32, 12)
        name = QLabel("FeedbackLens")
        name.setObjectName("appName")
        back = QPushButton("← Back to start")
        back.setObjectName("linkButton")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested)
        top_layout.addWidget(name)
        top_layout.addStretch()
        top_layout.addWidget(back)

        self.__banner = self.__build_banner()
        form = self.__build_form()

        column = QWidget()
        column.setMaximumWidth(WIDTH)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(20)
        column_layout.addWidget(self.__banner)
        column_layout.addWidget(form)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(column, 1)
        row.addStretch()
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 32, 16, 32)
        body_layout.addLayout(row)
        body_layout.addStretch()
        self.__scroll = QScrollArea()
        self.__scroll.setWidgetResizable(True)
        self.__scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.__scroll.setWidget(body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(top)
        layout.addWidget(self.__scroll, 1)
        self.reset()

    def reset(self) -> None:
        self.__banner.hide()
        self.__clear_form()

    def __build_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("successBanner")
        icon = QLabel("✓")
        icon.setObjectName("successIcon")
        icon.setFixedSize(32, 32)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Thanks, your feedback was received")
        title.setObjectName("successTitle")
        self.__banner_text = QLabel("")
        self.__banner_text.setObjectName("successText")
        self.__banner_text.setWordWrap(True)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(title)
        text.addWidget(self.__banner_text)
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        return banner

    def __build_form(self) -> QFrame:
        form = QFrame()
        form.setObjectName("formCard")
        layout = QVBoxLayout(form)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(28)

        heading = QVBoxLayout()
        heading.setSpacing(6)
        title = QLabel("Share your feedback")
        title.setObjectName("formTitle")
        intro = QLabel("Tell us what's working or what isn't. Your feedback is reviewed by staff.")
        intro.setObjectName("formIntro")
        intro.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(intro)
        layout.addLayout(heading)

        self.__text = QPlainTextEdit()
        self.__text.setObjectName("feedbackBox")
        self.__text.setPlaceholderText("Describe what happened, where, and how it affects you…")
        self.__text.setMinimumHeight(160)
        self.__text.textChanged.connect(self.__on_text_changed)
        self.__counter = QLabel(f"0 / {MAX_CHARS}")
        self.__counter.setObjectName("statusLine")
        hint = QLabel("Must contain words, not just symbols.")
        hint.setObjectName("statusLine")
        below = QHBoxLayout()
        below.addWidget(hint)
        below.addStretch()
        below.addWidget(self.__counter)
        layout.addLayout(self.__question("Your feedback", self.__text, below))

        self.__theme = QLineEdit()
        self.__theme.setObjectName("studentTheme")
        self.__theme.setPlaceholderText("e.g. Facilities, lectures, wifi, assignments")
        chips = QVBoxLayout()
        chips.setSpacing(8)
        for start in range(0, len(self.__themes), CHIPS_PER_ROW):
            chip_row = QHBoxLayout()
            chip_row.setSpacing(8)
            for theme in self.__themes[start:start + CHIPS_PER_ROW]:
                chip = QPushButton(theme)
                chip.setObjectName("chip")
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.clicked.connect(lambda _checked=False, value=theme: self.__theme.setText(value))
                chip_row.addWidget(chip)
            chip_row.addStretch()
            chips.addLayout(chip_row)
        layout.addLayout(self.__question("What is it about?", self.__theme, chips))

        self.__sentiment_group = QButtonGroup(self)
        sentiments = QGridLayout()
        sentiments.setSpacing(10)
        self.__sentiment_cards = []
        for column, value in enumerate(SENTIMENTS):
            card = OptionCard(value, value.capitalize())
            self.__sentiment_group.addButton(card.radio)
            self.__sentiment_cards.append(card)
            sentiments.addWidget(card, 0, column)
            sentiments.setColumnStretch(column, 1)
        layout.addLayout(self.__question("Overall, how do you feel about it?", sentiments))

        self.__severity_group = QButtonGroup(self)
        severities = QGridLayout()
        severities.setSpacing(10)
        self.__severity_cards = []
        for column, value in enumerate(SEVERITIES):
            card = OptionCard(value, value.capitalize(), SEVERITY_TEXT.get(value, ""),
                              tone="critical" if value == CRITICAL else "")
            self.__severity_group.addButton(card.radio)
            self.__severity_cards.append(card)
            severities.addWidget(card, 0, column)
            severities.setColumnStretch(column, 1)
        layout.addLayout(self.__question("How serious is it?", severities))

        help_box = QFrame()
        help_box.setObjectName("helpBox")
        help_layout = QVBoxLayout(help_box)
        help_layout.setContentsMargins(16, 14, 16, 14)
        help_layout.setSpacing(6)
        help_title = QLabel("Need help now?")
        help_title.setObjectName("helpTitle")
        help_text = QLabel("If you or someone else is in danger, don't wait for a reply here. "
                           "Contact campus security or student wellbeing services straight away.")
        help_text.setObjectName("helpText")
        help_text.setWordWrap(True)
        help_layout.addWidget(help_title)
        help_layout.addWidget(help_text)
        layout.addWidget(help_box)

        self.__error = QLabel("")
        self.__error.setObjectName("errorText")
        self.__error.setWordWrap(True)
        self.__error.hide()
        layout.addWidget(self.__error)
        submit = QPushButton("Submit feedback")
        submit.setObjectName("bigPrimaryButton")
        submit.setCursor(Qt.CursorShape.PointingHandCursor)
        submit.clicked.connect(self.__on_submit)
        submit_row = QHBoxLayout()
        submit_row.addStretch()
        submit_row.addWidget(submit)
        layout.addLayout(submit_row)
        return form

    @staticmethod
    def __question(text: str, field, below=None) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(8)
        label = QLabel(text)
        label.setObjectName("questionLabel")
        box.addWidget(label)
        if isinstance(field, QWidget):
            box.addWidget(field)
        else:
            box.addLayout(field)
        if below is not None:
            box.addLayout(below)
        return box

    def __on_text_changed(self) -> None:
        text = self.__text.toPlainText()
        if len(text) > MAX_CHARS:
            self.__text.setPlainText(text[:MAX_CHARS])
            self.__text.moveCursor(QTextCursor.MoveOperation.End)
            return
        self.__counter.setText(f"{len(text)} / {MAX_CHARS}")

    def __on_submit(self, *_args) -> None:
        typed_theme = self.__theme.text().strip()
        raw = {"text": self.__text.toPlainText(), "theme": typed_theme,
               "sentiment": self.__checked(self.__sentiment_cards),
               "severity": self.__checked(self.__severity_cards)}
        entry, error = self.__validator.validate(raw)
        if error:
            self.__error.setText(f"Please check your answers: {error}.")
            self.__error.show()
            return

        record = self.__builder.build(entry)
        self.feedback_submitted.emit(record)

        theme = entry["theme"]
        where = f"filed under {theme}" if theme in self.__themes else "staff will sort it into a theme"
        self.__banner_text.setText(f"Reference {record.feedback_id} · \"{typed_theme}\" {where}")
        self.__banner.show()
        self.__clear_form()
        self.__scroll.verticalScrollBar().setValue(0)

    @staticmethod
    def __checked(cards: list[OptionCard]) -> str | None:
        return next((card.value for card in cards if card.radio.isChecked()), None)

    def __clear_form(self) -> None:
        self.__text.clear()
        self.__theme.clear()
        self.__error.hide()
        for group in (self.__sentiment_group, self.__severity_group):
            group.setExclusive(False)
            for button in group.buttons():
                button.setChecked(False)
            group.setExclusive(True)
