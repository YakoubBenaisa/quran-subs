"""The on-screen verses: a frameless, click-through, always-on-top window that only draws."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from ..core.models import Page
from ..core.settings import Settings
from .painter import page_lines, paint_lines

EXTRA_HEIGHT = 30


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                            | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.lines: list = []
        self.style: Settings | None = None
        self.hidden = False

    @staticmethod
    def screen_width() -> int:
        return QApplication.primaryScreen().availableGeometry().width()

    def render_page(self, page: Page, s: Settings) -> None:
        self.style = s
        self.lines, h = page_lines(page, s)
        scr = QApplication.primaryScreen().availableGeometry()
        h = int(h + EXTRA_HEIGHT)
        y = scr.top() + s.margin if s.pos == "top" else scr.bottom() - h - s.margin
        self.setGeometry(scr.left(), y, scr.width(), h)
        if not self.hidden:
            self.show(); self.raise_()
        self.update()

    def set_hidden(self, hidden: bool) -> None:
        self.hidden = hidden
        self.setVisible(not hidden)

    def paintEvent(self, _):
        if not self.style: return
        p = QPainter(self)
        paint_lines(p, self.width(), self.height(), self.lines, self.style)
        p.end()
