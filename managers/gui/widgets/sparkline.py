# Sparkline: a tiny line of one theme's priority over recent runs, with a gap where a run has none.

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..style import BLUE

WIDTH, HEIGHT, MARGIN = 96, 26, 3


# Values are 0-100 (priority); None breaks the line instead of dropping to zero.
class Sparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(WIDTH, HEIGHT)
        self.__values = []

    def set_values(self, values: list[float | None]) -> None:
        self.__values = list(values)
        self.update()

    # Runs of consecutive values, split wherever a value is None.
    def segments(self) -> list[list[tuple[int, float]]]:
        parts, current = [], []
        for index, value in enumerate(self.__values):
            if value is None:
                if current:
                    parts.append(current)
                current = []
            else:
                current.append((index, value))
        if current:
            parts.append(current)
        return parts

    def paintEvent(self, _event) -> None:
        if not self.__values:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = QColor(BLUE)
        painter.setPen(QPen(colour, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        last = None
        for part in self.segments():
            points = [self.__point(index, value) for index, value in part]
            if len(points) == 1:
                painter.drawEllipse(points[0], 1.2, 1.2)
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
            last = points[-1]
        if last is not None:
            painter.setBrush(colour)
            painter.drawEllipse(last, 2.4, 2.4)

    def __point(self, index: int, value: float) -> QPointF:
        steps = max(len(self.__values) - 1, 1)
        x = MARGIN + (WIDTH - 2 * MARGIN) * index / steps
        y = HEIGHT - MARGIN - (HEIGHT - 2 * MARGIN) * max(0.0, min(value, 100.0)) / 100
        return QPointF(x, y)
