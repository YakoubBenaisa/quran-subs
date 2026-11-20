"""Pauses in a recitation: stretches quieter than a level between the noise floor and the
speech level. Verse starts are nudged onto them."""
from dataclasses import dataclass

import numpy as np

HOP = 0.05             # s per envelope frame
MIN_PAUSE = 0.2        # s, shortest silence that can separate two verses


@dataclass(frozen=True)
class Pause:
    t: float           # where a verse would start (a little after the silence began)
    length: float      # s
    depth: float       # 0..1, how far below the threshold

    @property
    def strength(self) -> float:
        return min(1.0, self.length) * 0.5 + self.depth


@dataclass(frozen=True)
class Alignment:
    starts: list[float]        # start time (s) of every segment
    end: float                 # end of the recitation (s)
    strength: list[float]      # pause strength at each start (0 = no real pause there)


def _smooth(db: np.ndarray) -> np.ndarray:
    return np.convolve(db, np.ones(3) / 3, "same") if len(db) >= 3 else db


def levels(db: np.ndarray) -> tuple[float, float]:
    s = _smooth(db)
    return float(np.percentile(s, 5)), float(np.percentile(s, 60))


def find_pauses(db: np.ndarray) -> list[Pause]:
    s = _smooth(db)
    lo, hi = levels(db)
    span = hi - lo + 1e-6
    found: list[Pause] = []
    for frac in (0.30, 0.45):
        q = s < lo + frac * span
        # run-length encode the quiet frames
        edges = np.flatnonzero(np.diff(np.concatenate(([0], q.view(np.int8), [0]))))
        for i, j in zip(edges[::2], edges[1::2], strict=True):
            d = (j - i) * HOP
            if d >= MIN_PAUSE:
                found.append(Pause(i * HOP + min(0.1, d / 2), d, float((lo + frac * span - s[i:j].min()) / span)))
    found.sort(key=lambda p: p.t)
    merged: list[Pause] = []
    for p in found:     # the same silence found at both levels
        if merged and p.t - merged[-1].t < 0.25:
            if p.length > merged[-1].length: merged[-1] = p
        else:
            merged.append(p)
    return merged


def speech_span(db: np.ndarray) -> tuple[float, float]:
    s = _smooth(db)
    lo, hi = levels(db)
    loud = np.flatnonzero(s > lo + 0.45 * (hi - lo))
    if len(loud) == 0: return 0.0, len(db) * HOP
    return float(loud[0] * HOP), float((loud[-1] + 1) * HOP)


def envelope_from_samples(x: np.ndarray, rate: int = 8000) -> np.ndarray:
    """Loudness in dB, one value per HOP seconds."""
    h = int(rate * HOP); n = len(x) // h
    if n == 0: return np.zeros(0, np.float32)
    frames = x[:n * h].astype(np.float32).reshape(n, h)
    return (20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1)).astype(np.float32)
