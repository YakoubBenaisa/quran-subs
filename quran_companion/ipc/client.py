"""Talks to the overlay process: send commands, check it is running and up to date, (re)start it."""
import json
import os
import socket
import time

from .. import paths, system
from .protocol import PROTOCOL_VERSION, Cmd, Command
from .transport import connect


class OverlayClient:
    def __init__(self, path: str | None = None):
        self.path = path or paths.socket_path()

    def _send(self, data: bytes, timeout: float = 1.0) -> bool:
        try:
            s, prefix = connect(self.path, timeout)
            with s:
                s.sendall(prefix + data)
            return True
        except OSError:
            return False

    def send(self, cmd: Command | Cmd) -> bool:
        if isinstance(cmd, Cmd): cmd = Command(cmd)
        return self._send(cmd.encode())

    def send_raw(self, text: str) -> bool:
        """Plain-text command understood by every overlay version (used to quit old ones)."""
        return self._send(text.encode())

    def running(self) -> bool:
        return self._send(Command(Cmd.HELLO).encode(), 0.5)

    def hello(self, timeout: float = 0.6) -> dict | None:
        """{"version", "pid"} of the running overlay; None if not running or too old to answer."""
        try:
            s, prefix = connect(self.path, timeout)
            with s:
                s.sendall(prefix + Command(Cmd.HELLO).encode())
                s.shutdown(socket.SHUT_WR)
                data = s.recv(4096)
            return json.loads(data) if data else None
        except (OSError, ValueError):
            return None

    def up_to_date(self) -> bool:
        h = self.hello()
        return h is not None and h.get("version") == PROTOCOL_VERSION

    def spawn(self, hidden: bool = False) -> None:
        system.spawn_detached(system.self_command("overlay", *(["--hidden"] if hidden else [])),
                              cwd=None if system.FROZEN else os.path.dirname(paths.PKG))

    def restart(self, hidden: bool = False) -> None:
        """Quit whatever overlay runs (any version) and start the current one; it resumes at the saved verse."""
        self.send_raw("quit")

        for _ in range(40):
            if not self.running(): break
            time.sleep(0.05)
        self.spawn(hidden)
