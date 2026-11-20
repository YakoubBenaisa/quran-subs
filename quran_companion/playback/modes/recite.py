"""Recite: plays the reciter; the text follows the audio clock (verse timings + word timings).

The user's own recordings (synced automatically) can be corrected while listening:
next (→) = "the next verse starts now": that verse moves here at once, the rest follows, and
the recording is re-matched in the background with this as a fixed point.
previous (←) = "not yet": the text goes back one verse and waits for the next → (or for the
recitation to get clearly past it)."""
import bisect

from ...core.i18n import T
from .base import Mode

END_TOLERANCE_MS = 1000   # ended this close to the last verse = finished normally


class ReciteMode(Mode):
    def __init__(self, session):
        super().__init__(session)
        self._set_times(session.data.timings)
        self.correctable = bool(session.rec and session.rec.mine and session.corrector)
        self.hold: int | None = None          # verse kept on screen after "not yet"

    def _set_times(self, times) -> None:
        self.times = list(times)
        self.starts = [t.start_ms for t in self.times]
        self.tmap: dict[int, tuple[int, int]] = {}
        for t in self.times: self.tmap.setdefault(t.ayah, (t.start_ms, t.end_ms))   # first time through

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
        if not p.active() or pos is None or not self.times: return      # paused: still show where it is
        ms = pos * 1000
        i = max(0, bisect.bisect_right(self.starts, ms) - 1)
        t = self.times[i]
        if self.hold is not None:
            if self.hold in self.tmap and t.ayah <= self.hold + 1:
                if self.session.cur != self.hold: self.session.show(self.hold, 0)
                return
            self.hold = None                   # the recitation is clearly past it
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
        if self.correctable and d != 0 and self.session.player.active() and not self.session.player.paused:
            self._correct(d); return
        t = self.tmap.get((self.session.cur or 0) + d)
        if t: self.play_from(t[0] / 1000)

    # ---------------------------------------------------------------- corrections (own recordings)
    def _correct(self, d: int) -> None:
        cur = self.hold if self.hold is not None else (self.session.cur or 0)
        pos = self.session.player.position() or 0
        at = int(pos * 1000)
        # which entry is on screen: the verse shown, nearest to now (a verse can come more than once)
        same = [i for i, t in enumerate(self.times) if t.ayah == cur]
        if not same: return
        k = min(same, key=lambda i: abs(self.times[i].start_ms - at))
        if d < 0:                                  # "not yet"
            if k > 0:
                self.hold = self.times[k - 1].ayah; self.session.show(self.hold, 0)
            return
        if k + 1 >= len(self.times): return
        nxt = self.times[k + 1].ayah
        # move it here at once: shift the next verse and the ones after it
        delta = at - self.times[k + 1].start_ms
        shifted = [t if i <= k else type(t)(t.ayah, max(0, t.start_ms + delta), max(0, t.end_ms + delta))
                   for i, t in enumerate(self.times)]
        prev = shifted[k]; shifted[k] = type(prev)(prev.ayah, prev.start_ms, at)
        self._set_times(shifted)
        self.hold = None
        self.session.show(nxt, 0)
        rid, session = self.session.rec.id if self.session.rec else 0, self.session
        corrector = session.corrector
        assert corrector is not None

        def done(res) -> None:
            if session.mode is self and isinstance(res, list) and res: self._set_times(res)
        session.runner(lambda: corrector(rid, nxt, pos), done)

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
