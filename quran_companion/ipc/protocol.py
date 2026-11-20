"""Commands between the settings window / shortcuts and the overlay process (Command pattern).

Wire format: one JSON object per connection, e.g. {"v": 5, "cmd": "goto", "surah": 36, "ayah": 5}.
Plain-text commands of older versions ("next", "surah 36 5", "visible 1") are still understood.
"hello" is answered with {"version": ..., "pid": ...} so callers can detect an outdated overlay.
"""
import enum
import json
from dataclasses import dataclass, field

PROTOCOL_VERSION = 6


class Cmd(str, enum.Enum):
    HELLO = "hello"
    NEXT = "next"
    PREV = "prev"
    PAUSE = "pause"
    HIDE = "hide"              # toggle visibility
    VISIBLE = "visible"        # args: on (bool)
    BIGGER = "bigger"
    SMALLER = "smaller"
    GOTO = "goto"              # args: surah, ayah
    NEXT_SURAH = "nextsurah"
    PREV_SURAH = "prevsurah"
    PLAY = "play"              # re-read settings and start
    RESTYLE = "restyle"        # re-read style settings and redraw
    QUIT = "quit"


@dataclass(frozen=True)
class Command:
    cmd: Cmd
    args: dict = field(default_factory=dict)

    def encode(self) -> bytes:
        return json.dumps({"v": PROTOCOL_VERSION, "cmd": self.cmd.value, **self.args}).encode()

    def to_text(self) -> str:
        """Plain-text form, understood by every overlay version (used by keyboard shortcuts)."""
        if self.cmd is Cmd.GOTO: return f"surah {self.args.get('surah', 1)} {self.args.get('ayah', 1)}"
        if self.cmd is Cmd.VISIBLE: return "visible " + ("1" if self.args.get("on", True) else "0")
        return self.cmd.value


def parse_cli(words: list[str]) -> Command | None:
    """Command-line / legacy text form: `next`, `surah 36 5`, `visible 0`."""
    if not words: return None
    k, rest = words[0].lower(), words[1:]
    if k == "surah" and rest and rest[0].isdigit():
        return Command(Cmd.GOTO, {"surah": int(rest[0]), "ayah": int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 1})
    if k == "visible" and rest:
        return Command(Cmd.VISIBLE, {"on": rest[0] in ("1", "on", "true", "yes")})
    try:
        c = Cmd(k)
    except ValueError:
        return None
    return Command(c) if c not in (Cmd.GOTO, Cmd.VISIBLE) else None


def decode(raw: bytes) -> Command | None:
    text = raw.decode(errors="ignore").strip()
    if not text: return None
    if text.startswith("{"):
        try:
            d = json.loads(text)
            c = Cmd(d.pop("cmd"))
            d.pop("v", None)
            return Command(c, d)
        except (ValueError, KeyError, TypeError):
            return None
    return parse_cli(text.split())
