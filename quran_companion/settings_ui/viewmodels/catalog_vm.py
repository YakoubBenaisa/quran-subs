"""Reciters, surahs and translations for the pickers; loaded once and kept across window rebuilds."""
from PySide6.QtCore import QObject, Signal

from ...core.models import Ayah, Reciter, SurahInfo, Translation
from ...core.text import name_match
from ...data.repository import QuranRepository
from ..background import Background

SAMPLE_SURAH, SAMPLE_AYAH, SAMPLE_TRANSLATION = 2, 255, "en.sahih"   # Ayat al-Kursi for the preview


class CatalogViewModel(QObject):
    loaded = Signal()
    failed = Signal(str)
    sample_loaded = Signal(str, str, int)

    def __init__(self, repo: QuranRepository, bg: Background):
        super().__init__()
        self.repo, self.bg = repo, bg
        self.reciters: list[Reciter] = []
        self.surahs: list[SurahInfo] = []
        self.translations: list[Translation] = []
        self.sample: tuple[str, str, int] | None = None
        self.ready = False

    def load(self, translation: str = "") -> None:
        if self.ready:
            self.loaded.emit(); return
        self.bg.run(lambda: (self.repo.reciters(), self.repo.surahs(), self.repo.translations()), self._on_loaded)
        self.bg.run(lambda: self.repo.text.surah_text(SAMPLE_SURAH, translation or SAMPLE_TRANSLATION)[SAMPLE_AYAH],
                    self._on_sample)

    def _on_loaded(self, res) -> None:
        if isinstance(res, Exception):
            self.failed.emit(str(res)); return
        self.reciters, self.surahs, self.translations = res
        self.ready = True
        self.loaded.emit()

    def _on_sample(self, res) -> None:
        if isinstance(res, Ayah):
            self.sample = (res.ar, res.tr, res.n)
            self.sample_loaded.emit(res.ar, res.tr, res.n)

    def find_reciter(self, rid: int) -> Reciter | None:
        return self.repo.find_reciter(rid) if self.reciters else None

    def surah(self, n: int) -> SurahInfo | None:
        return self.surahs[n - 1] if 0 < n <= len(self.surahs) else None

    @staticmethod
    def matches(query: str, rec: Reciter) -> bool:
        q = query.strip()
        return not q or name_match(q, rec.search_text())
