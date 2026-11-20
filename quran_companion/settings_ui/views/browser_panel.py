"""Video in browser: pick what Firefox / Chrome is playing, sync it once, then follow it."""
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.guess import same_video
from ...core.i18n import T, rtl
from ...playback.mpris import Media
from ..background import Background
from ..theme.icons import icon
from ..theme.tokens import C
from ..viewmodels import CatalogViewModel, MineViewModel
from ..widgets.basic import lbl

WRONG_SURAH = 0.2      # so few verses agree that the surah is probably not the one chosen


class BrowserMediaViewModel(QObject):
    """What the browsers are playing, refreshed while the panel is visible."""
    listed = Signal(list)          # [Media]
    failed = Signal(str)

    def __init__(self, bg: Background):
        super().__init__()
        self.bg = bg
        self._mpris = None

    def refresh(self) -> None:
        def work():
            if self._mpris is None:
                from ...playback.mpris import Mpris
                self._mpris = Mpris()
            return [m for m in self._mpris.all() if m.title or m.url]
        self.bg.run(work, self._done)

    def _done(self, res) -> None:
        if isinstance(res, Exception): self._mpris = None; self.failed.emit(str(res))
        else: self.listed.emit(res)


class BrowserPanel(QWidget):
    follow_requested = Signal(int)      # reciter id of the recording to follow with
    surah_guessed = Signal(int)

    def __init__(self, mine: MineViewModel, catalog: CatalogViewModel, media_vm: BrowserMediaViewModel, current_surah):
        super().__init__()
        self.mine, self.catalog, self.vm, self.current_surah = mine, catalog, media_vm, current_surah
        self.selected: Media | None = None
        self._pending_sync = False
        self._asked = None                  # checked video whose surah the title did not give
        v = QVBoxLayout(self); v.setContentsMargins(0, 4, 0, 0); v.setSpacing(10)
        v.addWidget(lbl(T("browser_sub"), "muted", True))
        self.list = QListWidget(); self.list.setObjectName("lib"); self.list.setMinimumHeight(150)
        self.list.setWordWrap(True); self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); self.list.setFixedHeight(170)
        self.list.currentItemChanged.connect(self._chosen)
        v.addWidget(self.list)
        self.state = lbl("", "modedesc", True); self.state.setTextFormat(Qt.RichText); self.state.hide()
        self.state.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        v.addWidget(self.state)
        row = QHBoxLayout(); row.setSpacing(8)
        self.b_sync = QPushButton(T("sync_video")); self.b_sync.setIcon(icon("sync", C["SUB"], mirror=False))
        self.b_sync.clicked.connect(self._sync); self.b_sync.setCursor(Qt.PointingHandCursor)
        self.b_follow = QPushButton(T("follow_video")); self.b_follow.setObjectName("primary")
        self.b_follow.setIcon(icon("play", C["ON"], mirror=False)); self.b_follow.setCursor(Qt.PointingHandCursor)
        self.b_follow.clicked.connect(self._follow)
        row.addWidget(self.b_sync); row.addWidget(self.b_follow, 1)
        v.addLayout(row)
        self.prog = QProgressBar(); self.prog.setTextVisible(False); self.prog.setRange(0, 1000); self.prog.hide()
        v.addWidget(self.prog)
        self.status = lbl("", "small", True); v.addWidget(self.status)
        v.addWidget(lbl(T("listen_note"), "small", True))
        v.addStretch(1)

        self.timer = QTimer(self); self.timer.setInterval(2500); self.timer.timeout.connect(self.vm.refresh)
        media_vm.listed.connect(self._fill)
        media_vm.failed.connect(lambda err: self._show_empty(T("browser_unavailable", err=err)))
        mine.inspected.connect(self._on_inspected)
        mine.inspect_failed.connect(self._on_inspect_failed)
        mine.progress.connect(self._on_progress)
        mine.synced.connect(self._on_synced)
        mine.sync_failed.connect(self._on_sync_failed)
        mine.busy_changed.connect(lambda busy: self._update())
        self._update()

    # ------------------------------------------------------------ visibility drives polling
    def showEvent(self, e) -> None:
        super().showEvent(e); self.vm.refresh(); self.timer.start()

    def hideEvent(self, e) -> None:
        super().hideEvent(e); self.timer.stop()

    # ------------------------------------------------------------ list
    def _show_empty(self, text: str) -> None:
        self.list.clear()
        it = QListWidgetItem(text); it.setFlags(Qt.NoItemFlags); self.list.addItem(it)

    def _fill(self, media: list) -> None:
        keep = self.selected.bus if self.selected else None
        self.list.blockSignals(True); self.list.clear()
        for m in media:
            state = T("b_playing") if m.status == "Playing" else T("b_paused")
            mark = "▶" if m.status == "Playing" else "⏸"
            ready = self.mine.for_video(m.url) if m.url else None
            tick = "  ✓" if ready else ""
            it = QListWidgetItem(f"{mark}  {m.title}{tick}\n{m.short_app}  ·  {state}")
            it.setData(Qt.UserRole, m); self.list.addItem(it)
            if m.bus == keep: self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if not media: self._show_empty(T("browser_none")); self.selected = None
        elif self.list.currentItem() is None: self.list.setCurrentRow(0)
        else: self.selected = self.list.currentItem().data(Qt.UserRole)
        self._update()

    def _chosen(self, it, *_) -> None:
        self.selected = it.data(Qt.UserRole) if it else None
        if not self._waiting_for_surah(): self._asked = None
        self._update()

    def _waiting_for_surah(self) -> bool:
        m = self.selected
        return bool(self._asked and m and m.url and same_video(self._asked.info.source, m.url))

    def surah_changed(self) -> None:
        self._update()

    def _update(self) -> None:
        m = self.selected
        rec = self.mine.for_video(m.url) if m and m.url else None
        busy = self.mine.busy
        self.b_sync.setEnabled(bool(m and m.url) and not busy)
        self.b_follow.setEnabled(rec is not None and not busy)
        if self._waiting_for_surah():
            x = self.catalog.surah(self.current_surah())
            self.b_sync.setText(T("sync_as", surah=(x.short_name if rtl() else x.english) if x else self.current_surah()))
        else:
            self.b_sync.setText(T("sync_again") if rec else T("sync_video"))
        self.prog.setVisible(busy and self._pending_sync)
        if not m: self.state.hide(); return
        if not m.url: text = T("no_video_link")
        elif rec: text = T("browser_ready", q=self.mine.quality_text(rec))
        else: text = T("browser_needs_sync")
        self.state.setText(f"<b>{m.title.replace('<', '&lt;')}</b><br>{text}"); self.state.show()

    # ------------------------------------------------------------ sync & follow
    def _sync(self) -> None:
        if not (self.selected and self.selected.url): return
        if self._waiting_for_surah():                    # the user chose the surah: go
            ins, self._asked = self._asked, None
            self._pending_sync = True
            self.mine.sync(ins, self.current_surah(), 1, 0); self._update()
            return
        self._pending_sync = True
        self.status.setText(T("checking"))
        self.mine.inspect(self.selected.url, "browser")

    def _on_inspected(self, tag: str, ins) -> None:
        if tag != "browser" or not self._pending_sync: return
        if not ins.surah:                                # never guess: a wrong surah cannot be synced
            self._pending_sync, self._asked = False, ins
            self.status.setText(T("pick_surah_sync")); self._update()
            return
        self.surah_guessed.emit(ins.surah)
        self.mine.sync(ins, ins.surah, 1, 0)
        self._update()

    def _on_inspect_failed(self, tag: str, err: str) -> None:
        if tag != "browser": return
        self._pending_sync = False
        self.status.setText(f"<span style='color:#ef4444'>{err}</span>")

    def _on_progress(self, msg: str, f: float) -> None:
        if self._pending_sync: self.status.setText(msg); self.prog.setValue(int(f * 1000))

    def _on_synced(self, m) -> None:
        if not self._pending_sync: return
        self._pending_sync = False
        text = T("synced", n=len([t for t in m.timings if t.ayah]), q=self.mine.quality_text(m))
        if m.confident < WRONG_SURAH: text += "<br>" + T("poor_check_surah")
        self.status.setText(text)
        self._update()

    def _on_sync_failed(self, err: str) -> None:
        if not self._pending_sync: return
        self._pending_sync = False
        self.status.setText(f"<span style='color:#ef4444'>{err}</span>"); self._update()

    def follow_target(self) -> tuple[str, str] | None:
        """(browser player name prefix, video link) when a synced video is chosen."""
        m = self.selected
        if not (m and m.url and self.mine.for_video(m.url)): return None
        prefix = ".".join(m.bus.split(".")[:4])            # org.mpris.MediaPlayer2.firefox (instance may change)
        return prefix, m.url

    def _follow(self) -> None:
        m = self.selected
        rec = self.mine.for_video(m.url) if m and m.url else None
        if rec: self.follow_requested.emit(rec.reciter_id)

