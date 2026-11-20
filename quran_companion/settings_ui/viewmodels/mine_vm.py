"""The user's own recordings: check a link or file, sync it (with progress and cancel), list, delete."""
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ...core.guess import same_video
from ...core.i18n import T
from ...core.models import MyRecitation
from ...data.media import MissingTool
from ...data.repository import QuranRepository
from ..background import Background


class MineViewModel(QObject):
    inspected = Signal(str, object)     # tag, sync.service.Inspection
    inspect_failed = Signal(str, str)   # tag, message
    progress = Signal(str, float)       # stage message, 0..1
    synced = Signal(object)             # MyRecitation
    sync_failed = Signal(str)
    busy_changed = Signal(bool)
    changed = Signal()                  # list of recordings changed

    def __init__(self, repo: QuranRepository, bg: Background, service_factory: Callable[[], object]):
        """service_factory() -> SyncService; created on first use (loads numpy)."""
        super().__init__()
        self.repo, self.bg, self._factory = repo, bg, service_factory
        self._service = None
        self.busy = False
        self._cancel = False
        self._inspect_id = 0

    @property
    def service(self):
        if self._service is None: self._service = self._factory()
        return self._service

    def recordings(self) -> list[MyRecitation]:
        return self.repo.my_recitations()

    # ------------------------------------------------------------ inspect
    def inspect(self, src: str, tag: str = "link") -> None:
        """tag tells the panels apart (the link panel and the browser panel share this view model)."""
        self._inspect_id += 1
        iid = self._inspect_id
        self.bg.run(lambda: self.service.inspect(src), lambda res: self._on_inspected(iid, tag, res))

    def _on_inspected(self, iid: int, tag: str, res) -> None:
        if iid != self._inspect_id: return       # a newer link was given meanwhile
        if isinstance(res, MissingTool): self.inspect_failed.emit(tag, T("need_ytdlp"))
        elif isinstance(res, Exception): self.inspect_failed.emit(tag, str(res) or type(res).__name__)
        else: self.inspected.emit(tag, res)

    def for_video(self, url: str) -> MyRecitation | None:
        """The recording made from this video, if any."""
        return next((m for m in self.recordings() if same_video(m.source, url)), None)

    # ------------------------------------------------------------ sync
    def sync(self, inspection, surah: int, ayah_from: int, ayah_to: int) -> None:
        if self.busy: return
        self.busy, self._cancel = True, False
        self.busy_changed.emit(True)

        def report(stage: str, f: float) -> None:
            self.bg.call_soon(self._progress, (T("stage_" + stage), f))

        self.bg.run(lambda: self.service.create(inspection, surah, ayah_from, ayah_to, progress=report,
                                                cancel=lambda: self._cancel), self._on_synced)

    def _progress(self, v) -> None:
        self.progress.emit(*v)

    def _on_synced(self, res) -> None:
        self.busy = False
        self.busy_changed.emit(False)
        if isinstance(res, InterruptedError): self.sync_failed.emit(T("dl_cancelled")); return
        if isinstance(res, MissingTool): self.sync_failed.emit(T("need_ytdlp")); return
        if isinstance(res, Exception): self.sync_failed.emit(T("sync_failed", err=str(res) or type(res).__name__)); return
        self.synced.emit(res)
        self.changed.emit()

    def cancel(self) -> None:
        self._cancel = True

    def delete(self, m: MyRecitation) -> None:
        if self.repo.mine: self.repo.mine.delete(m.id)
        self.changed.emit()

    @staticmethod
    def quality_text(m: MyRecitation) -> str:
        return T("q_" + m.quality())
