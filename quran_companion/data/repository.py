"""QuranRepository: the single entry point the rest of the app uses for data."""
from dataclasses import dataclass

from .. import paths
from ..core.models import MINE_BASE, MyRecitation, Reciter, SurahData, SurahInfo, Translation
from .alquran_cloud import AlQuranCloud
from .http import CachedHttp
from .library import Library
from .mp3quran import Mp3Quran
from .my_recitations import MyRecitations
from .qurancom import QuranCom
from .sources import ReciterSource, TextSource, TimingSource, WordTimingSource


class NotInRecording(LookupError):
    """The chosen surah is not in the user's recording."""
    def __init__(self, have: int):
        super().__init__(f"this recording has surah {have} only"); self.have = have


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
                 words: WordTimingSource, library: Library, mine: MyRecitations | None = None):
        self.text, self.reciter_src, self.timing_src, self.words, self.library = text, reciters, timings, words, library
        self.mine = mine
        self._reciters: list[Reciter] | None = None

    # catalogue
    def timed_reciters(self) -> list[Reciter]:
        """Reciters with published verse timings."""
        if self._reciters is None: self._reciters = self.reciter_src.reciters()
        return self._reciters

    def reciters(self) -> list[Reciter]:
        """The user's own recordings first, then the reciters with timings."""
        return [m.as_reciter() for m in self.my_recitations()] + self.timed_reciters()

    def my_recitations(self) -> list[MyRecitation]:
        return self.mine.all() if self.mine else []

    def my_recitation(self, rec: Reciter | int) -> MyRecitation | None:
        rid = rec.id if isinstance(rec, Reciter) else rec
        return self.mine.get(rid - MINE_BASE) if self.mine and rid >= MINE_BASE else None

    def find_reciter(self, rid: int) -> Reciter:
        m = self.my_recitation(rid)
        if m: return m.as_reciter()
        recs = self.timed_reciters()
        return (next((r for r in recs if r.id == rid), None)
                or next((r for r in recs if "afasy" in r.folder), None) or recs[0])

    def surahs(self) -> list[SurahInfo]:
        return self.text.surahs()

    def translations(self) -> list[Translation]:
        return self.text.translations()

    # playback data
    def audio_source(self, rec: Reciter, surah: int) -> str:
        m = self.my_recitation(rec)
        if m: return m.audio
        return self.library.source(rec, surah, self.reciter_src.audio_url(rec, surah))

    def load(self, req: LoadRequest) -> tuple[Reciter, SurahData]:
        rec = self.find_reciter(req.reciter_id)
        m = self.my_recitation(rec)
        if m:
            if req.surah != m.surah: raise NotInRecording(m.surah)
            return rec, SurahData(req.surah, self.text.surah_text(req.surah, req.translation), list(m.timings))
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
    return QuranRepository(AlQuranCloud(http), mp3, mp3, QuranCom(http), Library(paths.library_dir(), http),
                           MyRecitations(paths.mine_dir()))
