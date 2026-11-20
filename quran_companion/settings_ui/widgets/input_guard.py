"""App-wide input fixes for value widgets inside scrolling pages.

* The mouse wheel over a closed dropdown, spin box or slider scrolls the page instead of
  silently changing the value. Dropdowns change only by clicking; spin boxes and sliders
  accept the wheel once they were clicked (focused).
* Dropdown lists open below the field as a rounded card with roomy, hoverable rows and
  smooth scrolling.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractItemView, QAbstractSlider, QAbstractSpinBox, QComboBox, QFontComboBox, QStyledItemDelegate

from .font_delegate import FontRowDelegate
from .smooth_scroll import SmoothScroll


def ensure_font_rows(cb: QFontComboBox) -> None:
    """Font names + a sample in each font. Qt puts its own font delegate back at times, so this
    is re-applied whenever the list opens."""
    if isinstance(cb.itemDelegate(), FontRowDelegate): return
    sample = cb.property("sample")
    cb.setItemDelegate(FontRowDelegate(cb, sample) if sample else FontRowDelegate(cb))


def polish_dropdown(cb: QComboBox) -> None:
    if cb.property("_polished"): return
    cb.setProperty("_polished", True)
    cb.setFocusPolicy(Qt.StrongFocus)
    if isinstance(cb, QFontComboBox):
        ensure_font_rows(cb)
    else:
        cb.setItemDelegate(QStyledItemDelegate(cb))   # lets the stylesheet style each row
    cb.setMaxVisibleItems(12)
    v = cb.view()
    v.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    v.setMouseTracking(True)
    SmoothScroll(v, step=0.6)
    popup = v.window()                          # the popup container, for rounded corners
    popup.setWindowFlags(popup.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WA_TranslucentBackground)


class InputGuard(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Polish and isinstance(obj, QComboBox):
            polish_dropdown(obj)
        elif t == QEvent.Polish and isinstance(obj, (QAbstractSpinBox, QAbstractSlider)):
            obj.setFocusPolicy(Qt.StrongFocus)
        elif t == QEvent.Show and isinstance(obj.parent(), QFontComboBox) and obj.isWindow():
            ensure_font_rows(obj.parent())      # the list popup is about to appear
        elif t == QEvent.Wheel:
            if isinstance(obj, QComboBox) or (isinstance(obj, (QAbstractSpinBox, QAbstractSlider)) and not obj.hasFocus()):
                ev.ignore()      # not handled here: Qt passes it on to the scrolling page
                return True
        return False


def install(app) -> InputGuard:
    g = InputGuard(app)
    app.installEventFilter(g)
    return g
