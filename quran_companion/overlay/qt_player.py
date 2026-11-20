"""Audio through Qt Multimedia (FFmpeg inside Qt): works on Windows, macOS and Linux with nothing
else installed. Same interface as playback.player.FfplayPlayer; call it from the Qt thread."""
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class QtPlayer:
    def __init__(self):
        self._out = QAudioOutput()
        self._p = QMediaPlayer()
        self._p.setAudioOutput(self._out)
        if hasattr(self._p, "setPitchCompensation"): self._p.setPitchCompensation(True)   # Qt 6.10+: speed without chipmunk voice
        self._p.mediaStatusChanged.connect(self._status)
        self._p.errorOccurred.connect(lambda *_: self._finish())
        self._seek: float | None = None
        self._active = self._ended = self._paused = False

    def play(self, src: str, start: float, speed: float = 1.0, volume: int = 100) -> None:
        self.stop()
        self._seek = start if start > 0 else None
        self._out.setVolume(max(0.0, min(1.0, volume / 100)))
        self._p.setPlaybackRate(float(speed))
        url = QUrl(src) if "://" in src else QUrl.fromLocalFile(src)
        self._p.setSource(url)
        self._active, self._ended, self._paused = True, False, False
        self._p.play()

    def _status(self, st) -> None:
        if st in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia) and self._seek is not None:
            self._p.setPosition(int(self._seek * 1000)); self._seek = None
        elif st == QMediaPlayer.EndOfMedia: self._finish()
        elif st == QMediaPlayer.InvalidMedia: self._finish()

    def _finish(self) -> None:
        if self._active: self._ended = True

    def stop(self) -> None:
        self._active = self._ended = self._paused = False
        self._p.stop()
        self._p.setSource(QUrl())

    def set_paused(self, paused: bool) -> None:
        if not self._active or paused == self._paused: return
        self._paused = paused
        if paused: self._p.pause()
        else: self._p.play()

    @property
    def paused(self) -> bool:
        return self._paused

    def active(self) -> bool:
        return self._active and not self._ended

    def position(self) -> float | None:
        if not self._active: return None
        if self._seek is not None: return self._seek                 # not loaded yet
        return self._p.position() / 1000

    def take_ended(self) -> bool:
        if self._ended and self._active:
            self._active = False
            return True
        return False
