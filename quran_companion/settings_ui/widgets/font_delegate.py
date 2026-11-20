"""Rows of a font dropdown: the font's name in the interface font, and a short sample written in
that font on the other side. Same rounded hover/selected look as the other dropdowns."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ...core.i18n import rtl
from ..theme.tokens import C

DEFAULT_SAMPLE = "أبجد Aa"


class FontRowDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, sample: str = DEFAULT_SAMPLE, sample_px: int = 17):
        super().__init__(parent)
        self.sample, self.sample_px = sample, sample_px

    def sizeHint(self, opt, idx):
        return QSize(220, max(40, int(QFontMetricsF(opt.font).height() + 18)))

    def paint(self, p: QPainter, opt, idx):
        family = idx.data(Qt.DisplayRole) or ""
        R = rtl()
        p.save(); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.TextAntialiasing)
        rect = QRectF(opt.rect).adjusted(2, 1, -2, -1)
        sel, hov = bool(opt.state & QStyle.State_Selected), bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            ac = QColor(C["ACCENT"]); fill = QColor(ac); fill.setAlpha(40 if sel else 0)
            if hov and not sel: fill = QColor(C["TEXT"]); fill.setAlpha(14)
            p.setPen(QPen(QColor(ac.red(), ac.green(), ac.blue(), 90), 1) if sel else Qt.NoPen); p.setBrush(fill)
            p.drawRoundedRect(rect, 8, 8)
        inner = rect.adjusted(12, 0, -12, 0)
        lead = (Qt.AlignRight if R else Qt.AlignLeft) | Qt.AlignAbsolute | Qt.AlignVCenter
        trail = (Qt.AlignLeft if R else Qt.AlignRight) | Qt.AlignAbsolute | Qt.AlignVCenter

        sf = QFont(family); sf.setPixelSize(self.sample_px)
        sm = QFontMetricsF(sf)
        sw = min(sm.horizontalAdvance(self.sample), inner.width() * 0.45)
        p.setFont(sf); p.setPen(QColor(C["SUB"]))
        p.drawText(inner, trail, sm.elidedText(self.sample, Qt.ElideRight, sw + 1))

        nf = QFont(opt.font)
        if sel: nf.setWeight(QFont.DemiBold)
        name_rect = QRectF(inner)
        if R: name_rect.setLeft(inner.left() + sw + 16)
        else: name_rect.setRight(inner.right() - sw - 16)
        p.setFont(nf); p.setPen(QColor(C["ACCENT"] if sel else C["TEXT"]))
        p.drawText(name_rect, lead, QFontMetricsF(nf).elidedText(family, Qt.ElideRight, name_rect.width()))
        p.restore()
