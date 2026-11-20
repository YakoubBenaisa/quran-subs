"""Link or file: paste a YouTube / MP3 link or choose a file, sync it, manage "My recordings"."""
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import T, rtl
from ...core.models import MyRecitation
from ..theme.icons import icon
from ..theme.tokens import C
from ..viewmodels import CatalogViewModel, MineViewModel
from ..widgets.basic import field, lbl

MEDIA_FILTER = "*.mp3 *.m4a *.aac *.ogg *.opus *.wav *.flac *.webm *.mp4 *.mkv *.mka"


class LinkPanel(QWidget):
    surah_guessed = Signal(int)
    recording_ready = Signal(int)       # reciter id of the new / chosen recording

    def __init__(self, vm: MineViewModel, catalog: CatalogViewModel, current_surah):
        """current_surah() -> int (the surah chosen on the Recite page)."""
        super().__init__()
        self.vm, self.catalog, self.current_surah = vm, catalog, current_surah
        self.inspection = None
        v = QVBoxLayout(self); v.setContentsMargins(0, 4, 0, 0); v.setSpacing(10)
        v.addWidget(lbl(T("link_sub"), "muted", True))

        row = QHBoxLayout(); row.setSpacing(8)
        self.src = QLineEdit(); self.src.setPlaceholderText(T("link_placeholder")); self.src.setClearButtonEnabled(True)
        self.src.addAction(icon("link", C["MUTED"]), QLineEdit.LeadingPosition)
        self.src.returnPressed.connect(self._check)
        self._debounce = QTimer(self); self._debounce.setSingleShot(True); self._debounce.setInterval(700)
        self._debounce.timeout.connect(self._check)
        self.src.textEdited.connect(lambda *_: self._debounce.start())
        paste = QPushButton(T("paste")); paste.clicked.connect(self._paste); paste.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.src, 1); row.addWidget(paste)
        v.addLayout(row)
        pick = QPushButton(T("choose_file")); pick.setIcon(icon("folder", C["SUB"])); pick.clicked.connect(self._choose)
        pick.setCursor(Qt.PointingHandCursor)
        v.addWidget(pick, 0, Qt.AlignRight if rtl() else Qt.AlignLeft)

        self.info = lbl("", "modedesc", True); self.info.setTextFormat(Qt.RichText); self.info.hide()
        self.info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        v.addWidget(self.info)

        rng = QHBoxLayout(); rng.setSpacing(10)
        self.a_from = QSpinBox(); self.a_from.setRange(1, 286)
        self.a_to = QSpinBox(); self.a_to.setRange(0, 286); self.a_to.setSpecialValueText(T("to_end"))
        rng.addWidget(field(T("from_ayah"), self.a_from)); rng.addWidget(field(T("to_ayah"), self.a_to))
        self.range_box = QWidget(); rv = QVBoxLayout(self.range_box); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(6)
        rv.addWidget(lbl(T("rec_covers").upper(), "field")); rv.addLayout(rng)
        v.addWidget(self.range_box)

        act = QHBoxLayout(); act.setSpacing(8)
        self.b_sync = QPushButton(T("sync")); self.b_sync.setObjectName("primary"); self.b_sync.setCursor(Qt.PointingHandCursor)
        self.b_sync.setIcon(icon("sync", C["ON"], mirror=False)); self.b_sync.clicked.connect(self._sync); self.b_sync.setEnabled(False)
        self.b_cancel = QPushButton(T("cancel")); self.b_cancel.clicked.connect(vm.cancel); self.b_cancel.hide()
        act.addWidget(self.b_sync, 1); act.addWidget(self.b_cancel)
        v.addLayout(act)
        self.prog = QProgressBar(); self.prog.setTextVisible(False); self.prog.setRange(0, 1000); self.prog.hide()
        v.addWidget(self.prog)
        self.status = lbl("", "small", True); v.addWidget(self.status)
        v.addWidget(lbl(T("fix_hint"), "small", True))

        v.addSpacing(6)
        head = QHBoxLayout(); head.addWidget(lbl(T("my_recordings").upper(), "field")); head.addStretch()
        self.b_del = QPushButton(T("delete")); self.b_del.setObjectName("danger"); self.b_del.clicked.connect(self._delete)
        head.addWidget(self.b_del); v.addLayout(head)
        self.list = QListWidget(); self.list.setObjectName("lib"); self.list.setMinimumHeight(120)
        self.list.setWordWrap(True); self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight); self.list.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.list.itemClicked.connect(self._chosen)
        v.addWidget(self.list, 1)
        self._update_range_max()

        vm.inspected.connect(self._on_inspected)
        vm.inspect_failed.connect(self._on_inspect_failed)
        vm.progress.connect(self._on_progress)
        vm.synced.connect(self._on_synced)
        vm.sync_failed.connect(self._on_sync_failed)
        vm.busy_changed.connect(self._on_busy)
        vm.changed.connect(self.fill)
        self.fill()
        self._on_busy(vm.busy)

    # ------------------------------------------------------------ input
    def _paste(self) -> None:
        self.src.setText(QGuiApplication.clipboard().text().strip()); self._check()

    def _choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, T("choose_file"), os.path.expanduser("~"), f"{T('audio_files')} ({MEDIA_FILTER})")
        if path: self.src.setText(path); self._check()

    def _check(self) -> None:
        self._debounce.stop()
        text = self.src.text().strip()
        self.inspection = None; self.b_sync.setEnabled(False)
        if not text: self.info.hide(); return
        self._show_info(T("checking"))
        self.vm.inspect(text)

    def _show_info(self, html: str) -> None:
        self.info.setText(html); self.info.show()

    def _on_inspected(self, ins) -> None:
        self.inspection = ins
        title = ins.info.title.replace("<", "&lt;")
        dur = f" &nbsp;·&nbsp; {T('duration_min', m=max(1, round(ins.info.duration / 60)))}" if ins.info.duration else ""
        found = []
        if ins.surah:
            x = self.catalog.surah(ins.surah)
            if x: found.append(x.short_name if rtl() else x.english)
            self.surah_guessed.emit(ins.surah)
        if ins.reciter: found.append(ins.reciter.name(rtl()))
        line = (f"{T('found_in_title')} <b>{' · '.join(found)}</b>" if ins.surah else T("not_found_in_title"))
        self._show_info(f"<b>{title}</b>{dur}<br>{line}")
        self._update_range_max()
        self.b_sync.setEnabled(not self.vm.busy)

    def _on_inspect_failed(self, err: str) -> None:
        self.inspection = None
        self._show_info(f"<span style='color:#ef4444'>{err}</span>")

    def _update_range_max(self) -> None:
        x = self.catalog.surah(self.current_surah())
        n = x.ayahs if x else 286
        self.a_from.setMaximum(n); self.a_to.setMaximum(n)

    def surah_changed(self) -> None:
        self._update_range_max(); self.a_from.setValue(1); self.a_to.setValue(0)

    # ------------------------------------------------------------ sync
    def _sync(self) -> None:
        if not self.inspection: return
        self.status.setText(""); self.prog.setValue(0)
        self.vm.sync(self.inspection, self.current_surah(), self.a_from.value(), self.a_to.value())

    def _on_progress(self, msg: str, f: float) -> None:
        self.status.setText(msg); self.prog.setValue(int(f * 1000))

    def _on_synced(self, m: MyRecitation) -> None:
        self.status.setText(T("synced", n=len([t for t in m.timings if t.ayah]), q=self.vm.quality_text(m)))
        self.recording_ready.emit(m.reciter_id)

    def _on_sync_failed(self, err: str) -> None:
        self.status.setText(f"<span style='color:#ef4444'>{err}</span>")

    def _on_busy(self, busy: bool) -> None:
        self.b_sync.setEnabled(not busy and self.inspection is not None)
        self.b_cancel.setVisible(busy); self.prog.setVisible(busy)

    # ------------------------------------------------------------ my recordings
    def fill(self) -> None:
        self.list.clear()
        for m in self.vm.recordings():
            x = self.catalog.surah(m.surah)
            name = (x.short_name if rtl() else x.english) if x else str(m.surah)
            it = QListWidgetItem(f"{m.title}\n" + T("rec_item", surah=name, n=len([t for t in m.timings if t.ayah]),
                                                  q=self.vm.quality_text(m)))
            it.setData(Qt.UserRole, m); self.list.addItem(it)
        if not self.list.count():
            it = QListWidgetItem(T("no_recordings")); it.setFlags(Qt.NoItemFlags); self.list.addItem(it)
        self.b_del.setEnabled(bool(self.vm.recordings()))

    def _chosen(self, it) -> None:
        m = it.data(Qt.UserRole)
        if m: self.recording_ready.emit(m.reciter_id)

    def _delete(self) -> None:
        it = self.list.currentItem()
        m = it.data(Qt.UserRole) if it else None
        if not m: return
        if QMessageBox.question(self, T("delete_rec_title"), T("delete_rec_q", name=m.title)) != QMessageBox.Yes: return
        self.vm.delete(m)
