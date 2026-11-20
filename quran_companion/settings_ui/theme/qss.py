"""Qt stylesheet and palette built from the active colour tokens."""
from PySide6.QtGui import QColor, QPalette

from ...core.i18n import rtl
from .tokens import C, rgba


def build_qss(i, ui_font: str = "", quran_font: str = ""):
    """ui_font goes into the stylesheet because Qt otherwise falls back to the desktop font
    (e.g. a monospace GNOME font) for every widget a stylesheet touches."""
    c = C
    fam = f'font-family:"{ui_font}";' if ui_font else ""
    qfam = f'font-family:"{quran_font}";' if quran_font else ""
    fill, rest = ("add", "sub") if rtl() else ("sub", "add")  # Qt does not mirror slider pages in RTL
    return f"""
QWidget {{ color:{c['TEXT']}; {fam} }}
QStackedWidget, QScrollArea, QWidget#page, QWidget#modeopts {{ background:transparent; }}
QScrollArea {{ border:none; }}
QFrame#side {{ background:{c['SIDE']}; border:none; }}
QFrame#bar {{ background:{c['SIDE']}; border-top:1px solid {c['BORDER']}; }}
QLabel#brandAr {{ color:{c['ACCENT']}; font-size:15pt; font-weight:700; }}
QLabel#quran {{ color:{c['ACCENT']}; {qfam} }}
QLabel#brand {{ font-size:12.5pt; font-weight:700; }}
QLabel#muted {{ color:{c['MUTED']}; }}
QLabel#small {{ color:{c['MUTED']}; font-size:9pt; }}
QLabel#h1 {{ font-size:20pt; font-weight:700; }}
QLabel#h2 {{ font-size:11.5pt; font-weight:700; }}
QLabel#field {{ color:{c['MUTED']}; font-size:8.5pt; font-weight:700; letter-spacing:0.6px; }}
QLabel#value {{ color:{c['ACCENT']}; font-weight:700; }}
QLabel#bigname {{ font-size:16pt; font-weight:700; }}
QLabel#npname {{ color:{c['ACCENT']}; font-size:12.5pt; font-weight:700; }}
QLabel#stat {{ font-size:22pt; font-weight:800; color:{c['ACCENT']}; }}
QLabel#kbd {{ background:{c['FIELD']}; border:1px solid {c['BORDER']}; border-bottom:2px solid {c['BORDER']};
             border-radius:6px; padding:1px 6px; font-size:8.5pt; font-weight:700; color:{c['SUB']}; }}
QLabel#modedesc {{ color:{c['SUB']}; background:{rgba(c['ACCENT'], 0.08)}; border:1px solid {rgba(c['ACCENT'], 0.18)};
                   border-radius:10px; padding:10px 12px; }}
QFrame#card {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['CARD2']}, stop:1 {c['CARD']});
              border:1px solid {c['BORDER']}; border-radius:18px; }}
QFrame#shortcuts {{ background:{c['CARD']}; border:1px solid {c['BORDER']}; border-radius:14px; }}
QPushButton#nav {{ text-align:left; padding:7px 10px; border:none; border-radius:12px; background:transparent;
                   color:{c['MUTED']}; font-weight:600; font-size:10.5pt; }}
QPushButton#nav:hover {{ background:{c['HOVER']}; color:{c['TEXT']}; }}
QPushButton#nav:checked {{ background:{rgba(c['ACCENT'], 0.12)}; color:{c['ACCENT']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {{ background:{c['FIELD']}; border:1px solid {c['BORDER']};
        border-radius:10px; padding:7px 10px; selection-background-color:{c['ACCENT']}; selection-color:{c['ON']}; min-height:20px; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QFontComboBox:hover {{ border-color:{rgba(c['ACCENT'], 0.45)}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QFontComboBox:focus {{ border:1px solid {c['ACCENT']}; }}
QComboBox::drop-down {{ border:none; width:28px; }}
QComboBox::down-arrow {{ image:url({i['down']}); width:12px; height:12px; }}
QComboBox {{ combobox-popup:0; }}
QComboBox:on {{ border:1px solid {c['ACCENT']}; background:{c['CARD2']}; }}
QComboBox::down-arrow:on {{ image:url({i['up']}); }}
QComboBoxPrivateContainer {{ background:transparent; border:none; padding:0; margin:0; }}
QComboBox QAbstractItemView {{ background:{c['CARD']}; border:1px solid {rgba(c['ACCENT'], 0.35)}; border-radius:12px;
        padding:6px; outline:0; selection-background-color:{rgba(c['ACCENT'], 0.16)}; selection-color:{c['TEXT']}; }}
QComboBox QAbstractItemView::item {{ min-height:32px; padding:0 10px; border-radius:8px; margin:1px 0; color:{c['TEXT']}; }}
QComboBox QAbstractItemView::item:hover {{ background:{c['HOVER']}; }}
QComboBox QAbstractItemView::item:selected {{ background:{rgba(c['ACCENT'], 0.16)}; color:{c['ACCENT']}; font-weight:600; }}
QSpinBox::up-button, QSpinBox::down-button {{ width:20px; border:none; background:transparent; }}
QSpinBox::up-arrow {{ image:url({i['up']}); width:10px; height:10px; }}
QSpinBox::down-arrow {{ image:url({i['down']}); width:10px; height:10px; }}
QListWidget {{ background:transparent; border:none; outline:0; }}
QListWidget#lib::item {{ padding:10px; border-radius:10px; margin:1px 0; }}
QListWidget#lib::item:hover {{ background:{c['HOVER']}; }}
QListWidget#lib::item:selected {{ background:{rgba(c['ACCENT'], 0.14)}; color:{c['TEXT']}; }}
QPushButton {{ background:{c['BTN']}; border:1px solid {c['BORDER']}; border-radius:10px; padding:8px 14px; font-weight:600; }}
QPushButton:hover {{ background:{c['BTNH']}; border-color:{rgba(c['ACCENT'], 0.35)}; }}
QPushButton:pressed {{ background:{c['HOVER']}; }}
QPushButton:disabled {{ color:{c['MUTED']}; background:{c['FIELD']}; border-color:{c['BORDER']}; }}
QPushButton#primary {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['ACCENT2']}, stop:1 {c['ACCENT']});
        color:{c['ON']}; border:1px solid {c['ACCENT3']}; padding:12px 22px; font-size:11pt; font-weight:700; border-radius:12px; }}
QPushButton#primary:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5ee0b0, stop:1 {c['ACCENT2']}); }}
QPushButton#primary:disabled {{ background:{rgba(c['ACCENT'], 0.35)}; color:{c['ON']}; border-color:transparent; }}
QPushButton#danger {{ color:#ef4444; }}
QPushButton#round {{ border-radius:21px; min-width:42px; max-width:42px; min-height:42px; max-height:42px; padding:0; }}
QPushButton#roundMain {{ border-radius:27px; min-width:54px; max-width:54px; min-height:54px; max-height:54px; padding:0;
        background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['ACCENT2']}, stop:1 {c['ACCENT3']}); border:none; }}
QPushButton#roundMain:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5ee0b0, stop:1 {c['ACCENT']}); }}
QPushButton#seg {{ border-radius:0; padding:8px 14px; background:{c['FIELD']}; }}
QPushButton#seg[first="true"] {{ border-top-left-radius:10px; border-bottom-left-radius:10px; }}
QPushButton#seg[last="true"] {{ border-top-right-radius:10px; border-bottom-right-radius:10px; }}
QPushButton#seg:checked {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['ACCENT2']}, stop:1 {c['ACCENT']});
        color:{c['ON']}; border-color:{c['ACCENT']}; }}
QPushButton#iconseg {{ border-radius:0; padding:7px; background:{c['FIELD']}; }}
QPushButton#iconseg[first="true"] {{ border-top-left-radius:10px; border-bottom-left-radius:10px; }}
QPushButton#iconseg[last="true"] {{ border-top-right-radius:10px; border-bottom-right-radius:10px; }}
QPushButton#iconseg:checked {{ background:{rgba(c['ACCENT'], 0.16)}; border-color:{c['ACCENT']}; }}
QCheckBox {{ spacing:12px; font-weight:600; }}
QCheckBox::indicator {{ width:40px; height:24px; image:url({i['off']}); }}
QCheckBox::indicator:checked {{ image:url({i['on']}); }}
QSlider {{ min-height:24px; }}
QSlider::groove:horizontal {{ height:8px; background:{c['TRACK']}; border-radius:4px; }}
QSlider::{fill}-page:horizontal {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['ACCENT2'] if rtl() else c['ACCENT3']}, stop:1 {c['ACCENT3'] if rtl() else c['ACCENT2']}); border-radius:4px; }}
QSlider::{rest}-page:horizontal {{ background:{c['TRACK']}; border-radius:4px; }}
QSlider::handle:horizontal {{ background:#ffffff; border:4px solid {c['ACCENT']}; width:12px; height:12px; margin:-6px 0; border-radius:10px; }}
QSlider::handle:horizontal:hover {{ border:4px solid {c['ACCENT2']}; }}
QProgressBar {{ background:{c['TRACK']}; border:none; border-radius:6px; max-height:12px; min-height:12px; color:transparent; }}
QProgressBar::chunk {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['ACCENT3']}, stop:1 {c['ACCENT2']}); border-radius:6px; }}
QLabel#pillOn {{ background:{rgba(c['ACCENT'], 0.16)}; color:{c['ACCENT']}; border-radius:12px; padding:5px 12px; font-size:9pt; font-weight:700; }}
QLabel#pillOff {{ background:{c['FIELD']}; color:{c['MUTED']}; border-radius:12px; padding:5px 12px; font-size:9pt; font-weight:700; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:4px 2px; }}
QScrollBar::handle:vertical {{ background:{c['SCROLL']}; border-radius:3px; min-height:40px; margin:0 2px; }}
QScrollBar::handle:vertical:hover {{ background:{c['MUTED']}; margin:0 1px; border-radius:4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
QToolTip {{ background:{c['CARD']}; color:{c['TEXT']}; border:1px solid {c['BORDER']}; padding:5px; border-radius:6px; }}
"""


def make_palette():
    c, pal = C, QPalette()
    for role, v in [(QPalette.Window, c["BG"]), (QPalette.WindowText, c["TEXT"]), (QPalette.Base, c["FIELD"]),
                    (QPalette.AlternateBase, c["CARD"]), (QPalette.Text, c["TEXT"]), (QPalette.Button, c["BTN"]),
                    (QPalette.ButtonText, c["TEXT"]), (QPalette.Highlight, c["ACCENT"]), (QPalette.HighlightedText, c["ON"]),
                    (QPalette.ToolTipBase, c["CARD"]), (QPalette.ToolTipText, c["TEXT"]), (QPalette.PlaceholderText, c["MUTED"])]:
        pal.setColor(role, QColor(v))
    return pal
