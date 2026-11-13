# DashboardPage: the admin home page, fed from Logic's results through read-only Data calls.

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from managers.models import CRITICAL, SENTIMENTS

from ..widgets.card import Card
from ..widgets.pill import Pill
from ..widgets.sparkline import Sparkline
from .base_page import BasePage

STATS = (
    ("Total entries", "→ Feedback"),
    ("Counted in statistics", ""),
    ("Needs review", "→ Feedback, review filter"),
    ("Critical", "→ top of review"),
)
SPARK_RUNS = 5
STATUS_KINDS = {"Escalating": "warn", "New": "info", "Easing": "good", "Steady": "neutral",
                "Not reported": "neutral"}
LATEST_ACTIONS = 3


# Number cards, AI notice, since-last-run strip, themes by priority, sentiment mix,
# new themes waiting, AI summary and latest actions.
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

        self.__notice = Card(padding=16, spacing=6)
        self.__notice.set_tone("critical")
        self.__notice_text = QLabel("")
        self.__notice_text.setWordWrap(True)
        self.__notice.body.addWidget(self.__notice_text)
        self.content_layout.addWidget(self.__notice)

        self.__strip = Card("Since the last run", padding=16, spacing=10)
        self.__strip_body = self.__box(self.__strip)
        self.content_layout.addWidget(self.__strip)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        self.__themes = Card("Themes by priority", padding=20, spacing=10)
        self.__themes_body = self.__box(self.__themes)
        side = QVBoxLayout()
        side.setSpacing(16)
        self.__sentiment = Card("Sentiment mix", padding=20, spacing=10)
        self.__sentiment_body = self.__box(self.__sentiment)
        self.__waiting = Card("New themes waiting", padding=20, spacing=8)
        self.__waiting_body = self.__box(self.__waiting)
        side.addWidget(self.__sentiment)
        side.addWidget(self.__waiting)
        side.addStretch()
        columns.addWidget(self.__themes, 3, Qt.AlignmentFlag.AlignTop)
        columns.addLayout(side, 2)
        self.content_layout.addLayout(columns)

        self.__actions = Card("Latest actions", padding=20, spacing=8)
        self.__actions_body = self.__box(self.__actions)
        hint = QLabel("The AI summary and suggested actions are on Trends & actions.")
        hint.setObjectName("smallNote")
        self.__actions.body.addWidget(hint)
        self.content_layout.addWidget(self.__actions)
        self.content_layout.addStretch()

    def refresh(self) -> None:
        self.show_values(self.__data.load_result(), self.__data.load_trend(), self.__data.load_summary(),
                         self.__data.load_review_queue(), self.__data.load_records(),
                         len(self.__data.load_pending()))

    # Shows the given results (QtFeedbackView.show_dashboard). Without records, the number
    # cards come from result and queue; the charts and actions are still read from Data.
    def show_values(self, result, trend, summary, queue, records=None, pending: int | None = None) -> None:
        queue = list(queue)
        unverified = result.unverified_count if result else 0
        if records is not None:
            total, counted = len(records), sum(1 for r in records if r.counted)
            critical = sum(1 for r in records if r.severity == CRITICAL)
        else:
            total = result.total_entries if result else 0
            counted = result.counted_entries if result else 0
            critical = sum(1 for r in queue if r.current_labels.get("severity") == CRITICAL)
        self.__values["Total entries"].setText(str(total))
        self.__values["Counted in statistics"].setText(str(counted))
        self.__feet["Counted in statistics"].setText(f"incl. {unverified} unverified (AI retries next run)")
        self.__values["Needs review"].setText(str(len(queue)))
        self.__values["Critical"].setText(str(critical))
        if pending is not None:
            self.set_subtitle(f"{pending} entries waiting for the AI" if pending else "Every entry has been processed")

        self.__fill_notice(unverified, summary)
        self.__fill_strip(trend)
        self.__fill_themes(result, trend)
        self.__fill_sentiment(result)
        self.__fill_waiting(result)
        self.__fill_actions()

    # Shown when the AI couldn't check some counted entries (D20, A26).
    def __fill_notice(self, unverified: int, summary) -> None:
        self.__notice.setVisible(bool(unverified))
        if not unverified:
            return
        when = f" The last AI summary is from {self.__date(summary.created_at)}." if summary else ""
        self.__notice_text.setText(
            f"<b>AI unavailable for {unverified} {'entry' if unverified == 1 else 'entries'}.</b> "
            f"They are counted with the student's values and will be sent to the AI again on the next run.{when}")

    def __fill_strip(self, trend) -> None:
        body = self.__clear(self.__strip_body)
        if trend is None or not trend.has_previous:
            body.addWidget(self.__muted((trend.message if trend and trend.message else None)
                                        or "First run: nothing to compare with yet."))
            return
        previous = trend.previous_run or {}
        body.addWidget(self.__muted(f"Compared with the run on {self.__date(previous.get('run_at'))}"
                                    + (f" ({previous['source_file']})" if previous.get("source_file") else "")))
        row = QHBoxLayout()
        row.setSpacing(8)
        headline = trend.headline
        for key, label in (("total_entries", "Entries"), ("counted_entries", "Counted"),
                           ("negative_percent", "Negative")):
            if key in headline:
                row.addWidget(Pill(f"{label} {headline[key]['text'].replace('->', '→')}", "neutral"))
        for status, count in headline.get("status_counts", {}).items():
            if count and status in ("Escalating", "New", "Easing"):
                row.addWidget(Pill(f"{count} {status.lower()}", STATUS_KINDS[status]))
        row.addStretch()
        body.addLayout(row)
        attention = trend.needs_attention()
        if attention:
            body.addWidget(self.__muted("Needs attention: " + ", ".join(attention)))

    def __fill_themes(self, result, trend) -> None:
        body = self.__clear(self.__themes_body)
        if result is None or not result.themes:
            body.addWidget(self.__muted("No counted entries yet."))
            return
        statuses = {row["theme"]: row["status"] for row in (trend.themes if trend else [])}
        history = self.__data.load_history()[-SPARK_RUNS:]
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        for column, title in enumerate(("Theme", "Priority", "", "Entries", f"Last {SPARK_RUNS} runs", "")):
            label = QLabel(title)
            label.setObjectName("smallNote")
            grid.addWidget(label, 0, column)
        for row, stats in enumerate(sorted(result.themes, key=lambda s: -s.priority), start=1):
            name = QLabel(stats.theme)
            name.setObjectName("fieldName")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(stats.priority)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            spark = Sparkline()
            spark.setObjectName("sparkline")
            spark.set_values([run.get("theme_priority", {}).get(stats.theme) for run in history])
            status = statuses.get(stats.theme)
            grid.addWidget(name, row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(QLabel(str(stats.priority)), row, 2)
            grid.addWidget(QLabel(str(stats.count)), row, 3)
            grid.addWidget(spark, row, 4)
            if status:
                grid.addWidget(Pill(status, STATUS_KINDS.get(status, "neutral")), row, 5)
        grid.setColumnStretch(1, 1)
        body.addLayout(grid)
        body.addWidget(self.__note("Priority (0-100) weighs severity and sentiment, so it can fall as well as "
                                   "rise; entry counts are running totals."))

    def __fill_sentiment(self, result) -> None:
        body = self.__clear(self.__sentiment_body)
        counts = result.sentiment_counts if result else {}
        total = sum(counts.values())
        if not total:
            body.addWidget(self.__muted("No counted entries yet."))
            return
        for sentiment in SENTIMENTS:
            count = counts.get(sentiment, 0)
            share = round(100 * count / total)
            row = QHBoxLayout()
            label = QLabel(sentiment.capitalize())
            label.setFixedWidth(70)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(share)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            value = QLabel(f"{share}% ({count})")
            value.setFixedWidth(72)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label)
            row.addWidget(bar, 1)
            row.addWidget(value)
            body.addLayout(row)

    def __fill_waiting(self, result) -> None:
        body = self.__clear(self.__waiting_body)
        waiting = result.pending_themes if result else {}
        if not waiting:
            body.addWidget(self.__muted("None waiting."))
            return
        for theme, count in sorted(waiting.items(), key=lambda item: -item[1]):
            row = QHBoxLayout()
            row.addWidget(Pill(theme, "info"))
            row.addWidget(self.__muted(f"{count} {'entry' if count == 1 else 'entries'}"))
            row.addStretch()
            body.addLayout(row)
        body.addWidget(self.__note("Not counted until confirmed. Confirm or change them in Feedback → Needs review."))

    def __fill_actions(self) -> None:
        body = self.__clear(self.__actions_body)
        actions = sorted(self.__data.load_actions(), key=lambda a: a.logged_at, reverse=True)[:LATEST_ACTIONS]
        if not actions:
            body.addWidget(self.__muted("No actions logged yet. Log one from Trends & actions."))
            return
        labels = {report.action.action_id: report.label for report in self.__data.load_impacts()}
        for action in actions:
            row = QHBoxLayout()
            text = QLabel(f"<b>{action.description}</b><br>{action.theme} · done {self.__date(action.action_date)}")
            text.setWordWrap(True)
            row.addWidget(text, 1)
            label = labels.get(action.action_id)
            if label:
                row.addWidget(Pill(label, {"Effective": "good", "Worse": "critical"}.get(label, "neutral")),
                              0, Qt.AlignmentFlag.AlignTop)
            body.addLayout(row)

    @staticmethod
    def __box(card: Card) -> QVBoxLayout:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        card.body.addWidget(holder)
        return layout

    # Empties a layout (widgets and nested layouts) so refresh can rebuild it.
    @classmethod
    def __clear(cls, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout() is not None:
                cls.__clear(item.layout())
                item.layout().deleteLater()
        return layout

    @staticmethod
    def __muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("mutedText")
        label.setWordWrap(True)
        return label

    @staticmethod
    def __note(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("smallNote")
        label.setWordWrap(True)
        return label

    # "2026-11-11T18:41:29" or "2026-11-11" -> "11 Nov 2026".
    @staticmethod
    def __date(text) -> str:
        try:
            moment = datetime.fromisoformat(str(text))
        except ValueError:
            return str(text or "an unknown date")
        return f"{moment.day} {moment:%b %Y}"
