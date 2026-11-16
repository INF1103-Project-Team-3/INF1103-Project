# EntryDetailPanel: one record's text with the student's, the AI's and the final values.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QStyle,
    QStyleOptionComboBox, QVBoxLayout,
)

from managers.io_manager import ReviewDecision
from managers.models import SENTIMENTS, SEVERITIES, FeedbackRecord

from ..style import Style
from .combo_box import ComboBox
from .date_text import DateText
from .record_tags import RecordTags

EMPTY = "—"
FIELDS = ("theme", "sentiment", "severity")
# The Final dropdowns get the most room: their padding and arrow take about 42px (G13).
FINAL_MIN_WIDTH = 170
COLUMNS = (("Field", 2, 92), ("Student", 3, 90), ("AI", 3, 90), ("Final", 5, FINAL_MIN_WIDTH))


# Shows a record and turns the admin's buttons into a ReviewDecision.
class EntryDetailPanel(QFrame):
    decision_requested = Signal(object)
    undo_requested = Signal(str)

    # is_new_theme is Logic's check (LogicManager.is_new_theme); without it, no Confirm button.
    def __init__(self, is_new_theme=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.__is_new_theme = is_new_theme
        self.__record = None
        self.__loading = False
        self.__dirty = False

        self.__heading = QLabel("Choose an entry")
        self.__heading.setObjectName("detailId")
        self.__date = QLabel("")
        self.__date.setObjectName("detailDate")
        self.__date.setWordWrap(True)
        top = QVBoxLayout()
        top.setSpacing(4)
        top.addWidget(self.__heading)
        top.addWidget(self.__date)

        self.__text = QLabel("")
        self.__text.setTextFormat(Qt.TextFormat.PlainText)     # shown as written (G6)
        self.__text.setObjectName("feedbackText")
        self.__text.setWordWrap(True)
        self.__text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.__summary = QLabel("")
        self.__summary.setTextFormat(Qt.TextFormat.PlainText)
        self.__summary.setObjectName("smallNote")
        self.__summary.setWordWrap(True)
        self.__summary.hide()
        self.__reasons = QLabel("")
        self.__reasons.setObjectName("reasonList")
        self.__reasons.setWordWrap(True)
        self.__reasons.setTextFormat(Qt.TextFormat.RichText)

        self.__theme_box = ComboBox()
        self.__sentiment_box = ComboBox()
        self.__sentiment_box.addItems(SENTIMENTS)
        self.__severity_box = ComboBox()
        self.__severity_box.addItems(SEVERITIES)
        self.__boxes = {"theme": self.__theme_box, "sentiment": self.__sentiment_box,
                        "severity": self.__severity_box}
        for box in self.__boxes.values():
            box.setPlaceholderText(EMPTY)
            box.currentTextChanged.connect(self.__mark_dirty)

        table = QVBoxLayout()
        table.setSpacing(0)
        table.addWidget(self.__row([QLabel(title.upper()) for title, _stretch, _width in COLUMNS], header=True))
        self.__cells = {}
        self.__rows = {}
        for field in FIELDS:
            name = QLabel(field.capitalize())
            name.setObjectName("fieldName")
            user, ai = QLabel(EMPTY), QLabel(EMPTY)
            for cell in (user, ai):
                cell.setObjectName("fieldValue")
                cell.setWordWrap(True)          # a long theme wraps instead of being cut off
            self.__cells[(field, "user")] = user
            self.__cells[(field, "ai")] = ai
            self.__rows[field] = self.__row([name, user, ai, self.__boxes[field]])
            table.addWidget(self.__rows[field])

        self.__save = QPushButton("Use these labels")
        self.__save.setObjectName("primaryButton")
        self.__use_user = QPushButton("Use student's")
        self.__use_ai = QPushButton("Use AI's")
        self.__delete = QPushButton("Delete")
        self.__delete.setObjectName("dangerButton")
        self.__confirm = QPushButton("Confirm new theme")
        self.__confirm.setObjectName("primaryButton")
        self.__confirm.clicked.connect(self.__on_confirm)
        self.__save.clicked.connect(self.__on_save)
        self.__use_user.clicked.connect(lambda _checked=False: self.__decide_with(self.__record.user))
        self.__use_ai.clicked.connect(lambda _checked=False: self.__decide_with(self.__record.ai))
        self.__delete.clicked.connect(self.__on_delete)
        # Two lines of buttons (saving, then shortcuts), so the panel fits a narrow window.
        button_row = QFrame()
        button_row.setObjectName("buttonRow")
        buttons = QVBoxLayout(button_row)
        buttons.setContentsMargins(0, 14, 0, 0)
        buttons.setSpacing(10)
        for group in ((self.__confirm, self.__save), (self.__use_user, self.__use_ai, self.__delete)):
            line = QHBoxLayout()
            line.setSpacing(10)
            for button in group:
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                line.addWidget(button)
            line.addStretch()
            buttons.addLayout(line)

        self.__queued = QFrame()
        self.__queued.setObjectName("helpBox")
        queued_layout = QHBoxLayout(self.__queued)
        queued_layout.setContentsMargins(16, 12, 16, 12)
        queued_layout.setSpacing(10)
        self.__queued_text = QLabel("")
        self.__queued_text.setObjectName("helpText")
        self.__queued_text.setWordWrap(True)
        undo = QPushButton("Undo")
        undo.clicked.connect(lambda _checked=False: self.undo_requested.emit(self.__record.feedback_id))
        undo.setCursor(Qt.CursorShape.PointingHandCursor)
        queued_layout.addWidget(self.__queued_text, 1)
        queued_layout.addWidget(undo)
        self.__queued.hide()

        note = QLabel("To leave an entry for later, just pick another one from the list; it stays in "
                      "Needs review. If the Final values were changed but not saved, a \"Discard "
                      "changes?\" prompt appears first.")
        note.setObjectName("smallNote")
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addLayout(top)
        layout.addWidget(self.__text)
        layout.addWidget(self.__summary)
        layout.addWidget(self.__reasons)
        layout.addLayout(table)
        layout.addWidget(self.__queued)
        layout.addWidget(button_row)
        layout.addWidget(note)
        layout.addStretch()
        self.clear()

    # Shows that this record's decision is queued until Save changes (with Undo), and locks the
    # decision buttons meanwhile; None returns to normal.
    def set_queued(self, text: str | None) -> None:
        queued = bool(text) and self.__record is not None
        self.__queued_text.setText(f"<b>{text}</b> when you press Save changes." if queued else "")
        self.__queued.setVisible(queued)
        if self.__record is not None:
            self.__set_buttons_enabled(not queued)
            self.__use_ai.setEnabled(not queued and self.__record.ai is not None)
            self.__confirm.setEnabled(not queued)

    @property
    def record(self) -> FeedbackRecord | None:
        return self.__record

    # True if the admin changed a Final box but has not saved.
    def has_unsaved_changes(self) -> bool:
        return self.__dirty

    # The Final boxes' current text, e.g. to put unsaved edits back after a refresh.
    def final_values(self) -> dict[str, str]:
        return {field: box.currentText() for field, box in self.__boxes.items()}

    # Puts edited Final values back and keeps them marked unsaved.
    def restore_edits(self, values: dict[str, str]) -> None:
        for field, text in values.items():
            box = self.__boxes[field]
            if text and box.findText(text) == -1:
                box.addItem(text)
            box.setCurrentIndex(box.findText(text) if text else -1)
        self.__dirty = True

    # Shows a queued update's values in the Final column (G13); None or a delete leaves them.
    def show_queued_values(self, decision) -> None:
        if decision is None or decision.action != ReviewDecision.UPDATE:
            return
        self.__loading = True
        for field in FIELDS:
            box, text = self.__boxes[field], getattr(decision, field)
            if box.findText(text) == -1:
                box.addItem(text)
            box.setCurrentIndex(box.findText(text))
        self.__loading = False

    def clear(self) -> None:
        self.__loading = True
        self.__record = None
        self.__heading.setText("Choose an entry")
        self.__date.setText("")
        self.__text.setText("Pick an entry from the list to see it here.")
        self.__summary.hide()
        self.__reasons.setText("")
        for (field, _source), cell in self.__cells.items():
            cell.setText(EMPTY)
            self.__set_mismatch(cell, False)
        for field, box in self.__boxes.items():
            box.setCurrentIndex(-1)
            self.__set_mismatch(self.__rows[field], False)
            self.__set_mismatch(box, False)
        self.__set_buttons_enabled(False)
        self.__confirm.hide()
        self.__queued.hide()
        self.__dirty = False
        self.__loading = False

    def show_record(self, record: FeedbackRecord, known_themes: list[str]) -> None:
        self.__loading = True
        self.__record = record
        self.__heading.setText(record.feedback_id)
        source = record.source_file or "typed in"
        self.__date.setText(f"Submitted {DateText.long(record.timestamp)} · {source}")
        self.__text.setText(record.text)
        summary = (record.ai or {}).get("summary")
        self.__summary.setText(f"AI summary: {summary}" if summary else "")
        self.__summary.setVisible(bool(summary))
        self.__reasons.setText(self.__reason_html(record))

        user, ai = record.user, record.ai or {}
        final = {"theme": record.theme, "sentiment": record.sentiment, "severity": record.severity}
        self.__theme_box.clear()
        themes = list(known_themes)
        for theme in (user.get("theme"), ai.get("theme"), final["theme"]):
            if theme and theme not in themes:
                themes.append(theme)
        self.__theme_box.addItems(themes)
        self.__fit_theme_box(themes)

        for field in FIELDS:
            mismatch = bool(ai.get(field)) and ai[field].lower() != user[field].lower()
            self.__cells[(field, "user")].setText(user.get(field) or EMPTY)
            ai_text = ai.get(field) or EMPTY
            if ai.get(field):
                ai_text += "  ✗" if mismatch else "  ✓"
            self.__cells[(field, "ai")].setText(ai_text)
            self.__set_mismatch(self.__cells[(field, "ai")], mismatch)
            self.__set_mismatch(self.__rows[field], mismatch)
            self.__set_mismatch(self.__boxes[field], mismatch)
            box = self.__boxes[field]
            box.setCurrentIndex(box.findText(final[field]) if final[field] else -1)

        self.__set_buttons_enabled(True)
        self.__use_ai.setEnabled(record.ai is not None)
        new_theme = self.__new_theme(record)
        self.__confirm.setVisible(new_theme is not None)
        if new_theme:
            self.__confirm.setText(f"Confirm new theme '{new_theme}'")
        self.__dirty = False
        self.__loading = False

    # The theme box is made wide enough to show its longest theme in full: the text width plus
    # what the style takes for padding and the arrow (GUI-B; the Docker GUI draws at 2x).
    def __fit_theme_box(self, themes: list[str]) -> None:
        box = self.__theme_box
        option = QStyleOptionComboBox()
        box.initStyleOption(option)
        field = box.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                           QStyle.SubControl.SC_ComboBoxEditField, box)
        chrome = box.width() - field.width()
        widest = max((box.fontMetrics().horizontalAdvance(theme) for theme in themes), default=0)
        width = max(FINAL_MIN_WIDTH, widest + chrome + 2)
        for final_box in self.__boxes.values():     # all three, so the Final column stays aligned
            final_box.setMinimumWidth(width)

    # One table row.
    def __row(self, widgets, header: bool = False) -> QFrame:
        row = QFrame()
        row.setObjectName("gridHeaderRow" if header else "fieldRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8 if header else 6, 0, 8 if header else 6)
        layout.setSpacing(12)
        for widget, (_title, stretch, min_width) in zip(widgets, COLUMNS):
            if header:
                widget.setObjectName("gridHeader")
            elif not isinstance(widget, QComboBox):
                widget.setMinimumHeight(40)
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            widget.setMinimumWidth(min_width)
            layout.addWidget(widget, stretch)
        return row

    @staticmethod
    def __reason_html(record: FeedbackRecord) -> str:
        if record.needs_review:
            items = "".join(f"<li>{RecordTags.explain_reason(reason)}</li>" for reason in record.review_reasons)
            return f'<ul style="margin:0; -qt-list-indent:1;">{items}</ul>'
        status, _kind = RecordTags.STATUS_TAGS.get(record.verification, (record.verification, ""))
        return f"Not flagged · {status}"

    @staticmethod
    def __set_mismatch(widget, mismatch: bool) -> None:
        widget.setProperty("mismatch", mismatch)
        Style.restyle(widget)

    def __set_buttons_enabled(self, enabled: bool) -> None:
        for widget in (self.__save, self.__use_user, self.__use_ai, self.__delete, *self.__boxes.values()):
            widget.setEnabled(enabled)

    def __mark_dirty(self, *_args) -> None:
        if not self.__loading:
            self.__dirty = True

    def __on_save(self, *_args) -> None:
        values = tuple(box.currentText().strip() for box in self.__boxes.values())
        if not all(values):
            QMessageBox.warning(self, "Missing value", "Choose a theme, sentiment and severity first.")
            return
        self.__emit_update(values)

    def __decide_with(self, values: dict | None) -> None:
        if values:
            self.__emit_update((values["theme"], values["sentiment"], values["severity"]))

    def __emit_update(self, values: tuple[str, str, str]) -> None:
        self.__dirty = False
        labels = dict(zip(FIELDS, values))
        self.decision_requested.emit(ReviewDecision.update(self.__record.feedback_id, labels))

    # The flagged record's theme if Logic says it is new (not yet confirmed), or None.
    def __new_theme(self, record: FeedbackRecord) -> str | None:
        if (record.needs_review and record.theme and self.__is_new_theme is not None
                and self.__is_new_theme(record.theme)):
            return record.theme
        return None

    # An update that keeps the new theme, which confirms it for everyone (D16).
    def __on_confirm(self, *_args) -> None:
        theme = self.__new_theme(self.__record)
        if theme is None:
            return
        answer = QMessageBox.question(
            self, "Confirm new theme",
            f"Add '{theme}' as a theme for everyone? Students can then pick it, the AI uses it, "
            f"and every entry with this theme is counted from the next run.")
        if answer == QMessageBox.StandardButton.Yes:
            self.__dirty = False
            labels = {**self.__record.current_labels, "theme": theme}
            self.decision_requested.emit(ReviewDecision.update(self.__record.feedback_id, labels))

    def __on_delete(self, *_args) -> None:
        answer = QMessageBox.question(self, "Delete feedback",
                                      f"Delete {self.__record.feedback_id} permanently?")
        if answer == QMessageBox.StandardButton.Yes:
            self.__dirty = False
            self.decision_requested.emit(ReviewDecision.delete(self.__record.feedback_id))
