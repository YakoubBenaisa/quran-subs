"""Audio playback behind a small interface. FfplayPlayer plays one whole surah with ffplay and
reads ffplay's own clock (position in the file, independent of the speed) to drive the text."""
import io
import re
import signal
import subprocess
import sys
import threading
from typing import Callable, Protocol


class AudioPlayer(Protocol):
    def play(self, src: str, start: float, speed: float, volume: int) -> None: ...
    def stop(self) -> None: ...
    def set_paused(self, paused: bool) -> None: ...
    @property
    def paused(self) -> bool: ...
    def active(self) -> bool: ...
    def position(self) -> float | None: ...
    def take_ended(self) -> bool:
        """True once after playback stopped by itself (end of file or error)."""
        ...


_CLOCK = re.compile(rb"\s*(\d+\.\d+)")


class FfplayPlayer:
    def __init__(self, binary: str = "ffplay"):
        self.binary = binary
        self._proc: subprocess.Popen | None = None
        self._gen = 0
        self._pos: float | None = None
        self._ended = False
        self._paused = False

    def play(self, src: str, start: float, speed: float = 1.0, volume: int = 100) -> None:
        self.stop()
        self._gen += 1
        g = self._gen
        cmd = [self.binary, "-nodisp", "-autoexit", "-loglevel", "error", "-stats", "-volume", str(int(volume))]
        if start > 0: cmd += ["-ss", f"{start:.2f}"]
        if abs(float(speed) - 1) > 0.01: cmd += ["-af", f"atempo={float(speed):.2f}"]
        cmd.append(src)
        self._pos, self._ended, self._paused = start, False, False
        p = self._proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        threading.Thread(target=self._read, args=(p, g), daemon=True).start()

    def _read(self, p: subprocess.Popen, g: int) -> None:
        buf = b""
        stream = p.stderr
        assert isinstance(stream, io.BufferedReader)
        while True:
            b = stream.read1(512)
            if not b: break
            parts = re.split(rb"[\r\n]", buf + b)
            buf = parts.pop()
            for ln in parts:
                m = _CLOCK.match(ln)
                if m and g == self._gen: self._pos = float(m.group(1))
        p.wait()
        if g == self._gen: self._ended = True

    def stop(self) -> None:
        self._gen += 1
        if self._proc and self._proc.poll() is None:
            if self._paused and sys.platform != "win32": self._proc.send_signal(signal.SIGCONT)
            self._proc.terminate()
        self._proc, self._paused, self._ended = None, False, False

    def set_paused(self, paused: bool) -> None:
        if sys.platform != "win32" and self._proc and self._proc.poll() is None and paused != self._paused:
            self._proc.send_signal(signal.SIGSTOP if paused else signal.SIGCONT)
            self._paused = paused

    @property
    def paused(self) -> bool:
        return self._paused

    def active(self) -> bool:
        return self._proc is not None and not self._ended

    def position(self) -> float | None:
        return self._pos

    def take_ended(self) -> bool:
        if self._ended and self._proc is not None:
            self._proc = None
            return True
        return False


class FakePlayer:
    """Test double: position is set by the test."""
    def __init__(self):
        self.calls: list[tuple] = []
        self.pos: float | None = None
        self._active = False
        self._paused = False
        self.ended = False

    def play(self, src, start, speed=1.0, volume=100):
        self.calls.append(("play", src, start, speed, volume)); self.pos = start; self._active = True; self.ended = False

    def stop(self):
        self.calls.append(("stop",)); self._active = False; self._paused = False

    def set_paused(self, paused):
        self._paused = paused

    @property
    def paused(self):
        return self._paused

    def active(self):
        return self._active

    def position(self):
        return self.pos

    def take_ended(self):
        if self.ended and self._active:
            self._active = False; self.ended = False
            return True
        return False


class RoutingPlayer:
    """Plays the audio itself (ffplay) or follows a browser video, as the settings say at play()."""
    def __init__(self, own: AudioPlayer, browser, settings, features_for: Callable[[str], str]):
        """settings() -> Settings; features_for(audio path) -> features file of that recording."""
        self.own, self.browser, self.settings, self.features_for = own, browser, settings, features_for
        self.cur: AudioPlayer = own

    def play(self, src: str, start: float, speed: float = 1.0, volume: int = 100) -> None:
        self.cur.stop()
        s = self.settings()
        if s.follow_player and self.browser is not None:
            self.browser.follow(s.follow_player, s.follow_url)
            self.cur = self.browser
            self.cur.play(self.features_for(src), start, speed, volume)
        else:
            self.cur = self.own
            self.cur.play(src, start, speed, volume)

    def stop(self) -> None: self.cur.stop()
    def set_paused(self, paused: bool) -> None: self.cur.set_paused(paused)

    @property
    def paused(self) -> bool: return self.cur.paused

    def active(self) -> bool: return self.cur.active()
    def position(self) -> float | None: return self.cur.position()
    def take_ended(self) -> bool: return self.cur.take_ended()
