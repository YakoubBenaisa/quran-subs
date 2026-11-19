import socket
import threading
import time

from quran_companion.ipc.client import OverlayClient
from quran_companion.ipc.protocol import PROTOCOL_VERSION, Cmd, Command, decode, parse_cli
from quran_companion.ipc.server import CommandServer


def test_json_round_trip():
    c = Command(Cmd.GOTO, {"surah": 36, "ayah": 5})
    assert decode(c.encode()) == c


def test_text_form_round_trips():
    for c in (Command(Cmd.NEXT), Command(Cmd.GOTO, {"surah": 36, "ayah": 5}), Command(Cmd.VISIBLE, {"on": False})):
        assert decode(c.to_text().encode()) == c


def test_legacy_text_commands():
    assert decode(b"next") == Command(Cmd.NEXT)
    assert decode(b"surah 36 5") == Command(Cmd.GOTO, {"surah": 36, "ayah": 5})
    assert decode(b"surah 18") == Command(Cmd.GOTO, {"surah": 18, "ayah": 1})
    assert decode(b"visible 0") == Command(Cmd.VISIBLE, {"on": False})
    assert decode(b"") is None and decode(b"dance") is None and decode(b"{broken") is None
    assert parse_cli(["goto"]) is None   # needs arguments: use "surah N"


def test_server_and_client(tmp_path):
    path = str(tmp_path / "s.sock")
    got = []
    srv = CommandServer(path, got.append); srv.start()
    c = OverlayClient(path)
    try:
        assert c.running()
        h = c.hello()
        assert h["version"] == PROTOCOL_VERSION and h["pid"] > 0 and c.up_to_date()
        assert c.send(Cmd.NEXT) and c.send(Command(Cmd.VISIBLE, {"on": False})) and c.send_raw("prev")
        for _ in range(50):
            if len(got) == 3: break
            time.sleep(0.02)
        assert got == [Command(Cmd.NEXT), Command(Cmd.VISIBLE, {"on": False}), Command(Cmd.PREV)]  # hello not forwarded
    finally:
        srv.close()
    assert not c.running() and c.hello() is None


def test_old_overlay_that_never_answers_is_outdated(tmp_path):
    path = str(tmp_path / "old.sock")
    s = socket.socket(socket.AF_UNIX); s.bind(path); s.listen(4)

    def old_overlay():   # v4 behaviour: reads the command, closes, never replies
        try:
            while True:
                conn, _ = s.accept(); conn.recv(256); conn.close()
        except OSError:   # socket closed by the test
            pass
    threading.Thread(target=old_overlay, daemon=True).start()
    c = OverlayClient(path)
    assert c.running() and not c.up_to_date()
    s.close()
