from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QColorDialog, QPushButton

from ...core.i18n import T
from ..theme.tokens import C


class ColorButton(QPushButton):
    """Shows a colour swatch + hex; opens a colour picker. Emits `changed(hex)`."""
    changed = Signal(str)

    def __init__(self, color: str):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self.pick)
        self.set(color)

    def set(self, color: str) -> None:
        self.color = color
        pm = QPixmap(36, 36); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(C["MUTED"]), 2)); p.setBrush(QColor(color)); p.drawEllipse(2, 2, 32, 32); p.end()
        self.setIcon(QIcon(pm)); self.setIconSize(QSize(18, 18)); self.setText("  " + color.upper())

    def pick(self) -> None:
        c = QColorDialog.getColor(QColor(self.color), self, T("pick_color"))
        if c.isValid():
            self.set(c.name()); self.changed.emit(c.name())
