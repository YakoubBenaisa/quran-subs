"""Paints one reciter row: name, other-language name, style, downloaded badge. RTL-aware."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ...core.i18n import T, rtl
from ...core.models import Reciter
from ..theme.tokens import C

ROW_HEIGHT = 60
RECITER_ROLE = Qt.UserRole
DOWNLOADED_ROLE = Qt.UserRole + 1


class ReciterDelegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        # tall enough for the name line and the style line in the current UI font (Arabic fonts are taller)
        base = opt.font.pointSizeF()
        f = QFont(opt.font); f.setPointSizeF(base + (1.5 if rtl() else 0.5)); f.setWeight(QFont.DemiBold)
        f2 = QFont(opt.font); f2.setPointSizeF(base - 1)
        h = QFontMetricsF(f).height() + QFontMetricsF(f2).height() + 2 + 22
        return QSize(200, max(ROW_HEIGHT, int(h + 0.99)))

    def paint(self, p, opt, idx):
        r: Reciter = idx.data(RECITER_ROLE); n = idx.data(DOWNLOADED_ROLE) or 0
        if not r: return
        R = rtl()
        p.save(); p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(opt.rect).adjusted(6 if R else 2, 2, -2 if R else -6, -2)
        sel, hov = bool(opt.state & QStyle.State_Selected), bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            ac = QColor(C["ACCENT"]); fill = QColor(ac); fill.setAlpha(34); hv = QColor(C["TEXT"]); hv.setAlpha(12)
            p.setPen(QPen(ac, 1.2) if sel else Qt.NoPen); p.setBrush(fill if sel else hv)
            p.drawRoundedRect(rect, 12, 12)
        x = rect.adjusted(14, 9, -14, -9)
        main = QRectF(x)
        f2 = QFont(opt.font); f2.setPointSizeF(opt.font.pointSizeF() - 1)
        if n:
            badge = f"⤓ {n}"; bw = QFontMetricsF(f2).horizontalAdvance(badge) + 18
            b = QRectF(x.left() if R else x.right() - bw, x.center().y() - 11, bw, 22)
            bc = QColor(C["ACCENT"]); bc.setAlpha(40)
            p.setPen(Qt.NoPen); p.setBrush(bc); p.drawRoundedRect(b, 11, 11)
            p.setFont(f2); p.setPen(QColor(C["ACCENT"])); p.drawText(b, Qt.AlignCenter, badge)
            if R: main.setLeft(b.right() + 10)
            else: main.setRight(b.left() - 10)
        title = r.name(R)
        other = (r.en or "") if R else r.ar
        style = r.short_style + (("  ·  " + T("n_surahs", n=r.count)) if r.count < 114 else "")
        A = (Qt.AlignRight if R else Qt.AlignLeft) | Qt.AlignAbsolute
        B = (Qt.AlignLeft if R else Qt.AlignRight) | Qt.AlignAbsolute
        fo = QFont(opt.font); fo.setPointSizeF(opt.font.pointSizeF() + (0 if R else 1.5))
        ow = min(QFontMetricsF(fo).horizontalAdvance(other), main.width() * 0.42) if other else 0
        p.setFont(fo); p.setPen(QColor(C["SUB"]))
        if other: p.drawText(main, B | Qt.AlignVCenter, QFontMetricsF(fo).elidedText(other, Qt.ElideRight, ow + 1))
        tx = QRectF(main)
        if R: tx.setLeft(main.left() + ow + 14)
        else: tx.setRight(main.right() - ow - 14)
        f = QFont(opt.font); f.setPointSizeF(opt.font.pointSizeF() + (1.5 if R else 0.5)); f.setWeight(QFont.DemiBold)
        p.setFont(f); p.setPen(QColor(C["ACCENT"] if sel else C["TEXT"]))
        p.drawText(tx, A | Qt.AlignTop, QFontMetricsF(f).elidedText(title, Qt.ElideRight, tx.width()))
        p.setFont(f2); p.setPen(QColor(C["MUTED"]))
        p.drawText(tx, A | Qt.AlignBottom, QFontMetricsF(f2).elidedText(style, Qt.ElideRight, tx.width()))
        p.restore()
