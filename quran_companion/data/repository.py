"""QuranRepository: the single entry point the rest of the app uses for data."""
from dataclasses import dataclass

from .. import paths
from ..core.models import Reciter, SurahData, SurahInfo, Translation
from .alquran_cloud import AlQuranCloud
from .http import CachedHttp
from .library import Library
from .mp3quran import Mp3Quran
from .qurancom import QuranCom
from .sources import ReciterSource, TextSource, TimingSource, WordTimingSource


@dataclass(frozen=True)
class LoadRequest:
    surah: int
    reciter_id: int
    translation: str = ""
    timings: bool = True      # needed by recite mode and "reciter's pace"
    word_sync: bool = False   # exact page turns
    timings_required: bool = True


class QuranRepository:
    def __init__(self, text: TextSource, reciters: ReciterSource, timings: TimingSource,
                 words: WordTimingSource, library: Library):
        self.text, self.reciter_src, self.timing_src, self.words, self.library = text, reciters, timings, words, library
        self._reciters: list[Reciter] | None = None

    # catalogue
    def reciters(self) -> list[Reciter]:
        if self._reciters is None: self._reciters = self.reciter_src.reciters()
        return self._reciters

    def find_reciter(self, rid: int) -> Reciter:
        recs = self.reciters()
        return (next((r for r in recs if r.id == rid), None)
                or next((r for r in recs if "afasy" in r.folder), None) or recs[0])

    def surahs(self) -> list[SurahInfo]:
        return self.text.surahs()

    def translations(self) -> list[Translation]:
        return self.text.translations()

    # playback data
    def audio_source(self, rec: Reciter, surah: int) -> str:
        return self.library.source(rec, surah, self.reciter_src.audio_url(rec, surah))

    def load(self, req: LoadRequest) -> tuple[Reciter, SurahData]:
        rec = self.find_reciter(req.reciter_id)
        data = SurahData(req.surah, self.text.surah_text(req.surah, req.translation))
        if req.timings:
            try:
                data.timings = self.timing_src.verse_timings(rec, req.surah)
            except Exception:
                if req.timings_required: raise
        if req.word_sync:
            try:
                data.word_fracs = self.words.word_fractions(rec, req.surah)
            except Exception:
                data.word_fracs = {}
        return rec, data

    # offline
    def download_surah(self, rec: Reciter, surah: int, translation: str, progress=None, cancel=lambda: False) -> None:
        """Audio + text + timings, so the surah plays without internet."""
        self.library.download(rec, surah, self.reciter_src.audio_url(rec, surah), progress, cancel)
        self.text.surah_text(surah, translation)
        self.timing_src.verse_timings(rec, surah)
        try:
            self.words.word_fractions(rec, surah)
        except Exception:
            pass


def default_repository() -> QuranRepository:
    http = CachedHttp(paths.cache_dir())
    mp3 = Mp3Quran(http)
    return QuranRepository(AlQuranCloud(http), mp3, mp3, QuranCom(http), Library(paths.library_dir(), http))
