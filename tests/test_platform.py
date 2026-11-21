"""Cross-platform pieces: the Windows command transport, paths, shortcut labels, the Qt player."""
import importlib
import os
import socket
import struct
import time
import wave

import pytest

from quran_companion.ipc import transport
from quran_companion.ipc.protocol import Cmd, Command


def test_tcp_transport_with_key(tmp_path, monkeypatch):
    """The Windows transport: port + key in a file; messages without the key are ignored."""
    monkeypatch.setattr(transport, "UNIX", False)
    from quran_companion.ipc.client import OverlayClient
    from quran_companion.ipc.server import CommandServer
    got = []
    path = str(tmp_path / "overlay.port")
    srv = CommandServer(path, got.append); srv.start()
    try:
        port, key = open(path).read().split()
        assert len(key) == 32
        c = OverlayClient(path)
        assert c.hello()["version"] and c.running()
        assert c.send(Command(Cmd.GOTO, {"surah": 36, "ayah": 5}))
        with socket.create_connection(("127.0.0.1", int(port))) as s:       # another program, without the key
            s.sendall(b"quit")
        for _ in range(50):
            if got: break
            time.sleep(0.02)
        time.sleep(0.1)
        assert [g.cmd for g in got] == [Cmd.GOTO] and got[0].args == {"surah": 36, "ayah": 5}
    finally:
        srv.close()
    assert not os.path.exists(path) and not OverlayClient(path).running()


@pytest.mark.parametrize("plat,expect", [
    ("win32", ("QuranCompanion", "settings.json", "overlay.port")),
    ("darwin", ("Library/Application Support/QuranCompanion", "settings.json", "quran-overlay.sock")),
    ("linux", (".config", "quran-overlay.json", "quran-overlay.sock")),
])
def test_paths_per_system(monkeypatch, tmp_path, plat, expect):
    import quran_companion.paths as P
    import quran_companion.system as S
    for v in ("QOV_CFG", "QOV_SOCK", "QOV_CACHE", "QOV_LIB", "QOV_MINE", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr("sys.platform", plat)
    try:
        importlib.reload(S); importlib.reload(P)
        folder, cfg, sock = expect
        assert folder in P.config_file().replace("\\", "/") and P.config_file().endswith(cfg)
        assert P.socket_path().endswith(sock)
        assert P.mine_dir() != P.library_dir() and P.cache_dir()
        if plat == "linux":
            linux_cfg = os.path.expanduser("~/.config/quran-overlay.json")                      # unchanged for Linux users
            assert os.path.normpath(P.config_file()) == os.path.normpath(linux_cfg)
            assert os.path.normpath(P.mine_dir()) == os.path.normpath(os.path.expanduser("~/.local/share/quran-overlay/mine"))
    finally:
        monkeypatch.undo()
        importlib.reload(S); importlib.reload(P)


def test_shortcut_label_follows_the_system(monkeypatch):
    from quran_companion.core import i18n
    t = i18n.Translator()
    t.set("en")
    monkeypatch.setattr(i18n, "MOD_LABEL", "Super+Alt")
    assert "Super+Alt" in t.t("fix_hint")
    monkeypatch.setattr(i18n, "MOD_LABEL", "Win+Alt")
    assert "Win+Alt+→" in t.t("fix_hint") and "Super" not in t.t("fix_hint")


def test_hotkeys_map_every_shortcut():
    from quran_companion.app import SHORTCUTS
    from quran_companion.overlay.hotkeys import _VK, KEYS
    assert set(KEYS) == set(_VK)
    sent = []
    from quran_companion.overlay.hotkeys import Hotkeys
    h = Hotkeys(sent.append)
    h._fire("right"); h._fire("page_up")
    assert [c.cmd for c in sent] == [Cmd.NEXT, Cmd.PREV_SURAH]
    assert len(SHORTCUTS) == len(KEYS)                       # GNOME gets the same set


def _tone(path, seconds=1.5, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        import math
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(int(seconds * rate))))


def test_qt_player_plays_seeks_and_ends(qtbot, tmp_path):
    pytest.importorskip("PySide6.QtMultimedia")
    from PySide6.QtMultimedia import QMediaDevices
    if not QMediaDevices.audioOutputs(): pytest.skip("no audio output on this machine")
    from quran_companion.overlay.qt_player import QtPlayer
    f = tmp_path / "tone.wav"; _tone(f)
    p = QtPlayer()
    p.play(str(f), 0.5, 1.0, 0)
    assert p.active() and p.position() == 0.5
    qtbot.waitUntil(lambda: (p.position() or 0) > 0.6, timeout=5000)
    p.set_paused(True); assert p.paused
    p.set_paused(False)
    qtbot.waitUntil(p.take_ended, timeout=8000)
    assert not p.active()


def test_duration_from_ffmpeg_without_ffprobe(tmp_path, monkeypatch):
    from quran_companion import system
    if not system.tool("ffmpeg"): pytest.skip("no ffmpeg")
    from quran_companion.data import media
    real = system.tool
    monkeypatch.setattr(system, "tool", lambda n: None if n == "ffprobe" else real(n))
    f = tmp_path / "tone.wav"; _tone(f, 2.0)
    title, dur = media._probe_title(str(f))
    assert abs(dur - 2.0) < 0.05
