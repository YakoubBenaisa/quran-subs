"""Arabic text rules: normalisation, tokenisation, name search. Pure functions."""
import re

BASMALA = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
ISTIADHA = "أَعُوذُ بِٱللَّهِ مِنَ ٱلشَّيْطَٰنِ ٱلرَّجِيمِ"
SADAQA = "صَدَقَ ٱللَّهُ ٱلْعَظِيمُ"
NBSP = " "
ELLIPSIS = "…"

_MARKS = re.compile("[ً-ٰٟۖ-ۭـ]")
_LETTER = re.compile("[ء-يٱ-ۓ]")
_SPLIT = re.compile(r"[\s\-'’·]+")


def bare(t: str) -> str:
    """Arabic letters only (no tashkeel / Quranic marks), for comparisons."""
    return _MARKS.sub("", t)


def norm(t: str) -> str:
    """Tolerant form: "husary" ~ "Al-Hussary", "alafasy" ~ "Alafasi", tashkeel ignored."""
    t = bare(t.casefold()).replace("ou", "u").replace("y", "i").replace("ee", "i").replace("oo", "u")
    t = re.sub(r"[^\w]", "", t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا"))
    return re.sub(r"(.)\1+", r"\1", t)


def _skeleton(w: str) -> str:
    w = norm(w)
    if len(w) > 4 and (w.startswith("al") or w.startswith("el")): w = w[2:]
    if len(w) > 3 and w.startswith("ال"): w = w[2:]
    return (w[0] + re.sub("[aeiou]", "", w[1:])) if re.match("[a-z]", w) else w


def name_match(query: str, text: str) -> bool:
    """'ahmed bin taleb' ~ 'Ahmad Talib bin Humaid', 'husary' ~ 'Al-Hussary', any word order."""
    qs = [_skeleton(x) for x in _SPLIT.split(query) if x.strip()]
    ts = [_skeleton(x) for x in _SPLIT.split(text) if x.strip()]
    whole = "".join(ts)
    return all(any(t.startswith(q) or (len(q) > 2 and q in t) for t in ts) or (len(q) > 3 and q in whole)
               for q in qs if q)


def ar_digits(n: int) -> str:
    return "".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in str(n))


def tokens(text: str) -> list[str]:
    """Display words of a verse. Stand-alone pause marks (ۚ ۖ ۗ …) stick to the previous word,
    so word positions line up with quran.com word timings."""
    out: list[str] = []
    for w in text.split(" "):
        if not w: continue
        if out and not _LETTER.search(w): out[-1] += " " + w
        else: out.append(w)
    return out


def strip_basmala(first_ayah: str, surah: int) -> str:
    """The text API prefixes verse 1 with the basmala; it is shown separately (timing "verse 0")."""
    t = first_ayah.replace("﻿", "").strip()
    w = t.split(" ")
    if surah not in (1, 9) and len(w) > 4 and bare(" ".join(w[:4])) == bare(BASMALA):
        return " ".join(w[4:])
    return t


def verse_with_marker(ar: str, n: int) -> str:
    """Verse text with its end-of-verse number, kept on the last word."""
    return f"{ar}{NBSP}﴿{ar_digits(n)}﴾"


def intro_text(surah: int) -> str:
    """What is recited before verse 1."""
    return ISTIADHA if surah in (1, 9) else BASMALA
