"""App-wide input fixes for value widgets inside scrolling pages.

* The mouse wheel over a closed dropdown, spin box or slider scrolls the page instead of
  silently changing the value. Dropdowns change only by clicking; spin boxes and sliders
  accept the wheel once they were clicked (focused).
* Dropdown lists open below the field as a rounded card with roomy, hoverable rows and
  smooth scrolling, as wide as the field.
* A click anywhere on a searchable dropdown opens its list (not only on the arrow); typing
  while the list is open moves the keys to the search field.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QFontComboBox, QStyledItemDelegate

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
    if cb.isEditable():
        cb.lineEdit().installEventFilter(_CLICK_OPENS); cb.lineEdit().setProperty("_combo_edit", True)
        v.installEventFilter(_CLICK_OPENS)
    popup = v.window()                          # the popup container, for rounded corners
    popup.setWindowFlags(popup.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WA_TranslucentBackground)


def _match_width(cb: QComboBox) -> None:
    """QFontComboBox makes its list 5/3 as wide as the field; keep it the field's width."""
    try:
        cb.view().window().setFixedWidth(max(cb.width(), 180))
    except RuntimeError:      # widget already deleted
        pass


class _ClickOpens(QObject):
    """Editable dropdowns: a click on the text opens the list; typing in the open list searches."""
    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj.property("_combo_edit"):
            cb = obj.parent()
            if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton and isinstance(cb, QComboBox):
                QTimer.singleShot(0, cb.showPopup)
                return False
        elif t == QEvent.KeyPress and ev.text().strip() and not ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            cb = _combo_of_view(obj)
            if cb is not None and cb.isEditable():
                cb.hidePopup()
                le = cb.lineEdit(); le.setFocus(); le.selectAll()
                QApplication.sendEvent(le, ev.clone())
                return True
        return False


def _combo_of_view(view):
    w = view.parent()
    while w is not None and not isinstance(w, QComboBox):
        w = w.parent()
    return w


_CLICK_OPENS = _ClickOpens()


class InputGuard(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Polish and isinstance(obj, QComboBox):
            polish_dropdown(obj)
        elif t == QEvent.Polish and isinstance(obj, (QAbstractSpinBox, QAbstractSlider)):
            obj.setFocusPolicy(Qt.StrongFocus)
        elif t == QEvent.Show and isinstance(obj.parent(), QFontComboBox) and obj.isWindow():
            ensure_font_rows(obj.parent())      # the list popup is about to appear
            _match_width(obj.parent())
        elif t == QEvent.Resize and isinstance(obj, QFontComboBox):
            QTimer.singleShot(0, lambda cb=obj: _match_width(cb))   # after Qt widened the list again
        elif t == QEvent.Wheel:
            if isinstance(obj, QComboBox) or (isinstance(obj, (QAbstractSpinBox, QAbstractSlider)) and not obj.hasFocus()):
                ev.ignore()      # not handled here: Qt passes it on to the scrolling page
                return True
        return False


def install(app) -> InputGuard:
    g = InputGuard(app)
    app.installEventFilter(g)
    return g
