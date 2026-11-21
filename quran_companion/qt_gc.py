"""Python's garbage collector runs in whichever thread happens to allocate, and freeing a Qt object from a
worker thread (downloads, the command server) crashes Qt. So automatic collection is turned off and run
from a timer on the Qt main thread instead, at the same thresholds Python would use."""
import gc

from PySide6.QtCore import QObject, QTimer


class MainThreadGC(QObject):
    def __init__(self, interval_ms: int = 500):
        super().__init__()
        self._thresholds = gc.get_threshold()
        gc.disable()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(interval_ms)

    def check(self) -> None:
        counts = gc.get_count()
        for gen in (2, 1, 0):
            if counts[gen] > self._thresholds[gen]:
                gc.collect(gen)
                return


def install(app: QObject) -> MainThreadGC:
    g = MainThreadGC()
    g.setParent(app)
    return g
