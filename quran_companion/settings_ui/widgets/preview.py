"""Live preview of the on-screen verses over a mock desktop, using the same paginator and painter."""
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

from ...core.i18n import T
from ...core.settings import Settings
from ...core.text import verse_with_marker
from ...overlay.painter import make_paginator, page_lines, paint_lines
from ...overlay.window import EXTRA_HEIGHT

SAMPLE = ("ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ", "All praise is due to Allah, Lord of the worlds.", 2)


class Preview(QWidget):
    def __init__(self, get_style: Callable[[], tuple[Settings, bool]]):
        """`get_style` returns (settings to preview, show translation?)."""
        super().__init__()
        self.get_style = get_style
        self.sample = SAMPLE          # replaced by a long verse (Ayat al-Kursi) once loaded
        self.setMinimumHeight(270)
        self.setLayoutDirection(Qt.LeftToRight)

    def set_sample(self, ar: str, tr: str, n: int) -> None:
        self.sample = (ar, tr, n); self.update()

    def _desktop(self, p: QPainter, W: int, H: int) -> None:
        g = QLinearGradient(0, 0, W, H); g.setColorAt(0, QColor("#1d3557")); g.setColorAt(1, QColor("#5b2a62"))
        p.fillRect(self.rect(), g)
        for x, y, w, h, c in [(0.05, 0.08, 0.5, 0.7, "#f3f4f6"), (0.44, 0.2, 0.5, 0.72, "#22272f")]:
            r = QRectF(W * x, H * y, W * w, H * h)
            p.setPen(Qt.NoPen); p.setBrush(QColor(c)); p.drawRoundedRect(r, 8, 8)
            p.setBrush(QColor(0, 0, 0, 28)); p.drawRoundedRect(QRectF(r.x(), r.y(), r.width(), 22), 8, 8)
            p.setBrush(QColor(128, 128, 128, 80))
            for k in range(6):
                p.drawRoundedRect(QRectF(r.x() + 16, r.y() + 38 + k * 17, r.width() * (0.35 + 0.15 * (k % 3)), 7), 3, 3)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, W, H), 12, 12); p.setClipPath(clip)
        self._desktop(p, W, H)
        s0, with_tr = self.get_style()
        k = min(1.0, max(0.2, W / max(1, QApplication.primaryScreen().geometry().width())))
        ar, tr, n = self.sample
        for _ in range(8):  # scale like the real screen; shrink more if the page would not fit the preview
            s = s0.with_(size=max(6, int(s0.size * k)), margin=int(s0.margin * k))
            pages = make_paginator(s, W * s.max_width / 100).paginate(verse_with_marker(ar, n), tr if with_tr else "")
            lines, h = page_lines(pages[0], s)
            h += EXTRA_HEIGHT
            if h + s.margin <= H - 6: break
            k *= 0.85
        p.save(); p.translate(0, s.margin if s.pos == "top" else H - h - s.margin)
        paint_lines(p, W, h, lines, s); p.restore()
        if len(pages) > 1:
            f = QFont(self.font()); f.setPointSizeF(8.5); f.setWeight(QFont.DemiBold); p.setFont(f)
            t = T("preview_page", k=1, n=len(pages)); tw = QFontMetricsF(f).horizontalAdvance(t) + 20
            r = QRectF(W - tw - 10, 10, tw, 22); p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 120)); p.drawRoundedRect(r, 11, 11)
            p.setPen(QColor("#ffffff")); p.drawText(r, Qt.AlignCenter, t)
        p.end()
