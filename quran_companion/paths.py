"""File-system locations. Environment variables override them (used by tests).

Linux: ~/.config, ~/.cache, ~/.local/share (or the XDG_* folders, as inside a Flatpak).
Windows: %APPDATA%\\QuranCompanion and %LOCALAPPDATA%\\QuranCompanion\\Cache.
macOS: ~/Library/Application Support/QuranCompanion and ~/Library/Caches/QuranCompanion.
"""
import os
import sys
import tempfile

from .system import MACOS, WINDOWS

PKG = os.path.dirname(os.path.abspath(__file__))
RESOURCES = os.path.join(PKG, "resources")
LANG_DIR = os.path.join(RESOURCES, "lang")
FONTS_DIR = os.path.join(RESOURCES, "fonts")
ICONS_DIR = os.path.join(RESOURCES, "icons")
LOGO = os.path.join(ICONS_DIR, "logo.png")
APP = "QuranCompanion"


def _xdg(var: str, default: str) -> str:
    return os.environ.get(var) or os.path.expanduser(default)


def _config_dir() -> str:
    if WINDOWS: return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP)
    if MACOS: return os.path.expanduser(f"~/Library/Application Support/{APP}")
    return _xdg("XDG_CONFIG_HOME", "~/.config")


def _data_dir() -> str:
    """Folder that holds audio/ and mine/."""
    if WINDOWS or MACOS: return _config_dir()
    return os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), "quran-overlay")


def config_file() -> str:
    return os.environ.get("QOV_CFG") or os.path.join(_config_dir(), "settings.json" if WINDOWS or MACOS else "quran-overlay.json")


def socket_path() -> str:
    """Unix socket of the overlay process; on Windows a small file with its local port and key."""
    if os.environ.get("QOV_SOCK"): return os.environ["QOV_SOCK"]
    if WINDOWS: return os.path.join(_config_dir(), "overlay.port")
    run = os.environ.get("XDG_RUNTIME_DIR") or (tempfile.gettempdir() if sys.platform == "darwin" else "/tmp")
    return os.path.join(run, "quran-overlay.sock")


def cache_dir() -> str:
    if os.environ.get("QOV_CACHE"): return os.environ["QOV_CACHE"]
    if WINDOWS: return os.path.join(os.environ.get("LOCALAPPDATA") or _config_dir(), APP, "Cache")
    if MACOS: return os.path.expanduser(f"~/Library/Caches/{APP}")
    return os.path.join(_xdg("XDG_CACHE_HOME", "~/.cache"), "quran-overlay")


def library_dir() -> str:
    return os.environ.get("QOV_LIB") or os.path.join(_data_dir(), "audio")


def mine_dir() -> str:
    """The user's own synced recordings (links and files)."""
    return os.environ.get("QOV_MINE") or os.path.join(_data_dir(), "mine")
