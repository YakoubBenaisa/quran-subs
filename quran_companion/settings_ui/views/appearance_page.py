"""Appearance page: Quran / translation fonts, lines & width, colours, background, position, interface font."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QFontComboBox, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...core.i18n import T, rtl
from ...core.settings import UI_FONT, Settings
from ...overlay.painter import register_fonts
from ..theme.icons import icon
from ..theme.tokens import C
from ..widgets.basic import card, field, lbl, page_header, page_layout, segmented, slider, switch
from ..widgets.color_button import ColorButton
from ..widgets.preview import Preview

APPLY_DELAY_MS = 150


class AppearancePage(QWidget):
    style_changed = Signal(dict)        # debounced; style values to save and send to the overlay
    ui_font_chosen = Signal(str)

    def __init__(self, s: Settings, show_translation):
        """`show_translation()` tells the preview whether a translation is selected."""
        super().__init__()
        self.s, self.show_translation = s, show_translation
        self._debounce = QTimer(self); self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self.style_changed.emit(self.values()))
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        w, v = page_layout(); root.addWidget(w)
        page_header(v, T("appearance_title"), T("appearance_sub"), "palette")

        pc, pv = card()
        row = QHBoxLayout(); row.addWidget(lbl(T("preview"), "h2")); row.addStretch(); row.addWidget(lbl(T("preview_note"), "small"))
        pv.addLayout(row)
        self.preview = Preview(lambda: (self.preview_settings(), bool(self.show_translation())))
        pv.addWidget(self.preview); v.addWidget(pc)

        g = QGridLayout(); g.setSpacing(18); v.addLayout(g)
        g.addWidget(self._quran_card(), 0, 0); g.addWidget(self._translation_card(), 0, 1)
        g.addWidget(self._layout_card(), 1, 0); g.addWidget(self._colour_card(), 1, 1)
        g.addWidget(self._background_card(), 2, 0); g.addWidget(self._interface_card(), 2, 1)
        g.setColumnStretch(0, 1); g.setColumnStretch(1, 1)

        row = QHBoxLayout(); row.addStretch()
        b = QPushButton(T("reset")); b.setIcon(icon("reset", C["SUB"])); b.clicked.connect(self.reset); row.addWidget(b)
        v.addLayout(row); v.addStretch()

        ch = self._changed
        for x in (self.font, self.trfont): x.currentFontChanged.connect(ch)
        for x in (self.size, self.trscale, self.outw, self.margin, self.bgalpha, self.maxlines, self.maxwidth, self.trlines):
            x.valueChanged.connect(ch)
        for x in (self.color, self.outline, self.bgcolor): x.changed.connect(ch)
        self.bg.toggled.connect(ch); self.posgroup.idClicked.connect(ch)

    # ---------------------------------------------------------------- cards
    def _quran_card(self):
        c, cv = card(T("arabic_text"))
        self.font = QFontComboBox(); self.font.setWritingSystem(QFontDatabase.WritingSystem.Arabic)
        self.font.setCurrentFont(QFont(self.s.font or register_fonts()))
        self.size, l = slider(16, 120, self.s.size, lambda x: f"{x} pt")
        cv.addWidget(field(T("font"), self.font)); cv.addWidget(field(T("size"), self.size, l))
        return c

    def _translation_card(self):
        c, cv = card(T("translation_text"))
        self.trfont = QFontComboBox(); self.trfont.setCurrentFont(QFont(self.s.tr_font))
        self.trscale, l = slider(20, 120, self.s.tr_scale, lambda x: T("pct_of_arabic", p=x))
        cv.addWidget(field(T("font"), self.trfont)); cv.addWidget(field(T("size"), self.trscale, l))
        return c

    def _layout_card(self):
        c, cv = card(T("layout"), T("layout_desc"))
        self.maxlines, l1 = slider(1, 6, self.s.max_lines, lambda x: T("n_lines", n=x))
        self.maxwidth, l2 = slider(30, 100, self.s.max_width, lambda x: T("pct_of_screen", p=x))
        self.trlines, l3 = slider(1, 4, self.s.tr_lines, lambda x: T("n_lines", n=x))
        cv.addWidget(field(T("max_lines"), self.maxlines, l1)); cv.addWidget(field(T("max_width"), self.maxwidth, l2))
        cv.addWidget(field(T("tr_lines"), self.trlines, l3))
        return c

    def _colour_card(self):
        c, cv = card(T("colour_outline"))
        self.color, self.outline = ColorButton(self.s.color), ColorButton(self.s.outline)
        row = QHBoxLayout(); row.addWidget(field(T("text_colour"), self.color)); row.addWidget(field(T("outline"), self.outline)); cv.addLayout(row)
        self.outw, l = slider(0, 15, self.s.outline_w, lambda x: T("off") if x == 0 else str(x))
        cv.addWidget(field(T("outline_w"), self.outw, l))
        return c

    def _background_card(self):
        c, cv = card(T("bg_position"))
        sw, self.bg = switch(T("bg_box")); self.bg.setChecked(self.s.bg); cv.addWidget(sw)
        self.bgcolor = ColorButton(self.s.bg_color)
        self.bgalpha, l = slider(0, 100, self.s.bg_alpha, lambda x: f"{x}%")
        row = QHBoxLayout(); row.addWidget(field(T("box_colour"), self.bgcolor)); row.addWidget(field(T("opacity"), self.bgalpha, l), 1)
        cv.addLayout(row)
        seg, self.posgroup = segmented([T("bottom"), T("top")], 1 if self.s.pos == "top" else 0)
        self.margin, l = slider(0, 600, self.s.margin, lambda x: f"{x} px")
        row = QHBoxLayout(); row.addWidget(field(T("position"), seg)); row.addWidget(field(T("distance"), self.margin, l), 1)
        cv.addLayout(row)
        return c

    def _interface_card(self):
        c, cv = card(T("interface"), T("interface_desc"))
        self.uifont = QFontComboBox(); self.uifont.setCurrentFont(QFont(self.s.ui_font or UI_FONT))
        cv.addWidget(field(T("ui_font"), self.uifont))
        b = QPushButton(T("apply")); b.clicked.connect(lambda: self.ui_font_chosen.emit(self.uifont.currentFont().family()))
        cv.addWidget(b, 0, Qt.AlignRight if rtl() else Qt.AlignLeft); cv.addStretch()
        return c

    # ---------------------------------------------------------------- values
    def _changed(self, *_) -> None:
        self.preview.update()
        self._debounce.start(APPLY_DELAY_MS)

    def values(self) -> dict:
        return dict(font=self.font.currentFont().family(), size=self.size.value(),
                    tr_font=self.trfont.currentFont().family(), tr_scale=self.trscale.value(),
                    color=self.color.color, outline=self.outline.color, outline_w=self.outw.value(),
                    bg=self.bg.isChecked(), bg_color=self.bgcolor.color, bg_alpha=self.bgalpha.value(),
                    pos="top" if self.posgroup.checkedId() == 1 else "bottom", margin=self.margin.value(),
                    max_lines=self.maxlines.value(), max_width=self.maxwidth.value(), tr_lines=self.trlines.value())

    def preview_settings(self) -> Settings:
        return self.s.with_(**self.values())

    def reset(self) -> None:
        d = Settings()
        self.font.setCurrentFont(QFont(register_fonts())); self.trfont.setCurrentFont(QFont(d.tr_font))
        for wdg, v in [(self.size, d.size), (self.trscale, d.tr_scale), (self.outw, d.outline_w), (self.bgalpha, d.bg_alpha),
                       (self.margin, d.margin), (self.maxlines, d.max_lines), (self.maxwidth, d.max_width), (self.trlines, d.tr_lines)]:
            wdg.setValue(v)
        self.color.set(d.color); self.outline.set(d.outline); self.bgcolor.set(d.bg_color)
        self.bg.setChecked(d.bg); self.posgroup.button(0).setChecked(True)
        self._changed()
