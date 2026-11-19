"""Manual: silent; next/previous walks through the pages of a verse, then to the next verse."""
from .base import Mode


class ManualMode(Mode):
    def start(self, ayah: int) -> None:
        self.session.show(ayah, 0)

    def step(self, d: int) -> None:
        s = self.session
        n = s.cur or 0
        pages = s.pages_for(n) if n else []
        if d > 0 and n and s.page + 1 < len(pages):
            s.show(n, s.page + 1)
        elif d < 0 and n and s.page > 0:
            s.show(n, s.page - 1)
        else:
            m = max(1, min(n + d, len(s.data.ayahs)))
            s.show(m, 0 if d >= 0 or m == n else len(s.pages_for(m)) - 1)
