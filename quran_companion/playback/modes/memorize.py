"""Memorize: silent, self-timed. Each verse is a list of steps (hint, pages, blank, pause after)."""
from dataclasses import dataclass, field

from ...core.text import tokens
from .base import Mode

MIN_PAGE_SECONDS = 1.0
MIN_RECITER_SECONDS = 1.5


# Advance policies (Strategy): how long a verse stays on screen
def seconds_by_words(session, n: int) -> float:
    s = session.s
    return max(float(s.mem_min), len(tokens(session.data.ayahs[n].ar)) * float(s.mem_per_word))


def seconds_fixed(session, n: int) -> float:
    return float(session.s.mem_fixed)


def seconds_reciter_pace(session, n: int) -> float:
    for t in session.data.timings:
        if t.ayah == n:
            return max(MIN_RECITER_SECONDS, (t.end_ms - t.start_ms) / 1000 / max(0.5, float(session.s.speed)))
    return seconds_by_words(session, n)


ADVANCE = {"words": seconds_by_words, "fixed": seconds_fixed, "reciter": seconds_reciter_pace}


Step = tuple[tuple, float]   # (("page", k) | ("hint",) | ("blank",), seconds)


@dataclass
class VersePlan:
    n: int
    rep: int
    steps: list[Step] = field(default_factory=list)
    i: int = -1
    end: float = 0.0
    left: float = 0.0


class MemorizeMode(Mode):
    def __init__(self, session):
        super().__init__(session)
        self.plan: VersePlan | None = None

    def plan_for(self, n: int, rep: int) -> VersePlan:
        st = self.session.s
        pages = self.session.pages_for(n)
        dur = ADVANCE.get(st.mem_advance, seconds_by_words)(self.session, n)
        steps: list[Step] = []
        if st.mem_hint == "reveal": steps.append((("hint",), float(st.hint_delay)))
        for k, pg in enumerate(pages):
            f1 = pages[k + 1].frac if k + 1 < len(pages) else 1.0
            steps.append((("page", k), max(MIN_PAGE_SECONDS, dur * (f1 - pg.frac))))
        if st.mem_hint == "fade": steps.append((("blank",), dur))
        if float(st.mem_gap) > 0:
            steps.append((("blank",) if st.mem_hint == "fade" else ("page", len(pages) - 1), float(st.mem_gap)))
        return VersePlan(n, rep, steps)

    def start(self, ayah: int, rep: int = 1) -> None:
        self.plan = self.plan_for(ayah, rep)
        self._next_step()

    def _next_step(self) -> None:
        p = self.plan
        if p is None: return
        p.i += 1
        if p.i >= len(p.steps):
            self._verse_done(); return
        what, dur = p.steps[p.i]
        p.end = self.session.clock.now() + dur
        if what[0] == "page": self.session.show(p.n, what[1])
        elif what[0] == "hint": self.session.show_hint(p.n)
        else: self.session.show_blank()

    def _verse_done(self) -> None:
        p, st = self.plan, self.session.s
        if p is None: return
        n = p.n
        if p.rep < int(st.mem_repeat):
            self.start(n, p.rep + 1); return
        end = self.session.range_end()
        last = len(self.session.data.ayahs)
        if (end and n >= end) or n >= last:
            if end and st.loop:
                self.start(self.session.rng[0]); return
            self.plan = None
            if n >= last and not end: self.session.next_surah_or_finish()
            else: self.session.finish()
            return
        self.start(n + 1)

    def tick(self) -> None:
        if self.plan and self.session.clock.now() >= self.plan.end: self._next_step()

    def step(self, d: int) -> None:
        n = (self.session.cur or 0) + d
        self.start(max(1, min(n, len(self.session.data.ayahs))))

    def pause(self) -> bool:
        if not self.plan: return False
        self.plan.left = max(0.0, self.plan.end - self.session.clock.now())
        return True

    def resume(self) -> None:
        if self.plan: self.plan.end = self.session.clock.now() + self.plan.left

    def stop(self) -> None:
        self.plan = None
