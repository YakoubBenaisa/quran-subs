"""Use case: turn a link or file into a synced "My recitation", and apply the user's corrections.

Stages (for the progress bar): download → analyse → references → match. Features of the
recording and of the reference reciters are cached, so corrections re-match in seconds.
"""
import os
from dataclasses import dataclass, replace
from typing import Callable

import numpy as np

from ..core.guess import clean_title, guess_reciter, guess_surah
from ..core.models import MyRecitation, Reciter
from ..data.media import MediaFetcher, MediaInfo
from ..data.my_recitations import MyRecitations
from ..data.repository import QuranRepository
from . import engine, features
from .pauses import envelope_from_samples

# Murattal, Hafs ʿan ʿAsim, with timings for (almost) every surah: Alafasy, Minshawi, Al-Dosari,
# Al-Sudais, Al-Jileel. The first three that have timings for the surah are used.
REFERENCE_IDS = (123, 112, 92, 54, 20)
N_REFS = 3

Progress = Callable[[str, float], None]     # stage, overall fraction 0..1
STAGES = {"download": (0.0, 0.35), "analyse": (0.35, 0.5), "references": (0.5, 0.75), "match": (0.75, 1.0)}


@dataclass(frozen=True)
class Inspection:
    info: MediaInfo
    surah: int | None             # recognised from the title
    reciter: Reciter | None       # recognised from the title (one with timings)
    downloaded: bool


def _stage(progress: Progress, name: str) -> Callable[[float], None]:
    a, b = STAGES[name]
    return lambda f: progress(name, a + (b - a) * max(0.0, min(1.0, f)))


class SyncService:
    def __init__(self, repo: QuranRepository, fetcher: MediaFetcher, store: MyRecitations):
        self.repo, self.fetcher, self.store = repo, fetcher, store

    # ------------------------------------------------------------ inspect
    def inspect(self, src: str) -> Inspection:
        info = self.fetcher.info(src)
        return Inspection(info, guess_surah(info.title, self.repo.surahs()),
                          guess_reciter(info.title, self.repo.timed_reciters()), self.fetcher.local_path(info) is not None)

    # ------------------------------------------------------------ create
    def create(self, ins: Inspection, surah: int, ayah_from: int = 1, ayah_to: int = 0, title: str = "",
               progress: Progress = lambda s, f: None, cancel: Callable[[], bool] = lambda: False) -> MyRecitation:
        audio = self.fetcher.fetch(ins.info, _stage(progress, "download"), cancel)
        n = next(s.ayahs for s in self.repo.surahs() if s.number == surah)
        a, b = max(1, ayah_from), (ayah_to if ayah_to and ayah_to >= ayah_from else n)
        ayahs = ([0] if a == 1 else []) + list(range(a, min(b, n) + 1))
        m = MyRecitation(self.store.new_id(), clean_title(title or ins.info.title), ins.info.source, audio, surah, ayahs,
                         reciter_name=(ins.reciter.name(False) if ins.reciter else ""))
        target = self._target(m, _stage(progress, "analyse"), cancel)
        refs = self._references(surah, ins.reciter, _stage(progress, "references"), cancel)
        res = engine.sync(target, refs, ayahs, progress=_stage(progress, "match"), cancel=cancel)
        m.timings, m.confident = res.timings, res.confident
        return self.store.save(m)

    # ------------------------------------------------------------ corrections
    def correct(self, m: MyRecitation, ayah: int, at: float, cancel: Callable[[], bool] = lambda: False) -> MyRecitation:
        """The user says `ayah` starts at `at` seconds: keep it as an anchor and re-match."""
        anchors = {**m.anchors, ayah: float(at)}
        return self.resync(replace(m, anchors=anchors), cancel)

    def resync(self, m: MyRecitation, cancel: Callable[[], bool] = lambda: False) -> MyRecitation:
        target = self._target(m, lambda f: None, cancel)
        refs = self._references(m.surah, self._named(m), lambda f: None, cancel)
        res = engine.sync(target, refs, m.ayahs, anchors=m.anchors, cancel=cancel)
        m.timings, m.confident = res.timings, res.confident
        return self.store.save(m)

    def delete(self, m: MyRecitation) -> None:
        self.store.delete(m.id)

    # ------------------------------------------------------------ features (cached)
    def _target(self, m: MyRecitation, progress, cancel) -> engine.Target:
        path = self.features_path(m)
        if os.path.exists(path):
            with np.load(path) as z:
                if "mean" in z: return engine.Target(z["features"], z["envelope"])
        progress(0.05)
        x = features.decode(m.audio, cancel=cancel)
        progress(0.5)
        raw = features.mfcc_raw(x)
        mean, std = features.stats(raw)
        t = engine.Target(features.normalize(raw, mean, std), envelope_from_samples(x))
        os.makedirs(self.store.cache_dir, exist_ok=True)
        np.savez_compressed(path, features=t.features, envelope=t.envelope, mean=mean, std=std)
        progress(1.0)
        return t

    def features_for_audio(self, audio: str) -> str:
        """Features file of the recording whose audio is `audio` (computed if missing)."""
        m = next((x for x in self.store.all() if x.audio == audio), None)
        if m is None: raise FileNotFoundError(audio)
        self._target(m, lambda f: None, lambda: False)
        return self.features_path(m)

    def features_path(self, m: MyRecitation) -> str:
        """Features of the recording (also used to find the position of a browser video by listening)."""
        return os.path.join(self.store.cache_dir, f"{m.id}.npz")

    def _named(self, m: MyRecitation) -> Reciter | None:
        if not m.reciter_name: return None
        return next((r for r in self.repo.timed_reciters() if r.name(False) == m.reciter_name), None)

    def _references(self, surah: int, named: Reciter | None, progress, cancel) -> list[engine.Reference]:
        ids = ([named.id] if named else []) + [i for i in REFERENCE_IDS if not named or i != named.id]
        out: list[engine.Reference] = []
        for rid in ids:
            if len(out) >= N_REFS: break
            if cancel(): raise InterruptedError("cancelled")
            rec = next((r for r in self.repo.timed_reciters() if r.id == rid), None)
            if rec is None: continue
            try:
                timings = self.repo.timing_src.verse_timings(rec, surah)
            except Exception:
                continue
            if not timings: continue
            out.append(engine.Reference(self._ref_features(rec, surah, cancel), timings))
            progress(len(out) / N_REFS)
        if not out: raise RuntimeError("no reference reciter with timings is available for this surah")
        return out

    def _ref_features(self, rec: Reciter, surah: int, cancel) -> np.ndarray:
        path = os.path.join(self.store.cache_dir, "ref", f"{rec.id}_{surah:03d}.npy")
        if os.path.exists(path): return np.load(path)
        f = features.mfcc(features.decode(self.repo.audio_source(rec, surah), cancel=cancel))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.save(path, f)
        return f
