"""Recite page: surah + range, mode and its options, reciter list. Exposes `values()` for the view models."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import T
from ...core.models import Reciter
from ...core.settings import ADVANCE, HINTS, MODES, Settings
from ...overlay.painter import register_fonts
from ..theme.icons import icon
from ..theme.tokens import C
from ..viewmodels import CatalogViewModel, DownloadsViewModel
from ..widgets.basic import FitStack, card, field, lbl, page_header, page_layout, segmented, slider, switch
from ..widgets.reciter_delegate import DOWNLOADED_ROLE, RECITER_ROLE, ReciterDelegate
from ..widgets.smooth_scroll import SmoothScroll


class RecitePage(QWidget):
    start_requested = Signal()
    reciter_changed = Signal(object)     # Reciter
    surah_changed = Signal(int)
    translation_changed = Signal(str)

    def __init__(self, s: Settings, catalog: CatalogViewModel, downloads: DownloadsViewModel):
        super().__init__()
        self.catalog, self.downloads, self.s = catalog, downloads, s
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        w, v = page_layout(); root.addWidget(w)
        page_header(v, T("recite_title"), T("recite_sub"), "book")
        h = QHBoxLayout(); h.setSpacing(18); v.addLayout(h, 1)
        left = QVBoxLayout(); left.setSpacing(18); h.addLayout(left, 5)
        left.addWidget(self._surah_card())
        left.addWidget(self._mode_card())
        left.addStretch()
        self.playbtn = QPushButton(T("start")); self.playbtn.setObjectName("primary")
        self.playbtn.setCursor(Qt.PointingHandCursor); self.playbtn.clicked.connect(self.start_requested.emit)
        self.playbtn.setIcon(icon("play", C["ON"], mirror=False)); self.playbtn.setIconSize(QSize(18, 18))
        left.addWidget(self.playbtn)
        h.addWidget(self._reciter_card(), 6)
        for cb in self.findChildren(QComboBox):  # long items must not widen the column
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); cb.setMinimumContentsLength(12)
        self._mode_changed(self.modeg.checkedId()); self.advopts.show_index(self.adv.currentIndex()); self._hint_changed()
        catalog.loaded.connect(self.populate)
        catalog.failed.connect(self._on_failed)
        if catalog.ready: self.populate()

    # ---------------------------------------------------------------- building
    def _surah_card(self):
        s = self.s
        cs, cv = card(T("surah"))
        self.surah = QComboBox(); self.surah.setEditable(True); self.surah.setInsertPolicy(QComboBox.NoInsert)
        self.surah.lineEdit().setPlaceholderText(T("search_surah"))
        self.surah.completer().setFilterMode(Qt.MatchContains)
        self.surah.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.surah.currentIndexChanged.connect(self._surah_changed)
        cv.addWidget(field(T("surah"), self.surah))
        self.ayah = QSpinBox(); self.ayah.setRange(1, 286)
        self.ayah_to = QSpinBox(); self.ayah_to.setRange(0, 286); self.ayah_to.setSpecialValueText(T("to_end"))
        sw, self.loop = switch(T("loop")); self.loop.setChecked(s.loop)
        row = QHBoxLayout(); row.addWidget(field(T("from_ayah"), self.ayah)); row.addWidget(field(T("to_ayah"), self.ayah_to))
        row.addWidget(sw, 0, Qt.AlignBottom); cv.addLayout(row)
        self.surah_ar = lbl("", "quran"); self.surah_ar.setFont(QFont(register_fonts(), 22))
        self.surah_ar.setAlignment(Qt.AlignCenter); self.surah_ar.setMinimumHeight(50); cv.addWidget(self.surah_ar)
        self.surah_meta = lbl("", "small"); self.surah_meta.setAlignment(Qt.AlignCenter); cv.addWidget(self.surah_meta)
        return cs

    def _mode_card(self):
        s = self.s
        cm, cv = card(T("mode"))
        segw, self.modeg = segmented([T("mode_recite"), T("mode_memorize"), T("mode_manual")], MODES.index(s.mode))
        cv.addWidget(segw)
        self.modedesc = lbl("", "modedesc", True); cv.addWidget(self.modedesc)
        self.trans = QComboBox(); self.trans.currentIndexChanged.connect(lambda *_: self.translation_changed.emit(self.translation()))
        cv.addWidget(field(T("translation"), self.trans))
        self.modeopts = FitStack(); self.modeopts.setObjectName("modeopts")
        self.modeopts.addWidget(self._recite_options())
        self.modeopts.addWidget(self._memorize_options())
        o = QWidget(); ov = QVBoxLayout(o); ov.setContentsMargins(0, 0, 0, 0)
        ov.addWidget(lbl(T("manual_desc"), "small", True)); self.modeopts.addWidget(o)
        cv.addWidget(self.modeopts)
        self.modeg.idClicked.connect(self._mode_changed)
        return cm

    def _recite_options(self):
        s = self.s
        o = QWidget(); ov = QVBoxLayout(o); ov.setContentsMargins(0, 0, 0, 0); ov.setSpacing(12)
        self.speed, sl = slider(50, 200, round(float(s.speed) * 100), lambda x: f"{x / 100:.2f}×", 5)
        self.volume, vl = slider(0, 100, s.volume, lambda x: f"{x}%")
        row = QHBoxLayout(); row.setSpacing(18); row.addWidget(field(T("speed"), self.speed, sl)); row.addWidget(field(T("volume"), self.volume, vl))
        ov.addLayout(row)
        sw, self.autonext = switch(T("autonext")); self.autonext.setChecked(s.autonext); ov.addWidget(sw)
        sw, self.wordsync = switch(T("word_sync"), T("word_sync_desc")); self.wordsync.setChecked(s.word_sync); ov.addWidget(sw)
        return o

    def _memorize_options(self):
        s = self.s
        o = QWidget(); ov = QVBoxLayout(o); ov.setContentsMargins(0, 0, 0, 0); ov.setSpacing(12)
        self.adv = QComboBox()
        for k in ADVANCE: self.adv.addItem(T("adv_" + k), k)
        self.adv.setCurrentIndex(ADVANCE.index(s.mem_advance))
        ov.addWidget(field(T("advance"), self.adv))
        self.advopts = FitStack(); self.advopts.setObjectName("modeopts")
        a = QWidget(); ah = QHBoxLayout(a); ah.setContentsMargins(0, 0, 0, 0); ah.setSpacing(18)
        self.perword, l1 = slider(3, 30, round(float(s.mem_per_word) * 10), lambda x: T("sec_per_word", s=f"{x / 10:.1f}"))
        self.memmin, l2 = slider(1, 30, round(float(s.mem_min)), lambda x: T("secs", s=x))
        ah.addWidget(field(T("per_word"), self.perword, l1)); ah.addWidget(field(T("minimum"), self.memmin, l2))
        self.advopts.addWidget(a)
        a = QWidget(); ah = QHBoxLayout(a); ah.setContentsMargins(0, 0, 0, 0)
        self.memfixed, l3 = slider(2, 120, round(float(s.mem_fixed)), lambda x: T("secs", s=x))
        ah.addWidget(field(T("per_verse"), self.memfixed, l3)); self.advopts.addWidget(a)
        a = QWidget(); ah = QHBoxLayout(a); ah.setContentsMargins(0, 0, 0, 0)
        ah.addWidget(lbl(T("adv_reciter_desc"), "small", True)); self.advopts.addWidget(a)
        ov.addWidget(self.advopts)
        self.adv.currentIndexChanged.connect(self.advopts.show_index)
        self.memgap, l4 = slider(0, 20, round(float(s.mem_gap)), lambda x: T("secs", s=x) if x else T("off"))
        self.memrep = QSpinBox(); self.memrep.setRange(1, 20); self.memrep.setValue(int(s.mem_repeat)); self.memrep.setSuffix(" ×")
        row = QHBoxLayout(); row.setSpacing(18); row.addWidget(field(T("gap"), self.memgap, l4), 1); row.addWidget(field(T("repeat"), self.memrep))
        ov.addLayout(row)
        self.hint = QComboBox()
        for k in HINTS: self.hint.addItem(T("hint_" + k), k)
        self.hint.setCurrentIndex(HINTS.index(s.mem_hint))
        self.hintwords = QSpinBox(); self.hintwords.setRange(1, 10); self.hintwords.setValue(int(s.hint_words))
        self.hintdelay, l5 = slider(1, 30, round(float(s.hint_delay)), lambda x: T("secs", s=x))
        row = QHBoxLayout(); row.setSpacing(18); row.addWidget(field(T("helper"), self.hint), 2)
        self.hw_field = field(T("hint_words"), self.hintwords); row.addWidget(self.hw_field)
        self.hd_field = field(T("hint_delay"), self.hintdelay, l5); row.addWidget(self.hd_field, 2)
        ov.addLayout(row)
        self.hint.currentIndexChanged.connect(self._hint_changed)
        return o

    def _reciter_card(self):
        cr, cv = card()
        row = QHBoxLayout(); row.addWidget(lbl(T("reciter"), "h2")); row.addStretch()
        self.reccount = lbl(T("loading"), "small"); row.addWidget(self.reccount); cv.addLayout(row)
        self.search = QLineEdit(); self.search.setPlaceholderText(T("search_reciter"))
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self._filter)
        self.search.addAction(icon("search", C["MUTED"]), QLineEdit.LeadingPosition)
        cv.addWidget(self.search)
        self.reclist = QListWidget(); self.reclist.setItemDelegate(ReciterDelegate(self.reclist))
        self.reclist.setMouseTracking(True); self.reclist.setMinimumHeight(340)
        self.reclist.setVerticalScrollMode(QListWidget.ScrollPerPixel); self.reclist.verticalScrollBar().setSingleStep(24)
        SmoothScroll(self.reclist, 1.0)
        self.reclist.currentItemChanged.connect(lambda *_: self.reciter_changed.emit(self.reciter()))
        self.reclist.itemDoubleClicked.connect(lambda *_: self.start_requested.emit())
        cv.addWidget(self.reclist, 1)
        self.rechint = lbl("", "small", True); cv.addWidget(self.rechint)
        cr.setMinimumWidth(380)
        return cr

    # ---------------------------------------------------------------- behaviour
    def _on_failed(self, _err: str) -> None:
        self.reccount.setText(T("offline"))

    def _mode_changed(self, i: int) -> None:
        self.modeopts.show_index(i)
        self.modedesc.setText(T("mode_desc_" + MODES[i]))
        self.rechint.setText(T("rec_hint_" + MODES[i]))

    def _hint_changed(self, *_) -> None:
        reveal = self.hint.currentData() == "reveal"
        self.hw_field.setVisible(reveal); self.hd_field.setVisible(reveal)

    def surah_label(self, s) -> str:
        return T("surah_item", n=s.number, en=s.english, meaning=s.meaning, ar=s.short_name, ayahs=s.ayahs)

    def populate(self) -> None:
        c, s = self.catalog, self.s
        self.surah.blockSignals(True); self.surah.clear()
        for x in c.surahs: self.surah.addItem(self.surah_label(x), x.ayahs)
        self.surah.setCurrentIndex(s.surah - 1); self.surah.blockSignals(False)
        n = self.surah.currentData() or 286
        self.ayah.setMaximum(n); self.ayah_to.setMaximum(n)
        self.ayah.setValue(s.range_from if s.range_to else s.ayah)
        self.ayah_to.setValue(min(s.range_to, n))
        self._show_surah_info()
        self.trans.blockSignals(True); self.trans.clear()
        self.trans.addItem(T("no_translation"), "")
        for e in sorted(c.translations, key=lambda e: (e.language, e.name)):
            self.trans.addItem(f"{e.language.upper()}  ·  {e.name}", e.id)
        self.trans.setCurrentIndex(max(0, self.trans.findData(s.trans))); self.trans.blockSignals(False)
        self.fill_reciters(c.find_reciter(s.reciter).id)
        self.reccount.setText(T("n_reciters", n=len(c.reciters)))
        self.reciter_changed.emit(self.reciter())

    def fill_reciters(self, select_id: int | None = None) -> None:
        if select_id is None and self.reciter(): select_id = self.reciter().id
        self.reclist.blockSignals(True); self.reclist.clear()
        for r in self.catalog.reciters:
            it = QListWidgetItem(r.search_text())
            it.setData(RECITER_ROLE, r); it.setData(DOWNLOADED_ROLE, self.downloads.stats(r).surahs)
            self.reclist.addItem(it)
            if r.id == select_id: self.reclist.setCurrentItem(it)
        self.reclist.blockSignals(False)
        self._filter(self.search.text())
        if self.reclist.currentItem(): self.reclist.scrollToItem(self.reclist.currentItem(), QListWidget.PositionAtCenter)

    def select_reciter(self, rid: int) -> None:
        self.search.clear(); self.fill_reciters(rid); self.reciter_changed.emit(self.reciter())

    def _filter(self, q: str) -> None:
        for i in range(self.reclist.count()):
            self.reclist.setRowHidden(i, not self.catalog.matches(q, self.reclist.item(i).data(RECITER_ROLE)))

    def _surah_changed(self, *_) -> None:
        n = self.surah.currentData()
        if n:
            self.ayah.setMaximum(n); self.ayah.setValue(1); self.ayah_to.setMaximum(n); self.ayah_to.setValue(0)
        self._show_surah_info()
        self.surah_changed.emit(self.surah_number())

    def _show_surah_info(self) -> None:
        x = self.catalog.surah(self.surah_number())
        if not x: return
        self.surah.lineEdit().setCursorPosition(0)
        self.surah_ar.setText(x.name)
        self.surah_meta.setText(T("surah_meta", meaning=x.meaning, ayahs=x.ayahs,
                                  place=T("meccan" if x.revelation == "Meccan" else "medinan")))

    # ---------------------------------------------------------------- values
    def reciter(self) -> Reciter | None:
        it = self.reclist.currentItem()
        return it.data(RECITER_ROLE) if it else self.catalog.find_reciter(self.s.reciter)

    def surah_number(self) -> int:
        return self.surah.currentIndex() + 1

    def translation(self) -> str:
        return self.trans.currentData() or ""

    def values(self) -> dict:
        d = dict(trans=self.translation(), speed=round(self.speed.value() / 100, 2), volume=self.volume.value(),
                 mode=MODES[self.modeg.checkedId()], autonext=self.autonext.isChecked(),
                 word_sync=self.wordsync.isChecked(), loop=self.loop.isChecked(),
                 mem_advance=self.adv.currentData(), mem_per_word=self.perword.value() / 10,
                 mem_min=float(self.memmin.value()), mem_fixed=float(self.memfixed.value()),
                 mem_gap=float(self.memgap.value()), mem_repeat=self.memrep.value(), mem_hint=self.hint.currentData(),
                 hint_words=self.hintwords.value(), hint_delay=float(self.hintdelay.value()))
        r = self.reciter()
        if r: d["reciter"] = r.id
        if self.catalog.ready:
            a, b = self.ayah.value(), self.ayah_to.value()
            d.update(surah=self.surah_number(), ayah=a, range_from=a, range_to=b if b >= a else 0)
        return d
