import pytest
from conftest import ALAFASY, FakeMeasurer

from quran_companion.core.settings import Settings
from quran_companion.core.text import verse_with_marker
from quran_companion.layout.paginator import Paginator, apply_word_timing, balance, hint_page

# Arabic dummy words: the tokenizer treats non-Arabic "words" as pause marks and glues them to the previous word.
W = ["ابجد", "هوزح", "طيكل", "منسع", "فصقر", "شتثخ", "ذضظغ", "سلام", "نورا", "قمرا"]


def test_balance_never_leaves_a_lonely_last_page():
    assert [len(g) for g in balance(list(range(7)), 3)] == [3, 2, 2]
    assert [len(g) for g in balance(list(range(9)), 3)] == [3, 3, 3]
    assert [len(g) for g in balance(list(range(3)), 3)] == [3]


def test_long_verse_is_split_into_pages_with_ellipsis():
    p = Paginator(FakeMeasurer(), max_width=100, max_lines=2)
    pages = p.paginate(" ".join(W), "one two three four five")
    assert [len(pg.lines) for pg in pages] == [2, 2, 1]
    assert all(pg.lines[-1].endswith("…") for pg in pages[:-1]) and not pages[-1].lines[-1].endswith("…")
    assert [pg.w0 for pg in pages] == [0, 4, 8]
    assert pages[0].frac == 0 and 0 < pages[1].frac < pages[2].frac < 1
    assert " ".join(" ".join(pg.tr) for pg in pages).replace("…", "").split() == "one two three four five".split()


def test_translation_shrinks_then_truncates():
    p = Paginator(FakeMeasurer(), max_width=100, max_lines=5, tr_lines=1)
    pg = p.paginate(W[0], "xxxx yyyy zzzz")[0]          # 140 px at 100%, fits at 70%
    assert pg.tr == ["xxxx yyyy zzzz"] and pg.tr_scale == 0.7
    pg = p.paginate(W[0], "x " * 40)[0]
    assert len(pg.tr) == 1 and pg.tr[0].endswith("…")


def test_word_timings_move_page_starts():
    p = Paginator(FakeMeasurer(), max_width=100, max_lines=1)
    pages = apply_word_timing(p.paginate(" ".join(W[:4])), {1: 0.0, 3: 0.61})
    assert pages[1].w0 == 2 and pages[1].frac == 0.61


def test_hint_shows_first_words():
    assert hint_page(" ".join(W[:3]), 2).lines == [f"{W[0]} {W[1]} …"]
    assert hint_page(W[0], 2).lines == [W[0]]


def test_pause_mark_stays_with_its_word():
    p = Paginator(FakeMeasurer(), max_width=1000, max_lines=1)
    assert p.paginate(f"{W[0]} ۚ {W[1]}")[0].lines == [f"{W[0]} ۚ {W[1]}"]


@pytest.mark.usefixtures("qapp_fonts")
def test_real_fonts_match_old_app(repo, golden):
    from quran_companion.overlay.painter import make_paginator
    rec = repo.find_reciter(ALAFASY)
    for case in golden["pages"]:
        s = Settings(max_lines=case["max_lines"], max_width=case["max_width"], trans=case["trans"])
        a = repo.text.surah_text(case["surah"], case["trans"])[case["ayah"]]
        pages = make_paginator(s, 1920 * case["max_width"] / 100).paginate(verse_with_marker(a.ar, a.n), a.tr)
        fr = repo.words.word_fractions(rec, case["surah"]).get(case["ayah"], {})
        assert len(pages) == len(case["pages"]), case
        for got, want in zip(pages, case["pages"], strict=True):
            assert got.lines == want["lines"] and got.tr == want["tr"] and got.w0 == want["w0"]
            assert round(got.frac, 6) == want["frac"]
            assert (round(fr[got.w0 + 1], 6) if got.w0 + 1 in fr else None) == want["word_frac"]
