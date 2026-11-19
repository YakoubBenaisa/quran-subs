"""Splits a verse into pages of at most N lines at a fixed text size.

Rules:
  * the text never shrinks; a verse longer than `max_lines` lines becomes several pages
  * pages are balanced: 7 lines with max 3 -> 3+2+2, never 3+3+1
  * every page but the last ends with "…"
  * the translation is split across the pages in proportion, and shrinks (down to 70%) to fit `tr_lines`
"""
from typing import Protocol

from ..core.models import Page
from ..core.text import ELLIPSIS, tokens

TR_SCALES = (1.0, 0.9, 0.8, 0.7)


class TextMeasurer(Protocol):
    def width(self, text: str, kind: str, scale: float = 1.0) -> float:
        """Rendered width in pixels. kind: "ar" (Quran text) or "tr" (translation)."""
        ...


def wrap(words: list[str], measure, maxw: float) -> list[list[str]]:
    lines: list[list[str]] = []
    cur: list[str] = []
    for w in words:
        if cur and measure(" ".join(cur + [w])) > maxw:
            lines.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur: lines.append(cur)
    return lines


def balance(lines: list, max_lines: int) -> list[list]:
    n_pages = -(-len(lines) // max_lines)
    if n_pages <= 1: return [lines]
    base, extra = divmod(len(lines), n_pages)
    groups, i = [], 0
    for k in range(n_pages):
        n = base + (1 if k < extra else 0)
        groups.append(lines[i:i + n]); i += n
    return groups


class Paginator:
    def __init__(self, measurer: TextMeasurer, max_width: float, max_lines: int = 3, tr_lines: int = 2):
        self.m, self.maxw = measurer, max_width
        self.max_lines, self.tr_lines = max(1, int(max_lines)), max(1, int(tr_lines))

    def fit_translation(self, words: list[str]) -> tuple[list[str], float]:
        if not words: return [], 1.0
        lines: list[list[str]] = []
        for scale in TR_SCALES:
            lines = wrap(words, lambda t, s=scale: self.m.width(t, "tr", s), self.maxw)
            if len(lines) <= self.tr_lines: return [" ".join(l) for l in lines], scale
        out = [" ".join(l) for l in lines[:self.tr_lines]]
        out[-1] += " " + ELLIPSIS
        return out, TR_SCALES[-1]

    def paginate(self, ar: str, tr: str = "") -> list[Page]:
        toks = tokens(ar)
        lines = wrap(toks, lambda t: self.m.width(t, "ar"), self.maxw) or [[]]
        groups = balance(lines, self.max_lines)
        total = sum(len(t) for t in toks) or 1
        pages, w0, acc = [], 0, 0
        for g in groups:
            pages.append(Page([" ".join(l) for l in g], w0=w0, frac=acc / total))
            w0 += sum(len(l) for l in g)
            acc += sum(len(t) for l in g for t in l)
        trw = tr.split() if tr else []
        for k, pg in enumerate(pages):
            f1 = pages[k + 1].frac if k + 1 < len(pages) else 1.0
            part = trw[round(pg.frac * len(trw)):round(f1 * len(trw))]
            if k + 1 < len(pages):
                pg.lines[-1] += " " + ELLIPSIS
                if part: part = part + [ELLIPSIS]
            pg.tr, pg.tr_scale = self.fit_translation(part)
        return pages

    def message(self, text: str, kind: str = "tr") -> Page:
        lines = [" ".join(l) for l in wrap(text.split(), lambda t: self.m.width(t, kind), self.maxw)]
        return Page(lines=lines) if kind == "ar" else Page(lines=[], tr=lines)


def apply_word_timing(pages: list[Page], fracs: dict[int, float] | None) -> list[Page]:
    """Use real word timings (word position -> fraction of the verse) for exact page turns."""
    if fracs:
        for pg in pages[1:]:
            if pg.w0 + 1 in fracs: pg.frac = fracs[pg.w0 + 1]
    return pages


def hint_page(ar: str, words: int) -> Page:
    toks = tokens(ar)
    k = max(1, int(words))
    return Page([" ".join(toks[:k]) + (" " + ELLIPSIS if len(toks) > k else "")])
