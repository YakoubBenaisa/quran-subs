"""Find where a recording is playing by listening: capture a few seconds of the speakers' output
(the PulseAudio/PipeWire monitor) and locate them in the recording's features.

Nothing is stored: the samples stay in a small ring buffer in memory and are only compared."""
import subprocess
import threading
import time

import numpy as np

from ..sync import features

SNIPPET = 8.0          # s of sound compared
MIN_CONFIDENCE = 0.3   # 1 - best / best elsewhere; same recording ≈ 0.5–1, unrelated sound < 0.15


class Locator:
    def __init__(self, track: np.ndarray, mean: np.ndarray, std: np.ndarray):
        """track: normalised features of the recording (features.FPS frames/s)."""
        self.T, self.mean, self.std = track.astype(np.float32), mean, std
        self._t2 = np.concatenate(([0.0], np.cumsum((self.T ** 2).sum(1))))

    def find(self, samples: np.ndarray, near: float | None = None, window: float = 20.0) -> tuple[float, float] | None:
        """(time in the recording where the snippet ends, confidence) or None."""
        S = features.normalize(features.mfcc_raw(samples), self.mean, self.std)
        k, n = len(S), len(self.T)
        if k < 20 or n <= k: return None
        lo, hi = 0, n - k
        if near is not None:
            c = int(near * features.FPS) - k
            lo, hi = max(0, c - int(window * features.FPS)), min(n - k, c + int(window * features.FPS))
            if hi <= lo: lo, hi = 0, n - k
        seg = self.T[lo:hi + k]
        L = 1 << int(np.ceil(np.log2(len(seg) + k)))
        corr = np.zeros(hi - lo + 1)
        for d in range(S.shape[1]):
            corr += np.fft.irfft(np.fft.rfft(seg[:, d], L) * np.conj(np.fft.rfft(S[:, d], L)), L)[:hi - lo + 1]
        t2 = self._t2[lo + k:hi + k + 1] - self._t2[lo:hi + 1]
        dist = (S ** 2).sum() + t2 - 2 * corr
        j = int(np.argmin(dist))
        # confidence: how much better the best place is than the best place elsewhere (±2 s away)
        away = dist.copy(); away[max(0, j - 2 * features.FPS):j + 2 * features.FPS + 1] = np.inf
        second = float(np.min(away)) if np.isfinite(away).any() else float(np.median(dist))
        conf = 1 - max(0.0, float(dist[j])) / second if second > 0 else 0.0
        if near is not None and conf < MIN_CONFIDENCE and (lo, hi) != (0, n - k):
            return self.find(samples, None)                 # not near the guess: search everywhere
        return ((lo + j + k) / features.FPS, conf)

    @classmethod
    def from_file(cls, path: str) -> "Locator":
        with np.load(path) as z:
            return cls(z["features"], z["mean"], z["std"])


class Capture:
    """Keeps the last few seconds of the speakers' output in memory."""
    CMD = ["parec", "-d", "@DEFAULT_MONITOR@", "--format=s16le", f"--rate={features.RATE}", "--channels=1",
           "--raw", "--latency-msec=100"]

    def __init__(self, seconds: float = SNIPPET + 2, cmd: list[str] | None = None):
        self.n = int(seconds * features.RATE)
        self.buf = np.zeros(self.n, np.int16); self.filled = 0
        self.t_last = 0.0
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(cmd or self.CMD, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        while True:
            b = self.proc.stdout.read(1600)                # 0.1 s
            if not b: break
            x = np.frombuffer(b[: len(b) // 2 * 2], np.int16)
            with self.lock:
                self.buf = np.roll(self.buf, -len(x)); self.buf[-len(x):] = x
                self.filled = min(self.n, self.filled + len(x)); self.t_last = time.monotonic()

    def last(self, seconds: float = SNIPPET) -> tuple[np.ndarray, float] | None:
        """(samples, monotonic time of the last sample) once enough sound was captured."""
        k = int(seconds * features.RATE)
        with self.lock:
            if self.filled < k: return None
            x = self.buf[-k:].copy(); t = self.t_last
        if np.abs(x).max() < 200: return None              # silence: nothing to match
        return x, t

    def close(self) -> None:
        if self.proc.poll() is None: self.proc.terminate()
