from quran_companion.core.text import BASMALA, ar_digits, bare, name_match, strip_basmala, tokens, verse_with_marker


def test_reciter_search_matches_old_app(repo, golden):
    recs = repo.reciters()
    for query, ids in golden["search"].items():
        got = sorted({r.id for r in recs if name_match(query, r.search_text())})
        assert got == ids, query


def test_search_examples(repo):
    names = {r.en for r in repo.reciters() if name_match("ahmed bin taleb", r.search_text())}
    assert names == {"Ahmad Talib bin Humaid"}
    assert name_match("husary", "Mahmoud Khalil Al-Hussary")
    assert name_match("afasy", "Mishary Alafasi")
    assert not name_match("zz", "Mishary Alafasi")


def test_pause_marks_stick_to_words(repo, golden):
    text = repo.text.surah_text(2)[282].ar
    assert len(tokens(text)) == golden["tokens_2_282"] == 128   # same count as quran.com word timings


def test_basmala_is_removed_from_verse_one(repo):
    assert repo.text.surah_text(2)[1].ar == "الٓمٓ"
    assert bare(repo.text.surah_text(1)[1].ar) == bare(BASMALA)       # in al-Fatiha it *is* verse 1
    assert strip_basmala("﻿" + BASMALA + " الٓمٓ", 9) .startswith("بِسْمِ")  # at-Tawba has none to strip


def test_verse_marker_is_glued_to_last_word():
    t = verse_with_marker("قُلْ هُوَ", 12)
    assert t.endswith(" ﴿١٢﴾") and ar_digits(286) == "٢٨٦"
    assert tokens(t)[-1].endswith("﴾")
