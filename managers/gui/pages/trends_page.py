# TrendsPage: each theme's priority across runs, comparing two runs, and the actions logged with their impact.

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..dialogs.log_action_dialog import LogActionDialog
from ..widgets.card import Card
from ..widgets.combo_box import ComboBox
from ..widgets.pill import Pill
from ..widgets.record_tags import short_date
from ..widgets.trend_chart import TrendChart
from .base_page import BasePage

SHOWN_AT_START = 3
MAX_COMPARED = 8
PILLS_PER_ROW = 4
LEGEND_COLUMNS = 4
SHAPE_SYMBOLS = {"circle": "●", "square": "■", "triangle": "▲"}
STATUS_KINDS = {"Escalating": "warn", "New": "info", "Easing": "good", "Steady": "neutral",
                "Not reported": "neutral"}
IMPACT_KINDS = {"Effective": "good", "Worse": "critical"}


# Emits action_logged(action). With a LogicManager and Data's runs, comparisons come from
# logic.compare_runs; otherwise they show the priority change only.
class TrendsPage(BasePage):
    action_logged = Signal(object)

    def __init__(self, data, logic=None, parent=None):
        super().__init__("Trends & actions", "How each theme's priority changes across runs, and whether "
                                             "the actions you took made a difference.", parent)
        self.__data = data
        self.__logic = logic
        self.__unsaved = []
        self.__checks = {}
        self.__history_size = -1
        self.__history = []

        self.__log_button = QPushButton("+ Log action")
        self.__log_button.setObjectName("bigPrimaryButton")
        self.__log_button.clicked.connect(self.open_log_dialog)
        self.add_header_widget(self.__log_button)

        chart_card = Card("Priority across runs")
        self.__legend = QGridLayout()
        self.__legend.setHorizontalSpacing(24)
        self.__legend.setVerticalSpacing(8)
        chart_card.body.addLayout(self.__legend)
        self.__chart = TrendChart()
        chart_card.body.addWidget(self.__chart)
        note = QLabel("Priority (0-100) weighs severity and sentiment. A gap means the theme had no "
                      "counted entries in that run (for example, before a new theme was confirmed).")
        note.setObjectName("smallNote")
        note.setWordWrap(True)
        chart_card.body.addWidget(note)

        picker = QHBoxLayout()
        picker.setSpacing(8)
        title = QLabel("Compare")
        title.setObjectName("fieldLabel")
        self.__run_x = ComboBox()
        self.__run_x.setObjectName("compareFrom")
        self.__run_y = ComboBox()
        self.__run_y.setObjectName("compareTo")
        for box in (self.__run_x, self.__run_y):
            box.currentIndexChanged.connect(self.__build_comparison)
        picker.addWidget(title)
        picker.addWidget(self.__run_x)
        picker.addWidget(QLabel("with"))
        picker.addWidget(self.__run_y)
        picker.addStretch()
        chart_card.body.addLayout(picker)
        compare = QFrame()
        compare.setObjectName("buttonRow")
        self.__compare = QGridLayout(compare)
        self.__compare.setContentsMargins(0, 4, 0, 0)
        self.__compare.setHorizontalSpacing(8)
        self.__compare.setVerticalSpacing(8)
        chart_card.body.addWidget(compare)
        self.content_layout.addWidget(chart_card)

        self.__actions_card = Card("Actions taken", spacing=0)
        self.__rows = QVBoxLayout()
        self.__rows.setSpacing(0)
        self.__actions_card.body.addSpacing(10)
        self.__actions_card.body.addLayout(self.__rows)
        self.content_layout.addWidget(self.__actions_card)
        self.content_layout.addStretch()

    @property
    def chart(self) -> TrendChart:
        return self.__chart

    def open_log_dialog(self, theme: str | None = None) -> None:
        dialog = LogActionDialog(self.__data.load_known_themes(), self,
                                 theme=theme if isinstance(theme, str) else None)
        if dialog.exec() and dialog.action is not None:
            self.__unsaved.append(dialog.action)
            self.action_logged.emit(dialog.action)
            self.refresh()

    def forget_unsaved(self) -> None:
        self.__unsaved.clear()

    def refresh(self) -> None:
        self.__history = self.__data.load_history()
        self.__refresh_chart()
        self.__refresh_pickers()
        self.__refresh_actions()

    # Shows Run x vs Run y (1-based run numbers) in the comparison row.
    def compare(self, older: int, newer: int) -> None:
        self.__run_x.setCurrentIndex(older - 1)
        self.__run_y.setCurrentIndex(newer - 1)
        self.__build_comparison()

    def __refresh_chart(self) -> None:
        history = self.__history
        themes = []
        for run in history:
            for theme in self.__priorities(run):
                if theme not in themes:
                    themes.append(theme)
        latest = self.__priorities(history[-1]) if history else {}
        themes.sort(key=lambda theme: -(latest.get(theme) or 0))
        if len(history) != self.__history_size:
            self.__history_size = len(history)
            self.__chart.set_data(self.__labels(), self.__series(themes))
            self.__build_legend(themes)
        self.__update_chart()

    def __build_legend(self, themes: list[str]) -> None:
        shown = {name for name, box in self.__checks.items() if box.isChecked()} or set(themes[:SHOWN_AT_START])
        while self.__legend.count():
            widget = self.__legend.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.__checks = {}
        for index, theme in enumerate(themes):
            colour = self.__chart.colour(theme)
            symbol = SHAPE_SYMBOLS[self.__chart.shape(theme)]
            box = QCheckBox(f"{theme}  {symbol}")
            box.setStyleSheet(f"QCheckBox {{ color: {colour}; font-weight: 600; }}")
            box.setChecked(theme in shown)
            box.toggled.connect(self.__update_chart)
            self.__checks[theme] = box
            self.__legend.addWidget(box, index // LEGEND_COLUMNS, index % LEGEND_COLUMNS)

    def __update_chart(self, *_args) -> None:
        shown = {name for name, box in self.__checks.items() if box.isChecked()}
        markers = []
        for action in [*self.__data.load_actions(), *self.__unsaved]:
            if action.theme in shown:
                position = self.__run_position(self.__history, action.action_date)
                if position is not None:
                    markers.append((position, f"Action: {action.description}"))
        self.__chart.set_data(self.__labels(), self.__series(list(self.__checks)), markers, top=100)
        self.__chart.set_visible_series(shown)

    def __labels(self) -> list[str]:
        return [f"{short_date(run['finished_at'])} · Run {run['run']}" for run in self.__history]

    def __series(self, themes: list[str]) -> dict[str, list[float | None]]:
        return {theme: [self.__priorities(run).get(theme) for run in self.__history] for theme in themes}

    # Older history rows (the demo's) may only have counts; those runs then show no priority.
    @staticmethod
    def __priorities(run: dict) -> dict:
        return run.get("theme_priority", {})

    # Where a date falls on the run axis, e.g. 1.5 = halfway between run 2 and run 3.
    @staticmethod
    def __run_position(history: list[dict], action_date: str) -> float | None:
        if len(history) < 2:
            return None
        day = date.fromisoformat(action_date)
        dates = [date.fromisoformat(run["finished_at"]) for run in history]
        if day <= dates[0] or day > dates[-1]:
            return None
        for index in range(1, len(dates)):
            if day <= dates[index]:
                span = (dates[index] - dates[index - 1]).days or 1
                return index - 1 + (day - dates[index - 1]).days / span
        return None

    def __refresh_pickers(self) -> None:
        labels = self.__labels()
        for box, default in ((self.__run_x, len(labels) - 2), (self.__run_y, len(labels) - 1)):
            box.blockSignals(True)
            box.clear()
            box.addItems(labels)
            box.setCurrentIndex(max(default, 0) if labels else -1)
            box.blockSignals(False)
        self.__build_comparison()

    def __build_comparison(self, *_args) -> None:
        while self.__compare.count():
            item = self.__compare.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        older, newer = self.__run_x.currentIndex(), self.__run_y.currentIndex()
        if len(self.__history) < 2 or older < 0 or newer < 0 or older == newer:
            note = QLabel("Pick two different runs to compare." if len(self.__history) >= 2
                          else "Run comparison appears after two runs.")
            note.setObjectName("mutedText")
            self.__compare.addWidget(note, 0, 0)
            return
        for index, (theme, status, before, after) in enumerate(self.__changes(older, newer)[:MAX_COMPARED]):
            if before is None:
                pill = Pill(f"{theme} · new ({after})", "info")
            elif after is None:
                pill = Pill(f"{theme} · not reported", "neutral")
            else:
                arrow = "▲" if after > before else "▼" if after < before else "—"
                kind = STATUS_KINDS.get(status) or ("warn" if after > before else "good" if after < before
                                                    else "neutral")
                pill = Pill(f"{theme} {arrow} {before} → {after}", kind)
            self.__compare.addWidget(pill, index // PILLS_PER_ROW, index % PILLS_PER_ROW,
                                     Qt.AlignmentFlag.AlignLeft)
        self.__compare.setColumnStretch(PILLS_PER_ROW, 1)

    # (theme, Logic's status or None, priority before, priority after), biggest change first.
    def __changes(self, older: int, newer: int) -> list[tuple]:
        runs = self.__data.load_runs() if self.__logic is not None and hasattr(self.__data, "load_runs") else []
        if len(runs) == len(self.__history):
            report = self.__logic.compare_runs(runs[newer], runs[older])
            rows = [(row["theme"], row["status"], row["priority"].get("previous"), row["priority"].get("current"))
                    for row in report.themes]
        else:
            before, after = self.__priorities(self.__history[older]), self.__priorities(self.__history[newer])
            rows = [(theme, None, before.get(theme), after.get(theme)) for theme in {*before, *after}]
        return sorted(rows, key=lambda row: -abs((row[3] or 0) - (row[2] or 0)))

    def __refresh_actions(self) -> None:
        while self.__rows.count():
            widget = self.__rows.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        saved = self.__data.load_actions()
        reports = {report.action.action_id: report for report in self.__data.load_impacts()}
        for action in saved:
            self.__rows.addWidget(self.__action_row(action, reports.get(action.action_id)))
        for action in self.__unsaved:
            self.__rows.addWidget(self.__action_row(action, None, "Saved on the next run"))
        if not saved and not self.__unsaved:
            empty = QLabel("No actions logged yet.")
            empty.setObjectName("mutedText")
            self.__rows.addWidget(empty)

    # One action: title, details, impact label, and the report with its weekly chart folded away.
    def __action_row(self, action, report, unsaved_text: str = "") -> QFrame:
        row = QFrame()
        row.setObjectName("actionRow")
        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 12, 0, 12)
        outer.setSpacing(8)
        top = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(action.description)
        title.setObjectName("actionTitle")
        title.setWordWrap(True)
        meta = f"{action.theme} · {short_date(action.action_date)}"
        if action.keyword:
            meta += f" · keyword \"{action.keyword}\""
        meta_label = QLabel(meta)
        meta_label.setObjectName("actionMeta")
        text.addWidget(title)
        text.addWidget(meta_label)
        top.addLayout(text, 1)
        if report is None:
            top.addWidget(Pill(unsaved_text or "Impact report after the next run",
                               "caution" if unsaved_text else "neutral"))
            outer.addLayout(top)
            return row
        top.addWidget(Pill(report.label, IMPACT_KINDS.get(report.label, "neutral")))
        toggle = QPushButton("Show report")
        toggle.setObjectName("linkButton")
        top.addWidget(toggle)
        outer.addLayout(top)

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        message = QLabel(report.message)
        message.setWordWrap(True)
        details_layout.addWidget(message)
        for warning in report.warnings:
            note = QLabel(f"⚠ {warning}")
            note.setObjectName("smallNote")
            note.setWordWrap(True)
            details_layout.addWidget(note)
        if report.weekly:
            chart = TrendChart()
            chart.setObjectName("impactChart")
            chart.setMinimumHeight(200)
            weeks = report.weekly
            chart.set_data([short_date(week["week_start"]) for week in weeks],
                           {"Negative": [week.get("negative") for week in weeks],
                            "All entries": [week.get("total") for week in weeks]},
                           [(self.__week_position(weeks, action.action_date), "Action")])
            details_layout.addWidget(chart)
            caption = QLabel("Entries per week with this theme (and keyword). Weeks that haven't started "
                             "are left out. This shows correlation, not proof.")
            caption.setObjectName("smallNote")
            caption.setWordWrap(True)
            details_layout.addWidget(caption)
        details.hide()
        outer.addWidget(details)

        def flip(_checked=False):
            details.setVisible(not details.isVisible())
            toggle.setText("Hide report" if details.isVisible() else "Show report")
        toggle.clicked.connect(flip)
        return row

    # The action date's position on the weekly axis, e.g. 2.5 = halfway through the third week.
    @staticmethod
    def __week_position(weeks: list[dict], action_date: str) -> float:
        first = date.fromisoformat(weeks[0]["week_start"])
        position = (date.fromisoformat(action_date) - first).days / 7
        return min(max(position, 0.0), len(weeks) - 1)
