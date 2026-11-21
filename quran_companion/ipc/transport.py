"""The local connection between the settings window / shortcuts and the overlay process.

A Unix socket where there is one (Linux, macOS). On Windows: TCP on 127.0.0.1, with the port and
a random key written to the `path` file (readable by this user only); every message starts with
the key, so other programs and users cannot drive the overlay."""
import os
import secrets
import socket

from ..system import WINDOWS

_AF_UNIX: int = getattr(socket, "AF_UNIX", -1)     # missing on some Windows builds and in mypy's Windows view
UNIX = _AF_UNIX != -1 and not WINDOWS


class Listener:
    def __init__(self, path: str):
        self.path = path
        self.key = b""
        _remove(path)
        if UNIX:
            self.sock = socket.socket(_AF_UNIX)
            self.sock.bind(path)
        else:
            self.sock = socket.socket(socket.AF_INET)
            self.sock.bind(("127.0.0.1", 0))
            self.key = secrets.token_hex(16).encode()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(f"{self.sock.getsockname()[1]} {self.key.decode()}")
        self.sock.listen(8)

    def accept(self) -> socket.socket:
        conn, _ = self.sock.accept()
        return conn

    def unwrap(self, raw: bytes) -> bytes | None:
        """The message without the key; None if the key is wrong."""
        if not self.key: return raw
        head, _, rest = raw.partition(b"\n")
        return rest if secrets.compare_digest(head, self.key) else None

    def close(self) -> None:
        self.sock.close()
        _remove(self.path)


def connect(path: str, timeout: float) -> tuple[socket.socket, bytes]:
    """(connected socket, prefix to send before the message)."""
    if UNIX:
        s = socket.socket(_AF_UNIX)
        s.settimeout(timeout)
        try:
            s.connect(path)
        except OSError:
            s.close(); raise
        return s, b""
    try:
        with open(path, encoding="utf-8") as f:
            port, key = f.read().split()
    except (OSError, ValueError) as e:
        raise ConnectionRefusedError("overlay not running") from e
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=timeout)
    return s, key.encode() + b"\n"


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
