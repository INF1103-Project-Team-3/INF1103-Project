# AddFeedbackPage: add feedback and watch a run's progress.

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..progress_signals import ProgressSignals
from ..widgets.card import Card
from ..widgets.progress_panel import ProgressPanel
from .base_page import BasePage


# For now: a Process card and the progress panel.
class AddFeedbackPage(BasePage):
    run_requested = Signal()

    def __init__(self, data, signals: ProgressSignals, parent=None):
        super().__init__("Add feedback",
                         "The Single entry and Import file tabs arrive with the I/O refactor.",
                         parent)
        self.__data = data
        self.__busy = False
        self.__new = 0

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

    # Disables Process while a run is going, so only one run happens at a time.
    def set_busy(self, busy: bool) -> None:
        self.__busy = busy
        self.__panel.set_running(busy)
        self.refresh()

    def set_new_count(self, count: int) -> None:
        self.__new = count
        self.refresh()

    def refresh(self) -> None:
        count = len(self.__data.load_pending()) + self.__new
        text = f"{count} {'entry' if count == 1 else 'entries'} waiting for the AI"
        if self.__new:
            text += f" · {self.__new} new from students"
        self.__pending.setText(text)
        if self.__busy:
            self.__process.setText("Processing…")
            self.__process.setEnabled(False)
        else:
            self.__process.setText(f"Process {count} {'entry' if count == 1 else 'entries'}"
                                   if count else "Nothing to process")
            self.__process.setEnabled(bool(count))
