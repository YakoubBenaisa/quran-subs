"""Downloading surahs for offline use, with progress and cancel."""
import os
import subprocess

from PySide6.QtCore import QObject, Signal

from ...core.i18n import T
from ...core.models import Reciter
from ...data.library import LibraryStats
from ...data.repository import QuranRepository
from ..background import Background


class DownloadsViewModel(QObject):
    progress = Signal(int, int, str)   # done, total, message
    saved = Signal()                   # one more surah on disk
    finished = Signal(str)             # final message
    busy_changed = Signal(bool)

    def __init__(self, repo: QuranRepository, bg: Background):
        super().__init__()
        self.repo, self.bg = repo, bg
        self.busy = False
        self._cancel = False

    @property
    def folder(self) -> str:
        return self.repo.library.root

    def stats(self, rec: Reciter) -> LibraryStats:
        return self.repo.library.stats(rec)

    def library(self, reciters: list[Reciter]) -> list[tuple[Reciter, LibraryStats]]:
        return [(r, st) for r in reciters if (st := self.stats(r)).surahs]

    def start(self, rec: Reciter, surahs: list[int], translation: str) -> None:
        if self.busy: return
        self.busy, self._cancel = True, False
        self.busy_changed.emit(True)
        total = len(surahs)

        def work():
            fails = 0
            for i, s in enumerate(surahs):
                if self._cancel: break
                try:
                    self.repo.download_surah(rec, s, translation,
                                             lambda got, tot, i=i, s=s: self.bg.call_soon(self._progress, (i, total, T(
                                                 "dl_progress", s=s, mb=f"{got / 1e6:.1f}" + (f" / {tot / 1e6:.1f}" if tot else "")))),
                                             lambda: self._cancel)
                except InterruptedError:
                    break
                except Exception as e:  # noqa: BLE001 - reported to the user, next surah continues
                    fails += 1
                    self.bg.call_soon(self._progress, (i, total, T("dl_failed", s=s, err=e)))
                self.bg.call_soon(self._saved, (i + 1, total))
            if self._cancel: return T("dl_cancelled")
            return T("dl_done_fail", n=fails) if fails else T("dl_done")

        self.bg.run(work, self._done)

    def _progress(self, v) -> None:
        self.progress.emit(*v)

    def _saved(self, v) -> None:
        self.progress.emit(v[0], v[1], ""); self.saved.emit()

    def _done(self, msg) -> None:
        self.busy = False
        self.busy_changed.emit(False)
        self.finished.emit(str(msg))

    def cancel(self) -> None:
        self._cancel = True

    def delete(self, rec: Reciter) -> None:
        self.repo.library.delete(rec)

    def open_folder(self) -> None:
        os.makedirs(self.folder, exist_ok=True)
        subprocess.Popen(["xdg-open", self.folder])
