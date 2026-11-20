"""Following a browser video: position rules from the browser's reports and from listening."""
import numpy as np

from quran_companion.core.guess import same_video as _same_video
from quran_companion.playback.browser_player import BrowserPlayer
from quran_companion.playback.mpris import Media


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def media(status, pos, url="https://www.youtube.com/watch?v=abc123"):
    return Media("org.mpris.MediaPlayer2.firefox.instance_1", "Firefox", "Surah", url, status, pos)


def player():
    c = Clock()
    p = BrowserPlayer(clock=c)
    p._active = True
    p.url = "https://youtu.be/abc123"
    return p, c


def test_firefox_style_reports_only_on_changes():
    p, c = player()
    p._browser_update(media("Playing", 0.0))          # playing from before we looked: value not trusted
    assert p.position() is None
    p._browser_update(media("Paused", 175.0))         # paused: Firefox reports the real position
    assert p.position() == 175.0 and p.paused
    c.t += 30; assert p.position() == 175.0            # stays while paused
    p._browser_update(media("Playing", 175.0))         # resumed; same value reported
    c.t += 10; p._browser_update(media("Playing", 175.0))
    assert abs(p.position() - 185.0) < 1e-6            # counts on from the pause
    p._browser_update(media("Playing", 60.0))          # user moved the video: fresh value
    c.t += 2; assert abs(p.position() - 62.0) < 1e-6


def test_chrome_style_continuous_position():
    p, c = player()
    p._browser_update(media("Playing", 10.0))
    c.t += 0.25; p._browser_update(media("Playing", 10.25))
    assert abs(p.position() - 10.25) < 1e-6


class FakeCapture:
    def __init__(self, t): self.t = t
    def last(self): return np.zeros(10, np.int16), self.t


class FakeLocator:
    def __init__(self, pos, conf): self.r = (pos, conf)
    def find(self, samples, near=None): return self.r


def test_listening_rules():
    p, c = player()
    p._status = "Playing"
    p._listen(FakeCapture(c.t), FakeLocator(42.0, 0.25))      # weak and nothing to agree with: ignored
    assert p.position() is None
    p._listen(FakeCapture(c.t), FakeLocator(42.0, 0.8))       # strong: taken
    assert abs(p.position() - 42.0) < 1e-6
    c.t += 5
    p._listen(FakeCapture(c.t), FakeLocator(47.5, 0.25))      # weak but agrees with 47: taken
    assert abs(p.position() - 47.5) < 1e-6
    p._listen(FakeCapture(c.t), FakeLocator(300.0, 0.25))     # weak and far away: ignored
    assert abs(p.position() - 47.5) < 1e-6
    p._listen(FakeCapture(c.t), FakeLocator(10.0, 0.05))      # sounds like something else (an ad)
    assert p.lost and p.position() is None
    p._listen(FakeCapture(c.t), FakeLocator(48.0, 0.9))       # recitation is back
    assert not p.lost and abs(p.position() - 48.0) < 1e-6


def test_same_video_links():
    assert _same_video("https://www.youtube.com/watch?v=zdw5Ozkr_wM&t=30s", "https://youtu.be/zdw5Ozkr_wM")
    assert not _same_video("https://www.youtube.com/watch?v=zdw5Ozkr_wM", "https://www.youtube.com/watch?v=other12345")
