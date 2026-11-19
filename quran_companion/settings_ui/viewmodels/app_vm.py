"""Window-wide choices (language, theme, interface font) that need the views to be rebuilt."""
from PySide6.QtCore import QObject, QTimer, Signal

from ...core.i18n import tr
from ...core.settings import SettingsStore


class AppViewModel(QObject):
    rebuild_requested = Signal()

    def __init__(self, store: SettingsStore):
        super().__init__()
        self.store = store

    def languages(self) -> list[tuple[str, str, str]]:
        return tr.languages()

    @property
    def language(self) -> str:
        return tr.code

    def _change(self, **kw) -> None:
        self.store.update(**kw)
        QTimer.singleShot(0, self.rebuild_requested.emit)   # after the click handler returns

    def set_language(self, code: str) -> None:
        self._change(ui_lang=code)

    def set_theme(self, theme: str) -> None:
        self._change(theme=theme)

    def set_ui_font(self, family: str) -> None:
        self._change(ui_font=family)
