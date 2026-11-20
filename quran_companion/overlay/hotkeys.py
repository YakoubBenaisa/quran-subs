"""Global shortcuts inside the overlay process, for systems without desktop shortcut settings we
can write to: Windows (RegisterHotKey, Win+Alt+key) and macOS (pynput, Ctrl+Option+key; needs
the Accessibility permission). On Linux the desktop's own shortcuts call the command line instead
(setup-shortcuts), so nothing runs here."""
import threading
from typing import Callable

from .. import system
from ..ipc.protocol import Cmd, Command

# key -> command; "ui" opens the settings window
KEYS: dict[str, Cmd | str] = {
    "q": Cmd.QUIT, "right": Cmd.NEXT, "left": Cmd.PREV, "space": Cmd.PAUSE, "h": Cmd.HIDE,
    "up": Cmd.BIGGER, "down": Cmd.SMALLER, "page_down": Cmd.NEXT_SURAH, "page_up": Cmd.PREV_SURAH, "s": "ui",
}
_VK = {"q": 0x51, "right": 0x27, "left": 0x25, "space": 0x20, "h": 0x48, "up": 0x26, "down": 0x28,
       "page_down": 0x22, "page_up": 0x21, "s": 0x53}


class Hotkeys:
    def __init__(self, emit: Callable[[Command], None]):
        """emit(command) is called from a background thread (a Qt signal's emit is fine)."""
        self.emit = emit
        self._stop: Callable[[], None] = lambda: None
        self.failed: list[str] = []          # keys another program already uses

    def _fire(self, key: str) -> None:
        what = KEYS[key]
        if what == "ui": system.spawn_detached(system.self_command("ui"))
        else: self.emit(Command(Cmd(what)))

    def start(self) -> bool:
        try:
            if system.WINDOWS: self._start_windows(); return True
            if system.MACOS: return self._start_macos()
        except Exception:  # noqa: BLE001 - shortcuts are a convenience; the app works without them
            return False
        return False

    def stop(self) -> None:
        self._stop()

    # ------------------------------------------------------------ Windows
    def _start_windows(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32  # type: ignore[attr-defined]
        MOD_ALT, MOD_WIN, MOD_NOREPEAT, WM_HOTKEY, WM_QUIT = 0x1, 0x8, 0x4000, 0x0312, 0x0012
        keys = list(_VK)
        ready = threading.Event()
        tid = [0]

        def loop() -> None:
            tid[0] = kernel32.GetCurrentThreadId()
            for i, k in enumerate(keys, 1):
                if not user32.RegisterHotKey(None, i, MOD_WIN | MOD_ALT | MOD_NOREPEAT, _VK[k]): self.failed.append(k)
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and 1 <= msg.wParam <= len(keys): self._fire(keys[msg.wParam - 1])
            for i in range(1, len(keys) + 1): user32.UnregisterHotKey(None, i)

        threading.Thread(target=loop, daemon=True, name="hotkeys").start()
        ready.wait(2)
        self._stop = lambda: user32.PostThreadMessageW(tid[0], WM_QUIT, 0, 0)

    # ------------------------------------------------------------ macOS
    def _start_macos(self) -> bool:
        try:
            from pynput import keyboard
        except ImportError:
            return False
        names = {"right": "<right>", "left": "<left>", "space": "<space>", "up": "<up>", "down": "<down>",
                 "page_down": "<page_down>", "page_up": "<page_up>"}
        hk = keyboard.GlobalHotKeys({f"<ctrl>+<alt>+{names.get(k, k)}": (lambda k=k: self._fire(k)) for k in KEYS})
        hk.start()
        self._stop = hk.stop
        return True
