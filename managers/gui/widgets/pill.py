# Pill: a small rounded tag such as "Critical", "Theme mismatch" or "5 to review".

from PySide6.QtWidgets import QLabel, QSizePolicy

from ..style import restyle

KINDS = ("critical", "warn", "info", "caution", "good", "neutral", "running")


# kind picks the colours (see style.py): critical, warn, info, caution, good, neutral, running.
class Pill(QLabel):
    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setObjectName("pill")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"Unknown pill kind: {kind}")
        self.setProperty("kind", kind)
        restyle(self)
