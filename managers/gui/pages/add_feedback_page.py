# AddFeedbackPage: type in one entry or import a file, then process the queue and watch the run.

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout

from managers.io_manager import EntryValidator, RecordBuilder
from managers.models import UNVERIFIED

from ..progress_signals import ProgressSignals
from ..widgets.card import Card
from ..widgets.import_panel import ImportPanel
from ..widgets.progress_panel import ProgressPanel
from ..widgets.single_entry_form import SingleEntryForm
from .base_page import BasePage


# Single entry and Import file tabs, a Process card and the progress panel.
class AddFeedbackPage(BasePage):
    run_requested = Signal()
    record_added = Signal(object)
    import_ready = Signal(object)

    def __init__(self, data, signals: ProgressSignals, validator: EntryValidator, builder: RecordBuilder,
                 importers=None, parent=None):
        super().__init__("Add feedback",
                         "Entries are queued here and saved when you process them.", parent)
        self.__data = data
        self.__busy = False
        self.__queued = 0

        self.__single = SingleEntryForm(validator, builder)
        self.__single.record_added.connect(self.record_added)
        self.__import = ImportPanel(importers, data)
        self.__import.import_ready.connect(self.import_ready)
        self.__tabs = QStackedWidget()
        self.__tabs.addWidget(self.__single)
        self.__tabs.addWidget(self.__import)
        self.content_layout.addWidget(self.__build_segments())
        self.content_layout.addWidget(self.__tabs)

        card = Card(padding=20, spacing=6)
        row = QHBoxLayout()
        row.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(4)
        self.__pending = QLabel("")
        self.__pending.setObjectName("cardTitle")
        hint = QLabel("Already-processed entries are skipped.")
        hint.setObjectName("statusLine")
        text.addWidget(self.__pending)
        text.addWidget(hint)
        row.addLayout(text, 1)
        self.__process = QPushButton("Process pending entries")
        self.__process.setObjectName("bigPrimaryButton")
        self.__process.clicked.connect(lambda _checked=False: self.run_requested.emit())
        row.addWidget(self.__process)
        card.body.addLayout(row)
        self.content_layout.addWidget(card)

        self.__panel = ProgressPanel(signals)
        self.content_layout.addWidget(self.__panel)
        self.content_layout.addStretch()

    @property
    def progress_panel(self) -> ProgressPanel:
        return self.__panel

    @property
    def single_entry(self) -> SingleEntryForm:
        return self.__single

    @property
    def import_panel(self) -> ImportPanel:
        return self.__import

    # Switches to the Import file tab (QtFeedbackView.show_rejected_rows).
    def show_import_tab(self) -> None:
        self.__tabs.setCurrentWidget(self.__import)
        for button in self.findChildren(QPushButton):
            if button.objectName() == "segment":
                button.setChecked(button.text() == "Import file")

    # Disables Process while a run is going, so only one run happens at a time.
    def set_busy(self, busy: bool) -> None:
        self.__busy = busy
        self.__panel.set_running(busy)
        self.refresh()

    # How many entries (student, typed or imported) are queued for the next run.
    def set_new_count(self, count: int) -> None:
        self.__queued = count
        self.refresh()

    # Waiting for the AI: pending entries plus saved ones the AI couldn't check (D4: unverified
    # entries go to the AI again on the next run, so Process must be possible without new feedback).
    def refresh(self) -> None:
        self.__single.set_themes(self.__data.load_known_themes())
        pending = {r.feedback_id for r in self.__data.load_pending()}
        unverified = {r.feedback_id for r in self.__data.load_records()
                      if r.ai is None and r.verification == UNVERIFIED} - pending
        waiting = len(pending) + len(unverified)
        count = waiting + self.__queued
        text = f"{waiting} {'entry' if waiting == 1 else 'entries'} waiting for the AI"
        if unverified:
            text += f" ({len(unverified)} unverified, retried when you process)"
        if self.__queued:
            text += f" · {self.__queued} queued in this session"
        self.__pending.setText(text)
        if self.__busy:
            self.__process.setText("Processing…")
            self.__process.setEnabled(False)
        else:
            self.__process.setText(f"Process {count} {'entry' if count == 1 else 'entries'}"
                                   if count else "Nothing to process")
            self.__process.setEnabled(bool(count))

    def __build_segments(self) -> QFrame:
        segments = QFrame()
        segments.setObjectName("segmentGroup")
        layout = QHBoxLayout(segments)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        group = QButtonGroup(self)
        for index, (name, side) in enumerate((("Single entry", "left"), ("Import file", "right"))):
            button = QPushButton(name)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setProperty("side", side)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(button, index)
            layout.addWidget(button)
        group.idClicked.connect(self.__tabs.setCurrentIndex)
        row = QFrame()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(segments)
        row_layout.addStretch()
        return row
