"""Decorative eight-pointed star motif and the sidebar that draws it."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame

from ...core.i18n import rtl
from ..theme.tokens import C


def paint_star(p, cx, cy, r, pen):
    """Eight-pointed star (two overlapping squares) used as a decorative motif."""
    p.save(); p.setPen(pen); p.setBrush(Qt.NoBrush)
    for a in (0, 45):
        p.save(); p.translate(cx, cy); p.rotate(a); p.drawRoundedRect(QRectF(-r, -r, 2 * r, 2 * r), r * 0.08, r * 0.08); p.restore()
    p.drawEllipse(QPointF(cx, cy), r * 0.42, r * 0.42)
    p.restore()


class Sidebar(QFrame):
    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        col = QColor(C["ACCENT"]); col.setAlpha(26)
        W, H = self.width(), self.height()
        for x, y, r in [(W * 0.15, H * 0.74, 58), (W * 0.78, H * 0.86, 40), (W * 0.36, H * 0.97, 30)]:
            paint_star(p, x, y, r, QPen(col, 1.4))
        p.setPen(QPen(QColor(C["BORDER"]), 1))
        x = 0.5 if rtl() else W - 0.5
        p.drawLine(QPointF(x, 0), QPointF(x, H))
        p.end()
