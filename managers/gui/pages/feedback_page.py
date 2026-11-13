# FeedbackPage: search and review in one page.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from managers.models import SEVERITIES

from ..widgets.card import Card
from ..widgets.combo_box import ComboBox
from ..widgets.entry_card import EntryCard
from ..widgets.entry_detail_panel import EntryDetailPanel
from .base_page import BasePage


RECOMMENDED = "Recommended"
SORTS = (RECOMMENDED, "Newest first", "Oldest first", "Most severe first", "Theme (A-Z)")


# A list of entry cards on the left and EntryDetailPanel on the right.
class FeedbackPage(BasePage):
    decision_made = Signal(object)

    def __init__(self, data, parent=None):
        super().__init__("Feedback", "", parent)
        self.__data = data
        self.__records = {}
        self.__cards = {}
        self.__current = None

        search_card = Card(padding=16, spacing=12)
        bar = QHBoxLayout()
        bar.setSpacing(12)
        segments = QFrame()
        segments.setObjectName("segmentGroup")
        segment_layout = QHBoxLayout(segments)
        segment_layout.setContentsMargins(1, 1, 1, 1)
        segment_layout.setSpacing(0)
        self.__review_button = QPushButton("Needs review")
        self.__all_button = QPushButton("All feedback")
        group = QButtonGroup(self)
        for button in (self.__review_button, self.__all_button):
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(button)
            segment_layout.addWidget(button)
        self.__review_button.setProperty("side", "left")
        self.__all_button.setProperty("side", "right")
        self.__review_button.setChecked(True)
        group.buttonClicked.connect(lambda _button: self.refresh())
        bar.addWidget(segments)
        self.__search = QLineEdit()
        self.__search.setObjectName("searchBox")
        self.__search.setPlaceholderText("Search text, theme or severity…  (press Enter)")
        self.__search.setClearButtonEnabled(True)
        self.__search.returnPressed.connect(self.refresh)
        self.__search.textChanged.connect(lambda text: None if text else self.refresh())
        bar.addWidget(self.__search, 1)
        sort_label = QLabel("Sort by")
        sort_label.setObjectName("fieldLabel")
        self.__sort = ComboBox()
        self.__sort.setObjectName("sortBox")
        self.__sort.addItems(list(SORTS))
        self.__sort.setToolTip("Recommended keeps the review queue's order: critical entries first.")
        self.__sort.currentTextChanged.connect(lambda _text: self.refresh())
        bar.addWidget(sort_label)
        bar.addWidget(self.__sort)
        search_card.body.addLayout(bar)
        self.content_layout.addWidget(search_card)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        self.__list_card = Card(padding=12, spacing=6)
        self.__list_layout = QVBoxLayout()
        self.__list_layout.setSpacing(6)
        self.__list_card.body.addLayout(self.__list_layout)
        self.__empty = QLabel("Nothing to show.")
        self.__empty.setObjectName("mutedText")
        self.__empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.__empty.setMinimumHeight(80)
        self.__list_card.body.addWidget(self.__empty)
        list_note = QLabel("In \"All feedback\", unflagged entries show a status tag instead: "
                           "Matched, Reviewed, or Unverified (AI unavailable, student's values "
                           "counted, re-checked next run).")
        list_note.setObjectName("smallNote")
        list_note.setWordWrap(True)
        list_note.setContentsMargins(4, 8, 4, 0)
        self.__list_card.body.addWidget(list_note)

        self.__detail = EntryDetailPanel()
        self.__detail.decision_requested.connect(self.decision_made)
        columns.addWidget(self.__list_card, 2, Qt.AlignmentFlag.AlignTop)
        columns.addWidget(self.__detail, 3, Qt.AlignmentFlag.AlignTop)
        self.content_layout.addLayout(columns)
        self.content_layout.addStretch()

    def review_count(self) -> int:
        return len(self.__data.load_review_queue())

    def refresh(self) -> None:
        query = self.__search.text().strip()
        if query:
            records = self.__data.search_records(query)
            if self.__review_button.isChecked():
                records = [r for r in records if r.needs_review]
        elif self.__review_button.isChecked():
            records = self.__data.load_review_queue()
        else:
            records = self.__data.load_records()

        self.__display(self.sort_records(records, self.__sort.currentText()))

    # Shows exactly these records (QtFeedbackView.show_search_results), in "All feedback".
    def show_records(self, records) -> None:
        self.__set_mode(review=False)
        self.__search.blockSignals(True)
        self.__search.clear()
        self.__search.blockSignals(False)
        self.__display(self.sort_records(list(records), self.__sort.currentText()))

    # Opens "Needs review" with this record selected; shown on its own if it isn't queued.
    def show_review_entry(self, record) -> None:
        self.__set_mode(review=True)
        self.__search.blockSignals(True)
        self.__search.clear()
        self.__search.blockSignals(False)
        self.refresh()
        if record.feedback_id not in self.__cards:
            self.__display([record])
        self.__select(record.feedback_id)

    def __set_mode(self, review: bool) -> None:
        (self.__review_button if review else self.__all_button).setChecked(True)

    def __display(self, records: list) -> None:
        self.__review_button.setText(f"Needs review · {self.review_count()}")
        self.__all_button.setText(f"All feedback · {len(self.__data.load_records())}")
        self.__records = {r.feedback_id: r for r in records}

        for card in self.__cards.values():
            self.__list_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.__cards = {}
        for record in records:
            card = EntryCard(record)
            card.clicked.connect(self.__on_card_clicked)
            self.__list_layout.addWidget(card)
            self.__cards[record.feedback_id] = card
        self.__empty.setVisible(not records)

        self.__current = None
        self.__detail.clear()
        if records:
            self.__select(records[0].feedback_id)

    def set_sort(self, name: str) -> None:
        self.__sort.setCurrentText(name)

    # Records in the chosen order. Recommended keeps Data's order (the review queue is critical
    # first); the others break ties newest first. Severity and theme use the final values when
    # Logic has set them, otherwise the student's.
    @staticmethod
    def sort_records(records: list, name: str) -> list:
        newest = sorted(records, key=lambda r: r.timestamp or "", reverse=True)
        if name == "Newest first":
            return newest
        if name == "Oldest first":
            return newest[::-1]
        if name == "Most severe first":
            rank = {severity: index for index, severity in enumerate(SEVERITIES)}
            return sorted(newest, key=lambda r: -rank.get(r.current_labels.get("severity"), -1))
        if name == "Theme (A-Z)":
            return sorted(newest, key=lambda r: (r.current_labels.get("theme") or "").lower())
        return list(records)

    def __on_card_clicked(self, feedback_id: str) -> None:
        if feedback_id == self.__current:
            return
        if self.__current is not None and self.__detail.has_unsaved_changes():
            answer = QMessageBox.question(self, "Discard changes?",
                                          "You changed this entry's labels without saving. Discard them?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.__select(feedback_id)

    def __select(self, feedback_id: str) -> None:
        if self.__current in self.__cards:
            self.__cards[self.__current].set_selected(False)
        self.__current = feedback_id
        self.__cards[feedback_id].set_selected(True)
        self.__detail.show_record(self.__records[feedback_id], self.__data.load_known_themes())
