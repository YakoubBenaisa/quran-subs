"""Controls the overlay process from the settings window and reports what it is doing."""
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from ...core.settings import SettingsStore
from ...ipc.client import OverlayClient
from ...ipc.protocol import Cmd, Command

REFRESH_MS = 1500


@dataclass(frozen=True)
class Status:
    running: bool
    shown: bool
    surah: int
    ayah: int
    mode: str
    reciter: int


class PlaybackViewModel(QObject):
    status_changed = Signal(object)   # Status

    def __init__(self, store: SettingsStore, client: OverlayClient):
        super().__init__()
        self.store, self.client = store, client
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(REFRESH_MS)
        self.status: Status | None = None

    def refresh(self) -> None:
        s, live = self.store.load(), self.client.running()
        st = Status(live, live and s.visible, s.surah, s.ayah, s.mode, s.reciter)
        if st != self.status:
            self.status = st
            self.status_changed.emit(st)

    def _later(self, ms: int = 700) -> None:
        QTimer.singleShot(ms, self.refresh)

    def start(self, **settings) -> None:
        """Save the chosen surah / reciter / mode / style and (re)start the recitation."""
        self.store.update(**settings)
        if self.client.running() and not self.client.up_to_date(): self.client.restart()
        elif not self.client.send(Cmd.PLAY): self.client.spawn()
        self._later(1200)

    def play_pause(self, **settings) -> None:
        if not self.client.send(Cmd.PAUSE): self.start(**settings)
        self._later()

    def stop(self) -> None:
        self.client.send(Cmd.QUIT); self._later(600)

    def step(self, d: int) -> None:
        self.client.send(Cmd.NEXT if d > 0 else Cmd.PREV)

    def set_visible(self, on: bool, **settings) -> None:
        if self.client.running():
            if self.client.up_to_date(): self.client.send(Command(Cmd.VISIBLE, {"on": on}))
            else: self.client.restart(hidden=not on)   # an older overlay without this command
        elif on:
            self.start(**settings)
        self._later()

    def apply_style(self, **style) -> None:
        self.store.update(**style)
        self.client.send(Cmd.RESTYLE)
