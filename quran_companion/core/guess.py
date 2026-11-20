"""Guess the surah and the reciter from a video or file title. Pure functions.

"سورة الكهف كاملة - مشاري العفاسي", "Surah Al-Kahf | Mishary Rashid Alafasy",
"Yasser Al Dossary - Surat Yasin", "018 Al-Kahf.mp3".
"""
import re

from .models import Reciter, SurahInfo
from .text import _skeleton, bare, name_match, norm

_SURAH_WORD = re.compile(r"(?:سورة|سوره|surah|surat|sura|soorah|sourate)\s*", re.I)
_EN_VARIANTS = {   # common spellings that the vowel-tolerant match would miss
    36: ("yasin", "yaseen", "ya sin", "yassin"), 1: ("fatiha", "fatihah", "fateha"), 2: ("baqara", "baqarah", "bakara"),
    18: ("kahf", "kahaf"), 55: ("rahman", "rahmaan"), 56: ("waqia", "waqiah", "waqiaa", "waqiah"), 67: ("mulk",),
    112: ("ikhlas", "ikhlaas"), 113: ("falaq",), 114: ("nas", "naas"), 3: ("imran", "imraan", "al imran"),
}


def _ar_key(name: str) -> str:
    w = norm(bare(name)).replace("ة", "ه").replace("ى", "ي")
    return w[2:] if w.startswith("ال") and len(w) > 3 else w


def _en_words(t: str) -> list[str]:
    return [_skeleton(w) for w in re.split(r"[^a-zA-Z]+", t) if w]


def guess_surah(title: str, surahs: list[SurahInfo]) -> int | None:
    if not title: return None
    t = title.replace("ـ", "")
    # 1. Arabic "سورة X"
    for m in re.finditer(r"سور[ةه]\s+([^\s\-|–—_()\[\]]+(?:\s+[^\s\-|–—_()\[\]]+)?)", t):
        words = m.group(1).split()
        for cand in (" ".join(words), words[0]):
            key = _ar_key(cand.replace(" ", ""))
            hit = [s.number for s in surahs if _ar_key(s.short_name.replace(" ", "")) == key]
            if hit: return hit[0]
    # 2. Arabic name anywhere (long names only, short ones are too ambiguous)
    ar_title = {_ar_key(w) for w in re.findall(r"[ء-ي]+", bare(t))}
    hits = [s.number for s in surahs if len(_ar_key(s.short_name)) >= 4 and _ar_key(s.short_name) in ar_title]
    if len(hits) == 1: return hits[0]
    # 3. English, preferably right after "surah"
    low = t.lower()
    after = [m.end() for m in _SURAH_WORD.finditer(low)]
    for start in after + [0]:
        seg = low[start:start + 40] if start else low
        words = _en_words(seg)
        joined = "".join(words)
        best = None
        for s in surahs:
            names = [s.english] + list(_EN_VARIANTS.get(s.number, ()))
            for nm in names:
                k = "".join(_en_words(nm))
                if len(k) < 3 and not start: continue
                ok = (joined.startswith(k) if start else (k in words or (len(k) >= 5 and k in joined)))
                if ok and (best is None or len(k) > best[0]): best = (len(k), s.number)
        if best: return best[1]
    # 4. a number: "surah 18", "018 ...", "18-"
    num = re.search(r"(?:surah|surat|sura|سورة)\s*(\d{1,3})\b", low) or re.match(r"\s*0*(\d{1,3})(?:\D|$)", low)
    if num and 1 <= int(num.group(1)) <= 114: return int(num.group(1))
    return None


def guess_reciter(title: str, reciters: list[Reciter]) -> Reciter | None:
    """The reciter whose (English or Arabic) name appears in the title; the longest name wins."""
    if not title: return None
    best: tuple[int, Reciter] | None = None
    ar_title = norm(bare(title))
    for r in reciters:
        score = 0
        if r.en and len(r.en) > 4 and name_match(r.en, title): score = len(r.en)
        ar = norm(bare(r.ar))
        if len(ar) > 4 and ar in ar_title: score = max(score, len(ar) + 1)
        if not score:   # family name alone ("Alafasy", "العفاسي") is usually enough
            last_en = r.en.split()[-1] if r.en else ""
            last_ar = bare(r.ar).split()[-1] if r.ar else ""
            if len(last_en) > 5 and name_match(last_en, title): score = len(last_en) - 2
            elif len(last_ar) > 4 and norm(last_ar) in ar_title: score = len(last_ar) - 2
        if score and (best is None or score > best[0]): best = (score, r)
    return best[1] if best else None


def clean_title(title: str, limit: int = 70) -> str:
    """A short name for a video title: its first two parts ("A | B | C" -> "A · B"), without
    hashtags, emoji-like symbols and repeated separators."""
    t = re.sub(r"#\S+", "", title or "")
    t = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", t)
    parts = [p.strip(" -–—_.") for p in re.split(r"\s*(?:\|\|?|｜|•|–|—)\s*", t)]
    parts = [p for p in parts if p]
    out = " · ".join(parts[:2]) if parts else (title or "").strip()
    return out if len(out) <= limit else out[:limit - 1].rstrip() + "…"


def same_video(a: str, b: str) -> bool:
    """Same YouTube video even if the links differ (&t=, &list=, youtu.be)."""
    def vid(u: str) -> str:
        m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{6,})", u or "")
        return m.group(1) if m else (u or "").split("#")[0].split("&")[0]
    return bool(a and b) and vid(a) == vid(b)
