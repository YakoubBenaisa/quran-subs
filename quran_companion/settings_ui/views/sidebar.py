from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ...core.i18n import T, rtl
from ...core.settings import THEMES, Settings
from ..theme.icons import icon, tile_icon
from ..theme.tokens import C
from ..viewmodels import AppViewModel
from ..widgets.basic import field, lbl, segmented
from ..widgets.decor import Sidebar

PAGES = [("nav_recite", "book"), ("nav_appearance", "palette"), ("nav_downloads", "cloud")]
SHORTCUTS = [("Q", "sc_toggle"), ("Space", "sc_pause"), ("← →", "sc_ayah"), ("PgUp/Dn", "sc_surah"),
             ("↑ ↓", "sc_size"), ("H", "sc_hide"), ("S", "sc_window")]
WIDTH = 248


class SidebarView(Sidebar):
    page_selected = Signal(int)

    def __init__(self, app: AppViewModel, s: Settings, page: int = 0):
        super().__init__()
        self.setObjectName("side"); self.setFixedWidth(WIDTH)
        v = QVBoxLayout(self); v.setContentsMargins(18, 22, 18, 18); v.setSpacing(4)
        top = QHBoxLayout(); top.setSpacing(12)
        logo = QLabel(); logo.setPixmap(tile_icon("star8", True).pixmap(QSize(50, 50))); top.addWidget(logo, 0, Qt.AlignVCenter)
        tv = QVBoxLayout(); tv.setSpacing(0)
        tv.addWidget(lbl("القرآن الكريم", "brandAr")); tv.addWidget(lbl(T("app_title"), "brand"))
        top.addLayout(tv, 1); v.addLayout(top)
        v.addSpacing(4); v.addWidget(lbl(T("app_sub"), "small", True)); v.addSpacing(18)

        self.nav = QButtonGroup(self)
        for i, (key, ic) in enumerate(PAGES):
            b = QPushButton("  " + T(key)); b.setObjectName("nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.setIcon(tile_icon(ic)); b.setIconSize(QSize(34, 34))
            if rtl(): b.setStyleSheet("text-align:right;")
            self.nav.addButton(b, i); v.addWidget(b)
        self.nav.button(page).setChecked(True)
        self.nav.idClicked.connect(self.page_selected.emit)
        v.addStretch()

        seg, themes = segmented(["", "", ""], THEMES.index(s.theme), icons=["auto", "sun", "moon"],
                                tips=[T("theme_system"), T("theme_light"), T("theme_dark")])
        themes.idClicked.connect(lambda i: app.set_theme(THEMES[i]))
        v.addWidget(field(T("theme"), seg)); v.addSpacing(8)

        langs = QComboBox()
        for code, name, _ in app.languages():
            langs.addItem(icon("globe", C["SUB"]), name, code)
            if code == app.language: langs.setCurrentIndex(langs.count() - 1)
        langs.currentIndexChanged.connect(lambda *_: app.set_language(langs.currentData()))
        v.addWidget(field(T("language"), langs)); v.addSpacing(10)

        sc = QFrame(); sc.setObjectName("shortcuts"); sv = QVBoxLayout(sc); sv.setContentsMargins(14, 12, 14, 12); sv.setSpacing(6)
        hr = QHBoxLayout(); kb = QLabel(); kb.setPixmap(icon("keyboard", C["MUTED"]).pixmap(QSize(16, 16)))
        hr.addWidget(kb); hr.addWidget(lbl(T("shortcuts").upper(), "field")); hr.addStretch(); sv.addLayout(hr)
        sv.addWidget(lbl(T("shortcuts_hold"), "small", True))
        for k, d in SHORTCUTS:
            r = QHBoxLayout(); r.addWidget(lbl(k, "kbd")); r.addStretch(); r.addWidget(lbl(T(d), "small")); sv.addLayout(r)
        v.addWidget(sc)
