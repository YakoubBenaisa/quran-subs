"""What differs between Windows, macOS and Linux, in one place. No Qt.

* how to start this app again (from source: `python -m quran_companion`; packaged: the app itself)
* external tools (ffmpeg) from the system, from the package, or from the imageio-ffmpeg wheel
* the name of the shortcut keys in texts ("Super+Alt" on Linux)
"""
import os
import shutil
import subprocess
import sys

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = not (WINDOWS or MACOS)
FLATPAK = os.path.exists("/.flatpak-info")
FROZEN = bool(getattr(sys, "frozen", False))          # a packaged build (PyInstaller)

# the modifier keys of the global shortcuts, as written in texts
MOD_LABEL = "Win+Alt" if WINDOWS else "Ctrl+Option" if MACOS else "Super+Alt"

# browser video following needs MPRIS (D-Bus) and the PulseAudio/PipeWire monitor
BROWSER_FOLLOW = LINUX


def self_command(*args: str) -> list[str]:
    """Command line that runs this app with `args` (e.g. "overlay", "ui")."""
    if FROZEN: return [sys.executable, *args]
    return [sys.executable, "-m", "quran_companion", *args]


def spawn_detached(args: list[str], cwd: str | None = None) -> None:
    """Start a process that outlives this one and has no console window."""
    kw: dict = dict(cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if WINDOWS:
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED, NEW_PROCESS_GROUP, NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)


def no_window() -> dict:
    """subprocess keyword arguments that keep a console window from flashing up on Windows."""
    return {"creationflags": 0x08000000} if WINDOWS else {}


def _bundled(name: str) -> str | None:
    """A tool shipped next to the packaged app (bin/ffmpeg[.exe])."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    exe = name + (".exe" if WINDOWS else "")
    for d in (os.path.join(base, "bin"), base):
        p = os.path.join(d, exe)
        if os.path.isfile(p): return p
    return None


def tool(name: str) -> str | None:
    """Path of an external program (ffmpeg, ffplay), or None if it is nowhere to be found."""
    found = shutil.which(name) or (_bundled(name) if FROZEN else None)
    if found: return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return str(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:  # noqa: BLE001 - not installed or no binary for this platform
            return None
    return None


def open_folder(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    if WINDOWS: os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    else: subprocess.Popen(["open" if MACOS else "xdg-open", path])
