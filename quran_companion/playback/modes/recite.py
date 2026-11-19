"""Recite: plays the reciter; the text follows the audio clock (verse timings + word timings)."""
import bisect

from ...core.i18n import T
from .base import Mode

END_TOLERANCE_MS = 1000   # ended this close to the last verse = finished normally


class ReciteMode(Mode):
    def __init__(self, session):
        super().__init__(session)
        d = session.data
        self.times = d.timings
        self.starts = [t.start_ms for t in self.times]
        self.tmap = {t.ayah: (t.start_ms, t.end_ms) for t in self.times}

    def start(self, ayah: int) -> None:
        if not self.times:
            self.session.message(T("ov_no_timing", s=self.session.surah)); return
        start = self.tmap.get(ayah, (0, 0))[0] if ayah > 1 else 0
        self.play_from(start / 1000)

    def play_from(self, sec: float) -> None:
        st = self.session.s
        self.session.player.play(self.session.repo.audio_source(self.session.rec, self.session.surah), sec, st.speed, st.volume)
        self.tick()

    def tick(self) -> None:
        p = self.session.player
        if p.take_ended():
            self._ended(); return
        pos = p.position()
        if not p.active() or p.paused or pos is None or not self.times: return
        ms = pos * 1000
        i = max(0, bisect.bisect_right(self.starts, ms) - 1)
        t = self.times[i]
        end = self.session.range_end()
        if end and t.ayah > end:
            if self.session.s.loop: self.play_from(self.tmap.get(self.session.rng[0], (0, 0))[0] / 1000)
            else: p.stop(); self.session.finish()
            return
        if not self.session.has_ayah(t.ayah): return
        pages = self.session.pages_for(t.ayah)
        frac = (ms - t.start_ms) / max(1, t.end_ms - t.start_ms)
        k = max([j for j, pg in enumerate(pages) if pg.frac <= frac] or [0])
        v = self.session.view
        if (t.ayah, k) != (self.session.cur, self.session.page) or (v and v.kind != "page"):
            self.session.show(t.ayah, k)

    def _ended(self) -> None:
        pos = self.session.player.position() or 0
        if self.times and pos * 1000 >= self.times[-1].start_ms - END_TOLERANCE_MS:
            self.session.next_surah_or_finish()
        else:
            self.session.message(T("ov_stopped"))

    def step(self, d: int) -> None:
        t = self.tmap.get((self.session.cur or 0) + d)
        if t: self.play_from(t[0] / 1000)

    def pause(self) -> bool:
        p = self.session.player
        if p.active():
            p.set_paused(True); return True
        if self.times: self.step(0)
        return False

    def resume(self) -> None:
        self.session.player.set_paused(False)

    def stop(self) -> None:
        self.session.player.stop()
