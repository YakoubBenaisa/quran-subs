"""Applies the theme, language direction and interface font to the application."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...core.i18n import rtl, tr
from ...core.settings import UI_FONT, Settings
from .icons import _ICON_CACHE, make_icons
from .qss import build_qss, make_palette
from .tokens import THEMES, C, theme_name


def apply_app_theme(app, s: Settings) -> None:
    """Apply language direction, interface font, colour theme and stylesheet to the whole app."""
    tr.set(s.ui_lang)
    t = theme_name(s.theme); C.clear(); C.update(THEMES[t], name=t)
    _ICON_CACHE.clear()
    app.setLayoutDirection(Qt.RightToLeft if rtl() else Qt.LeftToRight)
    f = QFont(s.ui_font or UI_FONT); f.setPointSizeF(10); app.setFont(f)
    app.setStyle("Fusion"); app.setPalette(make_palette()); app.setStyleSheet(build_qss(make_icons()))
