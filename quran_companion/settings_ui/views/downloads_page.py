"""Downloads page: selected reciter's stats, download / cancel, library of downloaded reciters."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import T, rtl
from ...core.models import Reciter
from ..theme.icons import icon
from ..theme.tokens import C
from ..viewmodels import CatalogViewModel, DownloadsViewModel
from ..widgets.basic import card, lbl, page_header, page_layout
from ..widgets.smooth_scroll import SmoothScroll

ALL_SURAHS = list(range(1, 115))


class DownloadsPage(QWidget):
    library_reciter_chosen = Signal(int)   # reciter id picked from the library list
    library_changed = Signal()

    def __init__(self, vm: DownloadsViewModel, catalog: CatalogViewModel, current_reciter, current_surah, translation):
        """current_reciter() -> Reciter, current_surah() -> int, translation() -> str (from the Recite page)."""
        super().__init__()
        self.vm, self.catalog = vm, catalog
        self.current_reciter, self.current_surah, self.translation = current_reciter, current_surah, translation
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        w, v = page_layout(); root.addWidget(w)
        page_header(v, T("downloads_title"), T("downloads_sub"), "cloud")

        c, cv = card()
        cv.addWidget(lbl(T("selected_reciter").upper(), "field"))
        self.name = lbl("—", "bigname"); cv.addWidget(self.name)
        self.sub = lbl("", "muted"); cv.addWidget(self.sub)
        row = QHBoxLayout(); row.setSpacing(28)
        self.st_n, self.st_mb = lbl("0", "stat"), lbl("0", "stat")
        for big, small in [(self.st_n, T("surahs_downloaded")), (self.st_mb, T("mb_on_disk"))]:
            col = QVBoxLayout(); col.setSpacing(0); col.addWidget(big); col.addWidget(lbl(small, "small")); row.addLayout(col)
        row.addStretch(); cv.addLayout(row)
        self.prog = QProgressBar(); self.prog.setTextVisible(False); cv.addWidget(self.prog)
        self.status = lbl(T("dl_hint"), "small"); cv.addWidget(self.status)
        row = QHBoxLayout()
        self.b_all = QPushButton(T("dl_all")); self.b_all.setObjectName("primary"); self.b_all.setCursor(Qt.PointingHandCursor)
        self.b_all.setIcon(icon("download", C["ON"])); self.b_all.setIconSize(QSize(18, 18))
        self.b_all.clicked.connect(lambda: self._download(ALL_SURAHS))
        self.b_one = QPushButton(T("dl_one", name="")); self.b_one.clicked.connect(lambda: self._download([self.current_surah()]))
        self.b_cancel = QPushButton(T("cancel")); self.b_cancel.setEnabled(False); self.b_cancel.clicked.connect(vm.cancel)
        row.addWidget(self.b_all); row.addWidget(self.b_one); row.addStretch(); row.addWidget(self.b_cancel)
        cv.addLayout(row)
        v.addWidget(c)

        c, cv = card(T("library"), T("library_desc"))
        self.lib = QListWidget(); self.lib.setObjectName("lib"); self.lib.setMinimumHeight(160)
        self.lib.setVerticalScrollMode(QListWidget.ScrollPerPixel); SmoothScroll(self.lib, 0.8)
        self.lib.itemClicked.connect(self._lib_clicked); cv.addWidget(self.lib)
        row = QHBoxLayout()
        b = QPushButton(T("open_folder")); b.setIcon(icon("folder", C["SUB"])); b.clicked.connect(vm.open_folder); row.addWidget(b)
        row.addStretch()
        b = QPushButton(T("delete_dl")); b.setObjectName("danger"); b.setIcon(icon("trash", "#ef4444")); b.clicked.connect(self._delete)
        row.addWidget(b); cv.addLayout(row)
        cv.addWidget(lbl(vm.folder, "small"))
        v.addWidget(c); v.addStretch()

        vm.progress.connect(self._on_progress)
        vm.saved.connect(self.refresh)
        vm.finished.connect(self._on_finished)
        vm.busy_changed.connect(self._on_busy)
        self._on_busy(vm.busy)

    # ---------------------------------------------------------------- display
    def refresh(self) -> None:
        r: Reciter | None = self.current_reciter()
        if not r: return
        st = self.vm.stats(r)
        self.name.setText(r.name(rtl()))
        self.sub.setText(f"{r.en}   ·   {r.short_style}" if rtl() else f"{r.short_style}   ·   {r.ar}")
        self.sub.setAlignment((Qt.AlignRight if rtl() else Qt.AlignLeft) | Qt.AlignAbsolute | Qt.AlignVCenter)
        self.st_n.setText(f"{st.surahs}<span style='font-size:11pt;color:{C['MUTED']}'> / {r.count}</span>")
        self.st_mb.setText(f"{st.megabytes:.0f}")
        if not self.vm.busy: self.prog.setRange(0, r.count); self.prog.setValue(st.surahs)

    def set_surah_name(self, name: str) -> None:
        self.b_one.setText(T("dl_one", name=name))

    def fill_library(self) -> None:
        self.lib.clear()
        for r, st in self.vm.library(self.catalog.reciters):
            it = QListWidgetItem(f"{r.name(rtl())}      " + T("lib_item", n=st.surahs, mb=f"{st.megabytes:.0f}"))
            it.setData(Qt.UserRole, r); self.lib.addItem(it)
        if not self.lib.count():
            it = QListWidgetItem(T("nothing_dl")); it.setFlags(Qt.NoItemFlags); self.lib.addItem(it)

    # ---------------------------------------------------------------- actions
    def _download(self, surahs: list[int]) -> None:
        r = self.current_reciter()
        if r:
            self.prog.setRange(0, len(surahs)); self.prog.setValue(0)
            self.vm.start(r, surahs, self.translation())

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self.prog.setValue(done)
        if msg: self.status.setText(msg)

    def _on_finished(self, msg: str) -> None:
        self.status.setText(msg)
        self.refresh(); self.fill_library(); self.library_changed.emit()

    def _on_busy(self, busy: bool) -> None:
        self.b_all.setEnabled(not busy); self.b_one.setEnabled(not busy); self.b_cancel.setEnabled(busy)

    def _lib_clicked(self, it) -> None:
        r = it.data(Qt.UserRole)
        if r: self.library_reciter_chosen.emit(r.id)

    def _delete(self) -> None:
        it = self.lib.currentItem()
        r = (it.data(Qt.UserRole) if it else None) or self.current_reciter()
        if not r or not self.vm.stats(r).surahs: return
        if QMessageBox.question(self, T("delete_title"), T("delete_q", name=r.name(rtl()))) != QMessageBox.Yes: return
        self.vm.delete(r)
        self.refresh(); self.fill_library(); self.library_changed.emit()
