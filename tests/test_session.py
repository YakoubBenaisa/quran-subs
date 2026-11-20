"""Playback session + modes, driven with a fake player, a fake clock and the offline fixtures."""
import pytest
from conftest import ALAFASY, Recorder

from quran_companion.core.text import SADAQA
from quran_companion.playback.clock import FakeClock
from quran_companion.playback.player import FakePlayer
from quran_companion.playback.session import InvalidTransition, Session, State

pytestmark = pytest.mark.usefixtures("qapp_fonts")
SCREEN = 1920


def make(repo, store, **settings):
    from quran_companion.overlay.painter import make_paginator
    store.update(reciter=ALAFASY, **settings)
    rec, player, clock = Recorder(), FakePlayer(), FakeClock()
    ses = Session(repo, player, clock, store, lambda s: make_paginator(s, SCREEN * s.max_width / 100), rec)
    return ses, player, clock, rec


def timing(ses, n):
    return next(t for t in ses.data.timings if t.ayah == n)


# ---------------------------------------------------------------- recite
def test_recite_follows_audio_and_turns_pages_on_words(repo, store):
    ses, player, _, rec = make(repo, store, mode="recite", trans="en.sahih")
    ses.load(2, 282)
    assert ses.state is State.ACTIVE
    t = timing(ses, 282)
    assert player.calls[0][:3] == ("play", "https://cdn.mp3quran.net/audio/mishary-alafasy/r1/002.mp3", t.start_ms / 1000)
    assert [round(p.frac, 3) for p in ses.pages_for(282)] == [0.0, 0.346, 0.651]   # quran.com word timings
    seen = []
    for f in (0.0, 0.2, 0.4, 0.6, 0.8, 0.99):
        player.pos = (t.start_ms + f * (t.end_ms - t.start_ms)) / 1000; ses.tick(); seen.append((ses.cur, ses.page))
    assert seen == [(282, 0), (282, 0), (282, 1), (282, 1), (282, 2), (282, 2)]
    player.pos = (t.end_ms + 500) / 1000; ses.tick()
    assert (ses.cur, ses.page) == (283, 0)             # next verse only after the last page
    assert store.load().ayah == 283                    # progress is saved


def test_recite_intro_shows_basmala(repo, store):
    ses, player, _, rec = make(repo, store, mode="recite")
    ses.load(2, 1)
    player.pos = 1.0; ses.tick()
    assert rec.views[-1].ayah == 0 and "بِسْمِ" in rec.views[-1].page.lines[0]


def test_recite_end_of_surah_continues_with_next(repo, store):
    ses, player, _, _ = make(repo, store, mode="recite", autonext=True)
    ses.load(1, 7)
    player.pos = timing(ses, 7).start_ms / 1000 + 1; player.ended = True; ses.tick()
    assert ses.surah == 2 and ses.state is State.ACTIVE
    assert player.calls[-1][1].endswith("/002.mp3") and player.calls[-1][2] == 0


def test_recite_stopped_early_says_so(repo, store):
    ses, player, _, rec = make(repo, store, mode="recite")
    ses.load(2, 10)
    player.ended = True; ses.tick()
    assert rec.views[-1].kind == "message" and ses.surah == 2


@pytest.mark.parametrize("loop", [False, True])
def test_recite_range_end(repo, store, loop):
    ses, player, _, rec = make(repo, store, mode="recite", loop=loop)
    ses.load(1, 1, rng=(1, 2))
    player.pos = timing(ses, 3).start_ms / 1000 + 0.2; ses.tick()
    if loop:
        assert player.calls[-1][2] == timing(ses, 1).start_ms / 1000 and ses.state is State.ACTIVE
    else:
        assert ses.state is State.FINISHED and rec.views[-1].text == SADAQA


def test_recite_pause_and_step(repo, store):
    ses, player, _, _ = make(repo, store, mode="recite")
    ses.load(2, 5)
    ses.toggle_pause(); assert ses.state is State.PAUSED and player.paused
    ses.toggle_pause(); assert ses.state is State.ACTIVE and not player.paused
    player.pos = timing(ses, 5).start_ms / 1000 + 0.1; ses.tick()
    ses.step(1); assert player.calls[-1][2] == timing(ses, 6).start_ms / 1000


# ---------------------------------------------------------------- memorize
def run(ses, clock, seconds, dt=0.05):
    for _ in range(int(seconds / dt)):
        clock.advance(dt); ses.tick()


def shown(rec):
    return [(v.kind, v.ayah) for v in rec.views if v.kind != "message"]


def test_memorize_repeats_and_loops_the_range(repo, store):
    ses, _, clock, rec = make(repo, store, mode="memorize", mem_per_word=0.3, mem_min=1, mem_gap=1, mem_repeat=2, loop=True)
    ses.load(112, 1, rng=(1, 2))
    run(ses, clock, 14)
    ayahs = [a for _, a in shown(rec)]
    # each verse: page + pause-after, twice; then verse 2 twice; then back to verse 1
    assert ayahs[:10] == [1, 1, 1, 1, 2, 2, 2, 2, 1, 1]


def test_memorize_timing_and_pause(repo, store):
    ses, _, clock, rec = make(repo, store, mode="memorize", mem_per_word=0.5, mem_min=1, mem_gap=0)
    ses.load(112, 1)                      # 4 words -> 2.0 s
    run(ses, clock, 1.0)
    ses.toggle_pause(); assert ses.state is State.PAUSED
    run(ses, clock, 5.0)                  # nothing moves while paused
    assert ses.cur == 1
    ses.toggle_pause()
    run(ses, clock, 1.1)
    assert ses.cur == 2


@pytest.mark.parametrize("hint, expected", [
    ("reveal", [("hint", 1), ("page", 1), ("hint", 2), ("page", 2)]),
    ("fade", [("page", 1), ("blank", 1), ("page", 2), ("blank", 2)]),
])
def test_memorize_helpers(repo, store, hint, expected):
    ses, _, clock, rec = make(repo, store, mode="memorize", mem_hint=hint, hint_delay=1, mem_per_word=0.3, mem_min=1,
                              mem_gap=0, hint_words=1)
    ses.load(112, 1)
    run(ses, clock, 5.5)
    got = []
    for k in shown(rec):
        if not got or got[-1] != k: got.append(k)
    assert got[:4] == expected
    if hint == "reveal":
        hint_view = next(v for v in rec.views if v.kind == "hint")
        assert hint_view.page.lines[0].endswith("…") and len(hint_view.page.lines[0].split()) == 2


def test_memorize_end_of_surah_moves_on(repo, store):
    ses, _, clock, _ = make(repo, store, mode="memorize", mem_per_word=0.1, mem_min=1, mem_gap=0, autonext=True)
    ses.load(1, 7)
    run(ses, clock, 1.5)
    assert ses.surah == 2 and ses.state is State.ACTIVE


# ---------------------------------------------------------------- manual
def test_manual_steps_through_pages_then_verses(repo, store):
    ses, _, _, _ = make(repo, store, mode="manual")
    ses.load(2, 281)
    path = []
    for d in [1] * 6 + [-1] * 3:
        ses.step(d); path.append((ses.cur, ses.page))
    assert path == [(282, 0), (282, 1), (282, 2), (283, 0), (284, 0), (285, 0), (284, 0), (283, 0), (282, 2)]


# ---------------------------------------------------------------- state machine & restyle
def test_state_machine_rejects_invalid_transitions(repo, store):
    ses, _, _, _ = make(repo, store, mode="manual")
    with pytest.raises(InvalidTransition):
        ses._go(State.ACTIVE)            # IDLE -> ACTIVE is not allowed
    ses.toggle_pause(); assert ses.state is State.IDLE   # nothing to pause


def test_offline_failure_goes_to_error_state(repo, store):
    ses, _, _, rec = make(repo, store, mode="recite")
    ses.load(113, 1)                      # not in the offline fixtures
    assert ses.state is State.ERROR and rec.views[-1].kind == "message"


def test_restyle_repaginates_current_verse(repo, store):
    ses, _, _, rec = make(repo, store, mode="manual")
    ses.load(2, 282)
    assert len(ses.pages_for(282)) == 3
    store.update(max_lines=6); ses.restyle()
    assert len(ses.pages_for(282)) == 2 and rec.views[-1].ayah == 282


# ---------------------------------------------------------------- the user's own recordings
def _my_recording(repo, tmp_path):
    from quran_companion.core.models import MyRecitation, VerseTiming
    from quran_companion.data.my_recitations import MyRecitations
    repo.mine = MyRecitations(str(tmp_path / "mine"))
    ts = [VerseTiming(0, 0, 5000)] + [VerseTiming(a, 5000 + (a - 1) * 10000, 5000 + a * 10000) for a in range(1, 111)]
    return repo.mine.save(MyRecitation(1, "Al-Kahf", "https://youtu.be/x", str(tmp_path / "a.m4a"), 18, list(range(111)), ts,
                                       confident=0.9))


def test_my_recording_plays_its_file_and_stays_on_its_surah(repo, store, tmp_path):
    m = _my_recording(repo, tmp_path)
    assert repo.reciters()[0].mine and repo.find_reciter(m.reciter_id).ar == "Al-Kahf"
    ses, player, _, rec = make(repo, store, mode="recite")
    store.update(reciter=m.reciter_id)
    ses.load(18, 1)
    assert player.calls[-1][1] == m.audio
    player.pos = 25.5; ses.tick()
    assert ses.cur == 3
    player.pos = 1104.9; player.ended = True; ses.tick()      # end of recording: no next surah
    assert ses.state is State.FINISHED
    ses.load(2, 1)                                             # another surah is not in the recording
    assert ses.state is State.ERROR


def test_correcting_my_recording(repo, store, tmp_path):
    from quran_companion.core.models import VerseTiming
    m = _my_recording(repo, tmp_path)
    calls = []

    def corrector(rid, ayah, at):
        calls.append((rid, ayah, round(at, 1)))
        d = int(at * 1000) - next(t.start_ms for t in m.timings if t.ayah == ayah)    # "re-matched" around the anchor
        return [VerseTiming(t.ayah, t.start_ms + (d if t.ayah >= ayah else 0), t.end_ms + (d if t.ayah >= ayah - 1 else 0))
                for t in m.timings]
    from quran_companion.overlay.painter import make_paginator
    store.update(reciter=m.reciter_id, mode="recite")
    rec, player, clock = Recorder(), FakePlayer(), FakeClock()
    ses = Session(repo, player, clock, store, lambda s: make_paginator(s, SCREEN * s.max_width / 100), rec, corrector=corrector)
    ses.load(18, 1)
    player.pos = 27.0; ses.tick()
    assert ses.cur == 3
    # the text is late: verse 4 really starts now (27 s instead of 35 s)
    ses.step(1)
    assert ses.cur == 4 and calls == [(m.reciter_id, 4, 27.0)]
    player.pos = 28.0; ses.tick()
    assert ses.cur == 4            # the timings after the result came back are the corrector's
    # "not yet": back to 3 and wait, even though the clock says 4
    player.pos = 36.0; ses.tick(); assert ses.cur == 4
    ses.step(-1); assert ses.cur == 3
    player.pos = 36.5; ses.tick(); assert ses.cur == 3          # verse 4 is 27–37 s now
    player.pos = 40.0; ses.tick(); assert ses.cur == 5          # clearly past it: follows the clock again
