"""Sync engine on synthetic 'recitations': feature sequences built from per-verse patterns,
stretched like a different reciter would, with unrelated audio before and after."""
import numpy as np

from quran_companion.core.models import VerseTiming
from quran_companion.sync import dtw, engine
from quran_companion.sync.features import FPS
from quran_companion.sync.pauses import HOP, find_pauses


def _verse_patterns(n, rng, dim=12):
    """Each verse: a sequence of 'phones' (random vectors), lengths in frames."""
    return [[rng.normal(size=dim) for _ in range(rng.integers(8, 20))] for _ in range(n)]


def _render(patterns, speed, rng, gap=6, pad_before=0, pad_after=0, dim=12):
    """Frames at FPS + verse start times (s). Each phone lasts ~2/speed frames with jitter."""
    frames, starts = [rng.normal(size=dim) * 3 for _ in range(pad_before)], []
    for p in patterns:
        starts.append(len(frames) / FPS)
        for ph in p:
            k = max(1, int(round(rng.uniform(1.5, 2.5) / speed)))
            frames += [ph + rng.normal(size=dim) * 0.15 for _ in range(k)]
        frames += [np.zeros(dim) + rng.normal(size=dim) * 0.05 for _ in range(gap)]
    frames += [rng.normal(size=dim) * 3 for _ in range(pad_after)]
    return np.array(frames, np.float32), starts


def _timings(starts, total):
    ends = starts[1:] + [total]
    return [VerseTiming(i + 1, int(a * 1000), int(b * 1000)) for i, (a, b) in enumerate(zip(starts, ends, strict=True))]


def _quiet_envelope(frames):
    """Envelope at pauses.HOP: loud where features are 'speech', quiet in the gaps."""
    loud = np.linalg.norm(frames, axis=1) > 1.0
    per = int(round(1 / FPS / HOP))
    return np.repeat(np.where(loud, 60.0, 10.0), per).astype(np.float32)


def test_dtw_maps_times_between_different_speeds():
    rng = np.random.default_rng(1)
    pats = _verse_patterns(25, rng)
    B, sb = _render(pats, 1.0, rng)
    A, sa = _render(pats, 0.6, rng)                    # slower reciter
    got = dtw.map_times(dtw.align(A, B), sb)
    err = np.abs(np.array(got) - np.array(sa))
    assert np.median(err) < 0.3 and err.max() < 1.5


def test_open_ends_skip_talk_before_and_after():
    rng = np.random.default_rng(2)
    pats = _verse_patterns(20, rng)
    B, sb = _render(pats, 1.0, rng)
    A, sa = _render(pats, 0.8, rng, pad_before=300, pad_after=200)   # 30 s talk, 20 s after
    got = dtw.map_times(dtw.align(A, B, open_a=True), sb)
    err = np.abs(np.array(got) - np.array(sa))
    assert np.median(err) < 0.3 and err.max() < 1.5


def test_engine_uses_references_and_anchors():
    rng = np.random.default_rng(3)
    pats = _verse_patterns(30, rng)
    refs = []
    for sp in (1.0, 1.2, 0.9):
        F, st = _render(pats, sp, rng)
        refs.append(engine.Reference(F, _timings(st, len(F) / FPS)))
    A, sa = _render(pats, 0.7, rng, pad_before=150)
    target = engine.Target(A, _quiet_envelope(A))
    ayahs = list(range(1, 31))
    res = engine.sync(target, refs, ayahs)
    got = np.array([t.start_ms / 1000 for t in res.timings])
    assert len(got) == 30 and np.all(np.diff(got) > 0)
    # verse starts sit at the start of the pause before the verse (like mp3quran's timings):
    # gap of 6 frames = 0.6 s, the pause point is 0.1 s into it
    expect = np.array(sa) - np.array([0.0] + [0.5] * 29)
    assert np.median(np.abs(got - expect)) < 0.2 and res.confident > 0.8
    assert abs(res.start - sa[0]) < 1.0
    # an anchor is kept exactly
    res2 = engine.sync(target, refs, ayahs, anchors={15: sa[14] + 0.05})
    assert abs(res2.timings[14].start_ms / 1000 - (sa[14] + 0.05)) < 1e-3


def test_pauses_found_in_envelope():
    env = np.array([60.0] * 40 + [10.0] * 10 + [60.0] * 40, np.float32)
    ps = find_pauses(env)
    assert len(ps) == 1 and abs(ps[0].t - 40 * HOP) < 0.2


def test_same_recording_twice_is_used_alone_and_both_passes_are_found():
    rng = np.random.default_rng(4)
    pats = _verse_patterns(20, rng)
    own, st = _render(pats, 1.0, rng)                       # the published recording itself
    other, st2 = _render(pats, 1.3, rng)                    # another reciter
    refs = [engine.Reference(other, _timings(st2, len(other) / FPS)), engine.Reference(own, _timings(st, len(own) / FPS))]
    video = np.concatenate([own, own])                      # the video plays it twice
    res = engine.sync(engine.Target(video, _quiet_envelope(video)), refs, list(range(1, 21)))
    assert len(res.passes) == 2 and len(res.timings) == 40
    first = np.array([t.start_ms / 1000 for t in res.timings[:20]])
    second = np.array([t.start_ms / 1000 for t in res.timings[20:]])
    expect = np.array(st) - np.array([0.0] + [0.5] * 19)    # verse starts sit at the pause before
    assert np.median(np.abs(first - expect)) < 0.2
    assert np.median(np.abs(second - (expect + len(own) / FPS))) < 0.3
    assert res.confident == 1.0
