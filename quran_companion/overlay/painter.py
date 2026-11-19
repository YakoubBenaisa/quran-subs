"""Qt side of the verse layout: fonts, text measuring and drawing (shared by the overlay and the preview)."""
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPainterPath, QPen

from .. import paths
from ..core.models import Page
from ..core.settings import Settings
from ..layout.paginator import Paginator

AR_LINE_HEIGHT = 1.25
TR_LINE_HEIGHT = 1.1
TOP_PAD = 15
BOX_PAD_X = 60
_quran_family: str | None = None


def register_fonts() -> str:
    """Load the bundled fonts once. Returns the Quran font family."""
    global _quran_family
    if _quran_family is None:
        for fn in sorted(os.listdir(paths.FONTS_DIR)):
            if fn.endswith((".ttf", ".otf")) and not fn.startswith("AmiriQuran"):
                QFontDatabase.addApplicationFont(os.path.join(paths.FONTS_DIR, fn))
        fid = QFontDatabase.addApplicationFont(os.path.join(paths.FONTS_DIR, "AmiriQuran.ttf"))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _quran_family = fams[0] if fams else "Noto Naskh Arabic"
    return _quran_family


def font_for(kind: str, s: Settings, scale: float = 1.0) -> QFont:
    if kind == "ar":
        return QFont(s.font or register_fonts(), max(6, int(s.size)))
    f = QFont(s.tr_font or "Sans", max(6, int(s.size * s.tr_scale / 100)))
    f.setWeight(QFont.DemiBold)
    if scale != 1.0: f.setPointSizeF(max(6.0, f.pointSizeF() * scale))
    return f


class QtMeasurer:
    """TextMeasurer implementation backed by QFontMetrics."""
    def __init__(self, s: Settings):
        self.s = s
        self._fm: dict = {}

    def width(self, text: str, kind: str, scale: float = 1.0) -> float:
        key = (kind, scale)
        if key not in self._fm: self._fm[key] = QFontMetricsF(font_for(kind, self.s, scale))
        return self._fm[key].horizontalAdvance(text)


def make_paginator(s: Settings, max_width_px: float) -> Paginator:
    return Paginator(QtMeasurer(s), max_width_px, s.max_lines, s.tr_lines)


def page_lines(page: Page, s: Settings) -> tuple[list[tuple[str, QFont, float, float]], float]:
    """[(text, font, line height, text width)], total height."""
    out, h = [], 0.0
    for kind, lines, f in (("ar", page.lines, font_for("ar", s)), ("tr", page.tr, font_for("tr", s, page.tr_scale))):
        fm = QFontMetricsF(f)
        for ln in lines:
            lh = fm.height() * (AR_LINE_HEIGHT if kind == "ar" else TR_LINE_HEIGHT)
            out.append((ln, f, lh, fm.horizontalAdvance(ln))); h += lh
    return out, h


def paint_lines(p: QPainter, width: float, height: float, lines, s: Settings) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    if s.bg and lines:
        w = max(l[3] for l in lines) + BOX_PAD_X
        col = QColor(s.bg_color); col.setAlpha(int(s.bg_alpha * 2.55))
        p.setPen(Qt.NoPen); p.setBrush(col)
        p.drawRoundedRect(QRectF((width - w) / 2, 4, w, height - 8), 16, 16)
    oc = QColor(s.outline); oc.setAlpha(230)
    y = TOP_PAD
    for text, f, lh, tw in lines:
        fm = QFontMetricsF(f)
        path = QPainterPath()
        path.addText(QPointF((width - tw) / 2, y + fm.ascent() + (lh - fm.height()) / 2), f, text)
        if s.outline_w > 0:
            pw = max(1.0, s.outline_w * f.pointSizeF() / 40)
            p.strokePath(path, QPen(oc, pw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.fillPath(path, QColor(s.color))
        y += lh
