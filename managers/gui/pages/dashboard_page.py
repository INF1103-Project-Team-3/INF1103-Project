# DashboardPage: the admin home page.

from PySide6.QtWidgets import QGridLayout, QLabel

from managers.models import CRITICAL, UNVERIFIED

from ..widgets.card import Card
from .base_page import BasePage

STATS = (
    ("Total entries", "→ Feedback"),
    ("Counted in statistics", ""),
    ("Needs review", "→ Feedback, review filter"),
    ("Critical", "→ top of review"),
)


# The four number cards for now.
class DashboardPage(BasePage):
    def __init__(self, data, parent=None):
        super().__init__("Dashboard", "", parent)
        self.__data = data
        self.__values = {}
        self.__feet = {}

        cards = QGridLayout()
        cards.setSpacing(16)
        for column, (name, foot) in enumerate(STATS):
            card = Card(padding=20, spacing=6)
            label = QLabel(name)
            label.setObjectName("statLabel")
            value = QLabel("0")
            value.setObjectName("statValue")
            foot_label = QLabel(foot)
            foot_label.setObjectName("statFoot")
            for widget in (label, value, foot_label):
                card.body.addWidget(widget)
            if name == "Critical":
                card.set_tone("critical")
            self.__values[name] = value
            self.__feet[name] = foot_label
            cards.addWidget(card, 0, column)
        self.content_layout.addLayout(cards)

        later = QLabel("Coming next: themes by priority with sparklines, the since-last-run strip, "
                       "sentiment mix, AI summary, suggested actions and latest actions "
                       "(needs Logic's AggregationResult and TrendReport, and Data's load_history).")
        later.setObjectName("placeholder")
        later.setWordWrap(True)
        self.content_layout.addWidget(later)
        self.content_layout.addStretch()

    def refresh(self) -> None:
        records = self.__data.load_records()
        counted = [r for r in records if r.counted]
        unverified = sum(1 for r in counted if r.verification == UNVERIFIED)
        pending = len(self.__data.load_pending())
        self.__values["Total entries"].setText(str(len(records)))
        self.__values["Counted in statistics"].setText(str(len(counted)))
        self.__feet["Counted in statistics"].setText(f"incl. {unverified} unverified (AI retries next run)")
        self.__values["Needs review"].setText(str(len(self.__data.load_review_queue())))
        self.__values["Critical"].setText(str(sum(1 for r in records if r.severity == CRITICAL)))
        self.set_subtitle(f"{pending} entries waiting for the AI" if pending else "Every entry has been processed")
