"""Playback modes (Strategy). Each mode drives the session through the same small interface."""
from .base import Mode
from .manual import ManualMode
from .memorize import MemorizeMode
from .recite import ReciteMode

MODES = {"recite": ReciteMode, "memorize": MemorizeMode, "manual": ManualMode}


def make_mode(name: str, session) -> Mode:
    return MODES.get(name, ReciteMode)(session)


__all__ = ["Mode", "ReciteMode", "MemorizeMode", "ManualMode", "make_mode"]
