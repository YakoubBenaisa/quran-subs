"""Unix-socket command server run by the overlay process."""
import json
import os
import socket
import threading
from typing import Callable

from .protocol import PROTOCOL_VERSION, Cmd, Command, decode


class CommandServer:
    def __init__(self, path: str, on_command: Callable[[Command], None]):
        """`on_command` is called from the server thread; the caller marshals it to its UI thread."""
        self.path, self.on_command = path, on_command
        self._sock: socket.socket | None = None

    def start(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        self._sock = socket.socket(socket.AF_UNIX)
        self._sock.bind(self.path)
        self._sock.listen(8)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        assert self._sock is not None
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(1.0)
                try:
                    raw = conn.recv(4096)
                except OSError:
                    continue
                cmd = decode(raw)
                if cmd is None: continue
                if cmd.cmd is Cmd.HELLO:
                    try:
                        conn.sendall(json.dumps({"version": PROTOCOL_VERSION, "pid": os.getpid()}).encode())
                    except OSError:
                        pass
                    continue
                self.on_command(cmd)

    def close(self) -> None:
        if self._sock:
            self._sock.close(); self._sock = None
        try:
            os.unlink(self.path)
        except OSError:
            pass
