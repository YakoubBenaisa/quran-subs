"""Media playing in other apps (browsers), through the MPRIS D-Bus interface. No Qt; uses jeepney.

Firefox reports title, link and play state but no position (always 0); Chrome reports the
position too. `BrowserPlayer` fills the gap by listening (see locator.py).
"""
from dataclasses import dataclass

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"


class MprisUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Media:
    bus: str               # D-Bus name, e.g. org.mpris.MediaPlayer2.firefox.instance_1_102
    app: str               # "Firefox", "Chromium", ...
    title: str
    url: str
    status: str            # "Playing" | "Paused" | "Stopped"
    position: float        # s (0 when the app does not report it)
    rate: float = 1.0
    trackid: str = ""

    @property
    def short_app(self) -> str:
        return self.bus[len(PREFIX):].split(".")[0].capitalize()


def _val(v):
    return v[1] if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str) else v


class Mpris:
    def __init__(self):
        try:
            from jeepney.io.blocking import open_dbus_connection
        except ImportError as e:
            raise MprisUnavailable("python3-jeepney is not installed") from e
        try:
            self.conn = open_dbus_connection(bus="SESSION")
        except Exception as e:  # noqa: BLE001 - no session bus
            raise MprisUnavailable(str(e)) from e

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _call(self, bus: str, path: str, iface: str, method: str, sig: str = "", body: tuple = ()):
        from jeepney import DBusAddress, new_method_call
        msg = new_method_call(DBusAddress(path, bus_name=bus, interface=iface), method, sig, body)
        reply = self.conn.send_and_get_reply(msg, timeout=2)
        if reply.header.message_type.name == "error":
            raise RuntimeError(f"{method}: {reply.body}")
        return reply.body

    def buses(self) -> list[str]:
        names = self._call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames")[0]
        return sorted(n for n in names if n.startswith(PREFIX) and not n.endswith("playerctld"))

    def media(self, bus: str) -> Media | None:
        try:
            props = self._call(bus, PATH, "org.freedesktop.DBus.Properties", "GetAll", "s", (PLAYER,))[0]
            try:
                ident = _val(self._call(bus, PATH, "org.freedesktop.DBus.Properties", "Get", "ss",
                                        ("org.mpris.MediaPlayer2", "Identity"))[0])
            except Exception:  # noqa: BLE001
                ident = ""
        except Exception:  # noqa: BLE001 - the app went away
            return None
        p = {k: _val(v) for k, v in props.items()}
        meta = {k: _val(v) for k, v in (p.get("Metadata") or {}).items()}
        title = meta.get("xesam:title") or ""
        artist = meta.get("xesam:artist") or []
        if isinstance(artist, list): artist = ", ".join(a for a in artist if a)
        return Media(bus, str(ident), str(title) + (f" — {artist}" if artist and artist not in title else ""),
                     str(meta.get("xesam:url") or ""), str(p.get("PlaybackStatus") or "Stopped"),
                     float(p.get("Position") or 0) / 1e6, float(p.get("Rate") or 1.0), str(meta.get("mpris:trackid") or ""))

    def all(self) -> list[Media]:
        return [m for m in (self.media(b) for b in self.buses()) if m]

    def play_pause(self, bus: str, play: bool) -> None:
        self._call(bus, PATH, PLAYER, "Play" if play else "Pause")

    def seek_to(self, m: Media, seconds: float) -> None:
        if m.trackid:
            self._call(m.bus, PATH, PLAYER, "SetPosition", "ox", (m.trackid, int(seconds * 1e6)))
