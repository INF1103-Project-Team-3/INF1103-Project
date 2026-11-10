# TrendChart: a line chart of each theme across runs, drawn with QPainter.

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..style import BORDER_SOFT, MUTED

SERIES_COLOURS = ("#C2551B", "#1E6B34", "#2F5BEA", "#7B4FD6", "#0F7C80", "#8A6D1F", "#C23A7A", "#6E6E6A")
SHAPES = ("circle", "square", "triangle")
ACTION_COLOUR = "#C9A227"
ACTION_TEXT = "#7A5300"
LEFT, RIGHT, TOP, BOTTOM = 44, 170, 34, 48
LABEL_GAP = 16


# Theme counts per run, with dashed lines for actions.
class TrendChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.__labels = []
        self.__series = {}
        self.__colours = {}
        self.__markers = []
        self.__hidden = set()

    def set_data(self, run_labels: list[str], series: dict[str, list[float]],
                 markers: list[tuple[float, str]] | None = None) -> None:
        self.__labels = list(run_labels)
        self.__series = {name: list(values) for name, values in series.items()}
        self.__colours = {name: SERIES_COLOURS[i % len(SERIES_COLOURS)] for i, name in enumerate(self.__series)}
        self.__markers = list(markers or [])
        self.update()

    def colour(self, name: str) -> str:
        return self.__colours.get(name, MUTED)

    def shape(self, name: str) -> str:
        names = list(self.__series)
        return SHAPES[names.index(name) % len(SHAPES)] if name in names else "circle"

    def set_visible_series(self, names: set[str]) -> None:
        self.__hidden = set(self.__series) - set(names)
        self.update()

    def visible_series(self) -> list[str]:
        return [name for name in self.__series if name not in self.__hidden]

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(LEFT, TOP, max(self.width() - LEFT - RIGHT, 10), max(self.height() - TOP - BOTTOM, 10))
        if not self.__labels:
            painter.setPen(QColor(MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No runs yet")
            return
        top_value = self.__nice_max()
        self.__draw_grid(painter, area, top_value)
        self.__draw_x_labels(painter, area)
        self.__draw_markers(painter, area)
        ends = []
        for name in self.visible_series():
            points = [self.__point(area, index, value, top_value)
                      for index, value in enumerate(self.__series[name]) if value is not None]
            self.__draw_line(painter, points, QColor(self.colour(name)), self.shape(name))
            if points:
                ends.append([points[-1].y(), name, points[-1].x()])
        self.__draw_end_labels(painter, ends, area)

    def __nice_max(self) -> int:
        values = [v for name in self.visible_series() for v in self.__series[name] if v is not None]
        highest = max(values, default=1)
        step = max(1, math.ceil(highest / 3))
        return step * 3 if highest > 0 else 3

    def __x(self, area: QRectF, position: float) -> float:
        runs = len(self.__labels)
        if runs == 1:
            return area.center().x()
        return area.left() + area.width() * position / (runs - 1)

    def __point(self, area: QRectF, index: int, value: float, top_value: int) -> QPointF:
        return QPointF(self.__x(area, index), area.bottom() - area.height() * value / top_value)

    def __small_font(self, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(bold)
        return font

    def __draw_grid(self, painter: QPainter, area: QRectF, top_value: int) -> None:
        painter.setFont(self.__small_font())
        step = top_value // 3
        for tick in range(0, top_value + 1, step):
            y = area.bottom() - area.height() * tick / top_value
            painter.setPen(QPen(QColor(BORDER_SOFT if tick else "#BDBDB8"), 1))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(QColor(MUTED))
            painter.drawText(QRectF(0, y - 8, LEFT - 10, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(tick))

    def __draw_x_labels(self, painter: QPainter, area: QRectF) -> None:
        painter.setFont(self.__small_font())
        painter.setPen(QColor(MUTED))
        for index, label in enumerate(self.__labels):
            x = self.__x(area, index)
            if index == 0 and len(self.__labels) > 1:
                painter.drawText(QRectF(x - 20, area.bottom() + 10, 140, 18), Qt.AlignmentFlag.AlignLeft, label)
            else:
                painter.drawText(QRectF(x - 70, area.bottom() + 10, 140, 18), Qt.AlignmentFlag.AlignHCenter, label)

    def __draw_markers(self, painter: QPainter, area: QRectF) -> None:
        painter.setFont(self.__small_font(bold=True))
        for position, text in self.__markers:
            x = self.__x(area, position)
            pen = QPen(QColor(ACTION_COLOUR), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, area.top() - 12), QPointF(x, area.bottom()))
            painter.setPen(QColor(ACTION_TEXT))
            painter.drawText(QRectF(x + 6, area.top() - 28, 260, 16), Qt.AlignmentFlag.AlignLeft, text)

    @staticmethod
    def __draw_line(painter: QPainter, points: list[QPointF], colour: QColor, shape: str) -> None:
        if len(points) > 1:
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.setPen(QPen(colour, 2.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        for point in points:
            if shape == "square":
                painter.drawRect(QRectF(point.x() - 5, point.y() - 5, 10, 10))
            elif shape == "triangle":
                painter.drawPolygon(QPolygonF([QPointF(point.x(), point.y() - 6),
                                               QPointF(point.x() - 6, point.y() + 5),
                                               QPointF(point.x() + 6, point.y() + 5)]))
            else:
                painter.drawEllipse(point, 5, 5)

    # Theme names at the right end of each line, pushed apart so they never overlap.
    def __draw_end_labels(self, painter: QPainter, ends: list, area: QRectF) -> None:
        ends.sort()
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + LABEL_GAP)
        overflow = ends[-1][0] - area.bottom() if ends else 0
        if overflow > 0:
            for end in ends:
                end[0] -= overflow
        painter.setFont(self.__small_font(bold=True))
        for y, name, x in ends:
            painter.setPen(QColor(self.colour(name)))
            painter.drawText(QRectF(x + 12, y - 8, RIGHT - 16, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
