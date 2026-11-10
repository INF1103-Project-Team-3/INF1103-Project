# QtABCMeta: lets a Qt widget class also be an abstract class.

from abc import ABCMeta

from PySide6.QtWidgets import QWidget


# Combines Qt's metaclass with ABCMeta, so @abstractmethod works on a QWidget subclass.
class QtABCMeta(type(QWidget), ABCMeta):
    pass
