"""Bottom bar: what is playing, transport buttons, show-on-screen switch, status pill."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.i18n import T, rtl
from ..theme.icons import icon
from ..theme.tokens import C
from ..viewmodels import CatalogViewModel, PlaybackViewModel, Status
from ..widgets.basic import lbl

HEIGHT = 84


class NowPlayingBar(QFrame):
    play_pause = Signal()
    visible_toggled = Signal(bool)

    def __init__(self, vm: PlaybackViewModel, catalog: CatalogViewModel):
        super().__init__()
        self.vm, self.catalog = vm, catalog
        self.setObjectName("bar"); self.setFixedHeight(HEIGHT)
        h = QHBoxLayout(self); h.setContentsMargins(24, 8, 24, 8)
        info = QWidget(); iv = QVBoxLayout(info); iv.setContentsMargins(0, 0, 0, 0); iv.setSpacing(2)
        self.name, self.sub = lbl("", "npname"), lbl("", "small")
        iv.addWidget(self.name); iv.addWidget(self.sub)
        h.addWidget(info, 1)

        mid = QHBoxLayout(); mid.setSpacing(12)
        for ic, tip, fn, name in [("prev", T("prev_ayah"), lambda: vm.step(-1), "round"),
                                  ("play", T("play_pause"), self.play_pause.emit, "roundMain"),
                                  ("next", T("next_ayah"), lambda: vm.step(1), "round"),
                                  ("stop", T("stop"), vm.stop, "round")]:
            b = QPushButton(); b.setObjectName(name); b.setToolTip(tip); b.setCursor(Qt.PointingHandCursor)
            main = name == "roundMain"
            b.setIcon(icon(ic, C["ON"] if main else C["SUB"], mirror=None if ic != "play" else False))
            b.setIconSize(QSize(24, 24) if main else QSize(18, 18))
            b.clicked.connect(fn); mid.addWidget(b)
            if main:
                self.pp = b
                glow = QGraphicsDropShadowEffect(b); glow.setBlurRadius(26); glow.setOffset(0, 4)
                gc = QColor(C["ACCENT"]); gc.setAlpha(C["GLOW"]); glow.setColor(gc); b.setGraphicsEffect(glow)
        h.addLayout(mid)

        right = QHBoxLayout(); right.setSpacing(14); right.addStretch()
        self.show_sw = QCheckBox(T("show_on_screen")); self.show_sw.setCursor(Qt.PointingHandCursor)
        self.show_sw.setToolTip(T("show_on_screen_tip")); self.show_sw.toggled.connect(self.visible_toggled.emit)
        right.addWidget(self.show_sw, 0, Qt.AlignVCenter)
        self.pill = QLabel(); right.addWidget(self.pill, 0, Qt.AlignVCenter)
        rw = QWidget(); rw.setLayout(right); h.addWidget(rw, 1)

        vm.status_changed.connect(self.render)
        catalog.loaded.connect(self._on_catalog)
        self._live = None
        vm.refresh()
        if vm.status: self.render(vm.status)

    def _on_catalog(self) -> None:
        if self.vm.status: self.render(self.vm.status)

    def render(self, st: Status) -> None:
        self.show_sw.blockSignals(True); self.show_sw.setChecked(st.shown); self.show_sw.blockSignals(False)
        self.pill.setObjectName("pillOn" if st.running else "pillOff")
        self.pill.setText(("●  " + (T("live") if st.shown else T("hidden_pill"))) if st.running else ("○  " + T("off_pill")))
        self.pill.style().unpolish(self.pill); self.pill.style().polish(self.pill)
        if self._live != st.running:
            self._live = st.running
            self.pp.setIcon(icon("pause" if st.running else "play", C["ON"], mirror=False))
        x = self.catalog.surah(st.surah)
        if not x: return
        self.name.setText(x.short_name if rtl() else f"{x.english}  ·  {x.short_name}")
        sub = T("np_ayah", a=st.ayah, n=x.ayahs) + "  ·  " + T("mode_" + st.mode)
        r = self.catalog.find_reciter(st.reciter)
        if r and st.mode == "recite": sub += "  ·  " + r.name(rtl())
        self.sub.setText(sub)
