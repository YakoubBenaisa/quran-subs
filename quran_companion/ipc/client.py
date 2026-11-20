"""Talks to the overlay process: send commands, check it is running and up to date, (re)start it."""
import json
import os
import socket
import subprocess
import sys
import time

from .. import paths
from .protocol import PROTOCOL_VERSION, Cmd, Command


class OverlayClient:
    def __init__(self, path: str | None = None):
        self.path = path or paths.socket_path()

    def _connect(self, timeout: float = 1.0) -> socket.socket:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(timeout)
        s.connect(self.path)
        return s

    def send(self, cmd: Command | Cmd) -> bool:
        if isinstance(cmd, Cmd): cmd = Command(cmd)
        try:
            with self._connect() as s:
                s.sendall(cmd.encode())
            return True
        except OSError:
            return False

    def send_raw(self, text: str) -> bool:
        """Plain-text command understood by every overlay version (used to quit old ones)."""
        try:
            with self._connect() as s:
                s.sendall(text.encode())
            return True
        except OSError:
            return False

    def running(self) -> bool:
        try:
            with self._connect(0.5) as s:
                s.sendall(Command(Cmd.HELLO).encode())
            return True
        except OSError:
            return False

    def hello(self, timeout: float = 0.6) -> dict | None:
        """{"version", "pid"} of the running overlay; None if not running or too old to answer."""
        try:
            with self._connect(timeout) as s:
                s.sendall(Command(Cmd.HELLO).encode())
                s.shutdown(socket.SHUT_WR)
                data = s.recv(4096)
            return json.loads(data) if data else None
        except (OSError, ValueError):
            return None

    def up_to_date(self) -> bool:
        h = self.hello()
        return h is not None and h.get("version") == PROTOCOL_VERSION

    def spawn(self, hidden: bool = False) -> None:
        args = [sys.executable, "-m", "quran_companion", "overlay"] + (["--hidden"] if hidden else [])
        subprocess.Popen(args, start_new_session=True, cwd=os.path.dirname(paths.PKG),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def restart(self, hidden: bool = False) -> None:
        """Quit whatever overlay runs (any version) and start the current one; it resumes at the saved verse."""
        self.send_raw("quit")

        for _ in range(40):
            if not self.running(): break
            time.sleep(0.05)
        self.spawn(hidden)
