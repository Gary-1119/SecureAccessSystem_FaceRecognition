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
        self.ntid_input.setPlaceholderText("e.g. 4372447")
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
            retry.clicked.connect(self.accept)

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
