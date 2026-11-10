# TrendsPage: themes across runs and the actions an admin has logged.

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..dialogs.log_action_dialog import LogActionDialog
from ..widgets.card import Card
from ..widgets.pill import Pill
from ..widgets.record_tags import short_date
from ..widgets.trend_chart import TrendChart
from .base_page import BasePage

SHOWN_AT_START = 3
MAX_COMPARED = 4
LEGEND_COLUMNS = 4
SHAPE_SYMBOLS = {"circle": "●", "square": "■", "triangle": "▲"}


# Emits action_logged(action). Run comparison here is a placeholder for Logic's TrendReport.
class TrendsPage(BasePage):
    action_logged = Signal(object)

    def __init__(self, data, parent=None):
        super().__init__("Trends & actions", "How themes change across runs, and whether "
                                             "the actions you took made a difference.", parent)
        self.__data = data
        self.__unsaved = []
        self.__checks = {}
        self.__history_size = -1

        self.__log_button = QPushButton("+ Log action")
        self.__log_button.setObjectName("bigPrimaryButton")
        self.__log_button.clicked.connect(self.open_log_dialog)
        self.add_header_widget(self.__log_button)

        chart_card = Card("Themes across runs")
        self.__legend = QGridLayout()
        self.__legend.setHorizontalSpacing(24)
        self.__legend.setVerticalSpacing(8)
        chart_card.body.addLayout(self.__legend)
        self.__chart = TrendChart()
        chart_card.body.addWidget(self.__chart)
        compare = QFrame()
        compare.setObjectName("buttonRow")
        self.__compare = QHBoxLayout(compare)
        self.__compare.setContentsMargins(0, 14, 0, 0)
        self.__compare.setSpacing(8)
        chart_card.body.addWidget(compare)
        self.content_layout.addWidget(chart_card)

        self.__actions_card = Card("Actions taken", spacing=0)
        self.__rows = QVBoxLayout()
        self.__rows.setSpacing(0)
        self.__actions_card.body.addSpacing(10)
        self.__actions_card.body.addLayout(self.__rows)
        self.content_layout.addWidget(self.__actions_card)
        self.content_layout.addStretch()

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
        self.__refresh_chart()
        self.__refresh_actions()

    def __refresh_chart(self) -> None:
        history = self.__data.load_history() if hasattr(self.__data, "load_history") else []
        themes = []
        for run in history:
            for theme in run["theme_counts"]:
                if theme not in themes:
                    themes.append(theme)
        latest = history[-1]["theme_counts"] if history else {}
        themes.sort(key=lambda theme: -latest.get(theme, 0))
        series = {theme: [run["theme_counts"].get(theme, 0) for run in history] for theme in themes}
        labels = [f"{short_date(run['finished_at'])} · Run {run['run']}" for run in history]
        self.__chart.set_data(labels, series)

        if len(history) != self.__history_size:
            self.__history_size = len(history)
            self.__build_legend(themes)
        self.__update_chart()
        self.__build_comparison(history)

    def __build_legend(self, themes: list[str]) -> None:
        shown = {name for name, box in self.__checks.items() if box.isChecked()} or set(themes[:SHOWN_AT_START])
        while self.__legend.count():
            widget = self.__legend.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.__checks = {}
        for index, theme in enumerate(themes):
            colour = self.__chart.colour(theme)
            symbol = SHAPE_SYMBOLS[self.__chart.shape(theme)]
            box = QCheckBox(f"{theme}  {symbol}")
            box.setStyleSheet(f"QCheckBox {{ color: {colour}; font-weight: 600; }}")
            box.setChecked(theme in shown)
            box.toggled.connect(self.__on_legend_toggled)
            self.__checks[theme] = box
            self.__legend.addWidget(box, index // LEGEND_COLUMNS, index % LEGEND_COLUMNS)

    def __on_legend_toggled(self, *_args) -> None:
        self.__update_chart()
        self.__build_comparison(self.__data.load_history() if hasattr(self.__data, "load_history") else [])

    def __update_chart(self, *_args) -> None:
        shown = {name for name, box in self.__checks.items() if box.isChecked()}
        self.__chart.set_visible_series(shown)
        history = self.__data.load_history() if hasattr(self.__data, "load_history") else []
        markers = []
        for action in [*self.__data.load_actions(), *self.__unsaved]:
            if action.theme in shown:
                position = self.__run_position(history, action.action_date)
                if position is not None:
                    markers.append((position, f"Action: {action.description}"))
        labels = [f"{short_date(run['finished_at'])} · Run {run['run']}" for run in history]
        series = {theme: [run["theme_counts"].get(theme, 0) for run in history] for theme in self.__checks}
        self.__chart.set_data(labels, series, markers)
        self.__chart.set_visible_series(shown)

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

    def __build_comparison(self, history: list[dict]) -> None:
        while self.__compare.count():
            item = self.__compare.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if len(history) < 2:
            note = QLabel("Run comparison appears after two runs.")
            note.setObjectName("mutedText")
            self.__compare.addWidget(note)
            return
        now, before = history[-1], history[-2]
        title = QLabel(f"Run {now['run']} vs Run {before['run']}:")
        title.setObjectName("fieldLabel")
        self.__compare.addWidget(title)
        shown = [name for name, box in self.__checks.items() if box.isChecked()]
        for theme in shown[:MAX_COMPARED]:
            new, old = now["theme_counts"].get(theme, 0), before["theme_counts"].get(theme, 0)
            if new == old == 0:
                continue
            if old == 0:
                pill = Pill(f"{theme} · new", "info")
            elif new > old:
                pill = Pill(f"{theme} ▲ {old} → {new}", "warn")
            elif new < old:
                pill = Pill(f"{theme} ▼ {old} → {new}", "good")
            else:
                pill = Pill(f"{theme} — stable", "neutral")
            self.__compare.addWidget(pill)
        self.__compare.addStretch()

    def __refresh_actions(self) -> None:
        while self.__rows.count():
            widget = self.__rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        saved = self.__data.load_actions()
        for action in saved:
            self.__rows.addWidget(self.__action_row(action, "Impact report pending", "neutral"))
        for action in self.__unsaved:
            self.__rows.addWidget(self.__action_row(action, "Saved on the next run", "caution"))
        if not saved and not self.__unsaved:
            empty = QLabel("No actions logged yet.")
            empty.setObjectName("mutedText")
            self.__rows.addWidget(empty)

    @staticmethod
    def __action_row(action, status: str, kind: str) -> QFrame:
        row = QFrame()
        row.setObjectName("actionRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 12, 0, 12)
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
        layout.addLayout(text, 1)
        layout.addWidget(Pill(status, kind))
        return row
