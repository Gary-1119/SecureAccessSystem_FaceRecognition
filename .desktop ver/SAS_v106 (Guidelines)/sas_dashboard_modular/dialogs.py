import sys
import time
import ctypes
import platform
import os
import json
import html
import requests
import xml.etree.ElementTree as ET
from threading import Event, Thread
from datetime import datetime

try:
    import cv2
except Exception:
    cv2 = None

from typing import cast

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
    QGraphicsDropShadowEffect,
    QSpacerItem,
)

from app_config import Theme

class LoginPopupDialog(QDialog):
    """Frameless login popup shown above a blurred dashboard."""

    def __init__(self, parent=None, compact_mode: bool = False):
        super().__init__(parent)
        self.compact_mode = compact_mode

        self.setObjectName("LoginPopupDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.resize(460 if not compact_mode else 410, 520 if not compact_mode else 470)
        self._popup_anim = None
        self._popup_geo_anim = None
        self.build_ui()

    def showEvent(self, event):
        super().showEvent(event)

        # Smooth popup effect: fade in + small upward motion.
        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 22, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(220)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(220)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("LoginPopupCard")
        outer.addWidget(card)

        self.card = card
        layout = QVBoxLayout(card)
        self.card_layout = layout
        layout.setContentsMargins(
            34 if not self.compact_mode else 26,
            32 if not self.compact_mode else 24,
            34 if not self.compact_mode else 26,
            30 if not self.compact_mode else 24,
        )
        layout.setSpacing(16 if not self.compact_mode else 12)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setObjectName("LoginCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        icon = QLabel("▣")
        icon.setObjectName("LoginShieldIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(56 if not self.compact_mode else 48, 56 if not self.compact_mode else 48)

        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        title = QLabel("SECURE ACCESS SYSTEM")
        title.setObjectName("LoginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Enter your credentials to manage security")
        subtitle.setObjectName("LoginSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QVBoxLayout()
        form.setSpacing(12 if not self.compact_mode else 10)

        ntid_label = QLabel("NTID")
        ntid_label.setObjectName("LoginFieldLabel")

        self.ntid_input = QLineEdit()
        self.ntid_input.setObjectName("LoginInput")
        self.ntid_input.setPlaceholderText("e.g. 1234567")
        self.ntid_input.setMinimumHeight(46 if not self.compact_mode else 40)

        password_top = QHBoxLayout()
        password_label = QLabel("Password")
        password_label.setObjectName("LoginFieldLabel")
        forgot = QLabel("Forgot Password?")
        forgot.setObjectName("LoginForgot")
        password_top.addWidget(password_label)
        password_top.addStretch()
        password_top.addWidget(forgot)

        password_row = QHBoxLayout()
        password_row.setSpacing(8)

        self.password_input = QLineEdit()
        self.password_input.setObjectName("LoginInput")
        self.password_input.setPlaceholderText("••••••••")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(46 if not self.compact_mode else 40)

        self.toggle_btn = QPushButton("Show")
        self.toggle_btn.setObjectName("LoginToggleButton")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setFixedSize(64 if not self.compact_mode else 56, 40 if not self.compact_mode else 36)
        self.toggle_btn.clicked.connect(self.toggle_password)

        password_row.addWidget(self.password_input, 1)
        password_row.addWidget(self.toggle_btn)

        self.status_label = QLabel("Administrator oversight enabled. Session monitoring active.")
        self.status_label.setObjectName("LoginStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        self.login_submit_btn = QPushButton("Login  →")
        self.login_submit_btn.setObjectName("LoginSubmitButton")
        self.login_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_submit_btn.setMinimumHeight(46 if not self.compact_mode else 40)
        self.login_submit_btn.clicked.connect(self.login_requested)
        self.login_submit_btn.setDefault(True)
        self.login_submit_btn.setAutoDefault(True)

        self.ntid_input.returnPressed.connect(self.login_requested)
        self.password_input.returnPressed.connect(self.login_requested)

        login_btn = self.login_submit_btn

        form.addWidget(ntid_label)
        form.addWidget(self.ntid_input)
        form.addLayout(password_top)
        form.addLayout(password_row)
        form.addWidget(login_btn)
        layout.addLayout(form)

        divider = QFrame()
        divider.setObjectName("LoginDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addWidget(self.status_label)

    def toggle_password(self):
        if self.password_input.echoMode() == QLineEdit.EchoMode.Password:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_btn.setText("Hide")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_btn.setText("Show")

    def login_requested(self):
        if hasattr(self, "login_submit_btn") and not self.login_submit_btn.isEnabled():
            return

        ntid = self.ntid_input.text().strip()
        password = self.password_input.text().strip()

        if not ntid:
            self.status_label.setText("Please enter your NTID.")
            self.ntid_input.setFocus()
            return

        if not password:
            self.status_label.setText("Please enter your password.")
            self.password_input.setFocus()
            return

        self.set_validation_state("Starting login validation...")

        parent = self.parent()
        if parent is not None and hasattr(parent, "_handle_login_from_popup"):
            parent._handle_login_from_popup(ntid, password, self)  # type: ignore[attr-defined]
        else:
            self.show_failed_state(
                "Login handler not found.",
                f"NTID={ntid}\nParent object does not expose _handle_login_from_popup()."
            )

    def set_validation_state(self, message: str):
        """Keep the login form visible while validation is running."""
        self.status_label.setText(message)
        if hasattr(self, "login_submit_btn"):
            self.login_submit_btn.setEnabled(False)
            self.login_submit_btn.setText("Checking...")

    def set_validation_message(self, message: str):
        self.status_label.setText(message)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _animate_state_change(self):
        """Small fade/move animation when this same popup changes state."""
        self.setWindowOpacity(0.0)
        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 18, end_geo.width(), end_geo.height())
        self.setGeometry(start_geo)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(220)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(220)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def _debug_box(self, debug_text: str):
        box = QFrame()
        box.setObjectName("InlineDebugBox")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(16, 12, 16, 12)
        box_layout.setSpacing(6)

        title = QLabel("DEBUG TRACE")
        title.setObjectName("InlineDebugTitle")

        body = QLabel(debug_text or "No debug trace.")
        body.setObjectName("InlineDebugText")
        body.setWordWrap(True)

        box_layout.addWidget(title)
        box_layout.addWidget(body)
        return box

    def show_success_state(self, ntid: str, role: str, debug_text: str):
        """Change this same login popup into the success UI."""
        if hasattr(self, "countdown_timer"):
            self.countdown_timer.stop()

        self._clear_layout(self.card_layout)
        self.resize(500 if not self.compact_mode else 430, 540 if not self.compact_mode else 500)
        self.seconds_left = 5

        brand = QLabel("SECURE ACCESS")
        brand.setObjectName("SuccessBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ring = QFrame()
        ring.setObjectName("SuccessOuterRing")
        ring.setFixedSize(90 if not self.compact_mode else 78, 90 if not self.compact_mode else 78)

        ring_layout = QVBoxLayout(ring)
        ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        check = QLabel("✓")
        check.setObjectName("SuccessCheckCircle")
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setFixedSize(62 if not self.compact_mode else 54, 62 if not self.compact_mode else 54)
        ring_layout.addWidget(check)

        ring_row = QHBoxLayout()
        ring_row.addStretch()
        ring_row.addWidget(ring)
        ring_row.addStretch()

        title = QLabel("Identity Confirmed")
        title.setObjectName("SuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.setAlignment(Qt.AlignmentFlag.AlignCenter)
        verified = QLabel("✓  VERIFIED")
        verified.setObjectName("SuccessBadge")
        badges.addWidget(verified)

        identity = QFrame()
        identity.setObjectName("IdentityCard")
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(16, 10, 16, 10)
        identity_layout.setSpacing(5)

        top = QHBoxLayout()
        id_text = QVBoxLayout()
        token_label = QLabel("SECURITY TOKEN")
        token_label.setObjectName("IdentityMeta")
        ntid_label = QLabel(f"NTID {ntid.upper()}")
        ntid_label.setObjectName("IdentityNtid")
        id_text.addWidget(token_label)
        id_text.addWidget(ntid_label)

        shield = QLabel("♜")
        shield.setObjectName("IdentityShield")
        shield.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shield.setFixedSize(30, 30)

        top.addLayout(id_text)
        top.addStretch()
        top.addWidget(shield)
        identity_layout.addLayout(top)

        divider = QFrame()
        divider.setObjectName("IdentityDivider")
        divider.setFixedHeight(1)
        identity_layout.addWidget(divider)

        access = QLabel(f"AUTHORIZED ACCESS • {role.upper()}")
        access.setObjectName("IdentityAccess")
        identity_layout.addWidget(access)

        continue_btn = QPushButton("Continue to Dashboard  →")
        continue_btn.setObjectName("SuccessPrimaryButton")
        continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        continue_btn.setMinimumHeight(44 if not self.compact_mode else 40)
        continue_btn.clicked.connect(self.accept)

        self.redirect_label = QLabel("Redirecting in 5 seconds")
        self.redirect_label.setObjectName("SuccessRedirect")
        self.redirect_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setObjectName("LoginCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)

        self.card_layout.addLayout(close_row)
        self.card_layout.addWidget(brand)
        self.card_layout.addLayout(ring_row)
        self.card_layout.addWidget(title)
        self.card_layout.addLayout(badges)
        success_msg = QLabel("Login successful. Your identity has been verified.")
        success_msg.setObjectName("SuccessRedirect")
        success_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        success_msg.setWordWrap(True)

        self.card_layout.addWidget(identity)
        self.card_layout.addWidget(success_msg)
        self.card_layout.addWidget(continue_btn)
        self.card_layout.addWidget(self.redirect_label)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._success_countdown)
        self.countdown_timer.start(1000)

        self._animate_state_change()

    def _success_countdown(self):
        self.seconds_left -= 1
        if self.seconds_left <= 0:
            self.countdown_timer.stop()
            self.accept()
            return
        self.redirect_label.setText(f"Redirecting in {self.seconds_left} seconds")

    def show_failed_state(self, reason: str, debug_text: str):
        """Change this same login popup into the failed UI."""
        if hasattr(self, "countdown_timer"):
            self.countdown_timer.stop()

        self._clear_layout(self.card_layout)
        self.resize(500 if not self.compact_mode else 430, 540 if not self.compact_mode else 500)

        brand = QLabel("SECURE ACCESS")
        brand.setObjectName("SuccessBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)

        fail = QLabel("!")
        fail.setObjectName("FailedCircle")
        fail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail.setFixedSize(78 if not self.compact_mode else 66, 78 if not self.compact_mode else 66)

        fail_row = QHBoxLayout()
        fail_row.addStretch()
        fail_row.addWidget(fail)
        fail_row.addStretch()

        title = QLabel("Authentication Failed")
        title.setObjectName("FailedTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        msg = QLabel(reason)
        msg.setObjectName("FailedReason")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)

        retry = QPushButton("Try Again")
        retry.setObjectName("FailedPrimaryButton")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.setMinimumHeight(48 if not self.compact_mode else 42)
        retry.clicked.connect(self.reject)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setObjectName("LoginCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)

        self.card_layout.addLayout(close_row)
        self.card_layout.addWidget(brand)
        self.card_layout.addLayout(fail_row)
        self.card_layout.addWidget(title)
        self.card_layout.addWidget(msg)
        self.card_layout.addWidget(retry)

        self._animate_state_change()


class LoginSuccessDialog(QDialog):
    """Premium login success popup based on the user's provided UI reference."""

    def __init__(self, parent=None, ntid: str = "", role: str = "User", compact_mode: bool = False):
        super().__init__(parent)
        self.ntid = ntid.upper()
        self.role = role
        self.compact_mode = compact_mode
        self.seconds_left = 5
        self._popup_anim = None
        self._popup_geo_anim = None

        self.setObjectName("LoginSuccessDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.resize(500 if not compact_mode else 430, 540 if not compact_mode else 500)
        self.build_ui()

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start(1000)

    def showEvent(self, event):
        super().showEvent(event)

        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 24, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(240)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(240)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("SuccessGlassPanel")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            40 if not self.compact_mode else 28,
            36 if not self.compact_mode else 28,
            40 if not self.compact_mode else 28,
            32 if not self.compact_mode else 26,
        )
        layout.setSpacing(20 if not self.compact_mode else 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        brand = QLabel("SECURE ACCESS")
        brand.setObjectName("SuccessBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        # Success ring
        ring_wrap = QWidget()
        ring_wrap.setFixedHeight(130 if not self.compact_mode else 112)
        ring_layout = QVBoxLayout(ring_wrap)
        ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ring = QFrame()
        ring.setObjectName("SuccessOuterRing")
        ring.setFixedSize(116 if not self.compact_mode else 98, 116 if not self.compact_mode else 98)

        ring_inner_layout = QVBoxLayout(ring)
        ring_inner_layout.setContentsMargins(0, 0, 0, 0)
        ring_inner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        check = QLabel("✓")
        check.setObjectName("SuccessCheckCircle")
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setFixedSize(80 if not self.compact_mode else 68, 80 if not self.compact_mode else 68)

        ring_inner_layout.addWidget(check)
        ring_layout.addWidget(ring)
        layout.addWidget(ring_wrap)

        title = QLabel("Identity Confirmed")
        title.setObjectName("SuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.setAlignment(Qt.AlignmentFlag.AlignCenter)

        verified = QLabel("✓  VERIFIED")
        verified.setObjectName("SuccessBadge")
        badges.addWidget(verified)
        layout.addLayout(badges)

        identity = QFrame()
        identity.setObjectName("IdentityCard")
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(22, 18, 22, 18)
        identity_layout.setSpacing(14)

        top = QHBoxLayout()
        id_text = QVBoxLayout()
        token_label = QLabel("SECURITY TOKEN")
        token_label.setObjectName("IdentityMeta")
        ntid_label = QLabel(f"NTID {self.ntid}")
        ntid_label.setObjectName("IdentityNtid")
        id_text.addWidget(token_label)
        id_text.addWidget(ntid_label)

        shield = QLabel("♜")
        shield.setObjectName("IdentityShield")
        shield.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shield.setFixedSize(42, 42)

        top.addLayout(id_text)
        top.addStretch()
        top.addWidget(shield)
        identity_layout.addLayout(top)

        divider = QFrame()
        divider.setObjectName("IdentityDivider")
        divider.setFixedHeight(1)
        identity_layout.addWidget(divider)

        bottom = QHBoxLayout()
        terminal_box = QVBoxLayout()
        terminal_label = QLabel("AUTHENTICATED TERMINAL")
        terminal_label.setObjectName("IdentityMeta")
        access_label = QLabel(f"AUTHORIZED ACCESS • {self.role.upper()}")
        access_label.setObjectName("IdentityAccess")
        terminal_box.addWidget(terminal_label)
        terminal_box.addWidget(access_label)

        session_id = QLabel("S-ID: 01-X9K")
        session_id.setObjectName("IdentitySession")

        bottom.addLayout(terminal_box)
        bottom.addStretch()
        bottom.addWidget(session_id)
        identity_layout.addLayout(bottom)

        layout.addWidget(identity)

        success_msg = QLabel("Login successful. Your identity has been verified.")
        success_msg.setObjectName("SuccessRedirect")
        success_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        success_msg.setWordWrap(True)
        layout.addWidget(success_msg)

        continue_btn = QPushButton("Continue to Dashboard  →")
        continue_btn.setObjectName("SuccessPrimaryButton")
        continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        continue_btn.setMinimumHeight(54 if not self.compact_mode else 48)
        continue_btn.clicked.connect(self.accept)
        layout.addWidget(continue_btn)

        small_line = QFrame()
        small_line.setObjectName("SuccessSmallLine")
        small_line.setFixedSize(120, 1)
        line_row = QHBoxLayout()
        line_row.addStretch()
        line_row.addWidget(small_line)
        line_row.addStretch()
        layout.addLayout(line_row)

        self.redirect_label = QLabel("Redirecting in 5 seconds")
        self.redirect_label.setObjectName("SuccessRedirect")
        self.redirect_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.redirect_label)

        footer = QHBoxLayout()
        stable = QLabel("●  SYSTEM STABLE")
        stable.setObjectName("SuccessFooterText")
        node = QLabel("/node_01/secure")
        node.setObjectName("SuccessFooterText")
        footer.addWidget(stable)
        footer.addStretch()
        footer.addWidget(node)
        layout.addStretch()
        layout.addLayout(footer)

    def update_countdown(self):
        self.seconds_left -= 1
        if self.seconds_left <= 0:
            self.countdown_timer.stop()
            self.accept()
            return

        self.redirect_label.setText(f"Redirecting in {self.seconds_left} seconds")


class LoginFailedDialog(QDialog):
    """Premium login failure popup with clear error and debug details."""

    def __init__(self, parent=None, reason: str = "", debug_text: str = "", compact_mode: bool = False):
        super().__init__(parent)
        self.reason = reason or "Authentication failed."
        self.debug_text = debug_text or "No debug details available."
        self.compact_mode = compact_mode
        self._popup_anim = None
        self._popup_geo_anim = None

        self.setObjectName("LoginFailedDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.resize(500 if not compact_mode else 430, 500 if not compact_mode else 450)
        self.build_ui()

    def showEvent(self, event):
        super().showEvent(event)

        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 22, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(220)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(220)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("FailedGlassPanel")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            38 if not self.compact_mode else 28,
            34 if not self.compact_mode else 26,
            38 if not self.compact_mode else 28,
            30 if not self.compact_mode else 24,
        )
        layout.setSpacing(18 if not self.compact_mode else 14)

        brand = QLabel("SECURE ACCESS")
        brand.setObjectName("SuccessBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        fail_circle = QLabel("!")
        fail_circle.setObjectName("FailedCircle")
        fail_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_circle.setFixedSize(78 if not self.compact_mode else 66, 78 if not self.compact_mode else 66)

        circle_row = QHBoxLayout()
        circle_row.addStretch()
        circle_row.addWidget(fail_circle)
        circle_row.addStretch()
        layout.addLayout(circle_row)

        title = QLabel("Authentication Failed")
        title.setObjectName("FailedTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        reason = QLabel(self.reason or "Invalid NTID or password. Please try again.")
        reason.setObjectName("FailedReason")
        reason.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reason.setWordWrap(True)
        layout.addWidget(reason)

        retry = QPushButton("Try Again")
        retry.setObjectName("FailedPrimaryButton")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.setMinimumHeight(48 if not self.compact_mode else 42)
        retry.clicked.connect(self.accept)
        layout.addWidget(retry)


class MissingCredentialsSetupDialog(QDialog):
    """First-launch warning popup for blank/missing SAS server credentials."""

    def __init__(self, parent=None, compact_mode: bool = False):
        super().__init__(parent)
        self.compact_mode = compact_mode
        self._popup_anim = None
        self._popup_geo_anim = None

        self.setObjectName("MissingCredentialsSetupDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(500 if not compact_mode else 430, 430 if not compact_mode else 390)
        self.build_ui()

    def showEvent(self, event):
        super().showEvent(event)

        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 22, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(230)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(230)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("MissingCredentialsPanel")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(36 if not self.compact_mode else 28)
        shadow.setOffset(0, 12 if not self.compact_mode else 8)
        shadow.setColor(QColor(0, 0, 0, 58))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(40 if not self.compact_mode else 30, 36 if not self.compact_mode else 28, 40 if not self.compact_mode else 30, 34 if not self.compact_mode else 26)
        layout.setSpacing(18 if not self.compact_mode else 14)

        shield = QLabel("▣")
        shield.setObjectName("MissingCredentialsWatermark")
        shield.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shield.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon = QLabel("!")
        icon.setObjectName("MissingCredentialsIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(72 if not self.compact_mode else 62, 72 if not self.compact_mode else 62)
        icon_row.addWidget(icon)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        title = QLabel("MISSING CREDENTIALS")
        title.setObjectName("MissingCredentialsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        message = QLabel(
            "System configuration is incomplete. Please login to Settings and set the server credentials before using Secure Access System."
        )
        message.setObjectName("MissingCredentialsMessage")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)

        # Keep the action button anchored at the bottom of the popup card,
        # matching the pasted UI where the user reads the warning first and
        # then moves down to the primary action.
        layout.addStretch(1)

        action = QPushButton("LOGIN TO SETTINGS")
        action.setObjectName("MissingCredentialsPrimaryButton")
        action.setCursor(Qt.CursorShape.PointingHandCursor)
        action.setMinimumHeight(48 if not self.compact_mode else 42)
        action.clicked.connect(self.accept)
        layout.addWidget(action)

        # The watermark is decorative only. Keep it outside the layout so it
        # does not push the login button away from the bottom area.
        shield.setParent(card)
        shield.setFixedSize(120 if not self.compact_mode else 96, 120 if not self.compact_mode else 96)
        shield.move(352 if not self.compact_mode else 292, 10)
        shield.raise_()


class SettingsConnectionDialog(QDialog):
    """Custom Settings Save/Connect result popup.

    Replaces QMessageBox so the app does not show black native dialogs.
    """

    def __init__(
        self,
        parent=None,
        success: bool = True,
        title: str = "",
        subtitle: str = "",
        server_path: str = "",
        timeout_seconds: int = 300,
        issues=None,
        compact_mode: bool = False,
    ):
        super().__init__(parent)
        self.success = success
        self.title = title or ("Connection Established" if success else "Connection Failed")
        self.subtitle = subtitle or ("Server linked successfully" if success else "Authentication or path error detected")
        self.server_path = server_path or "-"
        self.timeout_seconds = timeout_seconds
        self.issues = issues or []
        self.compact_mode = compact_mode
        self._popup_anim = None
        self._popup_geo_anim = None

        self.setObjectName("SettingsConnectionDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if self.success:
            self.resize(430 if not compact_mode else 390, 430 if not compact_mode else 390)
        else:
            self.resize(520 if not compact_mode else 460, 520 if not compact_mode else 480)

        self.build_ui()

    def showEvent(self, event):
        super().showEvent(event)

        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 22, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(230)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(230)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("SettingsSuccessPanel" if self.success else "SettingsFailPanel")

        # Soft border shadow to make the modal feel like a raised 3D card.
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34 if not self.compact_mode else 26)
        shadow.setOffset(0, 10 if not self.compact_mode else 7)
        shadow.setColor(QColor(0, 0, 0, 45))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            28 if not self.compact_mode else 22,
            24 if not self.compact_mode else 20,
            28 if not self.compact_mode else 22,
            24 if not self.compact_mode else 20,
        )
        layout.setSpacing(16 if not self.compact_mode else 12)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("×")
        close.setObjectName("LoginCloseButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(30, 30)
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        layout.addLayout(close_row)

        icon_row = QHBoxLayout()
        icon_row.addStretch()

        icon = QLabel("✓" if self.success else "!")
        icon.setObjectName("SettingsSuccessIcon" if self.success else "SettingsFailIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(64 if not self.compact_mode else 56, 64 if not self.compact_mode else 56)

        icon_row.addWidget(icon)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        title = QLabel(self.title)
        title.setObjectName("SettingsConnectTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        subtitle = QLabel(self.subtitle)
        subtitle.setObjectName("SettingsConnectSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        if self.success:
            layout.addWidget(self.success_meta_card())
            btn = QPushButton("Return to Settings")
            btn.setObjectName("SettingsConnectPrimaryButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(46 if not self.compact_mode else 40)
            btn.clicked.connect(self.accept)
            layout.addWidget(btn)
        else:
            layout.addWidget(self.failure_diagnostic_card())

            row = QHBoxLayout()
            row.setSpacing(10)

            retry = QPushButton("Retry Connection")
            retry.setObjectName("SettingsConnectPrimaryButton")
            retry.setCursor(Qt.CursorShape.PointingHandCursor)
            retry.setMinimumHeight(44 if not self.compact_mode else 40)
            retry.clicked.connect(self.retry_connection)

            edit = QPushButton("Edit Configuration")
            edit.setObjectName("SettingsConnectSecondaryButton")
            edit.setCursor(Qt.CursorShape.PointingHandCursor)
            edit.setMinimumHeight(44 if not self.compact_mode else 40)
            edit.clicked.connect(self.accept)

            row.addWidget(retry)
            row.addWidget(edit)
            layout.addLayout(row)

    def success_meta_card(self):
        card = QFrame()
        card.setObjectName("SettingsMetaCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addLayout(self.meta_row("NODE", self.server_path))
        layout.addLayout(self.meta_row("STATUS", "ACTIVE", success=True))
        layout.addLayout(self.meta_row("TIMEOUT", f"{self.timeout_seconds}s"))

        return card

    def failure_diagnostic_card(self):
        card = QFrame()
        card.setObjectName("SettingsDiagnosticCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QLabel("SYSTEM DIAGNOSTIC LOGS")
        header.setObjectName("SettingsDiagnosticHeader")
        layout.addWidget(header)

        if not self.issues:
            self.issues = [("CONNECTION FAILED", "Unable to validate the submitted configuration.")]

        for title, desc in self.issues:
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel("×")
            mark.setObjectName("SettingsIssueMark")
            mark.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            mark.setFixedWidth(18)

            text_box = QVBoxLayout()
            issue_title = QLabel(title)
            issue_title.setObjectName("SettingsIssueTitle")
            issue_desc = QLabel(desc)
            issue_desc.setObjectName("SettingsIssueDesc")
            issue_desc.setWordWrap(True)

            text_box.addWidget(issue_title)
            text_box.addWidget(issue_desc)

            row.addWidget(mark)
            row.addLayout(text_box, 1)
            layout.addLayout(row)

        return card

    def retry_connection(self):
        """Retry uses the same flow as pressing Save Connect again."""
        parent = self.parent()
        self.accept()

        save_settings = getattr(parent, "save_settings_from_ui", None)
        if callable(save_settings):
            QTimer.singleShot(120, save_settings)

    def meta_row(self, label: str, value: str, success: bool = False):
        row = QHBoxLayout()
        left = QLabel(label)
        left.setObjectName("SettingsMetaLabel")

        if success:
            right = QLabel("●  " + value)
            right.setObjectName("SettingsMetaSuccessValue")
        else:
            right = QLabel(value)
            right.setObjectName("SettingsMetaValue")

        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right.setWordWrap(True)

        row.addWidget(left)
        row.addStretch()
        row.addWidget(right)
        return row


class LockNotificationSecurityIcon(QWidget):
    """Small red shield icon matching the compact lock-notification design."""

    def __init__(self, parent=None, size: int = 18):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = float(self.width())
        height = float(self.height())
        red = QColor("#DC2626")

        shield = QPainterPath()
        shield.moveTo(width * 0.50, height * 0.08)
        shield.lineTo(width * 0.82, height * 0.21)
        shield.lineTo(width * 0.78, height * 0.57)
        shield.cubicTo(width * 0.74, height * 0.75, width * 0.62, height * 0.87, width * 0.50, height * 0.93)
        shield.cubicTo(width * 0.38, height * 0.87, width * 0.26, height * 0.75, width * 0.22, height * 0.57)
        shield.lineTo(width * 0.18, height * 0.21)
        shield.closeSubpath()

        painter.setPen(QPen(red, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shield)

        # A small keyhole keeps the icon recognisable as a security symbol
        # without relying on an emoji or the Material Symbols web font.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(red)
        painter.drawEllipse(QRectF(width * 0.455, height * 0.43, width * 0.09, height * 0.10))
        painter.drawRoundedRect(QRectF(width * 0.482, height * 0.52, width * 0.036, height * 0.15), 1.0, 1.0)


class LockNotificationFacePlaceholder(QWidget):
    """Muted face mark shown until the Pi camera sends its first frame."""

    def __init__(self, parent=None, size: int = 24):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        muted_red = QColor(220, 38, 38, 105)
        width = float(self.width())
        height = float(self.height())

        painter.setPen(QPen(muted_red, 1.55, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(width * 0.34, height * 0.16, width * 0.32, height * 0.34))

        shoulders = QPainterPath()
        shoulders.moveTo(width * 0.18, height * 0.84)
        shoulders.cubicTo(width * 0.24, height * 0.60, width * 0.76, height * 0.60, width * 0.82, height * 0.84)
        painter.drawPath(shoulders)


class SystemLockedNotification(QDialog):
    """Compact desktop lock notification with a read-only Pi camera preview.

    The visual layout follows the supplied ``SYSTEM LOCKED`` notification:
    a 380 x 90 bottom-right dark card, security status on the left, and a
    small 64 x 64 clear biometric camera preview on the right.  The preview remains
    an independent read-only subscriber to the Pi ``/video-feed`` endpoint;
    it never controls camera capture, recognition, training, or lock state.
    """

    live_frame_ready = Signal(object)
    live_status_changed = Signal(str)

    def __init__(
        self,
        compact_mode: bool = False,
        video_feed_url: str = "",
    ):
        super().__init__(None)
        self.compact_mode = compact_mode
        self.video_feed_url = str(video_feed_url or "").strip()
        self._allow_close = False
        self._popup_anim = None
        self._popup_geo_anim = None
        self._target_geometry = None

        # A dedicated visual subscriber is used while the main SAS dashboard
        # is minimized.  It is isolated from the dashboard camera widget.
        self._video_stream_running = False
        self._video_stream_stop = Event()
        self._video_capture = None
        self._video_thread = None
        self._video_received_first_frame = False
        self._last_frame_image = None

        # The camera preview is intentionally kept clear: no animated scan
        # line or red tint overlays are drawn over the live Pi video feed.
        self._status_pulse_animation = None

        self.setObjectName("SystemLockedNotification")
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        try:
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        except AttributeError:
            pass
        self.setWindowFlags(flags)
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        except Exception:
            pass

        # Normal desktop layout exactly matches the supplied card dimensions.
        # A slightly reduced compact version is retained only for small screens.
        self._notification_width = 380 if not compact_mode else 350
        self._notification_height = 90 if not compact_mode else 86
        self._camera_panel_side = 64 if not compact_mode else 60
        self.setFixedSize(self._notification_width, self._notification_height)

        self.live_frame_ready.connect(self._render_live_frame)
        self.live_status_changed.connect(self._set_live_status)
        self.build_ui()

    def reject(self):
        """Do not let Esc dismiss an active lock notification."""
        return

    def closeEvent(self, event):
        if self._allow_close:
            self._stop_visual_animations()
            self._stop_video_stream()
            event.accept()
        else:
            event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_camera_overlays()
        if self._last_frame_image is not None:
            self._display_frame_image(self._last_frame_image)

    def _bottom_right_geometry(self) -> QRect:
        screen = QApplication.primaryScreen()
        if screen is None:
            return self.geometry()
        available = screen.availableGeometry()
        margin = 24 if not self.compact_mode else 16
        return QRect(
            available.right() - self.width() - margin + 1,
            available.bottom() - self.height() - margin + 1,
            self.width(),
            self.height(),
        )

    def show_at_bottom_right(self):
        """Display without restoring/activating SAS or taking keyboard focus."""
        self._target_geometry = self._bottom_right_geometry()
        self.setGeometry(self._target_geometry)
        self.show()
        self.raise_()

        # The Qt layouts are final on the next event-loop turn.
        QTimer.singleShot(0, self._position_camera_overlays)
        QTimer.singleShot(0, self._start_visual_animations)
        QTimer.singleShot(80, self._start_video_stream)

    def showEvent(self, event):
        super().showEvent(event)
        end_geo = self._target_geometry or self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 14, end_geo.width(), end_geo.height())
        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._popup_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._popup_anim.setDuration(220)
        self._popup_anim.setStartValue(0.0)
        self._popup_anim.setEndValue(1.0)
        self._popup_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._popup_geo_anim.setDuration(220)
        self._popup_geo_anim.setStartValue(start_geo)
        self._popup_geo_anim.setEndValue(end_geo)
        self._popup_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._popup_anim.start()
        self._popup_geo_anim.start()

    def dismiss(self):
        """Close only when SAS has unlocked or is shutting down."""
        self._allow_close = True
        self._stop_visual_animations()
        self._stop_video_stream()
        self.hide()
        self.deleteLater()

    # --------------------------------------------------------
    # Read-only Pi camera feed
    # --------------------------------------------------------
    def _start_video_stream(self):
        if self._video_stream_running:
            return

        if not self.video_feed_url:
            self._set_live_status("Camera unavailable")
            return

        if cv2 is None:
            self._set_live_status("Camera unavailable")
            return

        self._video_stream_stop.clear()
        self._video_stream_running = True
        self._set_live_status("Connecting")

        self._video_thread = Thread(
            target=self._video_worker,
            name="sas-lock-notification-camera",
            daemon=True,
        )
        self._video_thread.start()

    def _stop_video_stream(self):
        self._video_stream_stop.set()
        self._video_stream_running = False

        capture = self._video_capture
        self._video_capture = None
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass

    def _open_video_capture(self):
        capture = cv2.VideoCapture(self.video_feed_url)
        try:
            capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
            capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return capture

    def _video_worker(self):
        """Read Pi MJPEG frames in a background thread without controlling Pi state."""
        capture = None

        try:
            last_emit_at = 0.0
            failed_reads = 0
            reconnect_attempt = 0

            while self._video_stream_running and not self._video_stream_stop.is_set():
                if capture is None or not capture.isOpened():
                    if capture is not None:
                        try:
                            capture.release()
                        except Exception:
                            pass

                    self.live_status_changed.emit("Reconnecting" if reconnect_attempt else "Connecting")
                    reconnect_attempt += 1
                    capture = self._open_video_capture()
                    self._video_capture = capture

                    if not capture.isOpened():
                        time.sleep(min(2.0, 0.25 + reconnect_attempt * 0.15))
                        continue

                    failed_reads = 0

                ok, frame = capture.read()

                if not ok or frame is None:
                    failed_reads += 1
                    if failed_reads >= 12:
                        self.live_status_changed.emit("Reconnecting")
                    if failed_reads >= 24:
                        try:
                            capture.release()
                        except Exception:
                            pass
                        capture = None
                        self._video_capture = None
                        failed_reads = 0
                    time.sleep(0.08)
                    continue

                failed_reads = 0
                reconnect_attempt = 0
                now = time.monotonic()
                if now - last_emit_at < 0.066:
                    continue

                last_emit_at = now
                self.live_frame_ready.emit(frame.copy())

        except Exception:
            try:
                self.live_status_changed.emit("Camera unavailable")
            except Exception:
                pass
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass

            if self._video_capture is capture:
                self._video_capture = None

            self._video_stream_running = False

            if not self._video_stream_stop.is_set():
                try:
                    self.live_status_changed.emit("Camera unavailable")
                except Exception:
                    pass

    def _render_live_frame(self, frame):
        if frame is None or not hasattr(self, "camera_preview_label"):
            return

        try:
            if cv2 is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                rgb = frame[:, :, ::-1].copy()

            height, width, channels = rgb.shape
            bytes_per_line = channels * width
            image = QImage(
                rgb.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            ).copy()

            self._last_frame_image = image
            self._display_frame_image(image)

            if not self._video_received_first_frame:
                self._video_received_first_frame = True
                self.camera_placeholder.hide()

            self._set_live_status("Live")
        except Exception:
            self._set_live_status("Camera unavailable")

    def _display_frame_image(self, image):
        target = self.camera_preview_label.size()
        if target.width() <= 1 or target.height() <= 1:
            return

        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_preview_label.setPixmap(scaled)

    def _set_live_status(self, status: str):
        """Keep status visual-only: the reference card shows only a tiny dot."""
        if not hasattr(self, "live_status_dot"):
            return

        status_text = str(status or "").strip().upper()
        if status_text != "LIVE":
            self._video_received_first_frame = False
            self._last_frame_image = None
            if hasattr(self, "camera_preview_label"):
                self.camera_preview_label.clear()
                self.camera_preview_label.setPixmap(QPixmap())
            if hasattr(self, "camera_placeholder"):
                self.camera_placeholder.show()

        if status_text in {"LIVE", "CONNECTING", "RECONNECTING"}:
            dot_color = "#DC2626"
            if self._status_pulse_animation is not None:
                self._status_pulse_animation.start()
        else:
            dot_color = "#747878"
            if self._status_pulse_animation is not None:
                self._status_pulse_animation.stop()
            if hasattr(self, "_status_opacity"):
                self._status_opacity.setOpacity(0.62)

        self.live_status_dot.setStyleSheet(
            f"background: {dot_color}; border: none; border-radius: 3px;"
        )

    # --------------------------------------------------------
    # Compact visual effects
    # --------------------------------------------------------
    def _start_visual_animations(self):
        if self._status_pulse_animation is not None:
            self._status_pulse_animation.start()

    def _stop_visual_animations(self):
        if self._status_pulse_animation is not None:
            self._status_pulse_animation.stop()

    # --------------------------------------------------------
    # Notification UI
    # --------------------------------------------------------
    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("SystemLockedNotificationCard")
        self.card.setStyleSheet("""
            QFrame#SystemLockedNotificationCard {
                background: #1C1B1B;
                border: 1px solid rgba(220, 38, 38, 0.30);
                border-radius: 8px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 153))
        self.card.setGraphicsEffect(shadow)

        # Very subtle red-to-transparent corner glow, equivalent to the
        # reference card's decorative gradient.  It never receives input.
        self.glow_overlay = QFrame(self.card)
        self.glow_overlay.setObjectName("SystemLockedNotificationGlow")
        self.glow_overlay.setStyleSheet("""
            QFrame#SystemLockedNotificationGlow {
                background: qlineargradient(
                    x1:0, y1:1, x2:1, y2:0,
                    stop:0 rgba(220, 38, 38, 32),
                    stop:0.52 rgba(220, 38, 38, 8),
                    stop:1 rgba(220, 38, 38, 0)
                );
                border: none;
                border-radius: 8px;
            }
        """)
        self.glow_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self.card)
        horizontal_margin = 14 if not self.compact_mode else 12
        layout.setContentsMargins(
            horizontal_margin,
            12 if not self.compact_mode else 11,
            horizontal_margin,
            12 if not self.compact_mode else 11,
        )
        layout.setSpacing(16 if not self.compact_mode else 12)

        left_content = QWidget(self.card)
        left_content.setStyleSheet("background: transparent; border: none;")
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5 if not self.compact_mode else 4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        security_icon = LockNotificationSecurityIcon(
            left_content,
            18 if not self.compact_mode else 17,
        )

        title = QLabel("SYSTEM LOCKED")
        title.setStyleSheet("""
            color: #FFFFFF;
            background: transparent;
            border: none;
            font-family: Inter, Segoe UI, Arial;
            font-size: 12px;
            font-weight: 800;
        """)
        title_font = title.font()
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.15)
        title.setFont(title_font)

        header.addWidget(security_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addStretch(1)

        message = QLabel(
            "Unauthorized access detected. Biometric verification required."
        )
        message.setWordWrap(True)
        message.setStyleSheet("""
            color: rgba(133, 131, 131, 0.90);
            background: transparent;
            border: none;
            font-family: Inter, Segoe UI, Arial;
            font-size: 10px;
            font-weight: 600;
        """)

        left_layout.addLayout(header)
        left_layout.addWidget(message, 1)

        self.camera_panel = QFrame(self.card)
        self.camera_panel.setObjectName("LockedNotificationCameraPanel")
        self.camera_panel.setFixedSize(self._camera_panel_side, self._camera_panel_side)
        self.camera_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.camera_panel.setStyleSheet("""
            QFrame#LockedNotificationCameraPanel {
                background: #000000;
                border: 1px solid rgba(220, 38, 38, 0.40);
                border-radius: 4px;
            }
        """)

        self.camera_preview_label = QLabel(self.camera_panel)
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setStyleSheet(
            "background: #000000; border: none; border-radius: 3px;"
        )

        self.camera_placeholder = LockNotificationFacePlaceholder(
            self.camera_panel,
            24 if not self.compact_mode else 22,
        )

        # Four small biometric brackets mirror the supplied scanner preview.
        corner_color = "#DC2626"
        self.corner_top_left = QFrame(self.camera_panel)
        self.corner_top_right = QFrame(self.camera_panel)
        self.corner_bottom_left = QFrame(self.camera_panel)
        self.corner_bottom_right = QFrame(self.camera_panel)
        self.corner_top_left.setStyleSheet(
            f"background: transparent; border-top: 2px solid {corner_color}; border-left: 2px solid {corner_color};"
        )
        self.corner_top_right.setStyleSheet(
            f"background: transparent; border-top: 2px solid {corner_color}; border-right: 2px solid {corner_color};"
        )
        self.corner_bottom_left.setStyleSheet(
            f"background: transparent; border-bottom: 2px solid {corner_color}; border-left: 2px solid {corner_color};"
        )
        self.corner_bottom_right.setStyleSheet(
            f"background: transparent; border-bottom: 2px solid {corner_color}; border-right: 2px solid {corner_color};"
        )

        # Keep the live Pi preview unobstructed.  The scanner line and red
        # tint used by the previous lock-card design are intentionally removed.

        self.live_status_dot = QFrame(self.camera_panel)
        self.live_status_dot.setFixedSize(6, 6)
        self._status_opacity = QGraphicsOpacityEffect(self.live_status_dot)
        self._status_opacity.setOpacity(1.0)
        self.live_status_dot.setGraphicsEffect(self._status_opacity)
        self._status_pulse_animation = QPropertyAnimation(self._status_opacity, b"opacity", self)
        self._status_pulse_animation.setDuration(1000)
        self._status_pulse_animation.setStartValue(1.0)
        self._status_pulse_animation.setKeyValueAt(0.5, 0.32)
        self._status_pulse_animation.setEndValue(1.0)
        self._status_pulse_animation.setLoopCount(-1)
        self._status_pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)

        for overlay in (
            self.camera_placeholder,
            self.corner_top_left,
            self.corner_top_right,
            self.corner_bottom_left,
            self.corner_bottom_right,
            self.live_status_dot,
        ):
            try:
                overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            except Exception:
                pass

        layout.addWidget(left_content, 1)
        layout.addWidget(self.camera_panel, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(self.card)

        self._position_camera_overlays()
        self._set_live_status("Connecting")

    def _position_camera_overlays(self):
        if not hasattr(self, "camera_panel"):
            return

        if hasattr(self, "glow_overlay") and hasattr(self, "card"):
            self.glow_overlay.setGeometry(self.card.rect())
            self.glow_overlay.lower()

        width = max(1, self.camera_panel.width())
        height = max(1, self.camera_panel.height())
        corner_size = 12 if not self.compact_mode else 11
        inset = 1

        self.camera_preview_label.setGeometry(0, 0, width, height)
        placeholder_width = self.camera_placeholder.width()
        placeholder_height = self.camera_placeholder.height()
        self.camera_placeholder.move(
            max(0, (width - placeholder_width) // 2),
            max(0, (height - placeholder_height) // 2),
        )

        self.corner_top_left.setGeometry(inset, inset, corner_size, corner_size)
        self.corner_top_right.setGeometry(width - corner_size - inset, inset, corner_size, corner_size)
        self.corner_bottom_left.setGeometry(inset, height - corner_size - inset, corner_size, corner_size)
        self.corner_bottom_right.setGeometry(
            width - corner_size - inset,
            height - corner_size - inset,
            corner_size,
            corner_size,
        )

        self.live_status_dot.move(max(3, width - 10), max(3, height - 10))

        # Keep only the small scanner corners and live-status dot above the
        # camera pixmap.  No red scan line or tint is drawn over the preview.
        for overlay in (
            self.camera_placeholder,
            self.corner_top_left,
            self.corner_top_right,
            self.corner_bottom_left,
            self.corner_bottom_right,
            self.live_status_dot,
        ):
            overlay.raise_()


class TrainingProgressDialog(QDialog):
    """Training progress modal based on the provided glass training UI.

    It has:
    - glass/3D card
    - animated progress ring
    - rotating status text
    - completion flip effect
    - green success glow / red failure glow
    """

    def __init__(self, parent=None, ntid: str = "", compact_mode: bool = False):
        super().__init__(parent)
        self.ntid = ntid or "-"
        self.compact_mode = compact_mode
        # Training uses a neutral loading spinner rather than a percentage.
        # Pi status still supplies true image counters in the text below, but
        # users do not see a misleading percentage while CPU-heavy encoding
        # work is in progress.
        self.progress = 0
        self.status_index = 0
        self.result_state = None
        self._ring_anim = None
        self._flip_anim = None

        self.status_messages = [
            "Stopping active camera processes...",
            "Optimizing neural weights...",
            "Analyzing facial vectors...",
            "Validating node connections...",
            "Calibrating accuracy filters...",
            "Updating biometric dataset...",
        ]

        self.setObjectName("TrainingProgressDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Keep the in-progress modal at the original v98 size/centering.
        # The larger completion layout is applied only after a result arrives.
        self.resize(420 if not compact_mode else 380, 470 if not compact_mode else 430)

        self.build_ui()
        self.start_animation()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("TrainingSolidModal")

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 65))
        self.card.setGraphicsEffect(shadow)

        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        self.training_layout = layout
        # Restore the centred in-progress layout from v98.  This keeps the
        # spinner, title, and dataset card vertically balanced while training.
        layout.setContentsMargins(
            28 if not self.compact_mode else 22,
            24 if not self.compact_mode else 20,
            28 if not self.compact_mode else 22,
            24 if not self.compact_mode else 20,
        )
        layout.setSpacing(14 if not self.compact_mode else 11)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Training in Progress")
        self.title_label.setObjectName("TrainingTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Stopping active camera processes...")
        self.status_label.setObjectName("TrainingStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("TrainingDetail")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.hide()

        # Use the title created above. The old reference to ``title`` caused
        # a runtime NameError when the Train button opened this dialog.
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.detail_label)

        # The spacer values are adjusted only after completion. During
        # training they reproduce the compact v98 spinner arrangement.
        self._ring_top_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._ring_bottom_spacer = QSpacerItem(0, 18 if not self.compact_mode else 14, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout.addItem(self._ring_top_spacer)

        self.ring = TrainingRingWidget()
        self.ring.setFixedSize(124 if not self.compact_mode else 112, 124 if not self.compact_mode else 112)
        layout.addWidget(self.ring, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addItem(self._ring_bottom_spacer)

        self.inner_icon = QLabel("◌")
        self.inner_icon.setParent(self.ring)
        self.inner_icon.setObjectName("TrainingInnerIcon")
        self.inner_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner_icon.setGeometry(28 if not self.compact_mode else 23, 24 if not self.compact_mode else 21, 68 if not self.compact_mode else 64, 32 if not self.compact_mode else 28)
        # Keep the centre of the spinner empty while training. The check/fail
        # symbol is shown only after the Pi reports a final result.
        self.inner_icon.hide()

        self.progress_label = QLabel("")
        self.progress_label.setParent(self.ring)
        self.progress_label.setObjectName("TrainingProgressText")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setGeometry(28 if not self.compact_mode else 23, 61 if not self.compact_mode else 54, 68 if not self.compact_mode else 64, 30 if not self.compact_mode else 26)
        self.progress_label.hide()

        token = QFrame()
        token.setObjectName("TrainingTokenCard")
        token_layout = QVBoxLayout(token)
        token_layout.setContentsMargins(12, 8, 12, 8)
        token_layout.setSpacing(4)

        self.ntid_title_label = QLabel("PROCESSING DATASET")
        self.ntid_title_label.setObjectName("TrainingTokenLabel")
        self.ntid_value_label = QLabel(self.ntid)
        self.ntid_value_label.setObjectName("TrainingTokenValue")
        self.ntid_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ntid_value_label.setWordWrap(True)

        token_layout.addWidget(self.ntid_title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        token_layout.addWidget(self.ntid_value_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(token)

        self.done_btn = QPushButton("Return to Face Recognition")
        self.done_btn.setObjectName("TrainingDoneButton")
        self.done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_btn.setMinimumHeight(38 if not self.compact_mode else 34)
        self.done_btn.clicked.connect(self.accept)
        self.done_btn.hide()
        layout.addWidget(self.done_btn)

    def start_animation(self):
        """Start a simple, indeterminate loading spinner for the training job."""
        self.progress_timer = None
        self.status_timer = None
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(45)
        self.loading_timer.timeout.connect(self.tick_loading)
        self.loading_timer.start()
        self.ring.set_loading(True)

    def tick_loading(self):
        if self.result_state is None:
            self.ring.advance_spinner()

    def tick_progress(self):
        # Retained for compatibility with older callers; percentage is hidden.
        return

    def tick_status(self):
        # Retained for compatibility with older callers.
        return

    def set_progress(self, value: int):
        self.progress = max(0, min(100, int(value)))
        self.ring.set_progress(self.progress)

    def set_live_progress(
        self,
        processed: int = 0,
        total: int = 0,
        percent: int | None = None,
        message: str = "",
        phase: str = "training",
        skipped: int = 0,
        already_trained: int = 0,
        dataset_total: int = 0,
    ):
        """Show real training status text without displaying a percentage."""
        if self.result_state is not None:
            return

        try:
            processed_value = max(0, int(processed or 0))
            total_value = max(0, int(total or 0))
            skipped_value = max(0, int(skipped or 0))
            already_value = max(0, int(already_trained or 0))
            dataset_value = max(0, int(dataset_total or 0))
        except Exception:
            processed_value = total_value = skipped_value = already_value = dataset_value = 0

        if message:
            self.status_label.setText(str(message))

        phase_value = str(phase or "training").strip().lower()
        if total_value > 0:
            self.ntid_title_label.setText("SCANNING NEW IMAGES")
            text = f"{processed_value} / {total_value} checked"
            if skipped_value:
                text += f"  •  {skipped_value} skipped"
            self.ntid_value_label.setText(text)
        elif phase_value == "preparing":
            self.ntid_title_label.setText("SCANNING DATASET")
            if dataset_value > 0:
                self.ntid_value_label.setText(f"Checking {dataset_value} image{'s' if dataset_value != 1 else ''}")
            else:
                self.ntid_value_label.setText("CHECKING FOR NEW IMAGES")
        elif phase_value == "completed" and already_value:
            self.ntid_title_label.setText("DATASET STATUS")
            self.ntid_value_label.setText(f"{already_value} already trained")

        self.ntid_title_label.update()
        self.ntid_value_label.update()

    def set_training_details(self, detail: str):
        if hasattr(self, "detail_label") and detail:
            self.detail_label.setText(detail)
            self.detail_label.show()

    def set_processing_users(self, users):
        """Update token card to show actual trained user data, not typed NTID."""
        if isinstance(users, dict):
            user_list = list(users.keys())
        elif isinstance(users, (list, tuple, set)):
            user_list = [str(u).upper() for u in users if str(u).strip()]
        else:
            user_list = []

        if user_list:
            preview = user_list[:4]
            text = ", ".join(preview)
            remaining = len(user_list) - len(preview)
            if remaining > 0:
                text += f" +{remaining} more"

            self.ntid_title_label.setText("TRAINED USER DATA")
            self.ntid_value_label.setText(text)
        else:
            self.ntid_title_label.setText("PROCESSING DATASET")
            self.ntid_value_label.setText("DATASET")

        self.ntid_title_label.update()
        self.ntid_value_label.update()


    def complete_success(self, message: str = "Training completed successfully.", detail: str = ""):
        self.result_state = "success"
        if detail:
            self.set_training_details(detail)
        self._finish(True, message)

    def complete_failed(self, message: str = "Training failed.", detail: str = ""):
        self.result_state = "failed"
        if detail:
            self.set_training_details(detail)
        self._finish(False, message)

    def _finish(self, success: bool, message: str):
        try:
            self.progress_timer.stop()
            self.status_timer.stop()
        except Exception:
            pass
        try:
            self.loading_timer.stop()
        except Exception:
            pass

        self.ring.set_loading(False)
        self.set_progress(100)

        # Completion has its own title. Hide an empty result message so the
        # no-new-images path does not show an unnecessary sentence below it.
        if hasattr(self, "title_label"):
            self.title_label.setText("Training Complete" if success else "Training Failed")
        if str(message or "").strip():
            self.status_label.setText(str(message).strip())
            self.status_label.show()
        else:
            self.status_label.clear()
            self.status_label.hide()

        # Completion includes the result ring and return button. Give this
        # state more height while keeping the ring exactly between the green
        # result-detail block and the dataset card.
        self.resize(420 if not self.compact_mode else 380, 520 if not self.compact_mode else 470)
        try:
            gap = 18 if not self.compact_mode else 14
            self._ring_top_spacer.changeSize(0, gap, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self._ring_bottom_spacer.changeSize(0, gap, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self.training_layout.invalidate()
            self.training_layout.activate()
        except Exception:
            pass

        self.card.setObjectName("TrainingSuccessModal" if success else "TrainingFailedModal")
        self.ring.set_result(success)

        self.inner_icon.setText("✓" if success else "×")
        self.inner_icon.show()
        self.inner_icon.setObjectName("TrainingSuccessIcon" if success else "TrainingFailedIcon")
        self.progress_label.setText("DONE" if success else "FAIL")
        self.progress_label.setObjectName("TrainingResultText")
        self.progress_label.show()

        self.card.style().unpolish(self.card)
        self.card.style().polish(self.card)
        self.inner_icon.style().unpolish(self.inner_icon)
        self.inner_icon.style().polish(self.inner_icon)
        self.progress_label.style().unpolish(self.progress_label)
        self.progress_label.style().polish(self.progress_label)

        self.flip_result_circle()
        self.done_btn.show()

    def flip_result_circle(self):
        """Refresh the result ring without moving a layout-managed widget.

        A geometry animation on ``self.ring`` can temporarily override the
        QVBoxLayout geometry and make the green DONE ring overlap the dataset
        card. The completed UI uses a stable final position instead.
        """
        self.ring.update()


class TrainingRingWidget(QWidget):
    """Indeterminate spinner while training, result ring after completion."""

    def __init__(self):
        super().__init__()
        self.progress = 0
        self.result = None
        self.loading = True
        self.spinner_angle = 90

    def set_progress(self, value):
        self.progress = max(0, min(100, int(value)))
        self.update()

    def set_loading(self, enabled: bool):
        self.loading = bool(enabled)
        self.update()

    def advance_spinner(self):
        if self.loading and self.result is None:
            self.spinner_angle = (self.spinner_angle - 12) % 360
            self.update()

    def set_result(self, success: bool):
        self.loading = False
        self.result = "success" if success else "failed"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = min(self.width(), self.height()) - 22
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

        if self.result == "success":
            glow = QColor(22, 163, 74, 80)
            pen_color = QColor("#16A34A")
        elif self.result == "failed":
            glow = QColor(220, 38, 38, 80)
            pen_color = QColor("#DC2626")
        else:
            glow = QColor(0, 0, 0, 20)
            pen_color = QColor("#111827")

        painter.setPen(QPen(glow, 5))
        painter.drawEllipse(rect)

        painter.setPen(QPen(QColor("#E2E2E2"), 3))
        painter.drawEllipse(rect)

        pen = QPen(pen_color, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if self.loading and self.result is None:
            # Indeterminate loading arc: no percentage is presented.
            painter.drawArc(rect, int(self.spinner_angle * 16), int(-105 * 16))
        else:
            painter.drawArc(rect, 90 * 16, int(-360 * (self.progress / 100) * 16))


class DeleteCompleteDialog(QDialog):
    """User deleted confirmation popup.

    Based on the provided UI:
    - solid white 3D card
    - emerald check vessel
    - user deleted title
    - NTID detail text
    - return button
    """

    def __init__(
        self,
        parent=None,
        ntid: str = "",
        dataset_removed: bool = False,
        encodings_removed: int = 0,
        compact_mode: bool = False,
    ):
        super().__init__(parent)
        self.ntid = str(ntid).upper() if ntid else "-"
        self.dataset_removed = dataset_removed
        self.encodings_removed = encodings_removed
        self.compact_mode = compact_mode
        self._enter_anim = None
        self._enter_geo_anim = None

        self.setObjectName("DeleteCompleteDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(440 if not compact_mode else 390, 420 if not compact_mode else 380)

        self.build_ui()

    def showEvent(self, event):
        super().showEvent(event)

        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 12, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._enter_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._enter_anim.setDuration(260)
        self._enter_anim.setStartValue(0.0)
        self._enter_anim.setEndValue(1.0)
        self._enter_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._enter_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._enter_geo_anim.setDuration(320)
        self._enter_geo_anim.setStartValue(start_geo)
        self._enter_geo_anim.setEndValue(end_geo)
        self._enter_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._enter_anim.start()
        self._enter_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("DeleteCompleteCard")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 55))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            34 if not self.compact_mode else 26,
            32 if not self.compact_mode else 26,
            34 if not self.compact_mode else 26,
            28 if not self.compact_mode else 24,
        )
        layout.setSpacing(16 if not self.compact_mode else 13)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_wrap = QFrame()
        icon_wrap.setObjectName("DeleteIconWrap")
        icon_wrap.setFixedSize(82 if not self.compact_mode else 70, 82 if not self.compact_mode else 70)

        icon_shadow = QGraphicsDropShadowEffect(icon_wrap)
        icon_shadow.setBlurRadius(16)
        icon_shadow.setOffset(0, 4)
        icon_shadow.setColor(QColor(16, 185, 129, 70))
        icon_wrap.setGraphicsEffect(icon_shadow)

        icon_layout = QVBoxLayout(icon_wrap)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon = QLabel("✓")
        icon.setObjectName("DeleteIconCheck")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(icon)

        title = QLabel("User Deleted")
        title.setObjectName("DeleteTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            f"The credentials and biometric data for <b>NTID {self.ntid}</b> "
            "have been purged from the local node and secure server."
        )
        desc.setObjectName("DeleteDesc")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        trace = QLabel(
            f"DATASET REMOVED: {'YES' if self.dataset_removed else 'NO'}  •  "
            f"ENCODINGS REMOVED: {self.encodings_removed}"
        )
        trace.setObjectName("DeleteTrace")
        trace.setAlignment(Qt.AlignmentFlag.AlignCenter)
        trace.setWordWrap(True)

        button = QPushButton("Return to Face Recognition")
        button.setObjectName("DeleteReturnButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(44 if not self.compact_mode else 40)
        button.clicked.connect(self.accept)

        layout.addWidget(icon_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(trace)
        layout.addStretch()
        layout.addWidget(button)


class CaptureCompleteDialog(QDialog):
    """Capture complete popup.

    Based on provided UI:
    - solid white confirmation card
    - emerald success icon
    - Capture Complete title
    - NTID + number of capture frames
    - Return button
    """

    def __init__(self, parent=None, ntid: str = "", frames: int = 0, compact_mode: bool = False):
        super().__init__(parent)
        self.ntid = str(ntid).upper() if ntid else "-"
        self.frames = int(frames or 0)
        self.compact_mode = compact_mode
        self._enter_anim = None
        self._enter_geo_anim = None

        self.setObjectName("CaptureCompleteDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(420 if not compact_mode else 380, 390 if not compact_mode else 350)

        self.build_ui()

    def showEvent(self, event):
        super().showEvent(event)

        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 12, end_geo.width(), end_geo.height())
        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._enter_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._enter_anim.setDuration(260)
        self._enter_anim.setStartValue(0.0)
        self._enter_anim.setEndValue(1.0)
        self._enter_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._enter_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._enter_geo_anim.setDuration(320)
        self._enter_geo_anim.setStartValue(start_geo)
        self._enter_geo_anim.setEndValue(end_geo)
        self._enter_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._enter_anim.start()
        self._enter_geo_anim.start()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("CaptureCompleteCard")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 55))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            30 if not self.compact_mode else 24,
            30 if not self.compact_mode else 24,
            30 if not self.compact_mode else 24,
            24 if not self.compact_mode else 20,
        )
        layout.setSpacing(16 if not self.compact_mode else 13)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_wrap = QFrame()
        icon_wrap.setObjectName("CaptureIconWrap")
        icon_wrap.setFixedSize(78 if not self.compact_mode else 66, 78 if not self.compact_mode else 66)

        icon_shadow = QGraphicsDropShadowEffect(icon_wrap)
        icon_shadow.setBlurRadius(16)
        icon_shadow.setOffset(0, 4)
        icon_shadow.setColor(QColor(16, 185, 129, 70))
        icon_wrap.setGraphicsEffect(icon_shadow)

        icon_layout = QVBoxLayout(icon_wrap)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon = QLabel("✓")
        icon.setObjectName("CaptureIconCheck")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(icon)

        title = QLabel("Capture Complete")
        title.setObjectName("CaptureTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        frame_word = "capture" if self.frames == 1 else "captures"
        desc = QLabel(
            f"<b>{self.frames}</b> high-fidelity facial {frame_word} have been successfully "
            f"optimized and stored for <b>NTID {self.ntid}</b>."
        )
        desc.setObjectName("CaptureDesc")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        footer = QFrame()
        footer.setObjectName("CaptureFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(6)

        verified = QLabel("✓")
        verified.setObjectName("CaptureFooterIcon")
        verified_text = QLabel("Secure Access Verified")
        verified_text.setObjectName("CaptureFooterText")
        footer_layout.addStretch()
        footer_layout.addWidget(verified)
        footer_layout.addWidget(verified_text)
        footer_layout.addStretch()

        button = QPushButton("Return to Face Recognition  →")
        button.setObjectName("CaptureReturnButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(42 if not self.compact_mode else 38)
        button.clicked.connect(self.accept)

        layout.addWidget(icon_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addWidget(button)
        layout.addWidget(footer)


class ConnectionSpinnerWidget(QWidget):
    """Small animated loading ring for Pi connection handshake."""

    def __init__(self, parent=None, size: int = 92):
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self.setFixedSize(size, size)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(28)

    def _tick(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def stop(self):
        self.timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)

        base_pen = QPen(QColor(255, 255, 255, 55), 5)
        painter.setPen(base_pen)
        painter.drawEllipse(rect)

        arc_pen = QPen(QColor(255, 255, 255, 230), 5)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, int(-self._angle * 16), int(110 * 16))

        painter.end()


class PiConnectionDialog(QDialog):
    """Card-style Pi connection popup.

    States:
    - loading: animated secure handshake
    - success: verified/stable
    - failed: offline/error
    """

    def __init__(
        self,
        parent=None,
        host: str = "",
        origin: str = "settings",
        compact_mode: bool = False,
    ):
        super().__init__(parent)
        self.host = host or "-"
        self.origin = origin
        self.compact_mode = compact_mode
        self.state = "loading"
        self.error_text = ""
        self.users = 0
        self.recognition = False
        self.capture = False
        self._enter_anim = None
        self._enter_geo_anim = None
        self._status_index = 0
        self._statuses = ["HANDSHAKE", "AUTHENTICATING", "ENCRYPTING", "VALIDATING"]
        self._status_timer = None

        self.setObjectName("PiConnectionDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(760 if not compact_mode else 640, 430 if not compact_mode else 380)

        self.build_ui()
        self.set_loading()

    def showEvent(self, event):
        super().showEvent(event)
        end_geo = self.geometry()
        start_geo = QRect(end_geo.x(), end_geo.y() + 12, end_geo.width(), end_geo.height())

        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)

        self._enter_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._enter_anim.setDuration(220)
        self._enter_anim.setStartValue(0.0)
        self._enter_anim.setEndValue(1.0)
        self._enter_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._enter_geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._enter_geo_anim.setDuration(280)
        self._enter_geo_anim.setStartValue(start_geo)
        self._enter_geo_anim.setEndValue(end_geo)
        self._enter_geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._enter_anim.start()
        self._enter_geo_anim.start()

    def closeEvent(self, event):
        try:
            if hasattr(self, "spinner") and self.spinner is not None:
                self.spinner.stop()
            if self._status_timer is not None:
                self._status_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def force_close(self):
        """Close the Pi connection dialog from the top-right X or action button.

        v121: use a single explicit close path because some Windows builds
        showed the success-card X button visually but did not dismiss the
        card reliably when connected.
        """
        try:
            if hasattr(self, "spinner") and self.spinner is not None:
                self.spinner.stop()
            if self._status_timer is not None:
                self._status_timer.stop()
        except Exception:
            pass
        try:
            self.done(QDialog.DialogCode.Accepted)
        except Exception:
            try:
                self.accept()
            except Exception:
                self.close()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("PiConnectionCard")

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.card.setGraphicsEffect(shadow)

        outer.addWidget(self.card)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.visual_panel = QFrame()
        self.visual_panel.setObjectName("PiConnectionVisualLoading")
        self.visual_panel.setMinimumWidth(280 if not self.compact_mode else 230)

        visual_layout = QVBoxLayout(self.visual_panel)
        visual_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        visual_layout.setSpacing(12)

        self.spinner = ConnectionSpinnerWidget(self, 98 if not self.compact_mode else 82)
        self.icon_label = QLabel("↻")
        self.icon_label.setObjectName("PiConnectionLargeIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.hide()

        self.visual_caption = QLabel("CONNECTING")
        self.visual_caption.setObjectName("PiConnectionVisualCaption")
        self.visual_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

        visual_layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        visual_layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        visual_layout.addWidget(self.visual_caption)

        self.content_panel = QFrame()
        self.content_panel.setObjectName("PiConnectionContent")

        content = QVBoxLayout(self.content_panel)
        content.setContentsMargins(
            38 if not self.compact_mode else 28,
            34 if not self.compact_mode else 26,
            38 if not self.compact_mode else 28,
            30 if not self.compact_mode else 24,
        )
        content.setSpacing(18 if not self.compact_mode else 14)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("LoginCloseButton")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setEnabled(True)
        self.close_btn.clicked.connect(self.force_close)
        close_row.addWidget(self.close_btn)
        self.close_btn.raise_()
        content.addLayout(close_row)

        self.title = QLabel("CONNECTING...")
        self.title.setObjectName("PiConnectionTitle")
        self.title.setWordWrap(True)

        self.subtitle = QLabel("Securing encrypted handshake protocol")
        self.subtitle.setObjectName("PiConnectionSubtitle")
        self.subtitle.setWordWrap(True)

        content.addWidget(self.title)
        content.addWidget(self.subtitle)

        self.node_label = self.info_block("PI SERVICE", "FACE RECOGNITION API")
        self.gateway_label = self.info_block("HOSTNAME / IP", self.host)
        self.status_label = self.info_block("CONNECTION", "AUTHENTICATING")

        content.addWidget(self.node_label)
        row = QHBoxLayout()
        row.setSpacing(20)
        row.addWidget(self.gateway_label)
        row.addWidget(self.status_label)
        content.addLayout(row)

        content.addStretch()

        self.action_btn = QPushButton("Return to Settings")
        self.action_btn.setObjectName("PiConnectionActionButton")
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setMinimumHeight(42 if not self.compact_mode else 38)
        self.action_btn.clicked.connect(self.force_close)
        content.addWidget(self.action_btn)
        self.action_btn.hide()

        footer = QHBoxLayout()
        footer.setSpacing(8)
        # Footer version/reference labels removed for a cleaner connection card.

        card_layout.addWidget(self.visual_panel, 5)
        card_layout.addWidget(self.content_panel, 7)

    def info_value_label(self, block: QFrame) -> QLabel:
        """Return the value QLabel stored on an info block.

        Uses Qt dynamic properties instead of assigning custom Python
        attributes to QFrame, so Pylance does not report value_label errors.
        """
        label = block.property("value_label")
        return cast(QLabel, label)

    def info_block(self, label_text: str, value_text: str):
        block = QFrame()
        block.setObjectName("PiConnectionInfoBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(label_text)
        label.setObjectName("PiConnectionInfoLabel")
        value = QLabel(value_text)
        value.setObjectName("PiConnectionInfoValue")
        value.setWordWrap(True)

        layout.addWidget(label)
        layout.addWidget(value)
        block.setProperty("value_label", value)
        return block

    def set_loading(self):
        self.state = "loading"
        self.visual_panel.setObjectName("PiConnectionVisualLoading")
        self.visual_panel.style().unpolish(self.visual_panel)
        self.visual_panel.style().polish(self.visual_panel)

        self.spinner.show()
        self.icon_label.hide()
        self.visual_caption.setText("CONNECTING")

        self.title.setText("CONNECTING...")
        self.subtitle.setText("Securing encrypted handshake protocol")
        self.info_value_label(self.gateway_label).setText(self.host)
        self.info_value_label(self.status_label).setText("AUTHENTICATING")
        self.action_btn.hide()
        self.close_btn.hide()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.next_loading_status)
        self._status_timer.start(900)

    def next_loading_status(self):
        self._status_index = (self._status_index + 1) % len(self._statuses)
        self.info_value_label(self.status_label).setText(self._statuses[self._status_index])

    def set_success(self, users: int = 0, recognition: bool = False, capture: bool = False):
        self.state = "success"
        self.users = users
        self.recognition = recognition
        self.capture = capture

        if self._status_timer is not None:
            self._status_timer.stop()
        if self.spinner is not None:
            self.spinner.stop()

        self.visual_panel.setObjectName("PiConnectionVisualSuccess")
        self.visual_panel.style().unpolish(self.visual_panel)
        self.visual_panel.style().polish(self.visual_panel)

        self.spinner.hide()
        self.icon_label.setText("✓")
        self.icon_label.show()
        self.visual_caption.setText("VERIFIED")

        self.title.setText("CONNECTION SUCCESSFUL")
        self.subtitle.setText("Encryption protocol active and stable")
        self.info_value_label(self.gateway_label).setText(self.host)
        self.info_value_label(self.status_label).setText("STABLE")
        self.info_value_label(self.node_label).setText(f"{users} USER RECORDS FOUND")

        self.action_btn.setText("Continue" if self.origin == "face" else "Return to Settings")
        self.action_btn.show()
        self.close_btn.setEnabled(True)
        self.close_btn.show()
        self.close_btn.raise_()

    def set_failed(self, error_text: str = ""):
        self.state = "failed"
        self.error_text = error_text or "Connection failed."

        if self._status_timer is not None:
            self._status_timer.stop()
        if self.spinner is not None:
            self.spinner.stop()

        self.visual_panel.setObjectName("PiConnectionVisualFailed")
        self.visual_panel.style().unpolish(self.visual_panel)
        self.visual_panel.style().polish(self.visual_panel)

        self.spinner.hide()
        self.icon_label.setText("×")
        self.icon_label.show()
        self.visual_caption.setText("FAILED")

        self.title.setText("CONNECTION FAILED")
        self.subtitle.setText("Please set/check Pi hostname or IP in Settings, then connect again.")
        self.info_value_label(self.gateway_label).setText(self.host)
        self.info_value_label(self.status_label).setText("OFFLINE")
        self.info_value_label(self.node_label).setText("FACE RECOGNITION API")

        self.action_btn.setText("Return to Settings")
        self.action_btn.show()
        self.close_btn.setEnabled(True)
        self.close_btn.show()
        self.close_btn.raise_()
