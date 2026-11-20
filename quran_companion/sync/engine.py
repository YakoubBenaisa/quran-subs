"""Verse timings for a recitation without timings, by matching it against reciters with timings.

For every reference reciter: match the recording to the reference's audio (DTW over MFCC
features) and carry the reference's known verse starts across. The middle value over the
references is used, then nudged onto a nearby pause. Corrections from the user ("verse k starts
at t") are anchors: the recording and the references are cut there and matched piece by piece.
"""
from dataclasses import dataclass, field

import numpy as np

from ..core.models import VerseTiming
from . import dtw
from .features import FPS
from .pauses import Pause, find_pauses

SNAP_WINDOW = 0.8      # s, how far a verse start may move to sit on a pause
AGREE = 1.5            # s, references agreeing within this make a verse "confident"


@dataclass(frozen=True)
class Reference:
    """A reciter with real timings: features of the whole surah + its verse timings."""
    features: np.ndarray
    timings: list[VerseTiming]


@dataclass(frozen=True)
class Target:
    features: np.ndarray
    envelope: np.ndarray                # loudness, for pauses (pauses.HOP per frame)


@dataclass
class SyncResult:
    timings: list[VerseTiming]
    confident: float                    # share of verses on which the references agree
    start: float                        # s, where the recitation starts in the recording
    end: float
    anchors: dict[int, float] = field(default_factory=dict)


def _ref_span(ref: Reference, ayahs: list[int]) -> dict[int, float]:
    """Start (s) of each wanted verse in the reference, plus the end of the last one under key -1."""
    t = {x.ayah: x for x in ref.timings}
    out = {a: t[a].start_ms / 1000 for a in ayahs if a in t}
    if ayahs and ayahs[-1] in t: out[-1] = t[ayahs[-1]].end_ms / 1000
    return out


def _map_piece(target: np.ndarray, ref: np.ndarray, t0: float, t1: float, r0: float, r1: float,
               ref_times: list[float], open_start: bool, open_end: bool) -> tuple[list[float], float, float]:
    """Map reference times inside [r0, r1] to the recording inside [t0, t1]."""
    a0, a1 = int(t0 * FPS), max(int(t0 * FPS) + 1, int(t1 * FPS))
    b0, b1 = int(r0 * FPS), max(int(r0 * FPS) + 1, int(r1 * FPS))
    A, B = target[a0:a1], ref[b0:b1]
    if len(A) < 2 or len(B) < 2:
        span = (t1 - t0) / max(1e-6, r1 - r0)
        return [t0 + (x - r0) * span for x in ref_times], t0, t1
    path = dtw.align(A, B, open_a=open_start or open_end)
    mapped = [a0 / FPS + x for x in dtw.map_times(path, [x - b0 / FPS for x in ref_times])]
    return mapped, a0 / FPS + path[0, 0] / FPS, a0 / FPS + (path[-1, 0] + 1) / FPS


def _snap(t: float, pauses: list[Pause], lo: float, hi: float) -> float:
    near = [p for p in pauses if abs(p.t - t) <= SNAP_WINDOW and lo < p.t < hi]
    return max(near, key=lambda p: p.strength - abs(p.t - t) * 0.5).t if near else t


LOW_CONFIDENCE = 0.5


def sync(target: Target, refs: list[Reference], ayahs: list[int], anchors: dict[int, float] | None = None,
         progress=lambda f: None, cancel=lambda: False) -> SyncResult:
    """ayahs: the verses the recording contains, in order (0 = intro first, if it has one).
    First lets the recitation start and end anywhere (talk before/after it); if the references
    then disagree a lot, matches the whole recording end to end instead and keeps the better."""
    res = _sync(target, refs, ayahs, anchors, True, lambda f: progress(f * 0.7), cancel)
    if res.confident >= LOW_CONFIDENCE: progress(1.0); return res
    alt = _sync(target, refs, ayahs, anchors, False, lambda f: progress(0.7 + f * 0.3), cancel)
    return alt if alt.confident > res.confident else res


def _sync(target: Target, refs: list[Reference], ayahs: list[int], anchors: dict[int, float] | None,
          open_ends: bool, progress, cancel) -> SyncResult:
    anchors = {a: t for a, t in (anchors or {}).items() if a in ayahs}
    dur = len(target.features) / FPS
    per_ref: list[dict[int, float]] = []
    starts_found, ends_found = [], []
    for ri, ref in enumerate(refs):
        if cancel(): raise InterruptedError("cancelled")
        span = _ref_span(ref, ayahs)
        if len(span) < 2: continue
        # cut points: (target time, reference time); open ends unless an anchor fixes them
        cuts: list[tuple[float | None, float]] = [(None, span.get(ayahs[0], 0.0))]
        cuts += [(anchors[a], span[a]) for a in ayahs if a in anchors and a in span and a != ayahs[0]]
        if ayahs[0] in anchors: cuts[0] = (anchors[ayahs[0]], span.get(ayahs[0], 0.0))
        cuts.append((None, span[-1]))
        got: dict[int, float] = {}
        for k in range(len(cuts) - 1):
            (ta, ra), (tb, rb) = cuts[k], cuts[k + 1]
            inside = [a for a in ayahs if a in span and ra <= span[a] < rb]
            t0 = ta if ta is not None else 0.0
            t1 = tb if tb is not None else dur
            mapped, s, e = _map_piece(target.features, ref.features, t0, t1, ra, rb, [span[a] for a in inside],
                                      open_ends and ta is None, open_ends and tb is None)
            got.update(zip(inside, mapped, strict=True))
            if k == 0: starts_found.append(s if ta is None else ta)
            if k == len(cuts) - 2: ends_found.append(e if tb is None else tb)
        per_ref.append(got)
        progress((ri + 1) / len(refs))
    if not per_ref: raise ValueError("no reference recitation has timings for these verses")
    start = float(np.median(starts_found)); end = float(np.median(ends_found))
    pauses = find_pauses(target.envelope)
    out: dict[int, float] = {}
    agree = 0
    for a in ayahs:
        vals = [g[a] for g in per_ref if a in g]
        if a in anchors: out[a] = anchors[a]; agree += 1; continue
        if not vals: continue
        if max(vals) - min(vals) <= AGREE: agree += 1
        out[a] = float(np.median(vals))
    keys = [a for a in ayahs if a in out]
    # nudge onto pauses (not anchors), keep the order strictly increasing
    times: list[float] = []
    for i, a in enumerate(keys):
        t = out[a]
        if a not in anchors:
            lo = times[-1] + 0.3 if times else 0.0
            hi = out[keys[i + 1]] - 0.3 if i + 1 < len(keys) else end
            t = _snap(t, pauses, lo, hi)
        if times: t = max(t, times[-1] + 0.3)
        times.append(t)
    tl = [VerseTiming(a, int(t * 1000), int((times[i + 1] if i + 1 < len(times) else max(end, t + 1)) * 1000))
          for i, (a, t) in enumerate(zip(keys, times, strict=True))]
    return SyncResult(tl, agree / max(1, len(ayahs)), start, end, dict(anchors))
