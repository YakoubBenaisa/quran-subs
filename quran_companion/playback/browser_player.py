"""Follow a video playing in the browser instead of playing the audio ourselves.

Position = last known point + time since then (while playing). Known points come from:
* the browser (MPRIS): Chrome reports its position continuously; Firefox only when the video is
  played, paused or moved, so a change in the reported value is a fresh point;
* listening (locator.py): a few seconds of the speakers' output found in the recording, at the
  start and every LISTEN_EVERY seconds, to catch seeks Firefox does not report.
Pause / resume from the app pause the video in the browser.
"""
import threading
import time
from typing import Callable

from ..core.guess import same_video as _same_video
from .locator import Capture, Locator
from .mpris import Media, Mpris

POLL = 0.25            # s between browser polls
LISTEN_EVERY = 15.0    # s between position checks by listening
STRONG = 0.5           # confidence accepted on its own
AGREE = 1.5            # s, a weaker match must agree with the expected position this well


class BrowserPlayer:
    def __init__(self, mpris_factory: Callable[[], Mpris] = Mpris, capture_factory: Callable[[], Capture] | None = Capture,
                 locator_factory: Callable[[str], Locator] = Locator.from_file, clock=time.monotonic):
        self.mpris_factory, self.capture_factory, self.locator_factory, self.clock = mpris_factory, capture_factory, locator_factory, clock
        self.bus = ""                 # which browser player to follow ("" = the one playing)
        self.url = ""                 # the video the recording was made from
        self._run = 0
        self._anchor: tuple[float, float] | None = None    # (position s, clock time)
        self._status = "Stopped"
        self._rate = 1.0
        self._last_reported: float | None = None
        self._next_listen = 0.0
        self._ended = False
        self._active = False
        self._other_video = False     # the browser shows another video
        self._no_match = False        # the sound does not match the recording (an ad, talk, …)
        self.media: Media | None = None

    # ------------------------------------------------------------ AudioPlayer interface
    def follow(self, bus: str, url: str) -> None:
        self.bus, self.url = bus, url

    def play(self, src: str, start: float, speed: float = 1.0, volume: int = 100) -> None:
        """src = features file of the recording (its .npz); start is ignored: the video decides."""
        self.stop()
        self._run += 1
        self._active, self._ended, self._anchor, self._last_reported = True, False, None, None
        self._other_video = self._no_match = False
        threading.Thread(target=self._loop, args=(self._run, src), daemon=True).start()

    def stop(self) -> None:
        self._run += 1
        self._active = False

    def set_paused(self, paused: bool) -> None:
        m = self.media
        if not m: return
        try:
            mp = self.mpris_factory(); mp.play_pause(m.bus, not paused); mp.close()
        except Exception:  # noqa: BLE001 - browser gone; the next poll notices
            pass

    @property
    def paused(self) -> bool:
        return self._status == "Paused"

    def active(self) -> bool:
        return self._active and not self._ended

    def position(self) -> float | None:
        a = self._anchor
        if a is None or self.lost: return None
        pos, t = a
        return pos + ((self.clock() - t) * self._rate if self._status == "Playing" else 0.0)

    @property
    def lost(self) -> bool:
        """Playing, but not the recording (another video, an ad): the text waits."""
        return self._other_video or self._no_match

    def take_ended(self) -> bool:
        if self._ended and self._active:
            self._active = False
            return True
        return False

    # ------------------------------------------------------------ following
    def _pick(self, mp: Mpris) -> Media | None:
        players = mp.all()
        if self.bus:
            players = [m for m in players if m.bus == self.bus] or [m for m in players if m.bus.startswith(self.bus)]
        same = [m for m in players if self.url and _same_video(m.url, self.url)]
        playing = [m for m in (same or players) if m.status == "Playing"]
        pick = playing or same or players
        return pick[0] if pick else None

    def _set(self, pos: float) -> None:
        self._anchor = (max(0.0, pos), self.clock())

    def _loop(self, run: int, features_path: str) -> None:
        try:
            mp = self.mpris_factory()
        except Exception:  # noqa: BLE001
            self._ended = True; return
        loc = cap = None
        try:
            loc = self.locator_factory(features_path)
            cap = self.capture_factory() if self.capture_factory else None
        except Exception:  # noqa: BLE001 - listening is optional; the browser's own position still works
            cap = None
        self._next_listen = self.clock() + 3.0
        gone = 0
        try:
            while run == self._run:
                m = self._pick(mp)
                if m is None or (self.url and m.url and not _same_video(m.url, self.url)):
                    gone += 1
                    if gone * POLL > 3: self._other_video = True
                    if m is None and gone * POLL > 10: self._ended = True; return
                else:
                    gone = 0; self._other_video = False
                    self.media, self._rate = m, m.rate or 1.0
                    self._browser_update(m)
                    if m.status == "Stopped": self._ended = True; return
                if cap and loc and self._status == "Playing" and self.clock() >= self._next_listen:
                    self._next_listen = self.clock() + LISTEN_EVERY
                    self._listen(cap, loc)
                time.sleep(POLL)
        finally:
            if cap: cap.close()
            mp.close()

    def _browser_update(self, m: Media) -> None:
        """Rules for the browser's own report (Firefox: only fresh right after play/pause/seek)."""
        rep, was = m.position, self._last_reported
        if m.status != self._status and self._anchor is not None:
            self._set(self.position() or 0.0)        # keep the estimate across play <-> pause
            self._next_listen = self.clock() + 2.5    # check by listening soon after a change
        if was is None:
            if m.status != "Playing" and rep > 0: self._set(rep)     # paused: the value is current
        elif rep != was:
            self._set(rep)                            # the browser just reported: fresh point
        self._last_reported = rep
        self._status = m.status

    def _listen(self, cap: Capture, loc: Locator) -> None:
        got = cap.last()
        if got is None: return
        samples, t_cap = got
        expected = None
        if self._anchor:
            p, t = self._anchor
            expected = p + (t_cap - t) * self._rate
        r = loc.find(samples, expected)
        if r is None: return
        pos, conf = r
        agrees = expected is not None and abs(pos - expected) <= AGREE
        if conf >= STRONG or (conf >= 0.2 and agrees):
            self._no_match = False
            self._anchor = (pos + (self.clock() - t_cap) * self._rate, self.clock())
        elif conf < 0.15:
            self._no_match = True                            # playing something else (an ad?)

