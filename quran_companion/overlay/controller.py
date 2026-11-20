"""Wires the overlay process together: Session (logic) ⇄ OverlayWindow (view), CommandServer (input)."""
import os
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ..core.i18n import tr
from ..core.settings import SettingsStore
from ..data.repository import QuranRepository
from ..ipc.protocol import PROTOCOL_VERSION, Cmd, Command
from ..ipc.server import CommandServer
from ..playback.clock import MonotonicClock
from ..playback.player import AudioPlayer
from ..playback.session import Session, View
from .hotkeys import Hotkeys
from .painter import make_paginator, register_fonts
from .window import OverlayWindow

TICK_MS = 100
SIZE_STEP, MIN_SIZE = 4, 16


class _Bridge(QObject):
    """Moves calls from worker / server threads onto the UI thread."""
    command = Signal(object)
    done = Signal(object, object)


class OverlayController:
    def __init__(self, repo: QuranRepository, store: SettingsStore, player: AudioPlayer, socket_path: str,
                 start_hidden: bool = False, corrector=None):
        register_fonts()
        self.store = store
        tr.set(store.load().ui_lang)
        self.window = OverlayWindow()
        self.window.hidden = start_hidden
        self.bridge = _Bridge()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.bridge.done.connect(lambda cb, res: cb(res))
        self.bridge.command.connect(self.handle)
        self.session = Session(repo, player, MonotonicClock(), store,
                               lambda s: make_paginator(s, self.window.screen_width() * s.max_width / 100),
                               listener=self, runner=self._run_async, corrector=corrector)
        self.server = CommandServer(socket_path, self.bridge.command.emit)
        self.hotkeys = Hotkeys(self.bridge.command.emit)     # Windows / macOS; Linux uses desktop shortcuts
        self.timer = QTimer(); self.timer.timeout.connect(self.session.tick)
        store.update(visible=not start_hidden, ov_pid=os.getpid(), ov_version=PROTOCOL_VERSION)

    def _run_async(self, fn, done) -> None:
        def job():
            try:
                res = fn()
            except Exception as e:  # noqa: BLE001 - delivered to the session
                res = e
            self.bridge.done.emit(done, res)
        self.pool.submit(job)

    def start(self) -> None:
        self.server.start()
        self.hotkeys.start()
        s = self.store.load()
        self.session.load(s.surah, s.ayah, rng=(s.range_from, s.range_to))
        self.timer.start(TICK_MS)

    # Listener
    def on_view(self, view: View) -> None:
        self.window.render_page(view.page, self.session.s)

    # Commands
    def handle(self, c: Command) -> None:
        ses, k = self.session, c.cmd
        if k is Cmd.NEXT: ses.step(1)
        elif k is Cmd.PREV: ses.step(-1)
        elif k is Cmd.PAUSE: ses.toggle_pause()
        elif k is Cmd.HIDE: self.set_visible(self.window.hidden)
        elif k is Cmd.VISIBLE: self.set_visible(bool(c.args.get("on", True)))
        elif k in (Cmd.BIGGER, Cmd.SMALLER):
            size = max(MIN_SIZE, ses.s.size + (SIZE_STEP if k is Cmd.BIGGER else -SIZE_STEP))
            self.store.update(size=size); ses.restyle()
        elif k is Cmd.GOTO: ses.goto(int(c.args.get("surah", 1)), int(c.args.get("ayah", 1)))
        elif k is Cmd.NEXT_SURAH: ses.next_surah(1)
        elif k is Cmd.PREV_SURAH: ses.next_surah(-1)
        elif k is Cmd.PLAY: ses.replay()
        elif k is Cmd.RESTYLE: ses.restyle()
        elif k is Cmd.QUIT: QApplication.quit()

    def set_visible(self, on: bool) -> None:
        """Show or hide the verses; the recitation keeps going."""
        self.window.set_hidden(not on)
        if on: self.session.redraw()
        self.store.update(visible=on)

    def shutdown(self) -> None:
        self.session.stop()
        self.hotkeys.stop()
        self.server.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
