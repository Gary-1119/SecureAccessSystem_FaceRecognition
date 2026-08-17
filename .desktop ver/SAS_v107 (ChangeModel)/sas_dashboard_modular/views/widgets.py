from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QObject, QTimer, QRect
from PySide6.QtGui import QFont, QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget


class ExportCircleSpinnerWidget(QWidget):
    """Pi-connectivity style loading ring with a centre icon."""

    def __init__(self, parent=None, size: int = 112, icon_text: str = "⇧"):
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self._icon_text = icon_text
        self.setFixedSize(size, size)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _tick(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def stop(self):
        try:
            self.timer.stop()
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)

        # Soft outer track
        base_pen = QPen(QColor(196, 199, 199, 150), 5)
        painter.setPen(base_pen)
        painter.drawEllipse(rect)

        # Animated arc
        arc_pen = QPen(QColor(0, 0, 0, 230), 5)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, int(-self._angle * 16), int(110 * 16))

        # Centre icon circle
        center = self.rect().center()
        inner_radius = int(self._size * 0.22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0))
        painter.drawEllipse(center, inner_radius, inner_radius)

        painter.setPen(QColor(255, 255, 255))
        font = QFont()
        font.setPointSize(17 if self._size >= 100 else 14)
        font.setBold(True)
        painter.setFont(font)

        icon_rect = QRect(
            center.x() - inner_radius,
            center.y() - inner_radius,
            inner_radius * 2,
            inner_radius * 2,
        )
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, self._icon_text)

        painter.end()



class SftpEnterKeyFilter(QObject):
    """Keep the SFTP dialog open when Enter is pressed and trigger Transfer instead."""

    def __init__(self, trigger_callback, parent=None):
        super().__init__(parent)
        self.trigger_callback = trigger_callback

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Type.KeyPress and event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            ):
                self.trigger_callback()
                event.accept()
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


