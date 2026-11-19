"""Downloaded recitations on disk."""
import os
from dataclasses import dataclass
from typing import Callable

from ..core.models import Reciter
from .http import CachedHttp


@dataclass(frozen=True)
class LibraryStats:
    surahs: int
    megabytes: float


class Library:
    def __init__(self, root: str, http: CachedHttp):
        self.root, self.http = root, http

    def folder(self, rec: Reciter) -> str:
        return os.path.join(self.root, rec.slug)

    def path(self, rec: Reciter, surah: int) -> str:
        return os.path.join(self.folder(rec), f"{surah:03d}.mp3")

    def has(self, rec: Reciter, surah: int) -> bool:
        return os.path.exists(self.path(rec, surah))

    def source(self, rec: Reciter, surah: int, url: str) -> str:
        """Local file if downloaded, otherwise the stream URL."""
        return self.path(rec, surah) if self.has(rec, surah) else url

    def stats(self, rec: Reciter) -> LibraryStats:
        d = self.folder(rec)
        files = [os.path.join(d, x) for x in os.listdir(d) if x.endswith(".mp3")] if os.path.isdir(d) else []
        return LibraryStats(len(files), sum(os.path.getsize(x) for x in files) / 1e6)

    def download(self, rec: Reciter, surah: int, url: str, progress: Callable[[int, int], None] | None = None,
                 cancel: Callable[[], bool] = lambda: False) -> None:
        if not self.has(rec, surah):
            self.http.download(url, self.path(rec, surah), progress, cancel)

    def delete(self, rec: Reciter) -> None:
        d = self.folder(rec)
        if not os.path.isdir(d): return
        for x in os.listdir(d): os.unlink(os.path.join(d, x))
        os.rmdir(d)
