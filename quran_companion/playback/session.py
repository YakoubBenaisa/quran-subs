"""Playback session: loads a surah, runs one mode (Strategy), and tells a listener what to show.

State machine:

    IDLE ──load──▶ LOADING ──loaded──▶ ACTIVE ⇄ PAUSED
                     │  ▲                │
                  error│  └──load (next surah, goto)
                     ▼                   ▼
                   ERROR             FINISHED

The session has no Qt dependency. The caller drives it with `tick()` (about 10× per second) and
gives it a `runner` that executes the blocking load off the UI thread and calls back on it.
"""
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol

from ..core.i18n import T
from ..core.models import Page, Reciter, SurahData
from ..core.settings import Settings, SettingsStore
from ..core.text import SADAQA, intro_text, verse_with_marker
from ..data.repository import LoadRequest, QuranRepository
from ..layout.paginator import Paginator, apply_word_timing, hint_page
from .clock import Clock
from .player import AudioPlayer

if TYPE_CHECKING:
    from .modes.base import Mode


class State(enum.Enum):
    IDLE = "idle"
    LOADING = "loading"
    ACTIVE = "active"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"


ALLOWED = {
    State.IDLE: {State.LOADING},
    State.LOADING: {State.LOADING, State.ACTIVE, State.ERROR, State.FINISHED},
    State.ACTIVE: {State.LOADING, State.PAUSED, State.FINISHED, State.IDLE},
    State.PAUSED: {State.LOADING, State.ACTIVE, State.FINISHED, State.IDLE},
    State.FINISHED: {State.LOADING, State.ACTIVE, State.IDLE},
    State.ERROR: {State.LOADING, State.IDLE},
}


class InvalidTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class View:
    """What the overlay should show now."""
    kind: str                 # "page" | "message" | "hint" | "blank"
    page: Page
    ayah: int = 0
    index: int = 0            # page index inside the verse
    text: str = ""            # message text
    text_kind: str = "tr"     # message style: "ar" or "tr"


class Listener(Protocol):
    def on_view(self, view: View) -> None: ...


Runner = Callable[[Callable[[], object], Callable[[object], None]], None]


def sync_runner(fn, done):
    """Runs the load immediately (tests, command-line)."""
    try:
        res = fn()
    except Exception as e:  # noqa: BLE001 - handed to the session as a result
        res = e
    done(res)


class Session:
    def __init__(self, repo: QuranRepository, player: AudioPlayer, clock: Clock, store: SettingsStore,
                 paginator_factory: Callable[[Settings], Paginator], listener: Listener, runner: Runner = sync_runner):
        self.repo, self.player, self.clock, self.store = repo, player, clock, store
        self.paginator_factory, self.listener, self.runner = paginator_factory, listener, runner
        self.state = State.IDLE
        self.s: Settings = store.load()
        self.paginator = paginator_factory(self.s)
        self.rec: Reciter | None = None
        self.data: SurahData | None = None
        self.surah = self.s.surah
        self.cur: int | None = None
        self.page = 0
        self.view: View | None = None
        self.rng = (self.s.range_from, self.s.range_to)
        self.mode: "Mode | None" = None
        self._pages: dict[int, list[Page]] = {}
        self._load_id = 0

    # ---------------------------------------------------------------- state machine
    def _go(self, new: State) -> None:
        if new not in ALLOWED[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {new.value}")
        self.state = new

    # ---------------------------------------------------------------- loading
    def load(self, surah: int, ayah: int = 1, rng: tuple[int, int] | None = None) -> None:
        if self.mode: self.mode.stop()
        self._go(State.LOADING)
        self.s = self.store.load()
        self.paginator = self.paginator_factory(self.s)
        if rng is not None: self.rng = rng
        self.surah, self.cur, self.page, self.data, self._pages = surah, None, 0, None, {}
        self._load_id += 1
        lid = self._load_id
        self.message(T("ov_loading"))
        s = self.s
        req = LoadRequest(surah, s.reciter, s.trans, timings=s.mode != "manual",
                          word_sync=s.mode == "recite" and s.word_sync, timings_required=s.mode == "recite")
        self.runner(lambda: self.repo.load(req), lambda res: self._loaded(lid, ayah, res))

    def _loaded(self, lid: int, ayah: int, res) -> None:
        if lid != self._load_id: return  # a newer load started meanwhile
        if isinstance(res, Exception):
            self._go(State.ERROR)
            self.message(T("ov_failed", err=f"{type(res).__name__}: {res}"))
            return
        self.rec, self.data = res
        from .modes import make_mode
        mode = self.mode = make_mode(self.s.mode, self)
        self._go(State.ACTIVE)
        mode.start(max(1, min(ayah, len(res[1].ayahs))))

    # ---------------------------------------------------------------- commands
    def tick(self) -> None:
        if self.state is State.ACTIVE and self.mode: self.mode.tick()

    def step(self, d: int) -> None:
        if self.state in (State.ACTIVE, State.PAUSED) and self.mode and self.data:
            if self.state is State.PAUSED: self._resume_state()
            self.mode.step(d)

    def toggle_pause(self) -> None:
        if not self.mode: return
        if self.state is State.ACTIVE:
            if self.mode.pause(): self._go(State.PAUSED)
        elif self.state is State.PAUSED:
            self.mode.resume(); self._go(State.ACTIVE)
        elif self.state is State.FINISHED and self.data:
            self._go(State.ACTIVE); self.mode.step(0)

    def _resume_state(self) -> None:
        if self.mode: self.mode.resume()
        self._go(State.ACTIVE)

    def goto(self, surah: int, ayah: int = 1) -> None:
        self.load(max(1, min(114, surah)), ayah, rng=(1, 0))

    def next_surah(self, d: int) -> None:
        self.goto(self.surah + d, 1)

    def replay(self) -> None:
        """Re-read settings and start again (the settings window pressed Start)."""
        s = self.store.load()
        self.load(s.surah, s.ayah, rng=(s.range_from, s.range_to))

    def restyle(self) -> None:
        """Style or layout settings changed: re-split pages and redraw what is shown."""
        st = self.store.load()
        self.s = self.s.with_(**st.style())
        self.paginator = self.paginator_factory(self.s)
        self._pages = {}
        self.redraw()

    def stop(self) -> None:
        if self.mode: self.mode.stop()
        if self.state is not State.IDLE: self.state = State.IDLE

    def finish(self) -> None:
        self.message(SADAQA, "ar")
        if self.state in (State.ACTIVE, State.PAUSED): self._go(State.FINISHED)

    def next_surah_or_finish(self) -> None:
        if self.s.autonext and self.surah < 114 and not self.range_end():
            self.store.update(range_from=1, range_to=0)
            self.load(self.surah + 1, 1, rng=(1, 0))
        else:
            self.finish()

    def range_end(self) -> int:
        a, b = self.rng
        return b if b and b >= a else 0

    # ---------------------------------------------------------------- pages & views (used by the modes)
    @property
    def loaded(self) -> SurahData:
        """The loaded surah; only valid once loading finished (modes run only then)."""
        if self.data is None: raise RuntimeError("no surah loaded")
        return self.data

    def pages_for(self, n: int) -> list[Page]:
        if n not in self._pages:
            if n == 0:
                pages = self.paginator.paginate(intro_text(self.surah))
            else:
                d = self.loaded
                a = d.ayahs[n]
                pages = apply_word_timing(self.paginator.paginate(verse_with_marker(a.ar, n), a.tr), d.word_fracs.get(n))
            self._pages[n] = pages
        return self._pages[n]

    def has_ayah(self, n: int) -> bool:
        return n == 0 or bool(self.data and n in self.data.ayahs)

    def show(self, n: int, k: int) -> None:
        if not self.has_ayah(n): return
        pages = self.pages_for(n)
        k = max(0, min(k, len(pages) - 1))
        changed = n != self.cur
        self.cur, self.page = n, k
        self._emit(View("page", pages[k], n, k))
        if changed and n > 0: self.store.update(surah=self.surah, ayah=n)

    def show_hint(self, n: int) -> None:
        self.cur = n
        self._emit(View("hint", hint_page(self.loaded.ayahs[n].ar, self.s.hint_words), n))
        self.store.update(surah=self.surah, ayah=n)

    def show_blank(self) -> None:
        self._emit(View("blank", Page([]), self.cur or 0))

    def message(self, text: str, kind: str = "tr") -> None:
        self._emit(View("message", self.paginator.message(text, kind), text=text, text_kind=kind))

    def redraw(self) -> None:
        v = self.view
        if v is None: return
        if v.kind == "page": self.show(v.ayah, v.index)
        elif v.kind == "hint": self.show_hint(v.ayah)
        elif v.kind == "message": self.message(v.text, v.text_kind)
        else: self.show_blank()

    def _emit(self, v: View) -> None:
        self.view = v
        self.listener.on_view(v)
