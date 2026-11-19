"""Small building blocks for the settings pages: cards, labelled fields, switches, sliders, segmented buttons."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import rtl
from ..theme.icons import icon, tile_icon
from ..theme.tokens import C
from .smooth_scroll import SmoothScroll

SWITCH_INDENT = 50


def lbl(text: str, name: str | None = None, wrap: bool = False) -> QLabel:
    l = QLabel(text)
    if name: l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def card(title: str | None = None, subtitle: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    fr = QFrame(); fr.setObjectName("card")
    v = QVBoxLayout(fr); v.setContentsMargins(20, 18, 20, 20); v.setSpacing(12)
    if title: v.addWidget(lbl(title, "h2"))
    if subtitle: v.addWidget(lbl(subtitle, "muted", True))
    return fr, v


def field(label: str, widget: QWidget, value_label: QLabel | None = None) -> QWidget:
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
    if value_label is not None:
        h = QHBoxLayout(); h.addWidget(lbl(label.upper(), "field")); h.addStretch(); h.addWidget(value_label)
        v.addLayout(h)
    else:
        v.addWidget(lbl(label.upper(), "field"))
    v.addWidget(widget)
    return w


def switch(text: str, desc: str | None = None) -> tuple[QWidget, QCheckBox]:
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
    cb = QCheckBox(text); cb.setCursor(Qt.PointingHandCursor); v.addWidget(cb)
    if desc:
        d = lbl(desc, "small", True)
        d.setContentsMargins(*((0, 0, SWITCH_INDENT, 0) if rtl() else (SWITCH_INDENT, 0, 0, 0))); v.addWidget(d)
    return w, cb


def slider(lo: int, hi: int, val, fmt, step: int = 1) -> tuple[QSlider, QLabel]:
    s = QSlider(Qt.Horizontal); s.setRange(lo, hi); s.setSingleStep(step); s.setPageStep(step * 5)
    l = lbl("", "value"); s.valueChanged.connect(lambda x: l.setText(fmt(x))); s.setValue(int(val)); l.setText(fmt(s.value()))
    return s, l


def segmented(labels: list[str], checked: int = 0, icons: list[str] | None = None,
              tips: list[str] | None = None) -> tuple[QWidget, QButtonGroup]:
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
    g = QButtonGroup(w)
    first, last = ("last", "first") if rtl() else ("first", "last")  # physical corners flip in RTL
    for i, t in enumerate(labels):
        b = QPushButton(t); b.setObjectName("iconseg" if icons else "seg"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
        if icons: b.setIcon(icon(icons[i], C["SUB"])); b.setIconSize(QSize(18, 18))
        if tips: b.setToolTip(tips[i])
        if i == 0: b.setProperty(first, True)
        if i == len(labels) - 1: b.setProperty(last, True)
        g.addButton(b, i); h.addWidget(b, 1)
    g.button(checked).setChecked(True)
    return w, g


class FitStack(QStackedWidget):
    """A stack that only takes the size of the page being shown."""
    def sizeHint(self):
        w = self.currentWidget(); return w.sizeHint() if w else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget(); return w.minimumSizeHint() if w else super().minimumSizeHint()

    def show_index(self, i: int) -> None:
        self.setCurrentIndex(i)
        for j in range(self.count()):
            self.widget(j).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if j == i else QSizePolicy.Ignored)
        self.updateGeometry()


def scroll_page(w: QWidget) -> QScrollArea:
    w.setObjectName("page")
    sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(w); sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.viewport().setAutoFillBackground(False); w.setAutoFillBackground(False)
    SmoothScroll(sa)
    return sa


def page_header(v: QVBoxLayout, title: str, sub: str, ic: str | None = None) -> None:
    row = QHBoxLayout(); row.setSpacing(14)
    if ic:
        t = QLabel(); t.setPixmap(tile_icon(ic, True).pixmap(QSize(44, 44))); row.addWidget(t, 0, Qt.AlignTop)
    col = QVBoxLayout(); col.setSpacing(2); col.addWidget(lbl(title, "h1")); col.addWidget(lbl(sub, "muted", True))
    row.addLayout(col, 1); v.addLayout(row); v.addSpacing(4)


def page_layout() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(32, 22, 32, 22); v.setSpacing(14)
    return w, v
