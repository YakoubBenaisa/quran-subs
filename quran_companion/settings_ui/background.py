"""Run blocking work on a thread pool and deliver the result on the Qt UI thread."""
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from PySide6.QtCore import QObject, Signal


class Background(QObject):
    _deliver = Signal(object, object)

    def __init__(self, workers: int = 3):
        super().__init__()
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self._deliver.connect(lambda cb, res: cb(res))

    def run(self, fn: Callable[[], object], done: Callable[[object], None] | None = None) -> None:
        """`done(result)` runs on the UI thread; result is the exception if `fn` raised."""
        def job():
            try:
                res = fn()
            except Exception as e:  # noqa: BLE001 - handed to the callback
                res = e
            if done: self._deliver.emit(done, res)
        self.pool.submit(job)

    def call_soon(self, cb: Callable[[object], None], value: object) -> None:
        """Deliver `value` to `cb` on the UI thread (safe to call from any thread)."""
        self._deliver.emit(cb, value)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
