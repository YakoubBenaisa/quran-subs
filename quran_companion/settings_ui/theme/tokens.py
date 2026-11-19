"""Colour tokens for the dark and light themes. `C` holds the active theme (set by the theme manager)."""
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

THEMES = {
    "dark": dict(BG="#0b0d10", SIDE="#101419", CARD="#151a20", CARD2="#1a2027", FIELD="#1d232b", BORDER="#252c35",
                 TEXT="#e8ebef", MUTED="#8b94a3", SUB="#b2b9c3", ACCENT="#10b981", ACCENT2="#34d399", ACCENT3="#047857",
                 ON="#03130d", HOVER="#1b2129", BTN="#1f252e", BTNH="#272e38", SCROLL="#2b323c", KNOB="#8b94a3",
                 TRACK="#262c35", GLOW=90, BLOB=30),
    "light": dict(BG="#f2f5f4", SIDE="#ffffff", CARD="#ffffff", CARD2="#fbfdfc", FIELD="#f1f4f3", BORDER="#dfe6e3",
                  TEXT="#111827", MUTED="#6b7280", SUB="#4b5563", ACCENT="#059669", ACCENT2="#10b981", ACCENT3="#047857",
                  ON="#ffffff", HOVER="#edf3f0", BTN="#ffffff", BTNH="#f1f5f3", SCROLL="#cbd5d1", KNOB="#ffffff",
                  TRACK="#d5ddda", GLOW=60, BLOB=34),
}
C = dict(THEMES["dark"], name="dark")


def system_dark():
    try:
        cs = QApplication.styleHints().colorScheme()
        if cs == Qt.ColorScheme.Dark: return True
        if cs == Qt.ColorScheme.Light: return False
    except Exception:
        pass
    try:  # GNOME fallback
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=2).stdout
        return "dark" in out
    except Exception:
        return True


def theme_name(choice: str) -> str:
    t = choice
    if t not in THEMES: t = "dark" if system_dark() else "light"
    return t


def rgba(hexc, a):
    q = QColor(hexc); return f"rgba({q.red()},{q.green()},{q.blue()},{a})"
