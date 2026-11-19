"""Main settings window: arranges the views and connects their signals to the view models."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ... import paths
from ...core.i18n import T, rtl
from ...core.settings import SettingsStore
from ..theme.tokens import C
from ..viewmodels import AppViewModel, CatalogViewModel, DownloadsViewModel, PlaybackViewModel
from ..widgets.basic import scroll_page
from ..widgets.decor import paint_star
from .appearance_page import AppearancePage
from .downloads_page import DownloadsPage
from .now_playing import NowPlayingBar
from .recite_page import RecitePage
from .sidebar import SidebarView

RECITE, APPEARANCE, DOWNLOADS = range(3)
SIZE, MIN_SIZE = (1140, 840), (960, 660)


class MainWindow(QWidget):
    def __init__(self, store: SettingsStore, app: AppViewModel, catalog: CatalogViewModel,
                 playback: PlaybackViewModel, downloads: DownloadsViewModel, page: int = RECITE):
        super().__init__()
        self.store, self.app, self.catalog, self.playback = store, app, catalog, playback
        s = store.load()
        self.setWindowTitle(T("app_title")); self.setWindowIcon(QIcon(paths.LOGO))
        self.resize(*SIZE); self.setMinimumSize(*MIN_SIZE)

        self.recite = RecitePage(s, catalog, downloads)
        self.appearance = AppearancePage(s, self.recite.translation)
        self.downloads = DownloadsPage(downloads, catalog, self.recite.reciter, self.recite.surah_number, self.recite.translation)
        self.sidebar = SidebarView(app, s, page)
        self.bar = NowPlayingBar(playback, catalog)
        self.stack = QStackedWidget()
        for pg in (self.recite, self.appearance, self.downloads): self.stack.addWidget(scroll_page(pg))
        self.stack.setCurrentIndex(page)

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        body = QHBoxLayout(); body.setSpacing(0); outer.addLayout(body, 1)
        body.addWidget(self.sidebar); body.addWidget(self.stack, 1)
        outer.addWidget(self.bar)
        self._connect()
        catalog.load(s.trans)

    def _connect(self) -> None:
        r, a, d, b = self.recite, self.appearance, self.downloads, self.bar
        self.sidebar.page_selected.connect(self.go)
        r.start_requested.connect(lambda: self.playback.start(**self.all_values()))
        r.translation_changed.connect(lambda *_: a.preview.update())
        r.reciter_changed.connect(lambda *_: d.refresh())
        r.surah_changed.connect(self._surah_changed)
        a.style_changed.connect(lambda style: self.playback.apply_style(**style))
        a.ui_font_chosen.connect(self.app.set_ui_font)
        d.library_reciter_chosen.connect(r.select_reciter)
        d.library_changed.connect(r.fill_reciters)
        b.play_pause.connect(lambda: self.playback.play_pause(**self.all_values()))
        b.visible_toggled.connect(lambda on: self.playback.set_visible(on, **self.all_values()))
        self.catalog.sample_loaded.connect(a.preview.set_sample)
        self.catalog.loaded.connect(self._on_catalog)
        if self.catalog.sample: a.preview.set_sample(*self.catalog.sample)

    def _on_catalog(self) -> None:
        self._surah_changed(self.recite.surah_number())

    def _surah_changed(self, n: int) -> None:
        x = self.catalog.surah(n)
        if x: self.downloads.set_surah_name(x.short_name if rtl() else x.english)

    def go(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        if i == DOWNLOADS: self.downloads.refresh(); self.downloads.fill_library()

    def all_values(self) -> dict:
        return {**self.recite.values(), **self.appearance.values()}

    def save_state(self) -> None:
        """Keep unsaved choices when the window is rebuilt (language / theme / font change)."""
        self.store.update(**self.all_values())

    def paintEvent(self, _):  # soft background with glowing shapes
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(C["BG"]))
        for cx, cy, r, alpha in [(0.88, 0.05, 520, C["BLOB"]), (0.42, 1.0, 460, C["BLOB"] * 0.7)]:
            x = (1 - cx) * W if rtl() else cx * W
            g = QRadialGradient(QPointF(x, cy * H), r)
            c1 = QColor(C["ACCENT"]); c1.setAlpha(int(alpha)); c2 = QColor(C["ACCENT"]); c2.setAlpha(0)
            g.setColorAt(0, c1); g.setColorAt(1, c2); p.fillRect(self.rect(), g)
        col = QColor(C["ACCENT"]); col.setAlpha(20)
        paint_star(p, (W - 150) if not rtl() else 150, 120, 70, QPen(col, 1.5))
        p.end()
