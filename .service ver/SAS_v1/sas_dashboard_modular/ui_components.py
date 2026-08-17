import sys
import ctypes
import platform
import os
import json
import html
import requests
import xml.etree.ElementTree as ET
from threading import Thread
from datetime import datetime

try:
    import cv2
except Exception:
    cv2 = None

from PySide6.QtCore import (
    Qt, QTimer, QDateTime, QRectF, QRect, QPoint,
    QPropertyAnimation, QEasingCurve, Property, QObject, Signal
)
from PySide6.QtGui import (
    QFont, QPainter, QPen, QColor, QIcon, QPixmap, QImage, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMainWindow,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QWidget,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QLineEdit,
    QCheckBox,
    QDialog,
    QGraphicsBlurEffect,
)

from app_config import Theme

class GlassCard(QFrame):
    def __init__(self, green_border: bool = False):
        super().__init__()
        self.setObjectName("GlassCardGreen" if green_border else "GlassCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


class InfoLabel(QLabel):
    def __init__(self, title: str, value: str, scale: float = 1.0):
        super().__init__()
        self.setObjectName("InfoLabel")
        title_size = max(8, int(10 * scale))
        value_size = max(10, int(14 * scale))
        self.setText(
            f"<span style='font-size:{title_size}px; line-height:{title_size + 3}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>{title}</span>"
            f"<br><span style='font-size:{value_size}px; line-height:{value_size + 5}px; color:{Theme.TEXT}; font-weight:700;'>{value}</span>"
        )


class TopNavButton(QPushButton):
    def __init__(self, text: str, active: bool = False):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.set_active(active)

    def set_active(self, active: bool):
        self.setChecked(active)
        self.setObjectName("TopNavActive" if active else "TopNav")
        self.style().unpolish(self)
        self.style().polish(self)


class FlipCircleLabel(QWidget):
    """Draws a circle face as a horizontally scaled pixmap.

    This avoids the old clipped-circle problem because the pixmap is compressed
    around the centre instead of the real widget being cut by its parent.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale_x = 1.0
        self._pixmap = QPixmap()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    def get_scale_x(self):
        return self._scale_x

    def set_scale_x(self, value):
        self._scale_x = max(0.05, min(1.0, float(value)))
        self.update()

    scaleX = Property(float, get_scale_x, set_scale_x)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        full_w = self.width()
        full_h = self.height()
        draw_w = max(2, int(full_w * self._scale_x))
        x = (full_w - draw_w) // 2

        draw_rect = QRect(x, 0, draw_w, full_h)
        draw_rect_f = QRectF(draw_rect)

        # Clip to ellipse so the flip remains circle/coin shaped.
        path = QPainterPath()
        path.addEllipse(draw_rect_f)
        painter.setClipPath(path)

        painter.drawPixmap(draw_rect, self._pixmap)

        # Simple dark green rim so the green circle does not look flat/dry.
        rim_alpha = int(90 + (1.0 - self._scale_x) * 80)
        painter.setPen(QPen(QColor("#2F6F4F"), 3))
        painter.drawEllipse(draw_rect_f.adjusted(2, 2, -2, -2))

        # Thin inner soft highlight for a cleaner premium look, not a shadow.
        painter.setPen(QPen(QColor(255, 255, 255, int(35 * self._scale_x)), 1))
        painter.drawEllipse(draw_rect_f.adjusted(5, 5, -5, -5))


class AutoCaptureSegment(QFrame):
    """Two-option segmented control with smooth snake indicator."""

    def __init__(self, parent=None, compact_mode: bool = False):
        super().__init__(parent)
        self.compact_mode = compact_mode
        self.enabled_state = True
        self.anim = None

        self.setObjectName("SegmentedToggle")
        self.setFixedHeight(42 if not compact_mode else 38)

        self.indicator = QFrame(self)
        self.indicator.setObjectName("SegmentSnakeIndicator")
        self.indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.indicator.show()
        self.indicator.lower()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self.enabled_btn = QPushButton("Enabled")
        self.enabled_btn.setObjectName("SegmentButtonActive")

        self.disabled_btn = QPushButton("Disabled")
        self.disabled_btn.setObjectName("SegmentButtonInactive")

        for btn in (self.enabled_btn, self.disabled_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setMinimumHeight(34 if not compact_mode else 30)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.enabled_btn.setChecked(True)
        self.disabled_btn.setChecked(False)

        self.enabled_btn.clicked.connect(lambda: self.set_enabled(True))
        self.disabled_btn.clicked.connect(lambda: self.set_enabled(False))

        layout.addWidget(self.enabled_btn, 1)
        layout.addWidget(self.disabled_btn, 1)

    def segment_rect(self, enabled: bool) -> QRect:
        margin = 3
        gap = 3
        wrap_w = max(0, self.width())
        wrap_h = max(0, self.height())

        segment_w = max(1, int((wrap_w - (margin * 2) - gap) / 2))
        segment_h = max(1, wrap_h - (margin * 2))
        x = margin if enabled else margin + segment_w + gap
        return QRect(x, margin, segment_w, segment_h)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Critical first-load fix:
        # always force the indicator to exactly one segment after layout resize.
        self.indicator.setGeometry(self.segment_rect(self.enabled_state))
        self.indicator.lower()

    def set_enabled(self, enabled: bool):
        if self.enabled_state == enabled:
            return

        start = self.segment_rect(self.enabled_state)
        target = self.segment_rect(enabled)

        self.enabled_state = enabled

        # Text state updates immediately, indicator animates behind it.
        self.enabled_btn.setChecked(enabled)
        self.disabled_btn.setChecked(not enabled)

        self.enabled_btn.setObjectName("SegmentButtonActive" if enabled else "SegmentButtonInactive")
        self.disabled_btn.setObjectName("SegmentButtonInactive" if enabled else "SegmentButtonActive")

        for btn in (self.enabled_btn, self.disabled_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

        left = min(start.x(), target.x())
        right = max(start.x() + start.width(), target.x() + target.width())
        mid = QRect(left, target.y(), right - left, target.height())

        if self.anim is not None:
            self.anim.stop()

        self.indicator.show()
        self.indicator.setGeometry(start)
        self.indicator.lower()

        self.anim = QPropertyAnimation(self.indicator, b"geometry", self)
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.setStartValue(start)
        self.anim.setKeyValueAt(0.45, mid)
        self.anim.setEndValue(target)
        self.anim.start()


class ProgressRing(QWidget):
    def __init__(self, total_seconds=60, start_seconds=17):
        super().__init__()
        self.total_seconds = total_seconds
        self.time_left = start_seconds
        self.setMinimumSize(100, 100)

    def set_time_left(self, seconds: int):
        self.time_left = max(0, seconds)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = min(self.width(), self.height()) - 12
        x = (self.width() - size) / 2
        y = (self.height() - size) / 2
        rect = QRectF(x, y, size, size)

        painter.setPen(QPen(QColor("#C4C7C7"), 4))
        painter.drawEllipse(rect)

        progress = self.time_left / self.total_seconds if self.total_seconds else 0
        arc_pen = QPen(QColor(Theme.PRIMARY), 4)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, 90 * 16, int(-360 * progress * 16))


class FadeStack(QStackedWidget):
    """Smooth horizontal slide transition for Dashboard / Face Recognition / Settings."""

    def __init__(self):
        super().__init__()
        self._animating = False
        self._current_anim = None
        self._next_anim = None
        self._fade_anim = None

    def fade_to(self, widget: QWidget):
        """Keep old method name, but perform a smooth slide transition."""
        self.slide_to(widget)

    def slide_to(self, widget: QWidget):
        if self.currentWidget() == widget or self._animating:
            return

        current = self.currentWidget()
        if current is None:
            self.setCurrentWidget(widget)
            return

        current_index = self.currentIndex()
        next_index = self.indexOf(widget)

        direction = 1 if next_index > current_index else -1
        w = self.width()
        h = self.height()

        current_rect = QRect(0, 0, w, h)
        current_end = QRect(-direction * w, 0, w, h)
        next_start = QRect(direction * w, 0, w, h)
        next_end = QRect(0, 0, w, h)

        widget.setGeometry(next_start)
        widget.show()
        widget.raise_()

        self._animating = True

        self._current_anim = QPropertyAnimation(current, b"geometry", self)
        self._current_anim.setDuration(260)
        self._current_anim.setStartValue(current_rect)
        self._current_anim.setEndValue(current_end)
        self._current_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._next_anim = QPropertyAnimation(widget, b"geometry", self)
        self._next_anim.setDuration(260)
        self._next_anim.setStartValue(next_start)
        self._next_anim.setEndValue(next_end)
        self._next_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finish():
            self.setCurrentWidget(widget)
            widget.setGeometry(next_end)
            current.hide()
            self._animating = False

        self._next_anim.finished.connect(finish)
        self._current_anim.start()
        self._next_anim.start()
