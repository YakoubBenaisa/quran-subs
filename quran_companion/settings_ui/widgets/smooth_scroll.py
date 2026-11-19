from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt


class SmoothScroll(QObject):
    """Animated mouse-wheel scrolling (touchpads keep their native pixel scrolling)."""
    def __init__(self, area, step=1.1):
        super().__init__(area)
        self.sb, self.step, self.target = area.verticalScrollBar(), step, None
        self.anim = QPropertyAnimation(self.sb, b"value", self)
        self.anim.setDuration(320); self.anim.setEasingCurve(QEasingCurve.OutCubic)
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Wheel or ev.modifiers() & Qt.ControlModifier: return False
        if not ev.pixelDelta().isNull() and ev.phase() != Qt.NoScrollPhase: return False
        d = ev.angleDelta().y()
        if not d or self.sb.maximum() <= 0: return False
        base = self.target if (self.anim.state() == QAbstractAnimation.Running and self.target is not None) else self.sb.value()
        self.target = max(self.sb.minimum(), min(self.sb.maximum(), base - d * self.step))
        self.anim.stop(); self.anim.setStartValue(self.sb.value()); self.anim.setEndValue(int(self.target)); self.anim.start()
        return True
