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
        self.on_state_changed = None

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

    def set_enabled(self, enabled: bool, emit: bool = True):
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

        if emit and callable(self.on_state_changed):
            self.on_state_changed(bool(enabled))


    def is_enabled(self) -> bool:
        return bool(self.enabled_state)

    def set_checked(self, enabled: bool):
        # Used while loading settings; do not sync to Pi during initial load.
        self.set_enabled(bool(enabled), emit=False)


class TransferSnakeTabs(QFrame):
    """Two-option transfer popup tab selector with Auto-Capture-style snake animation."""

    def __init__(self, labels, parent=None, compact_mode: bool = False):
        super().__init__(parent)
        self.labels = list(labels)
        self.compact_mode = compact_mode
        self.current_index = 0
        self.anim = None
        self.on_index_changed = None

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

        self.buttons = []
        for idx, label in enumerate(self.labels):
            btn = QPushButton(str(label))
            btn.setObjectName("SegmentButtonActive" if idx == 0 else "SegmentButtonInactive")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setMinimumHeight(34 if not compact_mode else 30)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked=False, i=idx: self.set_index(i))
            self.buttons.append(btn)
            layout.addWidget(btn, 1)

    def segment_rect(self, index: int) -> QRect:
        margin = 3
        gap = 3
        count = max(1, len(self.buttons))
        wrap_w = max(0, self.width())
        wrap_h = max(0, self.height())
        total_gap = gap * (count - 1)
        segment_w = max(1, int((wrap_w - (margin * 2) - total_gap) / count))
        segment_h = max(1, wrap_h - (margin * 2))
        x = margin + (segment_w + gap) * max(0, min(index, count - 1))
        return QRect(x, margin, segment_w, segment_h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.indicator.setGeometry(self.segment_rect(self.current_index))
        self.indicator.lower()

    def set_index(self, index: int, emit: bool = True):
        index = max(0, min(int(index), max(0, len(self.buttons) - 1)))
        if self.current_index == index:
            return

        start = self.segment_rect(self.current_index)
        target = self.segment_rect(index)
        self.current_index = index

        for i, btn in enumerate(self.buttons):
            active = i == index
            btn.setChecked(active)
            btn.setObjectName("SegmentButtonActive" if active else "SegmentButtonInactive")
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

        if emit and callable(self.on_index_changed):
            self.on_index_changed(index)

    def set_checked(self, index: int):
        self.set_index(index, emit=False)

class ProgressRing(QWidget):
    """Smooth animated countdown ring.

    The label can still update every second, but the arc itself interpolates
    smoothly between values so it does not jump.
    """

    def __init__(self, total_seconds=60, start_seconds=17):
        super().__init__()
        self.total_seconds = max(1, total_seconds)
        self.time_left = max(0, start_seconds)
        self._display_time_left = float(self.time_left)
        self._ring_anim = None
        self.setMinimumSize(100, 100)

    def get_display_time_left(self):
        return self._display_time_left

    def set_display_time_left(self, value):
        self._display_time_left = max(0.0, float(value))
        self.update()

    displayTimeLeft = Property(float, get_display_time_left, set_display_time_left)

    def set_time_left(self, seconds: int, animate: bool = True):
        seconds = max(0, int(seconds))
        self.time_left = seconds

        if not animate:
            if self._ring_anim is not None:
                self._ring_anim.stop()
            self.set_display_time_left(float(seconds))
            return

        if self._ring_anim is not None:
            self._ring_anim.stop()

        self._ring_anim = QPropertyAnimation(self, b"displayTimeLeft", self)
        # Use a full second so the arc reaches the next value smoothly
        # exactly when the label changes to the next second.
        self._ring_anim.setDuration(1000)
        self._ring_anim.setStartValue(float(self._display_time_left))
        self._ring_anim.setEndValue(float(seconds))
        self._ring_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._ring_anim.start()

    def set_total_seconds(self, total_seconds: int):
        self.total_seconds = max(1, int(total_seconds))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = min(self.width(), self.height()) - max(12, int(min(self.width(), self.height()) * 0.055))
        x = (self.width() - size) / 2
        y = (self.height() - size) / 2
        rect = QRectF(x, y, size, size)

        pen_w = max(4, int(size * 0.035))
        painter.setPen(QPen(QColor(255, 255, 255, 70), pen_w))
        painter.drawEllipse(rect)

        progress = self._display_time_left / self.total_seconds if self.total_seconds else 0
        progress = max(0.0, min(1.0, progress))

        arc_pen = QPen(QColor("#FFFFFF"), pen_w)
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
