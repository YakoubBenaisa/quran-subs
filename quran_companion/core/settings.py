"""User settings: one dataclass, one store that saves atomically and migrates old files.

The file stays at ~/.config/quran-overlay.json and keeps the same keys, so existing settings carry over.
"""
import json
import os
import threading
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

MODES = ("recite", "memorize", "manual")
ADVANCE = ("words", "fixed", "reciter")
HINTS = ("none", "reveal", "fade")
THEMES = ("system", "light", "dark")
UI_FONT = "IBM Plex Sans Arabic"

STYLE_KEYS = ("font", "size", "tr_font", "tr_scale", "color", "outline", "outline_w", "bg", "bg_color", "bg_alpha",
              "pos", "margin", "max_lines", "max_width", "tr_lines")


@dataclass(frozen=True)
class Settings:
    # what to play
    surah: int = 1
    ayah: int = 1
    range_from: int = 1
    range_to: int = 0          # 0 = to the end of the surah
    loop: bool = False
    reciter: int = 0           # 0 = default reciter
    trans: str = ""            # translation edition id, "" = none
    mode: str = "recite"
    speed: float = 1.0
    volume: int = 100
    autonext: bool = True
    word_sync: bool = True
    # memorize mode
    mem_advance: str = "words"
    mem_per_word: float = 0.8
    mem_min: float = 3.0
    mem_fixed: float = 10.0
    mem_gap: float = 2.0
    mem_repeat: int = 1
    mem_hint: str = "none"
    hint_words: int = 2
    hint_delay: float = 4.0
    # on-screen style
    font: str = "Amiri Quran"
    size: int = 40
    tr_font: str = "Sans"
    tr_scale: int = 45
    color: str = "#ffffff"
    outline: str = "#000000"
    outline_w: int = 4
    bg: bool = False
    bg_color: str = "#000000"
    bg_alpha: int = 55
    pos: str = "bottom"
    margin: int = 40
    max_lines: int = 3
    max_width: int = 80
    tr_lines: int = 2
    # settings window
    ui_lang: str = "auto"
    ui_font: str = UI_FONT
    theme: str = "system"
    # runtime state shared between processes
    visible: bool = True
    ov_pid: int = 0
    ov_version: int = 0

    def with_(self, **kw: Any) -> "Settings":
        return replace(self, **kw)

    def style(self) -> dict:
        return {k: getattr(self, k) for k in STYLE_KEYS}


_FIELDS = {f.name: f for f in fields(Settings)}


def migrate(raw: dict) -> dict:
    """Bring a settings dict from any older version up to date."""
    d = dict(raw)
    if not isinstance(d.get("reciter", 0), int): d["reciter"] = 0      # v1 stored "ar.alafasy"
    if "follow" in d:                                                    # v2 boolean
        if d.pop("follow"): d["mode"] = "manual"
    if d.get("mode") not in MODES: d["mode"] = "recite"
    if d.get("mem_advance") not in ADVANCE: d["mem_advance"] = "words"
    if d.get("mem_hint") not in HINTS: d["mem_hint"] = "none"
    if d.get("theme") not in THEMES: d["theme"] = "system"
    return d


def from_dict(raw: dict) -> Settings:
    d = migrate(raw)
    kw: dict[str, Any] = {}
    for k, v in d.items():
        f = _FIELDS.get(k)
        if f is None: continue
        try:
            kw[k] = f.type(v) if f.type in (int, float, str) and not isinstance(v, bool) else bool(v) if f.type is bool else v
        except (TypeError, ValueError):
            pass
    return Settings(**kw)


class SettingsStore:
    """Reads and writes the settings file. Writes are atomic and only touch the given keys,
    so the settings window and the overlay process never overwrite each other's changes."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def _read_raw(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def load(self) -> Settings:
        return from_dict(self._read_raw())

    def update(self, **kw: Any) -> Settings:
        unknown = set(kw) - set(_FIELDS)
        if unknown: raise KeyError(f"unknown settings: {sorted(unknown)}")
        with self._lock:
            raw = migrate(self._read_raw())
            raw.update(asdict(from_dict(raw)))
            raw.update(kw)
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            return from_dict(raw)
