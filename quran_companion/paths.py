"""File-system locations. Environment variables override them (used by tests)."""
import os

PKG = os.path.dirname(os.path.abspath(__file__))
RESOURCES = os.path.join(PKG, "resources")
LANG_DIR = os.path.join(RESOURCES, "lang")
FONTS_DIR = os.path.join(RESOURCES, "fonts")
ICONS_DIR = os.path.join(RESOURCES, "icons")
LOGO = os.path.join(ICONS_DIR, "logo.png")


def config_file() -> str:
    return os.environ.get("QOV_CFG") or os.path.expanduser("~/.config/quran-overlay.json")


def socket_path() -> str:
    return os.environ.get("QOV_SOCK") or os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "quran-overlay.sock")


def cache_dir() -> str:
    return os.environ.get("QOV_CACHE") or os.path.expanduser("~/.cache/quran-overlay")


def library_dir() -> str:
    return os.environ.get("QOV_LIB") or os.path.expanduser("~/.local/share/quran-overlay/audio")


def mine_dir() -> str:
    """The user's own synced recordings (links and files)."""
    return os.environ.get("QOV_MINE") or os.path.expanduser("~/.local/share/quran-overlay/mine")
