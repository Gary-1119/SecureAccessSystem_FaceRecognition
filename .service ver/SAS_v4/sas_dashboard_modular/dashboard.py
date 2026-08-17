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
    QFileDialog,
    QMessageBox,
)

from app_config import *
from ui_components import *
from dialogs import *

from services.admin_service import AdminService
from services.credential_service import CredentialService
from services.ad_service import ActiveDirectoryService
from services.face_api_service import FaceApiService
from services.recognition_state_service import RecognitionStateService
from services.runtime_lock_service import RuntimeLockService

class SecureAccessDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui_bridge = UiBridge()
        self.top_nav_buttons = {}
        self.current_top_tab = "Dashboard"
        self.time_left = 17
        self.total_seconds = 60
        self.is_locked = True
        self.is_logged_in = False
        self.current_user = None
        self.current_user_role = "Guest"
        self.is_admin = False
        self.server_path = SERVER_PATH
        self.pi_api_host = "10.121.168.62"
        self.pi_api_port = "5000"
        self.pi_api_base = f"http://{self.pi_api_host}:{self.pi_api_port}"

        # Backend services migrated from lockapp.py.
        # Keep business logic here, not inside the UI methods.
        self.admin_service = AdminService(ADMIN_FILE)
        self.credential_service = CredentialService(CRED_FILE)
        self.ad_service = ActiveDirectoryService(SOAP_URL, debug_callback=self.login_debug)
        self.face_api_service = FaceApiService(self.pi_api_host, self.pi_api_port, debug_callback=self.append_system_log)
        self.recognition_state_service = RecognitionStateService(RECOGNITION_RESULT_FILE, SCAN_VALID_SECONDS)
        self.runtime_lock_service = RuntimeLockService()

        self.lock_timeout_seconds = DEFAULT_LOCK_TIMEOUT_SECONDS
        self.disable_keyboard_when_locked = False
        self.disable_mouse_when_locked = False
        self.disable_usb_when_locked = False
        self.enable_hotkey = True

        # Face detection state:
        # True  = authorised face currently detected, countdown pauses
        # False = face no longer detected, countdown resumes
        self.face_detected = False
        self._countdown_flip_anim_1 = None
        self._countdown_flip_anim_2 = None
        self._circle_flip_animating = False
        self._pending_face_detected_state = None
        self.ui_scale = 1.0
        self.compact_mode = False

        self.build_window()
        self.build_ui()
        self.apply_styles()
        self.apply_app_icon()
        self.load_settings_from_credentials()

        # Apply after the native window handle is ready.
        QTimer.singleShot(0, self.apply_window_chrome)

        self.start_timers()

    # --------------------------------------------------------
    # Window - keep this responsive size
    # --------------------------------------------------------
    def build_window(self):
        self.setWindowTitle("Secure Access System | Enterprise Dashboard")
        screen = QApplication.primaryScreen().availableGeometry()
        sw, sh = screen.width(), screen.height()

        self.ui_scale = max(0.68, min(1.0, min(sw / 1920, sh / 1080)))
        self.compact_mode = sw < 1500 or sh < 850

        if self.compact_mode:
            width = int(sw * 0.82)
            height = int(sh * 0.78)
            min_w, min_h = 900, 600
        else:
            width = int(sw * 0.75)
            height = int(sh * 0.76)
            min_w, min_h = 1180, 720

        width = max(min_w, min(width, sw - 80, 1480))
        height = max(min_h, min(height, sh - 80, 860))

        self.resize(width, height)
        self.setMinimumSize(min_w, min_h)
        self.move(screen.x() + (sw - width) // 2, screen.y() + (sh - height) // 2)

    # --------------------------------------------------------
    # Window chrome / app icon
    # --------------------------------------------------------
    def apply_app_icon(self):
        """Create a simple Secure Access app icon without needing an external .ico file."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor("#000000"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(6, 6, 52, 52, 14, 14)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Inter", 28, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")

        painter.end()

        icon = QIcon(pixmap)
        self.setWindowIcon(icon)

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setWindowIcon(icon)

    def apply_window_chrome(self):
        """Match the native Windows title bar colour with the app style."""
        if platform.system() != "Windows":
            return

        try:
            hwnd = int(self.winId())

            # Windows 11 / recent Windows DWM attributes.
            DWMWA_BORDER_COLOR = 34
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            def rgb_to_colorref(hex_color: str):
                hex_color = hex_color.lstrip("#")
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)

                # COLORREF uses 0x00BBGGRR
                return b << 16 | g << 8 | r

            # Match native title bar with dashboard background.
            caption_color = ctypes.c_int(rgb_to_colorref(Theme.BG))
            text_color = ctypes.c_int(rgb_to_colorref(Theme.TEXT))
            border_color = ctypes.c_int(rgb_to_colorref(Theme.BG))

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_CAPTION_COLOR,
                ctypes.byref(caption_color),
                ctypes.sizeof(caption_color),
            )

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_TEXT_COLOR,
                ctypes.byref(text_color),
                ctypes.sizeof(text_color),
            )

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                ctypes.byref(border_color),
                ctypes.sizeof(border_color),
            )

        except Exception as e:
            print("[WINDOW CHROME WARNING]", e)

    # --------------------------------------------------------
    # Build UI
    # --------------------------------------------------------
    def build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.build_header())

        self.stack = FadeStack()
        self.stack.setObjectName("PageStack")

        self.dashboard_page = self.build_dashboard_page()
        self.face_page = self.build_face_page()
        self.settings_page = self.build_settings_page()
        self.login_page = self.build_login_page()

        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.face_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.login_page)

        layout.addWidget(self.stack, 1)

        # Fixed footer. It is outside the stack/scroll area, so always remains below.
        layout.addWidget(self.build_footer_area())

        # Floating account menu for logged-in user.
        self.build_account_menu()

    def build_header(self):
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(64 if not self.compact_mode else 54)

        layout = QHBoxLayout(header)
        pad = 48 if not self.compact_mode else 26
        layout.setContentsMargins(pad, 0, pad, 0)
        layout.setSpacing(0)

        side_width = 260 if not self.compact_mode else 190

        left_zone = QWidget()
        left_zone.setFixedWidth(side_width)
        left_layout = QHBoxLayout(left_zone)
        left_layout.setContentsMargins(0, 0, 0, 0)

        brand = QLabel("SECURE ACCESS")
        brand.setObjectName("Brand")
        left_layout.addWidget(brand, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        center_zone = QWidget()
        center_layout = QHBoxLayout(center_zone)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(28 if not self.compact_mode else 16)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for tab_name in ["Dashboard", "Face Recognition", "Settings"]:
            btn = TopNavButton(tab_name, active=(tab_name == "Dashboard"))
            btn.clicked.connect(lambda checked=False, name=tab_name: self.switch_top_tab(name))
            self.top_nav_buttons[tab_name] = btn
            center_layout.addWidget(btn)

        right_zone = QWidget()
        right_zone.setFixedWidth(side_width)
        right_layout = QHBoxLayout(right_zone)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.login_btn = QPushButton("Login")
        self.login_btn.setObjectName("LoginButton")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setFixedSize(96 if not self.compact_mode else 82, 34 if not self.compact_mode else 30)
        self.login_btn.clicked.connect(self.handle_login_button_clicked)
        right_layout.addWidget(self.login_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(left_zone)
        layout.addWidget(center_zone, 1)
        layout.addWidget(right_zone)

        # Animated underline indicator for the active tab.
        # It performs a "snake" motion: stretch first, then shorten into the next tab.
        self.nav_header = header
        self.tab_indicator = QFrame(header)
        self.tab_indicator.setObjectName("TabIndicator")
        self.tab_indicator.setFixedHeight(2)
        self.tab_indicator.hide()
        self.tab_indicator.raise_()
        self.tab_indicator_anim = None

        QTimer.singleShot(120, lambda: self.animate_tab_indicator("Dashboard", animate=False))

        return header

    def animate_tab_indicator(self, tab_name: str, animate: bool = True):
        """Animate active tab underline with stretch-shorten snake effect."""
        if not hasattr(self, "tab_indicator") or not hasattr(self, "nav_header"):
            return

        btn = self.top_nav_buttons.get(tab_name)
        if btn is None:
            return

        header = self.nav_header
        btn_pos = btn.mapTo(header, btn.rect().topLeft())

        target_w = max(30, int(btn.width() * 0.72))
        target_h = 2
        target_x = btn_pos.x() + (btn.width() - target_w) // 2
        target_y = header.height() - target_h - 1

        target = QRect(target_x, target_y, target_w, target_h)

        if not self.tab_indicator.isVisible() or not animate:
            self.tab_indicator.setGeometry(target)
            self.tab_indicator.show()
            self.tab_indicator.raise_()
            return

        start = self.tab_indicator.geometry()

        # Snake midpoint: underline stretches to cover the distance,
        # then contracts into the selected tab.
        left = min(start.x(), target.x())
        right = max(start.x() + start.width(), target.x() + target.width())
        mid = QRect(left, target_y, right - left, target_h)

        if self.tab_indicator_anim is not None:
            self.tab_indicator_anim.stop()

        self.tab_indicator_anim = QPropertyAnimation(self.tab_indicator, b"geometry", self)
        self.tab_indicator_anim.setDuration(300)
        self.tab_indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.tab_indicator_anim.setStartValue(start)
        self.tab_indicator_anim.setKeyValueAt(0.45, mid)
        self.tab_indicator_anim.setEndValue(target)
        self.tab_indicator_anim.start()

    def switch_top_tab(self, name: str):
        self.current_top_tab = name

        for tab_name, btn in self.top_nav_buttons.items():
            btn.set_active(tab_name == name)

        if name in self.top_nav_buttons:
            self.animate_tab_indicator(name, animate=True)

        if name == "Dashboard":
            self.stack.fade_to(self.dashboard_page)
            self.update_time()
        elif name == "Face Recognition":
            self.stack.fade_to(self.face_page)
        elif name == "Settings":
            self.stack.fade_to(self.settings_page)
        elif name == "Login":
            self.stack.fade_to(self.login_page)

    # --------------------------------------------------------
    # Login popup
    # --------------------------------------------------------
    def clear_blur_effect(self, widget):
        """Clear blur effect safely with a smooth blur-out animation."""
        old_effect = widget.graphicsEffect()

        if old_effect is None:
            return

        self._blur_out_anim = QPropertyAnimation(old_effect, b"blurRadius", self)
        self._blur_out_anim.setDuration(180)
        self._blur_out_anim.setStartValue(10)
        self._blur_out_anim.setEndValue(0)
        self._blur_out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finish_clear():
            old_effect.setEnabled(False)
            old_effect.deleteLater()

        self._blur_out_anim.finished.connect(finish_clear)
        self._blur_out_anim.start()

    def open_login_popup(self):
        """Blur the current dashboard and show the login popup."""
        root = self.centralWidget()

        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(0)
        root.setGraphicsEffect(blur)

        # Smooth background blur.
        self._blur_anim = QPropertyAnimation(blur, b"blurRadius", self)
        self._blur_anim.setDuration(220)
        self._blur_anim.setStartValue(0)
        self._blur_anim.setEndValue(10)
        self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._blur_anim.start()

        dialog = LoginPopupDialog(self, self.compact_mode)

        # Centre popup relative to the main window.
        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        dialog.finished.connect(lambda _: self.clear_blur_effect(root))
        dialog.exec()

    def handle_login_button_clicked(self):
        """Login button behaviour.

        - Guest: open login popup
        - Logged in: show account dropdown
        """
        if self.current_user:
            self.append_system_log(f"Account menu opened for {self.current_user.upper()}")
            self.toggle_account_menu()
        else:
            self.open_login_popup()

    def build_account_menu(self):
        """Animated dropdown menu shown when the logged-in NTID button is pressed."""
        self.account_menu = QFrame(self.centralWidget() if self.centralWidget() is not None else self)
        self.account_menu.setObjectName("AccountDropdown")
        self.account_menu.setFixedWidth(190 if not self.compact_mode else 170)
        self.account_menu.resize(190 if not self.compact_mode else 170, 0)
        self.account_menu.hide()

        self.account_menu_effect = QGraphicsOpacityEffect(self.account_menu)
        self.account_menu_effect.setOpacity(0.0)
        self.account_menu.setGraphicsEffect(self.account_menu_effect)

        menu_layout = QVBoxLayout(self.account_menu)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(6)

        self.account_menu_title = QLabel("SIGNED IN")
        self.account_menu_title.setObjectName("AccountDropdownTitle")

        self.account_menu_user = QLabel("Guest")
        self.account_menu_user.setObjectName("AccountDropdownUser")

        switch_btn = QPushButton("Switch Account")
        switch_btn.setObjectName("AccountDropdownButton")
        switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        switch_btn.clicked.connect(self.switch_account_flow)

        logout_btn = QPushButton("Log Out")
        logout_btn.setObjectName("AccountDropdownDangerButton")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self.logout_flow)

        menu_layout.addWidget(self.account_menu_title)
        menu_layout.addWidget(self.account_menu_user)
        menu_layout.addWidget(switch_btn)
        menu_layout.addWidget(logout_btn)

        self.account_menu_height = 166 if not self.compact_mode else 148
        self.account_menu_anim = None
        self.account_menu_opacity_anim = None

    def get_account_menu_target_geometry(self):
        if not hasattr(self, "account_menu") or not hasattr(self, "login_btn"):
            return QRect(0, 0, 190 if not self.compact_mode else 170, self.account_menu_height)

        menu_w = 190 if not self.compact_mode else 170
        menu_h = self.account_menu_height

        parent_widget = self.account_menu.parentWidget()
        if parent_widget is None:
            parent_widget = self

        global_bottom_right = self.login_btn.mapToGlobal(QPoint(self.login_btn.width(), self.login_btn.height()))
        global_bottom_left = self.login_btn.mapToGlobal(QPoint(0, self.login_btn.height()))

        btn_bottom_right = parent_widget.mapFromGlobal(global_bottom_right)
        btn_bottom_left = parent_widget.mapFromGlobal(global_bottom_left)

        x = btn_bottom_right.x() - menu_w
        y = btn_bottom_left.y() + 8

        x = max(12, min(x, parent_widget.width() - menu_w - 12))
        y = max(12, y)

        return QRect(x, y, menu_w, menu_h)

    def position_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        target = self.get_account_menu_target_geometry()
        self.account_menu.setGeometry(target)
        self.account_menu.raise_()

    def toggle_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        if self.account_menu.isVisible() and self.account_menu.maximumHeight() > 0:
            self.hide_account_menu()
        else:
            self.show_account_menu()

    def show_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        if self.current_user:
            self.account_menu_user.setText(f"{self.current_user.upper()} • {self.current_user_role}")
        else:
            self.account_menu_user.setText("Guest")

        target = self.get_account_menu_target_geometry()
        start = QRect(target.x(), target.y(), target.width(), 0)

        self.account_menu.setEnabled(True)
        self.account_menu.setGeometry(start)
        self.account_menu.show()
        self.account_menu.raise_()

        if self.account_menu_anim is not None:
            self.account_menu_anim.stop()
        if self.account_menu_opacity_anim is not None:
            self.account_menu_opacity_anim.stop()

        self.account_menu_effect.setOpacity(0.0)

        self.account_menu_anim = QPropertyAnimation(self.account_menu, b"geometry", self)
        self.account_menu_anim.setDuration(220)
        self.account_menu_anim.setStartValue(start)
        self.account_menu_anim.setEndValue(target)
        self.account_menu_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.account_menu_opacity_anim = QPropertyAnimation(self.account_menu_effect, b"opacity", self)
        self.account_menu_opacity_anim.setDuration(180)
        self.account_menu_opacity_anim.setStartValue(0.0)
        self.account_menu_opacity_anim.setEndValue(1.0)
        self.account_menu_opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.account_menu_anim.start()
        self.account_menu_opacity_anim.start()

        self.append_system_log(
            f"Account menu visible={self.account_menu.isVisible()} "
            f"geometry={self.account_menu.geometry().getRect()}"
        )

    def hide_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        if not self.account_menu.isVisible():
            return

        if self.account_menu_anim is not None:
            self.account_menu_anim.stop()
        if self.account_menu_opacity_anim is not None:
            self.account_menu_opacity_anim.stop()

        start = self.account_menu.geometry()
        end = QRect(start.x(), start.y(), start.width(), 0)

        self.account_menu_anim = QPropertyAnimation(self.account_menu, b"geometry", self)
        self.account_menu_anim.setDuration(180)
        self.account_menu_anim.setStartValue(start)
        self.account_menu_anim.setEndValue(end)
        self.account_menu_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        self.account_menu_opacity_anim = QPropertyAnimation(self.account_menu_effect, b"opacity", self)
        self.account_menu_opacity_anim.setDuration(150)
        self.account_menu_opacity_anim.setStartValue(self.account_menu_effect.opacity())
        self.account_menu_opacity_anim.setEndValue(0.0)
        self.account_menu_opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def after_hide():
            self.account_menu.hide()

        self.account_menu_anim.finished.connect(after_hide)
        self.account_menu_anim.start()
        self.account_menu_opacity_anim.start()

    def switch_account_flow(self):
        """Switch account: keep current session until another login succeeds."""
        self.hide_account_menu()
        self.open_login_popup()

    def logout_flow(self):
        """Complete logout flow."""
        old_user = self.current_user.upper() if self.current_user else "Unknown"

        self.hide_account_menu()

        self.is_logged_in = False
        self.current_user = None
        self.current_user_role = "Guest"
        self.is_admin = False

        self.update_account_ui()

        # Lock the system after logout so the state is safe.
        self.is_locked = True
        self.apply_lock_state()

        self.set_face_detected(False)
        self.append_system_log(f"Logged out: {old_user}")

    def mousePressEvent(self, event):
        if hasattr(self, "account_menu") and self.account_menu.isVisible():
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

            # login_btn.geometry() is relative to its parent, not QMainWindow.
            # Convert it to main-window coordinates before checking.
            btn_top_left = self.login_btn.mapTo(self, QPoint(0, 0))
            btn_rect = QRect(
                btn_top_left.x(),
                btn_top_left.y(),
                self.login_btn.width(),
                self.login_btn.height()
            )

            clicked_menu = self.account_menu.geometry().contains(pos)
            clicked_login_button = btn_rect.contains(pos)

            if not clicked_menu and not clicked_login_button:
                self.hide_account_menu()

        super().mousePressEvent(event)


    # --------------------------------------------------------
    # Login helpers
    # --------------------------------------------------------
    def toggle_login_password(self):
        if not hasattr(self, "login_password_input"):
            return

        if self.login_password_input.echoMode() == QLineEdit.EchoMode.Password:
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.login_toggle_btn.setText("Hide")
        else:
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.login_toggle_btn.setText("Show")

    def login_requested(self):
        ntid = self.login_ntid_input.text().strip() if hasattr(self, "login_ntid_input") else ""
        password = self.login_password_input.text().strip() if hasattr(self, "login_password_input") else ""

        if not ntid:
            self.login_status_label.setText("Please enter your NTID.")
            self.login_ntid_input.setFocus()
            return

        if not password:
            self.login_status_label.setText("Please enter your password.")
            self.login_password_input.setFocus()
            return

        # Temporary only. Later connect this to your SOAP / AD validation.
        self.login_status_label.setText(f"Authentication requested for NTID: {ntid}")

    # --------------------------------------------------------
    # Pages
    # --------------------------------------------------------
    def make_scrollbar_invisible(self, scroll: QScrollArea):
        """Keep scrolling enabled, but hide the visible scroll bars."""
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(scroll.styleSheet() + """
            QScrollBar:vertical {
                width: 0px;
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 0px;
                background: transparent;
            }
            QScrollBar::handle {
                background: transparent;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                width: 0px;
                height: 0px;
                background: transparent;
            }
        """)

    def build_dashboard_page(self):
        outer = QWidget()
        outer.setObjectName("Page")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("MainContent")
        # Responsive full-width content. Do not cap width, so fullscreen layouts can expand naturally.
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(main)
        mx = 42 if not self.compact_mode else 24
        mt = 20 if not self.compact_mode else 12
        mb = 12 if not self.compact_mode else 8
        sp = 16 if not self.compact_mode else 10

        main_layout.setContentsMargins(mx, mt, mx, mb)
        main_layout.setSpacing(sp)
        main_layout.addWidget(self.build_time_section())
        main_layout.addLayout(self.build_bento_cards())
        main_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    def build_face_page(self):
        outer = QWidget()
        outer.setObjectName("Page")

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("MainContent")
        # Responsive full-width content. Do not cap width, so fullscreen layouts can expand naturally.
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(main)
        mx = 42 if not self.compact_mode else 24
        mt = 24 if not self.compact_mode else 16
        mb = 12 if not self.compact_mode else 8
        sp = 20 if not self.compact_mode else 12
        main_layout.setContentsMargins(mx, mt, mx, mb)
        main_layout.setSpacing(sp)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20 if not self.compact_mode else 12)
        grid.setVerticalSpacing(20 if not self.compact_mode else 12)

        # Layout target:
        # Left side: camera feed on top, then Primary Controls + System Log beside each other.
        # Right side: Authorised Users panel stretches from top to bottom.
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 2)

        camera = self.camera_feed_card()
        controls = self.face_controls_card()
        logs = self.system_log_card()
        users = self.face_users_card()

        self.face_cards = [camera, controls, logs, users]
        self.update_face_card_sizes()

        grid.addWidget(camera, 0, 0, 1, 2)
        grid.addWidget(controls, 1, 0)
        grid.addWidget(logs, 1, 1)
        grid.addWidget(users, 0, 2, 2, 1)

        main_layout.addLayout(grid)
        main_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    def build_settings_page(self):
        """Settings page based on the uploaded settings UI reference."""
        outer = QWidget()
        outer.setObjectName("Page")

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("MainContent")
        # Responsive full-width content. Do not cap width, so fullscreen layouts can expand naturally.
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(main)
        layout.setContentsMargins(
            42 if not self.compact_mode else 24,
            28 if not self.compact_mode else 18,
            42 if not self.compact_mode else 24,
            28 if not self.compact_mode else 18,
        )
        layout.setSpacing(20 if not self.compact_mode else 14)

        # Settings header row:
        # Left = page title and description
        # Right = Cancel / Save Connect action buttons
        settings_header = QHBoxLayout()
        settings_header.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(6)

        title = QLabel("System Configuration")
        title.setObjectName("SettingsTitle")

        desc = QLabel("Manage administrative credentials and security protocol thresholds.")
        desc.setObjectName("SettingsDesc")

        title_box.addWidget(title)
        title_box.addWidget(desc)

        header_actions = QHBoxLayout()
        header_actions.setSpacing(10)

        save = QPushButton("Save Connect")
        save.setObjectName("SettingsPrimaryButton")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setMinimumHeight(40 if not self.compact_mode else 34)
        save.setMinimumWidth(118 if not self.compact_mode else 104)
        save.clicked.connect(self.save_settings_from_ui)

        header_actions.addWidget(save)

        settings_header.addLayout(title_box, 1)
        settings_header.addLayout(header_actions, 0)

        layout.addLayout(settings_header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20 if not self.compact_mode else 12)
        grid.setVerticalSpacing(20 if not self.compact_mode else 12)
        grid.setColumnStretch(0, 7)
        grid.setColumnStretch(1, 5)

        grid.addWidget(self.server_credentials_card(), 0, 0)
        grid.addWidget(self.security_options_card(), 0, 1)
        grid.addWidget(self.pi_connectivity_card(), 1, 0)
        grid.addWidget(self.auto_capture_card(), 1, 1)
        grid.addWidget(self.face_data_transfer_card(), 2, 0)
        grid.addWidget(self.admin_management_card(), 2, 1)

        layout.addLayout(grid)


        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    def build_login_page(self):
        """Login page based on the uploaded login overlay design, using the same header/footer."""
        outer = QWidget()
        outer.setObjectName("Page")

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("LoginMainContent")

        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(
            42 if not self.compact_mode else 24,
            30 if not self.compact_mode else 20,
            42 if not self.compact_mode else 24,
            30 if not self.compact_mode else 20,
        )
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("LoginCard")
        card.setMaximumWidth(430 if not self.compact_mode else 380)
        card.setMinimumWidth(360 if not self.compact_mode else 320)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            34 if not self.compact_mode else 26,
            32 if not self.compact_mode else 24,
            34 if not self.compact_mode else 26,
            30 if not self.compact_mode else 24,
        )
        card_layout.setSpacing(16 if not self.compact_mode else 12)

        icon = QLabel("▣")
        icon.setObjectName("LoginShieldIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(56 if not self.compact_mode else 48, 56 if not self.compact_mode else 48)

        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon)
        icon_row.addStretch()
        card_layout.addLayout(icon_row)

        title = QLabel("SECURE ACCESS SYSTEM")
        title.setObjectName("LoginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Enter your credentials to manage security")
        subtitle.setObjectName("LoginSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        form = QVBoxLayout()
        form.setSpacing(12 if not self.compact_mode else 10)

        ntid_label = QLabel("NTID")
        ntid_label.setObjectName("LoginFieldLabel")

        self.login_ntid_input = QLineEdit()
        self.login_ntid_input.setObjectName("LoginInput")
        self.login_ntid_input.setPlaceholderText("e.g. 4372447")
        self.login_ntid_input.setMinimumHeight(46 if not self.compact_mode else 40)

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

        self.login_password_input = QLineEdit()
        self.login_password_input.setObjectName("LoginInput")
        self.login_password_input.setPlaceholderText("••••••••")
        self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password_input.setMinimumHeight(46 if not self.compact_mode else 40)

        self.login_toggle_btn = QPushButton("Show")
        self.login_toggle_btn.setObjectName("LoginToggleButton")
        self.login_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_toggle_btn.setFixedSize(64 if not self.compact_mode else 56, 40 if not self.compact_mode else 36)
        self.login_toggle_btn.clicked.connect(self.toggle_login_password)

        password_row.addWidget(self.login_password_input, 1)
        password_row.addWidget(self.login_toggle_btn)

        self.login_status_label = QLabel("Administrator oversight enabled. Session monitoring active.")
        self.login_status_label.setObjectName("LoginStatus")
        self.login_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_status_label.setWordWrap(True)

        login_btn = QPushButton("Login  →")
        login_btn.setObjectName("LoginSubmitButton")
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.setMinimumHeight(46 if not self.compact_mode else 40)
        login_btn.clicked.connect(self.login_requested)
        login_btn.setDefault(True)
        login_btn.setAutoDefault(True)

        self.login_ntid_input.returnPressed.connect(self.login_requested)
        self.login_password_input.returnPressed.connect(self.login_requested)

        form.addWidget(ntid_label)
        form.addWidget(self.login_ntid_input)
        form.addLayout(password_top)
        form.addLayout(password_row)
        form.addWidget(login_btn)
        card_layout.addLayout(form)

        divider = QFrame()
        divider.setObjectName("LoginDivider")
        divider.setFixedHeight(1)
        card_layout.addWidget(divider)
        card_layout.addWidget(self.login_status_label)

        main_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    # --------------------------------------------------------
    # Settings page parts
    # --------------------------------------------------------
    def settings_card_base(self, title_text: str, icon_text: str):
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            24 if not self.compact_mode else 18,
            22 if not self.compact_mode else 16,
            24 if not self.compact_mode else 18,
            22 if not self.compact_mode else 16,
        )
        layout.setSpacing(14 if not self.compact_mode else 10)

        header = QHBoxLayout()
        icon = QLabel(icon_text)
        icon.setObjectName("SettingsCardIcon")
        title = QLabel(title_text)
        title.setObjectName("SettingsCardTitle")
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        line = QFrame()
        line.setObjectName("SettingsDivider")
        line.setFixedHeight(1)
        layout.addWidget(line)

        return card, layout

    def settings_label(self, text: str):
        label = QLabel(text)
        label.setObjectName("SettingsLabel")
        return label

    def settings_input(self, value: str = "", placeholder: str = "", password: bool = False, readonly: bool = False):
        field = QLineEdit()
        field.setObjectName("SettingsInput")
        field.setText(value)
        field.setPlaceholderText(placeholder)
        field.setReadOnly(readonly)
        if password:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setMinimumHeight(38 if not self.compact_mode else 34)
        return field

    def settings_button(self, text: str, primary: bool = False):
        btn = QPushButton(text)
        btn.setObjectName("SettingsPrimaryButton" if primary else "SettingsSecondaryButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(38 if not self.compact_mode else 34)
        return btn

    def add_form_row(self, layout: QVBoxLayout, label_text: str, widget: QWidget):
        label = self.settings_label(label_text)
        layout.addWidget(label)
        layout.addWidget(widget)

    def server_credentials_card(self):
        card, layout = self.settings_card_base("Server Credentials", "▣")

        two_col = QGridLayout()
        two_col.setHorizontalSpacing(14)
        two_col.setVerticalSpacing(8)

        ntid_box = QVBoxLayout()
        ntid_box.addWidget(self.settings_label("NTID / Username"))
        self.settings_ntid_input = self.settings_input("4372447", readonly=False)
        ntid_box.addWidget(self.settings_ntid_input)

        pass_box = QVBoxLayout()
        pass_box.addWidget(self.settings_label("Password"))
        self.settings_password_input = self.settings_input("", password=True)
        pass_box.addWidget(self.settings_password_input)

        two_col.addLayout(ntid_box, 0, 0)
        two_col.addLayout(pass_box, 0, 1)
        layout.addLayout(two_col)

        domain = QLabel("corp.JABIL.ORG        (fixed)")
        domain.setObjectName("SettingsReadonlyBox")
        self.add_form_row(layout, "Domain", domain)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.settings_server_path_input = self.settings_input("//mypenm0vdspc16/internship/Gary LIm")
        browse = self.settings_button("Browse")
        browse.clicked.connect(self.browse_server_path)
        path_row.addWidget(self.settings_server_path_input, 1)
        path_row.addWidget(browse)
        layout.addWidget(self.settings_label("Server Path"))
        layout.addLayout(path_row)

        return card

    def pi_connectivity_card(self):
        card, layout = self.settings_card_base("Pi Connectivity", "⌁")

        host_row = QHBoxLayout()
        host_row.setSpacing(8)
        self.pi_host_input = self.settings_input(self.pi_api_host, "raspberrypi.local")
        connect = self.settings_button("Connect", primary=True)
        connect.clicked.connect(self._face_api_test_connection)
        host_row.addWidget(self.pi_host_input, 1)
        host_row.addWidget(connect)
        layout.addWidget(self.settings_label("Pi Hostname"))
        layout.addLayout(host_row)

        self.pi_status_label = QLabel("●  Status: Disconnected")
        self.pi_status_label.setObjectName("SettingsDisconnected")
        layout.addWidget(self.pi_status_label)

        return card

    def face_data_transfer_card(self):
        card, layout = self.settings_card_base("Face Data Transfer", "◎")

        top_actions = QHBoxLayout()
        top_actions.addStretch()
        export_btn = self.settings_button("⇧  Export")
        import_btn = self.settings_button("⇩  Import")
        top_actions.addWidget(export_btn)
        top_actions.addWidget(import_btn)
        layout.addLayout(top_actions)

        panel = QFrame()
        panel.setObjectName("SettingsInnerPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(8)

        title = QLabel("Transfer Face Data via SFTP")
        title.setObjectName("SettingsMiniTitle")
        desc = QLabel("Securely send or receive dataset packages between authorised nodes.")
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)

        actions = QHBoxLayout()
        send = self.settings_button("Send to Another Pi", primary=True)
        check = self.settings_button("Check Received")
        actions.addWidget(send)
        actions.addWidget(check)

        panel_layout.addWidget(title)
        panel_layout.addWidget(desc)
        panel_layout.addLayout(actions)
        layout.addWidget(panel)

        return card

    def security_options_card(self):
        card, layout = self.settings_card_base("Security Options", "◈")

        self.security_option_buttons = {}

        for key, text, default in [
            ("disable_keyboard", "Disable Keyboard When Locked", True),
            ("disable_mouse", "Disable Mouse When Locked", True),
            ("disable_usb", "Disable USB Storage When Locked", True),
            ("enable_hotkey", "Enable Emergency Hotkey", True),
        ]:
            row = QHBoxLayout()
            label = QLabel(text)
            label.setObjectName("SettingsOptionText")
            cb = QPushButton("✓")
            cb.setObjectName("SettingsCheckBoxButton")
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setCheckable(True)
            cb.setChecked(default)
            cb.setFixedSize(26, 26)
            self.security_option_buttons[key] = cb
            row.addWidget(label)
            row.addStretch()
            row.addWidget(cb)
            layout.addLayout(row)

        layout.addSpacing(4)
        layout.addWidget(self.settings_label("Inactivity Lock Time"))

        time_grid = QGridLayout()
        time_grid.setHorizontalSpacing(8)

        self.timeout_inputs = {}
        for col, (key, label, value) in enumerate([("hours", "Hours", "0"), ("minutes", "Minutes", "5"), ("seconds", "Seconds", "0")]):
            box = QVBoxLayout()
            inp = self.settings_input(value, "0")
            inp.setFixedWidth(90 if not self.compact_mode else 70)
            self.timeout_inputs[key] = inp
            cap = QLabel(label)
            cap.setObjectName("SettingsLabel")
            box.addWidget(inp)
            box.addWidget(cap)
            time_grid.addLayout(box, 0, col)

        layout.addLayout(time_grid)
        layout.addStretch()
        return card

    def auto_capture_card(self):
        card, layout = self.settings_card_base("Auto-Capture", "▣")

        desc = QLabel("Automatically capture face data when a subject is detected in range.")
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.auto_capture_toggle = AutoCaptureSegment(self, self.compact_mode)
        layout.addWidget(self.auto_capture_toggle)

        layout.addStretch()
        return card

    def admin_management_card(self):
        card, layout = self.settings_card_base("Admin Management", "👥")

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.admin_add_input = self.settings_input("", "Enter NTID to add...")
        add_btn = self.settings_button("Add", primary=True)
        add_btn.clicked.connect(self.add_admin_from_ui)
        add_row.addWidget(self.admin_add_input, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        admin_box = QFrame()
        admin_box.setObjectName("AdminListBox")
        self.admin_list_layout = QVBoxLayout(admin_box)
        self.admin_list_layout.setContentsMargins(0, 0, 0, 0)
        self.admin_list_layout.setSpacing(0)

        layout.addWidget(admin_box)
        QTimer.singleShot(0, self.refresh_admin_list_ui)
        layout.addStretch()
        return card

    def admin_row(self, ntid: str, tag: str = "", removable: bool = False):
        row = QFrame()
        row.setObjectName("AdminRow")
        row.setMinimumHeight(40)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)

        name = QLabel(ntid + (f"  {tag}" if tag else ""))
        name.setObjectName("AdminName")
        layout.addWidget(name)
        layout.addStretch()

        if removable:
            remove = QPushButton("Remove")
            remove.setObjectName("RemoveButton")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(remove)

        return row

    # --------------------------------------------------------
    # Dashboard page parts
    # --------------------------------------------------------
    def build_time_section(self):
        section = QWidget()
        section.setObjectName("TimeSection")
        section.setFixedHeight(150 if not self.compact_mode else 105)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4 if not self.compact_mode else 2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.time_label = QLabel("08:16:23")
        self.time_label.setObjectName("TerminalTime")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.date_label = QLabel("THURSDAY, OCTOBER 24, 2024 • GLOBAL NODE 01")
        self.date_label.setObjectName("TerminalDate")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)
        return section

    def build_bento_cards(self):
        grid = QGridLayout()
        grid.setHorizontalSpacing(20 if not self.compact_mode else 12)
        grid.setVerticalSpacing(20 if not self.compact_mode else 12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        status = self.status_card()
        countdown = self.countdown_card()
        users = self.users_card()

        self.dashboard_cards = [status, countdown, users]
        self.update_dashboard_card_sizes()

        grid.addWidget(status, 0, 0)
        grid.addWidget(countdown, 0, 1)
        grid.addWidget(users, 0, 2)
        return grid

    def card_padding(self):
        return (34, 30) if not self.compact_mode else (22, 18)

    def status_card(self):
        card = GlassCard(green_border=True)
        self.status_card_widget = card
        card.setObjectName("StatusCard")

        # Faded lock/unlock watermark inside the card
        self.status_watermark = QLabel("🔓", card)
        self.status_watermark.setObjectName("FadeLockBgWhite")
        self.status_watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_watermark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_watermark.lower()

        def move_watermark(event):
            size = 130 if not self.compact_mode else 95
            self.status_watermark.setFixedSize(size, size)
            y_pos = 105 if not self.compact_mode else 82
            x_pos = card.width() - size - 32
            self.status_watermark.move(x_pos, y_pos)
            QFrame.resizeEvent(card, event)

        card.resizeEvent = move_watermark

        layout = QVBoxLayout(card)
        px, py = self.card_padding()
        layout.setContentsMargins(px, py, px, py)
        layout.setSpacing(20 if not self.compact_mode else 12)

        label = QLabel("PROTOCOL STATUS")
        label.setObjectName("CardEyebrowWhite")

        self.status_title = QLabel("SYSTEM UNLOCKED")
        self.status_title.setObjectName("UnlockedTitleWhite")

        layout.addWidget(label)
        layout.addWidget(self.status_title)

        middle = QHBoxLayout()
        lock_box = QVBoxLayout()

        self.status_lock_icon = QLabel("🔓")
        self.status_lock_icon.setObjectName("WhiteLockIcon")
        self.status_lock_icon.setAlignment(Qt.AlignmentFlag.AlignLeft)

        encrypted = QLabel("ENCRYPTED")
        encrypted.setObjectName("EncryptedWhite")
        lock_box.addWidget(self.status_lock_icon)
        lock_box.addWidget(encrypted)

        self.status_pill = QLabel("●  UNLOCKED")
        self.status_pill.setObjectName("UnlockedPillGreen")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFixedSize(120 if not self.compact_mode else 104, 34 if not self.compact_mode else 28)

        middle.addLayout(lock_box)
        middle.addStretch()
        middle.addWidget(self.status_pill, alignment=Qt.AlignmentFlag.AlignBottom)

        line = QFrame()
        line.setObjectName("DividerWhite")
        line.setFixedHeight(1)

        self.manual_lock_btn = QPushButton("MANUAL LOCK")
        self.manual_lock_btn.setObjectName("ManualLockButtonWhite")
        self.manual_lock_btn.setFixedHeight(42 if not self.compact_mode else 34)
        self.manual_lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_lock_btn.clicked.connect(self.toggle_lock_state)

        layout.addStretch()
        layout.addLayout(middle)
        layout.addWidget(line)
        layout.addWidget(self.manual_lock_btn)

        self.apply_lock_state()
        return card

    def toggle_lock_state(self):
        if self.is_locked:
            self._grant_access(self.current_user or "")
        else:
            self._do_logout()

    def apply_lock_state(self):
        """Update the status card colour and icon based on locked/unlocked state."""
        if not hasattr(self, "status_card_widget"):
            return

        radius = 28 if not self.compact_mode else 22

        if self.is_locked:
            # Direct stylesheet is the most reliable way to force the red state.
            self.status_card_widget.setStyleSheet(
                f"""
                QFrame#StatusCard {{
                    background-color: #B23A3A;
                    border: none;
                    border-radius: {radius}px;
                }}
                """
            )
            self.status_title.setText("SYSTEM LOCKED")
            self.status_lock_icon.setText("🔒")
            self.status_watermark.setText("🔒")
            self.status_pill.setText("●  LOCKED")
            self.status_pill.setObjectName("LockedPillRed")
            self.manual_lock_btn.setText("UNLOCK")
            self.manual_lock_btn.setProperty("lockState", "locked")
        else:
            # Direct stylesheet is the most reliable way to force the green state.
            self.status_card_widget.setStyleSheet(
                f"""
                QFrame#StatusCard {{
                    background-color: #3F9468;
                    border: none;
                    border-radius: {radius}px;
                }}
                """
            )
            self.status_title.setText("SYSTEM UNLOCKED")
            self.status_lock_icon.setText("🔓")
            self.status_watermark.setText("🔓")
            self.status_pill.setText("●  UNLOCKED")
            self.status_pill.setObjectName("UnlockedPillGreen")
            self.manual_lock_btn.setText("MANUAL LOCK")
            self.manual_lock_btn.setProperty("lockState", "unlocked")

        for widget in (
            self.status_pill,
            self.manual_lock_btn,
            self.status_title,
            self.status_lock_icon,
            self.status_watermark,
        ):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

        self.status_card_widget.update()

    def countdown_card(self):
        card = GlassCard()
        self.countdown_card_widget = card
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(card)
        px, py = self.card_padding()
        layout.setContentsMargins(px, py, px, py)
        layout.setSpacing(14 if not self.compact_mode else 10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Only this circle area flips. The outer card stays fixed.
        self.circle_flip_container = QWidget()
        self.circle_flip_container.setObjectName("CircleFlipContainer")
        circle_size = 168 if not self.compact_mode else 126
        self.circle_flip_container.setFixedSize(circle_size, circle_size)

        self.circle_stack = QStackedWidget(self.circle_flip_container)
        self.circle_stack.setObjectName("CircleStack")
        self.circle_stack.setGeometry(0, 0, circle_size, circle_size)
        self.circle_stack.setFixedSize(circle_size, circle_size)

        self.timer_circle_front = self.build_timer_circle_front(circle_size)
        self.face_circle_back = self.build_face_circle_back(circle_size)

        self.circle_stack.addWidget(self.timer_circle_front)
        self.circle_stack.addWidget(self.face_circle_back)

        # Overlay used only during flip animation.
        # It draws a compressed pixmap, so the circle is not cut/clipped.
        self.circle_flip_overlay = FlipCircleLabel(self.circle_flip_container)
        self.circle_flip_overlay.setGeometry(0, 0, circle_size, circle_size)
        self.circle_flip_overlay.hide()

        self.countdown_title_label = QLabel("Auto-Lock Sequence")
        self.countdown_title_label.setObjectName("CountdownTitle")
        self.countdown_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_state_label = QLabel("Active session expires soon")
        self.face_state_label.setObjectName("CountdownDesc")
        self.face_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(self.circle_flip_container, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.countdown_title_label)
        layout.addWidget(self.face_state_label)
        layout.addStretch(1)

        # Temporary testing: click the card to toggle face detected / not detected.
        # Later call self.set_face_detected(True/False) from recognition_result.json.
        card.mousePressEvent = lambda event: self.set_face_detected(not self.face_detected)

        return card

    def build_timer_circle_front(self, circle_size: int):
        front = QWidget()
        front.setObjectName("CircleFace")

        layout = QVBoxLayout(front)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ring = ProgressRing(self.total_seconds, self.time_left)
        self.ring.setFixedSize(circle_size, circle_size)

        self.countdown_label = QLabel("00:17")
        self.countdown_label.setObjectName("CountdownText")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        remaining = QLabel("REMAINING")
        remaining.setObjectName("RemainingText")
        remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)

        overlay = QVBoxLayout(self.ring)
        overlay.setContentsMargins(0, 0, 0, 0)
        overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay.addWidget(self.countdown_label)
        overlay.addWidget(remaining)

        layout.addWidget(self.ring)
        return front

    def build_face_circle_back(self, circle_size: int):
        back = QFrame()
        back.setObjectName("FaceDetectedCircle")
        back.setFixedSize(circle_size, circle_size)

        layout = QVBoxLayout(back)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("☻")
        icon.setObjectName("FaceDetectedIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("FACE DETECTED")
        label.setObjectName("FaceDetectedCircleText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Slightly move the face icon and text upward for better visual balance.
        layout.addStretch(2)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(3)

        return back

    def set_face_detected(self, detected: bool):
        """Update face state.

        detected=True:
            - authorised face is currently detected
            - countdown pauses
            - only the circle flips like a coin
            - label below changes to authorised user detected

        detected=False:
            - face not detected
            - countdown resumes
            - circle flips back to timer
        """
        if self.face_detected == detected and not self._circle_flip_animating:
            return

        # If user clicks very fast, do not start another animation in the middle.
        # Store the latest target and apply it when the current flip finishes.
        if self._circle_flip_animating:
            self._pending_face_detected_state = detected
            return

        self.face_detected = detected
        target_index = 1 if detected else 0

        self.flip_countdown_circle(target_index, detected)

    def update_face_detected_label(self, detected: bool):
        if not hasattr(self, "face_state_label"):
            return

        if detected:
            self.face_state_label.setText("●  AUTHORISED USER DETECTED")
            self.face_state_label.setObjectName("FaceDetectedState")
        else:
            self.face_state_label.setText("Active session expires soon")
            self.face_state_label.setObjectName("CountdownDesc")

        self.face_state_label.style().unpolish(self.face_state_label)
        self.face_state_label.style().polish(self.face_state_label)
        self.face_state_label.update()

    def grab_circle_face(self, widget: QWidget) -> QPixmap:
        """Grab a transparent pixmap of a circle face for the coin-flip overlay."""
        pixmap = QPixmap(widget.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        widget.render(pixmap)
        return pixmap

    def flip_countdown_circle(self, target_index: int, detected: bool):
        """Coin-style flip for only the circle.

        The old version animated the QWidget width directly. That caused the
        circle to look cut. This version takes a pixmap snapshot and compresses
        the image horizontally like a coin flip.
        """
        if not hasattr(self, "circle_flip_container") or not hasattr(self, "circle_stack"):
            return

        if not hasattr(self, "circle_flip_overlay"):
            self.circle_stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            return

        holder = self.circle_flip_container
        stack = self.circle_stack
        overlay = self.circle_flip_overlay

        full_w = max(1, holder.width())
        full_h = max(1, holder.height())

        if full_w <= 1 or full_h <= 1:
            stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            return

        self._circle_flip_animating = True

        # Keep overlay aligned and use snapshots for animation.
        overlay.setGeometry(0, 0, full_w, full_h)

        current_widget = stack.currentWidget()
        target_widget = stack.widget(target_index)

        if current_widget is None or target_widget is None:
            stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            self._circle_flip_animating = False
            return

        start_pixmap = self.grab_circle_face(current_widget)
        target_pixmap = self.grab_circle_face(target_widget)

        overlay.set_pixmap(start_pixmap)
        overlay.set_scale_x(1.0)
        overlay.show()
        overlay.raise_()
        stack.hide()

        if self._countdown_flip_anim_1 is not None:
            self._countdown_flip_anim_1.stop()

        if self._countdown_flip_anim_2 is not None:
            self._countdown_flip_anim_2.stop()

        self._countdown_flip_anim_1 = QPropertyAnimation(overlay, b"scaleX", self)
        self._countdown_flip_anim_1.setDuration(170)
        self._countdown_flip_anim_1.setStartValue(1.0)
        self._countdown_flip_anim_1.setEndValue(0.08)
        self._countdown_flip_anim_1.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._countdown_flip_anim_2 = QPropertyAnimation(overlay, b"scaleX", self)
        self._countdown_flip_anim_2.setDuration(210)
        self._countdown_flip_anim_2.setStartValue(0.08)
        self._countdown_flip_anim_2.setEndValue(1.0)
        self._countdown_flip_anim_2.setEasingCurve(QEasingCurve.Type.OutCubic)

        first_anim = self._countdown_flip_anim_1
        second_anim = self._countdown_flip_anim_2

        def switch_face():
            stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            overlay.set_pixmap(target_pixmap)
            second_anim.start()

        def finish_flip():
            overlay.hide()
            stack.show()
            overlay.set_scale_x(1.0)

            self._circle_flip_animating = False

            # If user clicked again during animation, apply latest requested state now.
            pending = self._pending_face_detected_state
            self._pending_face_detected_state = None

            if pending is not None and pending != self.face_detected:
                self.set_face_detected(pending)

        first_anim.finished.connect(switch_face)
        second_anim.finished.connect(finish_flip)
        first_anim.start()

    def users_card(self):
        card = GlassCard()
        layout = QVBoxLayout(card)
        px, py = self.card_padding()
        layout.setContentsMargins(px, py, px, py)
        layout.setSpacing(20 if not self.compact_mode else 12)

        header = QHBoxLayout()
        title = QLabel("AUTHORIZED USERS")
        title.setObjectName("UsersTitle")
        status = QLabel("STATUS     3 active")
        status.setObjectName("UsersStatus")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(status)
        layout.addLayout(header)

        users_divider = QFrame()
        users_divider.setObjectName("UsersDivider")
        users_divider.setFixedHeight(1)
        layout.addWidget(users_divider)

        users_box = QVBoxLayout()
        users_box.setSpacing(18 if not self.compact_mode else 10)
        users_box.addWidget(self.user_row("4372447", "124 Photos", True))
        users_box.addWidget(self.user_row("8829103", "82 Photos", True))
        users_box.addWidget(self.user_row("5542190", "0 Photos", False))
        layout.addLayout(users_box)
        layout.addStretch()

        manage = QPushButton("MANAGE ACCESS")
        manage.setObjectName("ManageAccessButton")
        manage.setFixedHeight(42 if not self.compact_mode else 34)
        layout.addWidget(manage)
        return card

    def user_row(self, user_id, detail, active=True):
        row = QFrame()
        row.setObjectName("UserRow")
        row.setFixedHeight(44 if not self.compact_mode else 34)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        text = QVBoxLayout()
        name = QLabel(user_id)
        name.setObjectName("UserName")
        sub = QLabel(detail)
        sub.setObjectName("UserDetail")
        text.addWidget(name)
        text.addWidget(sub)

        right = QLabel("●") if active else QLabel("Idle")
        right.setObjectName("GreenDot" if active else "IdleText")

        layout.addLayout(text)
        layout.addStretch()
        layout.addWidget(right)
        return row

    # --------------------------------------------------------
    # Face recognition page parts
    # --------------------------------------------------------
    def camera_feed_card(self):
        card = QFrame()
        card.setObjectName("CameraFeedCard")
        card.setMinimumHeight(360 if not self.compact_mode else 300)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        top = QHBoxLayout()
        live = QLabel("● FEED_04_LIVE")
        live.setObjectName("LiveBadge")
        quality = QLabel("CAMERA PREVIEW")
        quality.setObjectName("QualityBadge")
        top.addWidget(live)
        top.addStretch()
        top.addWidget(quality)

        self.camera_preview_label = QLabel("Camera preview loading...")
        self.camera_preview_label.setObjectName("CameraPreviewLabel")
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setMinimumHeight(240 if not self.compact_mode else 200)
        self.camera_preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        bottom = QHBoxLayout()
        self.camera_left_meta = QLabel("LATENCY: --MS\nFPS: --")
        self.camera_left_meta.setObjectName("CameraMeta")

        self.camera_right_meta = QLabel("SOURCE: Local camera / API feed\nSTATUS: Waiting")
        self.camera_right_meta.setObjectName("CameraMeta")
        self.camera_right_meta.setAlignment(Qt.AlignmentFlag.AlignRight)

        bottom.addWidget(self.camera_left_meta)
        bottom.addStretch()
        bottom.addWidget(self.camera_right_meta)

        layout.addLayout(top)
        layout.addWidget(self.camera_preview_label, 1)
        layout.addLayout(bottom)

        QTimer.singleShot(300, self.start_camera_preview)
        return card

    def start_camera_preview(self):
        """Start simple local camera preview. Falls back to placeholder if unavailable."""
        if not hasattr(self, "camera_preview_label"):
            return

        if cv2 is None:
            self.camera_preview_label.setText(
                "OpenCV is not installed.\n"
                "Install opencv-python or connect Pi /video-feed later."
            )
            if hasattr(self, "camera_right_meta"):
                self.camera_right_meta.setText("SOURCE: Not connected\nSTATUS: OpenCV missing")
            return

        if hasattr(self, "camera_capture") and self.camera_capture is not None:
            return

        self.camera_capture = cv2.VideoCapture(0)

        if not self.camera_capture.isOpened():
            self.camera_preview_label.setText(
                "No local camera detected.\n"
                "Later connect this area to Raspberry Pi /video-feed."
            )
            if hasattr(self, "camera_right_meta"):
                self.camera_right_meta.setText("SOURCE: Camera 0\nSTATUS: Not available")
            self.camera_capture.release()
            self.camera_capture = None
            return

        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.update_camera_frame)
        self.camera_timer.start(33)

        if hasattr(self, "camera_right_meta"):
            self.camera_right_meta.setText("SOURCE: Camera 0\nSTATUS: Active")

    def update_camera_frame(self):
        if cv2 is None:
            return

        if not hasattr(self, "camera_capture") or self.camera_capture is None:
            return

        ok, frame = self.camera_capture.read()
        if not ok or frame is None:
            return

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        bytes_per_line = ch * w

        qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.camera_preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.camera_preview_label.setPixmap(pixmap)

        if hasattr(self, "camera_left_meta"):
            self.camera_left_meta.setText("LATENCY: LIVE\nFPS: 30")

    def closeEvent(self, event):
        if hasattr(self, "camera_timer") and self.camera_timer is not None:
            self.camera_timer.stop()

        if hasattr(self, "camera_capture") and self.camera_capture is not None:
            self.camera_capture.release()
            self.camera_capture = None

        super().closeEvent(event)

    def face_controls_card(self):
        card = GlassCard()
        card.setMinimumHeight(205 if not self.compact_mode else 185)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            24 if not self.compact_mode else 18,
            20 if not self.compact_mode else 15,
            24 if not self.compact_mode else 18,
            18 if not self.compact_mode else 14,
        )
        layout.setSpacing(10)

        title = QLabel("PRIMARY CONTROLS")
        title.setObjectName("FaceSectionTitle")
        layout.addWidget(title)

        self.ntid_input = QLineEdit()
        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter NTID / user ID for capture")
        self.ntid_input.setClearButtonEnabled(True)
        self.ntid_input.setFixedHeight(32 if not self.compact_mode else 30)
        layout.addWidget(self.ntid_input)

        # Compact action area.
        # Row 1: Capture + Train
        # Row 2: Recognize full width
        # Row 3: Stop + Delete
        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(10)
        button_grid.setVerticalSpacing(8)

        capture = QPushButton("＋  CAPTURE")
        capture.setObjectName("OutlineActionButton")

        train = QPushButton("◎  TRAIN")
        train.setObjectName("OutlineActionButton")

        recognize = QPushButton("⌁  RECOGNIZE")
        recognize.setObjectName("GreenActionButton")

        stop = QPushButton("STOP")
        stop.setObjectName("StopButton")

        delete = QPushButton("DELETE")
        delete.setObjectName("DeleteButton")

        for btn in (capture, train, recognize, stop, delete):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        small_h = 31 if not self.compact_mode else 29
        main_h = 34 if not self.compact_mode else 31

        capture.setFixedHeight(main_h)
        train.setFixedHeight(main_h)
        recognize.setFixedHeight(main_h)
        stop.setFixedHeight(small_h)
        delete.setFixedHeight(small_h)

        capture.clicked.connect(self._face_api_capture_user)
        train.clicked.connect(self._face_api_train)
        recognize.clicked.connect(self._face_api_get_result)
        stop.clicked.connect(self._face_api_stop_recognition)
        delete.clicked.connect(self._face_api_delete_user)

        button_grid.addWidget(capture, 0, 0)
        button_grid.addWidget(train, 0, 1)
        button_grid.addWidget(recognize, 1, 0, 1, 2)
        button_grid.addWidget(stop, 2, 0)
        button_grid.addWidget(delete, 2, 1)

        layout.addLayout(button_grid)
        layout.addStretch(1)
        return card

    def system_log_card(self):
        card = GlassCard()
        card.setObjectName("SystemLogCard")
        card.setMinimumHeight(190 if not self.compact_mode else 170)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28 if not self.compact_mode else 20, 24 if not self.compact_mode else 18, 28 if not self.compact_mode else 20, 24 if not self.compact_mode else 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("SYSTEM LOG")
        title.setObjectName("FaceSectionTitle")
        dot = QLabel("●")
        dot.setObjectName("GreenDot")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(dot)
        layout.addLayout(top)

        logs = QLabel(
            "<span style='color:#1F7A45'>09:10:02</span> &gt; LOADED SAVE_PATH: //NODE_01/RECOGNITION<br>"
            "<span style='color:#1F7A45'>09:10:05</span> &gt; SERVER_STATUS: ONLINE<br>"
            "<span style='color:#1F7A45'>09:10:12</span> &gt; API_STARTED: 0.0.0.0:5000<br>"
            "<span style='color:#1F7A45'>09:10:45</span> &gt; SUBJECT_DETECTION: IN_PROGRESS...<br>"
            "&gt; WAITING FOR INPUT_BUFFER"
        )
        self.system_log_label = logs
        logs.setObjectName("LogText")
        logs.setWordWrap(True)
        layout.addWidget(logs, 1)
        return card

    def face_users_card(self):
        card = GlassCard()
        card.setMinimumHeight(0)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28 if not self.compact_mode else 20, 24 if not self.compact_mode else 18, 28 if not self.compact_mode else 20, 24 if not self.compact_mode else 18)
        layout.setSpacing(16)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AUTHORIZED USERS")
        title.setObjectName("UsersTitle")
        sub = QLabel("5 ACTIVE RECORDS")
        sub.setObjectName("UsersStatus")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        filter_btn = QLabel("☰")
        filter_btn.setObjectName("UsersStatus")
        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(filter_btn)
        layout.addLayout(top)

        self.face_users_layout = layout
        self.face_users_subtitle = sub
        QTimer.singleShot(300, self._face_api_refresh_users)

        layout.addStretch()
        return card

    def face_user_row(self, user_id, frames, status, active=True):
        row = QFrame()
        row.setObjectName("FaceUserRow")
        row.setMinimumHeight(58 if not self.compact_mode else 48)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        text = QVBoxLayout()
        name = QLabel(user_id)
        name.setObjectName("UserName")
        detail = QLabel(frames)
        detail.setObjectName("UserDetail")
        text.addWidget(name)
        text.addWidget(detail)

        badge = QLabel(status)
        badge.setObjectName("TrainedBadge" if active else "PendingBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dot = QLabel("●" if active else "IDLE")
        dot.setObjectName("GreenDot" if active else "IdleText")

        layout.addLayout(text, 1)
        layout.addWidget(badge)
        layout.addWidget(dot)
        return row

    def capture_requested(self):
        """Temporary capture validation before connecting to the real API."""
        ntid = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""

        if not ntid:
            print("[FACE ACTION] Please enter NTID before capture")
            if hasattr(self, "ntid_input"):
                self.ntid_input.setFocus()
                self.ntid_input.setPlaceholderText("NTID is required before capture")
            return

        self.face_action_feedback(f"Capture requested for NTID: {ntid}")

    # --------------------------------------------------------
    # Phase 1 migrated LockApp logic
    # --------------------------------------------------------
    def qt_after(self, ms: int, callback):
        """Run callback on Qt main thread.

        If called from a worker thread, QTimer.singleShot alone may not execute
        because the worker thread has no Qt event loop. The bridge signal fixes that.
        """
        if ms <= 0:
            self.ui_bridge.run_callback.emit(callback)
        else:
            QTimer.singleShot(ms, lambda: self.ui_bridge.run_callback.emit(callback))

    def append_system_log(self, message: str):
        now = datetime.now().strftime("%H:%M:%S")
        line = f"<span style='color:#1F7A45'>{now}</span> &gt; {html.escape(str(message))}"
        if not hasattr(self, "_system_log_lines"):
            self._system_log_lines = []
        self._system_log_lines.append(line)
        self._system_log_lines = self._system_log_lines[-8:]
        if hasattr(self, "system_log_label"):
            self.system_log_label.setText("<br>".join(self._system_log_lines))
        print("[SAS]", message)

    def set_status_message(self, message: str):
        self.append_system_log(message)
        if hasattr(self, "pi_status_label"):
            self.pi_status_label.setText("●  " + str(message))

    def _ensure_admin_file(self):
        self.admin_service.ensure_admin_file()

    def _load_admins(self):
        return self.admin_service.load_admins()

    def _save_admin(self, ntid):
        self.admin_service.save_admin(ntid)

    def _check_admin_login(self, ntid):
        return self.admin_service.check_admin_login(ntid)

    def refresh_admin_list_ui(self):
        if not hasattr(self, "admin_list_layout"):
            return
        while self.admin_list_layout.count():
            item = self.admin_list_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        admins = self._load_admins()
        if not admins:
            self.admin_list_layout.addWidget(self.admin_row("No admin yet", "first valid login becomes admin", removable=False))
            return
        for index, admin in enumerate(admins):
            tag = "(you)" if self.current_user and admin == self.current_user.lower() else ""
            self.admin_list_layout.addWidget(self.admin_row(admin.upper(), tag, removable=(index != 0)))

    def add_admin_from_ui(self):
        ntid = self.admin_add_input.text().strip().lower() if hasattr(self, "admin_add_input") else ""
        if not ntid:
            self.append_system_log("Please enter NTID to add admin")
            return
        def worker():
            valid = self._validate_ntid_in_ad(ntid)
            def done():
                if not valid:
                    self.append_system_log(f"Invalid NTID or AD unreachable: {ntid}")
                    return
                self._save_admin(ntid)
                self.admin_add_input.clear()
                self.refresh_admin_list_ui()
                self.append_system_log(f"Admin added: {ntid.upper()}")
            self.qt_after(0, done)
        Thread(target=worker, daemon=True).start()

    def _validate_ntid_in_ad(self, ntid: str) -> bool:
        return self.ad_service.validate_ntid_in_ad(ntid)

    def _parse_ad_response(self, response: str) -> bool:
        return self.ad_service.parse_ad_response(response)

    def _read_credentials(self):
        return self.credential_service.read_credentials()

    def _encrypt_password(self, password: str):
        return self.ad_service.encrypt_password(password)

    def _validate_ntid_password_in_ad(self, ntid: str, password: str) -> bool:
        return self.ad_service.validate_ntid_password_in_ad(ntid, password)

    def _save_credentials(self, ntid, password, server, timeout, disable_keyboard=False, disable_mouse=False, disable_usb=False, enable_hotkey=True):
        self.credential_service.save_credentials(
            ntid,
            password,
            server,
            timeout,
            disable_keyboard=disable_keyboard,
            disable_mouse=disable_mouse,
            disable_usb=disable_usb,
            enable_hotkey=enable_hotkey,
        )

    def browse_server_path(self):
        """Browse and select the server folder used for SAS_LOG and recognition_result.json."""
        start_dir = self.settings_server_path_input.text().strip() if hasattr(self, "settings_server_path_input") else self.server_path
        if not start_dir or not os.path.exists(start_dir):
            start_dir = self.server_path if os.path.exists(self.server_path) else os.path.expanduser("~")

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Server Path",
            start_dir,
        )

        if folder:
            self.settings_server_path_input.setText(folder)
            self.append_system_log(f"Server path selected: {folder}")

    def show_settings_message(
        self,
        title: str,
        message: str,
        success: bool = True,
        issues=None,
        server_path: str = "",
        timeout_seconds: int = 300,
    ):
        """Show custom settings result dialog instead of native QMessageBox."""
        dialog = SettingsConnectionDialog(
            self,
            success=success,
            title=title,
            subtitle=message,
            server_path=server_path or self.server_path,
            timeout_seconds=timeout_seconds,
            issues=issues or [],
            compact_mode=self.compact_mode,
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        dialog.exec()


    def write_sas_log(self, message: str):
        """Write SAS runtime events to server_path/SAS_LOG/YYYY-MM-DD.txt."""
        try:
            log_root = os.path.join(self.server_path, "SAS_LOG")
            os.makedirs(log_root, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file = os.path.join(log_root, f"{date_str}.txt")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            self.append_system_log(f"SAS_LOG write failed: {e}")

    def apply_timeout_to_countdown(self, reset: bool = False):
        self.total_seconds = max(1, int(self.lock_timeout_seconds))
        if reset:
            self.time_left = self.total_seconds
        if hasattr(self, "ring"):
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)
        if hasattr(self, "countdown_label"):
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")

    def apply_security_options_runtime(self):
        """Apply saved security option flags.

        The low-level keyboard/mouse/USB blocking from lockapp.py should stay isolated
        in runtime_lock_service.py. This method records the current configuration and
        is the connection point for those controls.
        """
        self.append_system_log(
            "Security options applied: "
            f"keyboard={self.disable_keyboard_when_locked}, "
            f"mouse={self.disable_mouse_when_locked}, "
            f"usb={self.disable_usb_when_locked}, "
            f"hotkey={self.enable_hotkey}"
        )

    def load_settings_from_credentials(self):
        creds = self._read_credentials()
        self.server_path = creds.get("server", self.server_path)
        try:
            self.lock_timeout_seconds = int(creds.get("timeout", self.lock_timeout_seconds))
        except Exception:
            self.lock_timeout_seconds = DEFAULT_LOCK_TIMEOUT_SECONDS
        self.disable_keyboard_when_locked = creds.get("disable_keyboard", "false").lower() == "true"
        self.disable_mouse_when_locked = creds.get("disable_mouse", "false").lower() == "true"
        self.disable_usb_when_locked = creds.get("disable_usb", "false").lower() == "true"
        self.enable_hotkey = creds.get("enable_hotkey", "true").lower() == "true"
        if hasattr(self, "settings_ntid_input"):
            self.settings_ntid_input.setText(creds.get("ntid", ""))
        if hasattr(self, "settings_password_input"):
            self.settings_password_input.setText(creds.get("password", ""))
        if hasattr(self, "settings_server_path_input"):
            self.settings_server_path_input.setText(self.server_path)
        if hasattr(self, "security_option_buttons"):
            self.security_option_buttons["disable_keyboard"].setChecked(self.disable_keyboard_when_locked)
            self.security_option_buttons["disable_mouse"].setChecked(self.disable_mouse_when_locked)
            self.security_option_buttons["disable_usb"].setChecked(self.disable_usb_when_locked)
            self.security_option_buttons["enable_hotkey"].setChecked(self.enable_hotkey)
        if hasattr(self, "timeout_inputs"):
            total = int(self.lock_timeout_seconds)
            self.timeout_inputs["hours"].setText(str(total // 3600))
            self.timeout_inputs["minutes"].setText(str((total % 3600) // 60))
            self.timeout_inputs["seconds"].setText(str(total % 60))
        self.apply_timeout_to_countdown(reset=True)
        self.apply_security_options_runtime()
        self.update_footer_info()

    def validate_server_path_for_settings(self, server: str):
        """Validate server path used for SAS_LOG and recognition_result.json.

        The recognition_result.json file may not exist yet, so the path itself
        only needs to exist and be writable/readable.
        """
        issues = []

        if not server:
            issues.append(("SERVER PATH MISSING", "Please select or enter the shared server path."))
            return False, issues

        if not os.path.isdir(server):
            issues.append(("SERVER PATH UNREACHABLE", "The selected server path does not exist or cannot be reached."))
            return False, issues

        try:
            log_dir = os.path.join(server, "SAS_LOG")
            os.makedirs(log_dir, exist_ok=True)
            test_file = os.path.join(log_dir, ".sas_write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(test_file)
            except Exception:
                pass
        except Exception as e:
            issues.append(("SERVER PATH NOT WRITABLE", f"Unable to create SAS_LOG under this path: {e}"))
            return False, issues

        return True, issues

    def save_settings_from_ui(self):
        ntid = self.settings_ntid_input.text().strip() if hasattr(self, "settings_ntid_input") else ""
        password = self.settings_password_input.text().strip() if hasattr(self, "settings_password_input") else ""
        server = self.settings_server_path_input.text().strip() if hasattr(self, "settings_server_path_input") else self.server_path

        if not ntid:
            self.show_settings_message(
                "Connection Failed",
                "Authentication or path error detected",
                success=False,
                issues=[("INVALID NTID", "Please enter a valid NTID before saving settings.")],
                server_path=server,
            )
            return

        if not password:
            self.show_settings_message(
                "Connection Failed",
                "Authentication or path error detected",
                success=False,
                issues=[("PASSWORD REQUIRED", "Please enter the password before saving settings.")],
                server_path=server,
            )
            return

        try:
            h = int(self.timeout_inputs["hours"].text() or 0)
            m = int(self.timeout_inputs["minutes"].text() or 0)
            s = int(self.timeout_inputs["seconds"].text() or 0)
            timeout = max(1, h * 3600 + m * 60 + s)
        except Exception:
            timeout = DEFAULT_LOCK_TIMEOUT_SECONDS

        disable_keyboard = self.security_option_buttons["disable_keyboard"].isChecked()
        disable_mouse = self.security_option_buttons["disable_mouse"].isChecked()
        disable_usb = self.security_option_buttons["disable_usb"].isChecked()
        enable_hotkey = self.security_option_buttons["enable_hotkey"].isChecked()

        self.append_system_log("Validating settings NTID/password/server path before saving...")

        def worker():
            issues = []

            # 1) NTID exists check. This lets the failure popup tell user NTID is wrong.
            ntid_ok = self._validate_ntid_in_ad(ntid)
            if not ntid_ok:
                issues.append(("INVALID NTID", "Subject token verification failed. The NTID does not exist or AD is unreachable."))

            # 2) Password validation only if NTID exists.
            password_ok = False
            if ntid_ok:
                password_ok = self._validate_ntid_password_in_ad(ntid, password)
                if not password_ok:
                    issues.append(("CREDENTIAL MISMATCH", "Password validation failed. Please check the password and try again."))

            # 3) Server path validation.
            server_ok, server_issues = self.validate_server_path_for_settings(server)
            if not server_ok:
                issues.extend(server_issues)

            def done():
                if issues:
                    for issue_title, issue_desc in issues:
                        self.append_system_log(f"Settings validation failed: {issue_title} - {issue_desc}")

                    self.show_settings_message(
                        "Connection Failed",
                        "Authentication or path error detected",
                        success=False,
                        issues=issues,
                        server_path=server,
                        timeout_seconds=timeout,
                    )
                    return

                self._save_credentials(
                    ntid,
                    password,
                    server,
                    timeout,
                    disable_keyboard,
                    disable_mouse,
                    disable_usb,
                    enable_hotkey,
                )

                self.server_path = server
                self.lock_timeout_seconds = timeout
                self.disable_keyboard_when_locked = disable_keyboard
                self.disable_mouse_when_locked = disable_mouse
                self.disable_usb_when_locked = disable_usb
                self.enable_hotkey = enable_hotkey

                self.apply_timeout_to_countdown(reset=True)
                self.apply_security_options_runtime()
                self.update_footer_info()
                self.write_sas_log(f"SETTINGS SAVED | NTID={ntid.upper()} | TIMEOUT={timeout}s | SERVER={server}")
                self.append_system_log("Settings saved and connection established")

                self.show_settings_message(
                    "Connection Established",
                    "Server linked successfully",
                    success=True,
                    server_path=server,
                    timeout_seconds=timeout,
                )

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()


    def update_footer_info(self):
        if hasattr(self, "footer_server_label"):
            self.footer_server_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 3}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>SERVER PATH</span><br><span style='font-size:{max(10, int(14 * self.ui_scale))}px; line-height:{max(10, int(14 * self.ui_scale)) + 5}px; color:{Theme.TEXT}; font-weight:700;'>{html.escape(self.server_path)}</span>")
        if hasattr(self, "footer_timeout_label"):
            self.footer_timeout_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 3}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>LOCK TIME INTERVAL</span><br><span style='font-size:{max(10, int(14 * self.ui_scale))}px; line-height:{max(10, int(14 * self.ui_scale)) + 5}px; color:{Theme.TEXT}; font-weight:700;'>{self.lock_timeout_seconds}s</span>")

    def show_login_success_popup(self, ntid: str, role: str):
        """Show premium success modal after NTID/password validation succeeds."""
        popup = LoginSuccessDialog(self, ntid=ntid, role=role, compact_mode=self.compact_mode)

        geo = self.geometry()
        x = geo.x() + (geo.width() - popup.width()) // 2
        y = geo.y() + (geo.height() - popup.height()) // 2
        popup.move(x, y)

        popup.exec()

    def login_debug(self, message: str):
        """Debug helper for login validation flow."""
        line = f"[LOGIN DEBUG] {message}"
        print(line)
        if hasattr(self, "append_system_log"):
            self.append_system_log(line)

    def show_login_failed_popup(self, reason: str, debug_text: str = ""):
        """Show premium failure modal for invalid login or AD/SOAP errors."""
        popup = LoginFailedDialog(
            self,
            reason=reason,
            debug_text=debug_text,
            compact_mode=self.compact_mode
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - popup.width()) // 2
        y = geo.y() + (geo.height() - popup.height()) // 2
        popup.move(x, y)

        popup.exec()

    def _validate_ntid_password_in_ad_with_debug(self, ntid: str, password: str):
        return self.ad_service.validate_ntid_password_with_debug(ntid, password)

    def _handle_login_from_popup(self, ntid: str, password: str, dialog):
        dialog.set_validation_state("Starting login validation...")
        self.login_debug("Login button clicked.")
        self.login_debug(f"Received NTID from login popup: {ntid}")

        def set_dialog_status(message: str):
            if dialog is not None:
                dialog.set_validation_message(message)

        def worker():
            self.qt_after(0, lambda: set_dialog_status("Checking NTID in Active Directory..."))
            valid, reason, debug_text = self._validate_ntid_password_in_ad_with_debug(ntid, password)

            def done():
                if not valid:
                    self.login_debug(f"Login failed: {reason}")
                    user_reason = "Invalid NTID or password. Please check your credentials and try again."
                    dialog.show_failed_state(user_reason, debug_text)
                    return

                is_admin, role_msg = self._check_admin_login(ntid)

                self.current_user = ntid.lower()
                self.is_admin = is_admin
                self.current_user_role = "Admin" if is_admin else "User"
                self.is_logged_in = True

                self.update_account_ui()
                self.refresh_admin_list_ui()

                success_debug = debug_text + f"\nAdmin role check: {role_msg}\nFinal login role: {self.current_user_role}"
                self.login_debug(f"Admin check result: {role_msg}")
                self.append_system_log(f"Login successful: {ntid.upper()} ({self.current_user_role})")

                self.login_debug("Validation success. Switching login popup to success state.")
                dialog.show_success_state(ntid, self.current_user_role, success_debug)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()

    def update_account_ui(self):
        if hasattr(self, "login_btn"):
            if self.current_user:
                self.login_btn.setText(f"{self.current_user.upper()} ▾")
                self.login_btn.setToolTip(f"Logged in as {self.current_user.upper()} ({self.current_user_role})")
                self.login_btn.setObjectName("LoginButtonLoggedIn")
                self.login_btn.setFixedWidth(122 if not self.compact_mode else 104)
            else:
                self.login_btn.setText("Login")
                self.login_btn.setToolTip("")
                self.login_btn.setObjectName("LoginButton")
                self.login_btn.setFixedWidth(96 if not self.compact_mode else 82)

            self.login_btn.style().unpolish(self.login_btn)
            self.login_btn.style().polish(self.login_btn)
            self.login_btn.update()

    def _face_api_base_url(self):
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        port = self.pi_port_input.text().strip() if hasattr(self, "pi_port_input") else self.pi_api_port

        if not port:
            port = self.pi_api_port

        if host.startswith("http"):
            self.pi_api_base = host.rstrip("/")
            self.face_api_service.configure(host, port)
            return self.pi_api_base

        if not host:
            host = self.pi_api_host

        self.pi_api_host = host
        self.pi_api_port = port
        self.pi_api_base = f"http://{host}:{port}"
        self.face_api_service.configure(host, port)
        return self.pi_api_base

    def _face_api_request(self, method, endpoint, payload=None, timeout=10):
        self._face_api_base_url()
        return self.face_api_service.request(method, endpoint, payload=payload, timeout=timeout)

    def _face_api_test_connection(self):
        def worker():
            try:
                data = self._face_api_request("GET", "/status")
                msg = f"Connected: {data.get('users', 0)} users | Recognition: {data.get('recognition_running')}"
                self.qt_after(0, lambda: self.set_status_message(msg))
            except Exception as e:
                self.qt_after(0, lambda: self.set_status_message(f"Connection failed: {e}"))
        Thread(target=worker, daemon=True).start()

    def _face_api_stop_recognition(self):
        def worker():
            try:
                data = self._face_api_request("POST", "/stop-recognition")
                self.qt_after(0, lambda: self.face_action_feedback(json.dumps(data, indent=2)))
                self.qt_after(0, self._face_api_test_connection)
            except Exception as e:
                self.qt_after(0, lambda: self.face_action_feedback(f"Stop failed: {e}"))
        Thread(target=worker, daemon=True).start()

    def _face_api_get_result(self):
        def worker():
            try:
                data = self._face_api_request("GET", "/recognition-result")
                self.qt_after(0, lambda: self.face_action_feedback(json.dumps(data, indent=2)))
            except Exception as e:
                self.qt_after(0, lambda: self.face_action_feedback(f"Read result failed: {e}"))
        Thread(target=worker, daemon=True).start()

    def _face_api_train(self):
        def worker():
            try:
                data = self._face_api_request("POST", "/train")
                self.qt_after(0, lambda: self.face_action_feedback(json.dumps(data, indent=2)))
                self.qt_after(1500, self._face_api_refresh_users)
            except Exception as e:
                self.qt_after(0, lambda: self.face_action_feedback(f"Train failed: {e}"))
        Thread(target=worker, daemon=True).start()

    def _face_api_capture_user(self):
        user_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""
        if not user_id:
            self.append_system_log("Please enter NTID before capture")
            if hasattr(self, "ntid_input"):
                self.ntid_input.setFocus()
            return
        def worker():
            try:
                data = self._face_api_request("POST", "/capture-user", {"user_id": user_id, "mode": "add"}, timeout=60)
                self.qt_after(0, lambda: self.face_action_feedback(json.dumps(data, indent=2)))
                self.qt_after(1500, self._face_api_refresh_users)
            except Exception as e:
                self.qt_after(0, lambda: self.face_action_feedback(f"Capture failed: {e}"))
        Thread(target=worker, daemon=True).start()

    def _face_api_delete_user(self):
        user_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""
        if not user_id:
            self.append_system_log("Please enter NTID before delete")
            return
        def worker():
            try:
                data = self._face_api_request("POST", "/delete-user", {"user_id": user_id})
                self.qt_after(0, lambda: self.face_action_feedback(json.dumps(data, indent=2)))
                self.qt_after(0, self._face_api_refresh_users)
            except Exception as e:
                self.qt_after(0, lambda: self.face_action_feedback(f"Delete failed: {e}"))
        Thread(target=worker, daemon=True).start()

    def _face_api_refresh_users(self):
        if not hasattr(self, "face_users_layout"):
            return
        def worker():
            try:
                data = self._face_api_request("GET", "/users")
                users = data.get("users", [])
                self.qt_after(0, lambda: self.render_face_users(users))
            except Exception as e:
                self.qt_after(0, lambda: self.append_system_log(f"Failed to load face users: {e}"))
        Thread(target=worker, daemon=True).start()

    def render_face_users(self, users):
        if not hasattr(self, "face_users_layout"):
            return
        while self.face_users_layout.count() > 1:
            item = self.face_users_layout.takeAt(1)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if hasattr(self, "face_users_subtitle"):
            self.face_users_subtitle.setText(f"{len(users)} ACTIVE RECORDS")
        if not users:
            self.face_users_layout.addWidget(self.face_user_row("NONE", "No capture frames", "PENDING", False))
            self.face_users_layout.addStretch()
            return
        for user in users:
            uid = str(user.get("id", ""))
            photos = user.get("photos", 0)
            trained = bool(user.get("trained", False))
            self.face_users_layout.addWidget(self.face_user_row(uid.upper(), f"{photos} Capture frames", "TRAINED" if trained else "PENDING", trained))
        self.face_users_layout.addStretch()

    def _read_recognition_result(self):
        return self.recognition_state_service.read_result(self.server_path)

    def _grant_access(self, name=""):
        self.runtime_lock_service.grant_access(self, name)
        self.write_sas_log("ACCESS GRANTED" + (f" | {name}" if name else ""))

    def _do_logout(self):
        self.runtime_lock_service.lock_system(self)
        self.write_sas_log("LOCKED | REASON=MANUAL_OR_LOGOUT")

    def face_action_feedback(self, message: str):
        self.append_system_log(message)


    # --------------------------------------------------------
    # Fixed footer
    # --------------------------------------------------------
    def build_footer_area(self):
        # Fixed bottom footer component.
        # The wrapper is invisible; only the small server-path component is shown.
        area = QWidget()
        area.setObjectName("FooterArea")
        area.setFixedHeight(78 if not self.compact_mode else 66)

        area_layout = QHBoxLayout(area)
        area_layout.setContentsMargins(
            42 if not self.compact_mode else 24,
            8,
            42 if not self.compact_mode else 24,
            12,
        )

        footer = self.build_footer_strip()
        footer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        area_layout.addStretch(1)
        area_layout.addWidget(footer, 0, Qt.AlignmentFlag.AlignCenter)
        area_layout.addStretch(1)
        return area

    def build_footer_strip(self):
        footer = QFrame()
        footer.setObjectName("FooterStrip")
        footer.setFixedHeight(58 if not self.compact_mode else 52)
        footer.setMinimumWidth(820 if not self.compact_mode else 700)
        footer.setMaximumWidth(980 if not self.compact_mode else 820)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(
            28 if not self.compact_mode else 20,
            9 if not self.compact_mode else 7,
            28 if not self.compact_mode else 20,
            9 if not self.compact_mode else 7,
        )
        layout.setSpacing(28 if not self.compact_mode else 18)

        self.footer_server_label = InfoLabel("SERVER PATH", self.server_path, self.ui_scale)
        self.footer_state_label = InfoLabel("STATE FILE", RECOGNITION_RESULT_FILE, self.ui_scale)
        self.footer_timeout_label = InfoLabel("LOCK TIME INTERVAL", f"{self.lock_timeout_seconds}s", self.ui_scale)
        layout.addWidget(self.footer_server_label)
        layout.addWidget(self.vertical_line())
        layout.addWidget(self.footer_state_label)
        layout.addWidget(self.vertical_line())
        layout.addWidget(self.footer_timeout_label)
        layout.addStretch()

        copyright_label = QLabel("© 2026 SECURE ACCESS SYSTEM")
        copyright_label.setObjectName("Copyright")
        layout.addWidget(copyright_label)
        return footer

    def vertical_line(self):
        line = QFrame()
        line.setObjectName("VerticalLine")
        line.setFixedSize(1, 34 if not self.compact_mode else 26)
        return line

    # --------------------------------------------------------
    # Responsive layout scaling
    # --------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_dashboard_card_sizes()
        self.update_face_card_sizes()

        if hasattr(self, "account_menu") and self.account_menu.isVisible() and self.account_menu.height() > 0:
            self.position_account_menu()



    def update_dashboard_card_sizes(self):
        """Scale dashboard cards when the window becomes fullscreen or small."""
        if not hasattr(self, "dashboard_cards"):
            return

        w = max(1, self.width())
        h = max(1, self.height())

        if w >= 1700:
            card_h = int(h * 0.44)
        elif w >= 1300:
            card_h = int(h * 0.40)
        else:
            card_h = 300 if self.compact_mode else 360

        card_h = max(300, min(card_h, 540))

        for card in self.dashboard_cards:
            card.setMinimumHeight(card_h)
            card.setMaximumHeight(card_h)

        # Time section also scales slightly in fullscreen.
        if hasattr(self, "time_label"):
            if w >= 1700:
                self.time_label.setStyleSheet("font-size: 104px;")
            elif w >= 1300:
                self.time_label.setStyleSheet("font-size: 92px;")
            else:
                self.time_label.setStyleSheet("")

    def update_face_card_sizes(self):
        """Scale Face Recognition page composition for fullscreen and laptop sizes."""
        if not hasattr(self, "face_cards"):
            return

        w = max(1, self.width())
        h = max(1, self.height())

        camera, controls, logs, users = self.face_cards

        if w >= 1700:
            camera_h = int(h * 0.46)
            lower_h = int(h * 0.26)
        elif w >= 1300:
            camera_h = int(h * 0.40)
            lower_h = int(h * 0.23)
        else:
            camera_h = 300 if self.compact_mode else 360
            lower_h = 185 if self.compact_mode else 205

        camera_h = max(300, min(camera_h, 560))
        lower_h = max(180, min(lower_h, 320))

        camera.setMinimumHeight(camera_h)
        controls.setMinimumHeight(lower_h)
        logs.setMinimumHeight(lower_h)

        # Right user panel spans both rows, so let it grow with the page height.
        users.setMinimumHeight(camera_h + lower_h + (20 if not self.compact_mode else 12))

    # --------------------------------------------------------
    # Timers
    # --------------------------------------------------------
    def start_timers(self):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_time)
        self.clock_timer.start(1000)
        self.update_time()

        self.count_timer = QTimer(self)
        self.count_timer.timeout.connect(self.update_countdown)
        self.count_timer.start(1000)
        self.update_countdown(initial=True)

        self.recognition_timer = QTimer(self)
        self.recognition_timer.timeout.connect(self.poll_recognition_result)
        self.recognition_timer.start(1000)
        self.poll_recognition_result()

    def update_time(self):
        if self.current_top_tab != "Dashboard":
            return
        now = QDateTime.currentDateTime()
        self.time_label.setText(now.toString("HH:mm:ss"))
        self.date_label.setText(now.toString("dddd, MMMM dd, yyyy").upper() + " • GLOBAL NODE 01")

    def poll_recognition_result(self):
        """Poll server_path/recognition_result.json and update lock/face UI.

        Logic:
        - valid detected face: unlock green card, flip countdown circle to face detected, reset timer
        - no detected face while unlocked: flip back to countdown and let timer count down
        - countdown reaches 00:00: lock red card and keep timer at 00:00
        """
        result = self._read_recognition_result()
        state, ntid, detected_time, confidence = result

        if state == "valid":
            if self.is_locked:
                self._grant_access(f"{ntid.upper()} ({confidence}%)")
                self.write_sas_log(f"UNLOCKED | USER={ntid.upper()} | CONFIDENCE={confidence}%")

            self.is_locked = False
            self.is_logged_in = True
            self.apply_lock_state()

            self.time_left = max(1, int(self.lock_timeout_seconds))
            self.apply_timeout_to_countdown(reset=False)
            self.set_face_detected(True)
            return

        # No valid face now. If already unlocked, start/resume countdown.
        if not self.is_locked:
            self.set_face_detected(False)
        else:
            self.set_face_detected(False)
            self.time_left = 0
            self.apply_timeout_to_countdown(reset=False)

    def update_countdown(self, initial=False):
        if not hasattr(self, "countdown_label") or not hasattr(self, "ring"):
            return

        self.total_seconds = max(1, int(self.lock_timeout_seconds))
        self.ring.set_total_seconds(self.total_seconds)

        # Locked state stays at 00:00 until a valid face unlocks again.
        if self.is_locked:
            self.time_left = 0
            self.countdown_label.setText("00:00")
            self.ring.set_time_left(0)
            return

        # Face currently detected: keep unlocked and keep timer full.
        if self.face_detected:
            self.time_left = self.total_seconds
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
            self.ring.set_time_left(self.time_left)
            return

        # Unlocked but face no longer detected: count down to lock.
        if not initial:
            self.time_left = max(0, self.time_left - 1)

        mins = self.time_left // 60
        secs = self.time_left % 60
        self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
        self.ring.set_time_left(self.time_left)

        if self.time_left <= 0 and not self.is_locked:
            self.is_locked = True
            self.is_logged_in = False
            self.apply_lock_state()
            self.set_face_detected(False)
            self.write_sas_log("LOCKED | REASON=FACE_NOT_DETECTED_TIMEOUT")
            self.append_system_log("Auto locked: face not detected before countdown ended")


    # --------------------------------------------------------
    # Style
    # --------------------------------------------------------
    def apply_styles(self):
        time_font = 92 if not self.compact_mode else 64
        brand_font = 23 if not self.compact_mode else 18
        nav_font = 14 if not self.compact_mode else 12
        date_font = 14 if not self.compact_mode else 11
        card_radius = 28 if not self.compact_mode else 22
        title_font = 25 if not self.compact_mode else 18
        icon_font = 52 if not self.compact_mode else 36
        countdown_font = 28 if not self.compact_mode else 22

        self.setStyleSheet(f"""
            QMainWindow, #Root, #MainContent, #MainScroll, #Page, #PageStack {{
                background: {Theme.BG};
                color: {Theme.TEXT};
            }}

            QWidget {{
                background-color: transparent;
            }}

            QScrollArea {{
                border: none;
                background: transparent;
            }}

            QLabel, QPushButton {{
                font-family: Inter, Segoe UI, Arial;
            }}

            #Header {{
                background: {Theme.SURFACE};
                border-bottom: 1px solid {Theme.BORDER};
            }}

            #Brand {{
                color: {Theme.PRIMARY};
                font-size: {brand_font}px;
                font-weight: 800;
                letter-spacing: -0.02em;
            }}

            #TopNav, #TopNavActive {{
                background: transparent;
                border: none;
                color: {Theme.SECONDARY};
                font-size: {nav_font}px;
                font-weight: 600;
                padding: 16px 0px 12px 0px;
                border-bottom: 2px solid transparent;
            }}

            #TopNav:hover {{ color: {Theme.PRIMARY}; }}

            #TopNavActive {{
                color: {Theme.PRIMARY};
                border-bottom: 2px solid transparent;
            }}

            #TabIndicator {{
                background: {Theme.PRIMARY};
                border: none;
                border-radius: 1px;
            }}



            #AccountDropdown {{
                background: {Theme.PRIMARY};
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 18px;
            }}

            #AccountDropdownTitle {{
                color: rgba(255, 255, 255, 0.52);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
                padding-left: 8px;
                padding-top: 4px;
            }}

            #AccountDropdownUser {{
                color: white;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                padding-left: 8px;
                padding-bottom: 4px;
            }}

            #AccountDropdownButton {{
                background: rgba(255, 255, 255, 0.08);
                color: white;
                border: none;
                border-radius: 11px;
                min-height: 34px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
                text-align: left;
                padding-left: 12px;
            }}

            #AccountDropdownButton:hover {{
                background: rgba(255, 255, 255, 0.16);
            }}

            #AccountDropdownDangerButton {{
                background: rgba(255, 255, 255, 0.06);
                color: #FCA5A5;
                border: none;
                border-radius: 11px;
                min-height: 34px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                text-align: left;
                padding-left: 12px;
            }}

            #AccountDropdownDangerButton:hover {{
                background: rgba(220, 38, 38, 0.20);
                color: white;
            }}


            #LoginButtonLoggedIn {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: {17 if not self.compact_mode else 15}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
                padding: 0 18px;
            }}

            #LoginButtonLoggedIn:hover {{
                background: #2F3131;
            }}


            #LoginButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: {17 if not self.compact_mode else 15}px;
                font-size: {12 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #LoginButton:hover {{
                background: #1F1F1F;
            }}

            #LoginButton:pressed {{
                background: #333333;
                padding-top: 2px;
            }}

            #TerminalTime {{
                color: {Theme.PRIMARY};
                font-size: {time_font}px;
                font-weight: 900;
                letter-spacing: -4px;
            }}

            #TerminalDate {{
                color: {Theme.SECONDARY};
                font-size: {date_font}px;
                font-weight: 600;
                letter-spacing: {2 if not self.compact_mode else 1}px;
            }}

            #GlassCard, #GlassCardGreen {{
                background: rgba(255, 255, 255, 0.72);
                border-radius: {card_radius}px;
            }}

            #GlassCard {{
                border: 1px solid rgba(196, 199, 199, 0.60);
            }}

            #GlassCardGreen {{
                border: 2px solid rgba(22, 163, 74, 0.18);
            }}

            #UnlockedCard {{
                background: #3F9468;
                border: none;
                border-radius: {card_radius}px;
            }}

            #CardEyebrowWhite {{
                color: rgba(255, 255, 255, 0.65);
                font-size: {11 if not self.compact_mode else 9}px;
                font-weight: 700;
                letter-spacing: {1.6 if not self.compact_mode else 1.2}px;
            }}

            #UnlockedTitleWhite {{
                color: white;
                font-size: {title_font}px;
                font-weight: 900;
                letter-spacing: -0.03em;
            }}

            #WhiteLockIcon {{
                color: white;
                font-size: {icon_font}px;
                font-weight: 900;
            }}

            #FadeLockBgWhite {{
                color: rgba(255, 255, 255, 0.10);
                font-size: {120 if not self.compact_mode else 90}px;
            }}

            #EncryptedWhite {{
                color: white;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 800;
            }}

            #UnlockedPillGreen {{
                background: rgba(255, 255, 255, 0.22);
                color: white;
                border-radius: {17 if not self.compact_mode else 14}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #LockedPillRed {{
                background: rgba(255, 255, 255, 0.22);
                color: white;
                border-radius: {17 if not self.compact_mode else 14}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #Divider, #VerticalLine {{
                background: {Theme.BORDER};
                border: none;
            }}

            #DividerWhite {{
                background: rgba(255, 255, 255, 0.16);
                border: none;
            }}

            #ManualLockButtonWhite {{
                background: white;
                color: #3F9468;
                border: none;
                border-radius: 8px;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 900;
                letter-spacing: 1.3px;
            }}

            #ManualLockButtonWhite:hover {{
                background: rgba(255, 255, 255, 0.88);
            }}

            #ManualLockButtonWhite[lockState="unlocked"] {{
                color: #3F9468;
            }}

            #ManualLockButtonWhite[lockState="locked"] {{
                color: #B23A3A;
            }}

            #CountdownText {{
                color: {Theme.PRIMARY};
                font-size: {countdown_font}px;
                font-weight: 800;
            }}

            #RemainingText {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 600;
                letter-spacing: 1px;
            }}

            #CountdownTitle {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
            }}

            #CountdownDesc {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 11}px;
            }}


            #CircleFlipContainer, #CircleStack, #CircleFace {{
                background: transparent;
                border: none;
            }}

            #FaceDetectedCircle {{
                background: #3F9468;
                border: 3px solid #2F6F4F;
                border-radius: {84 if not self.compact_mode else 63}px;
            }}

            #FaceDetectedIcon {{
                color: white;
                font-size: {48 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #FaceDetectedCircleText {{
                color: white;
                font-size: {13 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 0.5px;
                padding-top: 2px;
            }}

            #FaceDetectedState {{
                color: #3F9468;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}


            #UsersTitle {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }}

            #UsersStatus {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
            }}

            #UsersDivider {{
                background: rgba(196, 199, 199, 0.65);
                border: none;
            }}

            #UserName {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #UserDetail {{
                color: {Theme.SECONDARY};
                font-size: {11 if not self.compact_mode else 9}px;
            }}

            #GreenDot {{
                color: {Theme.GREEN};
                font-size: {16 if not self.compact_mode else 12}px;
            }}

            #IdleText {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
            }}

            #ManageAccessButton {{
                background: transparent;
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}

            #ManageAccessButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
            }}

            #ManageAccessButton:pressed {{
                background: #333333;
                padding-top: 2px;
            }}

            #FooterArea {{
                background: transparent;
                border: none;
            }}

            #FooterStrip {{
                background: rgba(243, 243, 243, 0.88);
                border: 1px solid {Theme.BORDER};
                border-radius: {29 if not self.compact_mode else 26}px;
            }}

            #Copyright {{
                color: {Theme.MUTED};
                font-size: {11 if not self.compact_mode else 9}px;
            }}




            #LoginFailedDialog {{
                background: transparent;
            }}

            #FailedGlassPanel {{
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.70);
                border-radius: 30px;
            }}

            #FailedCircle {{
                background: #B23A3A;
                color: white;
                border-radius: {39 if not self.compact_mode else 33}px;
                font-size: {38 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #FailedTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 24}px;
                font-weight: 800;
                letter-spacing: -0.8px;
            }}

            #FailedReason {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                line-height: 1.5;
            }}

            #FailedDebugBox {{
                background: #F3F3F3;
                border: 1px solid {Theme.BORDER};
                border-radius: 16px;
            }}

            #FailedDebugTitle {{
                color: rgba(0, 0, 0, 0.48);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #FailedDebugText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
                line-height: 1.45;
            }}

            #FailedPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 16px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
            }}

            #FailedPrimaryButton:hover {{
                background: #2F3131;
            }}


            #LoginSuccessDialog {{
                background: transparent;
            }}

            #SuccessGlassPanel {{
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.70);
                border-radius: 32px;
            }}

            #SuccessBrand {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 6px;
            }}

            #SuccessOuterRing {{
                background: rgba(0, 0, 0, 0.03);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: {45 if not self.compact_mode else 39}px;
            }}

            #SuccessCheckCircle {{
                background: {Theme.PRIMARY};
                color: white;
                border-radius: {31 if not self.compact_mode else 27}px;
                font-size: {30 if not self.compact_mode else 26}px;
                font-weight: 300;
            }}

            #SuccessTitle {{
                color: {Theme.PRIMARY};
                font-size: {26 if not self.compact_mode else 22}px;
                font-weight: 700;
                letter-spacing: -1px;
            }}

            #SuccessBadge {{
                background: rgba(255, 255, 255, 0.65);
                color: rgba(0, 0, 0, 0.70);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 13px;
                padding: 5px 18px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.6px;
            }}

            #IdentityCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FFFFFF,
                    stop:0.52 #F3F3F3,
                    stop:1 #E8E8E8
                );
                border: 1px solid rgba(255, 255, 255, 0.95);
                border-radius: 18px;
            }}

            #IdentityMeta {{
                color: rgba(94, 94, 94, 0.70);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #IdentityNtid {{
                color: {Theme.PRIMARY};
                font-size: {16 if not self.compact_mode else 14}px;
                font-weight: 800;
                letter-spacing: -0.4px;
            }}

            #IdentityShield {{
                background: rgba(0, 0, 0, 0.05);
                color: rgba(0, 0, 0, 0.42);
                border-radius: 10px;
                font-size: 18px;
                font-weight: 900;
            }}

            #IdentityDivider {{
                background: rgba(0, 0, 0, 0.06);
                border: none;
            }}

            #IdentityAccess {{
                color: {Theme.PRIMARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #IdentitySession {{
                color: rgba(94, 94, 94, 0.65);
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #SuccessPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 18px;
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 800;
            }}

            #SuccessPrimaryButton:hover {{
                background: #2F3131;
            }}

            #SuccessPrimaryButton:pressed {{
                background: #444748;
                padding-top: 2px;
            }}

            #SuccessSmallLine {{
                background: rgba(0, 0, 0, 0.07);
                border: none;
            }}

            #SuccessRedirect {{
                color: rgba(94, 94, 94, 0.70);
                font-size: {12 if not self.compact_mode else 11}px;
                font-weight: 600;
            }}

            #SuccessFooterText {{
                color: rgba(0, 0, 0, 0.42);
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.4px;
            }}



            #InlineDebugBox {{
                background: #F3F3F3;
                border: 1px solid {Theme.BORDER};
                border-radius: 16px;
            }}

            #InlineDebugTitle {{
                color: rgba(0, 0, 0, 0.48);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #InlineDebugText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
                line-height: 1.45;
            }}



            #SettingsConnectionDialog {{
                background: transparent;
            }}

            #SettingsSuccessPanel {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 30px;
            }}

            #SettingsFailPanel {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 26px;
            }}

            #SettingsSuccessIcon {{
                background: #E8F5E9;
                color: #2E7D32;
                border: 1px solid rgba(46, 125, 50, 0.18);
                border-radius: {32 if not self.compact_mode else 28}px;
                font-size: {32 if not self.compact_mode else 28}px;
                font-weight: 900;
            }}

            #SettingsFailIcon {{
                background: #FFDAD6;
                color: #BA1A1A;
                border: 1px solid rgba(186, 26, 26, 0.20);
                border-radius: {32 if not self.compact_mode else 28}px;
                font-size: {34 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #SettingsConnectTitle {{
                color: {Theme.PRIMARY};
                font-size: {26 if not self.compact_mode else 22}px;
                font-weight: 800;
                letter-spacing: -0.8px;
            }}

            #SettingsConnectSubtitle {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
            }}

            #SettingsMetaCard {{
                background: #FFFFFF;
                border: 1px solid {Theme.BORDER};
                border-radius: 16px;
            }}

            #SettingsMetaLabel {{
                color: {Theme.MUTED};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.4px;
            }}

            #SettingsMetaValue {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
                font-family: Consolas;
            }}

            #SettingsMetaSuccessValue {{
                color: #2E7D32;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #SettingsDiagnosticCard {{
                background: #F3F3F3;
                border: 1px solid {Theme.BORDER};
                border-radius: 16px;
            }}

            #SettingsDiagnosticHeader {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.8px;
            }}

            #SettingsIssueMark {{
                color: #BA1A1A;
                font-size: {18 if not self.compact_mode else 16}px;
                font-weight: 900;
            }}

            #SettingsIssueTitle {{
                color: {Theme.PRIMARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SettingsIssueDesc {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #SettingsConnectPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SettingsConnectPrimaryButton:hover {{
                background: #2F3131;
            }}

            #SettingsConnectSecondaryButton {{
                background: #E1DFDF;
                color: #464747;
                border: 1px solid {Theme.BORDER};
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SettingsConnectSecondaryButton:hover {{
                background: #E8E8E8;
            }}


            #LoginPopupDialog {{
                background: transparent;
            }}

            #LoginPopupCard {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 24px;
            }}

            #LoginCloseButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 15px;
                font-size: 18px;
                font-weight: 800;
            }}

            #LoginCloseButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}


            #LoginMainContent {{
                background: {Theme.BG};
            }}

            #LoginCard {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 24px;
            }}

            #LoginShieldIcon {{
                background: {Theme.PRIMARY};
                color: white;
                border-radius: 14px;
                font-size: {28 if not self.compact_mode else 22}px;
                font-weight: 900;
            }}

            #LoginTitle {{
                color: {Theme.PRIMARY};
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 900;
                letter-spacing: -0.02em;
            }}

            #LoginSubtitle {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
            }}

            #LoginFieldLabel {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #LoginForgot {{
                color: {Theme.SECONDARY};
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #LoginInput {{
                background: {Theme.SURFACE};
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                padding: 0px 14px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                selection-background-color: {Theme.PRIMARY};
                selection-color: white;
            }}

            #LoginInput:hover {{
                border: 1px solid #747878;
                background: white;
            }}

            #LoginInput:focus {{
                border: 1px solid {Theme.PRIMARY};
                background: white;
            }}

            #LoginToggleButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #LoginToggleButton:hover {{
                background: #E2E2E2;
                color: {Theme.PRIMARY};
            }}

            #LoginSubmitButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #LoginSubmitButton:hover {{
                background: #2F3131;
            }}

            #LoginSubmitButton:pressed {{
                background: #444748;
                padding-top: 2px;
            }}

            #LoginDivider {{
                background: rgba(196, 199, 199, 0.50);
                border: none;
            }}

            #LoginStatus {{
                color: rgba(94, 94, 94, 0.75);
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}


            #SettingsTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 22}px;
                font-weight: 900;
            }}

            #SettingsDesc {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
            }}


            #SystemLogCard {{
                background: #dcdcdc;
                border: none;
                border-radius: {card_radius}px;
            }}

            #SystemLogCard #FaceSectionTitle {{
                color: #3F3F3F;
            }}

            #SystemLogCard #GreenDot {{
                color: #22C55E;
            }}


            #SettingsTitle {{
                color: {Theme.PRIMARY};
                font-size: {34 if not self.compact_mode else 24}px;
                font-weight: 900;
                letter-spacing: -0.02em;
            }}

            #SettingsDesc {{
                color: {Theme.SECONDARY};
                font-size: {15 if not self.compact_mode else 12}px;
            }}

            #SettingsCardTitle {{
                color: {Theme.PRIMARY};
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 800;
            }}

            #SettingsCardIcon {{
                color: {Theme.PRIMARY};
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 800;
            }}

            #SettingsDivider {{
                background: {Theme.BORDER};
                border: none;
            }}

            #SettingsLabel {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #SettingsInput {{
                background: white;
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                padding: 0px 12px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                selection-background-color: {Theme.PRIMARY};
                selection-color: white;
            }}

            #SettingsInput:hover {{
                border: 1px solid #747878;
            }}

            #SettingsInput:focus {{
                border: 1px solid {Theme.PRIMARY};
            }}

            #SettingsReadonlyBox {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                padding: 10px 12px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #SettingsPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 9px;
                padding: 0px 16px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsPrimaryButton:hover {{
                background: #2F3131;
            }}

            #SettingsPrimaryButton:pressed {{
                background: #444748;
                padding-top: 2px;
            }}

            #SettingsSecondaryButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                padding: 0px 16px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsSecondaryButton:hover {{
                background: #E2E2E2;
            }}

            #SettingsInnerPanel {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
            }}

            #SettingsMiniTitle {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #SettingsMiniDesc {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
            }}

            #SettingsOptionText {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
            }}


            #SettingsCheckBoxButton {{
                background: white;
                color: transparent;
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                font-size: 14px;
                font-weight: 900;
            }}

            #SettingsCheckBoxButton:hover {{
                border: 1px solid {Theme.PRIMARY};
                background: #F3F3F3;
            }}

            #SettingsCheckBoxButton:checked {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}

            #SettingsCheckBoxButton:pressed {{
                background: #333333;
            }}


            #SettingsCheckBox {{
                color: white;
                font-size: 12px;
                font-weight: 900;
                spacing: 0px;
            }}

            #SettingsCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 5px;
                border: 1px solid {Theme.BORDER};
                background: white;
            }}

            #SettingsCheckBox::indicator:hover {{
                border: 1px solid {Theme.PRIMARY};
                background: #F3F3F3;
            }}

            #SettingsCheckBox::indicator:checked {{
                background: {Theme.PRIMARY};
                border: 1px solid {Theme.PRIMARY};
            }}

            #SettingsCheckBox::indicator:unchecked {{
                background: white;
                border: 1px solid {Theme.BORDER};
            }}

            


            #SegmentedToggle {{
                background: {Theme.SURFACE_LOW};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
            }}

            #SegmentSnakeIndicator {{
                background: {Theme.PRIMARY};
                border: none;
                border-radius: 7px;
            }}

            #SegmentButtonActive {{
                background: transparent;
                color: white;
                border: none;
                border-radius: 7px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #SegmentButtonInactive {{
                background: transparent;
                color: {Theme.SECONDARY};
                border: none;
                border-radius: 7px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #SegmentButtonInactive:hover {{
                background: rgba(255, 255, 255, 0.45);
                color: {Theme.PRIMARY};
            }}

            #SegmentButtonActive:hover {{
                color: white;
            }}


            #SettingsDisconnected {{
                color: {Theme.RED};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #AdminListBox {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
            }}

            #AdminRow {{
                border-bottom: 1px solid {Theme.BORDER};
                background: transparent;
            }}

            #AdminName {{
                color: {Theme.PRIMARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #RemoveButton {{
                background: transparent;
                border: none;
                color: {Theme.RED};
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #RemoveButton:hover {{
                text-decoration: underline;
            }}

            #SettingsActionBar {{
                background: transparent;
                border: none;
            }}


            #CameraFeedCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #111827,
                    stop:0.5 #334155,
                    stop:1 #0F172A);
                border-radius: {card_radius}px;
            }}

            #LiveBadge, #QualityBadge {{
                background: rgba(0, 0, 0, 0.38);
                color: white;
                border-radius: 14px;
                padding: 6px 12px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.5px;
            }}

            #LiveBadge {{
                color: white;
            }}

            #QualityBadge {{
                background: rgba(63, 148, 104, 0.80);
            }}

            #ScanBox {{
                color: rgba(255, 255, 255, 0.72);
                font-family: Consolas;
                font-size: {18 if not self.compact_mode else 14}px;
                font-weight: 700;
            }}

            #CameraPreviewLabel {{
                background: #111827;
                color: rgba(255, 255, 255, 0.72);
                border-radius: 18px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 700;
            }}

            #CameraMeta {{
                color: rgba(255, 255, 255, 0.45);
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
            }}

            #FaceSectionTitle {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #NtidInput {{
                background: rgba(255, 255, 255, 0.74);
                color: {Theme.PRIMARY};
                border: 1px solid rgba(26, 28, 28, 0.26);
                border-radius: 10px;
                padding: 0px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
                selection-background-color: {Theme.GREEN_CARD};
                selection-color: white;
            }}

            #NtidInput:hover {{
                border: 1px solid rgba(26, 28, 28, 0.45);
                background: white;
            }}

            #NtidInput:focus {{
                border: 1px solid {Theme.PRIMARY};
                background: white;
            }}

            #OutlineActionButton {{
                background: rgba(255, 255, 255, 0.52);
                color: {Theme.PRIMARY};
                border: 1px solid rgba(26, 28, 28, 0.65);
                border-radius: 10px;
                min-height: 32px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
                letter-spacing: 0.7px;
                padding: 0px 8px;
            }}

            #OutlineActionButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}

            #OutlineActionButton:pressed {{
                background: #333333;
                color: white;
                padding-top: 1px;
            }}

            #GreenActionButton {{
                background: {Theme.GREEN_CARD};
                color: white;
                border: 1px solid {Theme.GREEN_CARD};
                border-radius: 10px;
                min-height: 32px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 850;
                letter-spacing: 0.8px;
                padding: 0px 8px;
            }}

            #GreenActionButton:hover {{
                background: #327A53;
                border: 1px solid #327A53;
            }}

            #GreenActionButton:pressed {{
                background: #276342;
                padding-top: 1px;
            }}

            #StopButton {{
                background: rgba(220, 38, 38, 0.04);
                color: {Theme.RED};
                border: 1px solid rgba(220, 38, 38, 0.35);
                border-radius: 9px;
                min-height: 30px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 850;
                letter-spacing: 0.4px;
            }}

            #StopButton:hover {{
                background: {Theme.RED};
                color: white;
                border: 1px solid {Theme.RED};
            }}

            #StopButton:pressed {{
                background: #B91C1C;
                padding-top: 1px;
            }}

            #DeleteButton {{
                background: rgba(255, 255, 255, 0.52);
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                min-height: 30px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 850;
                letter-spacing: 0.4px;
            }}

            #DeleteButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}

            #DeleteButton:pressed {{
                background: #333333;
                padding-top: 1px;
            }}

            #LogText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {11 if not self.compact_mode else 10}px;
                line-height: 1.8;
            }}

            #FaceUserRow {{
                background: rgba(255, 255, 255, 0.45);
                border: 1px solid transparent;
                border-radius: 18px;
            }}

            #FaceUserRow:hover {{
                background: white;
                border: 1px solid rgba(0, 0, 0, 0.05);
            }}

            #TrainedBadge {{
                background: rgba(22, 163, 74, 0.10);
                color: {Theme.GREEN_CARD};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
            }}

            #PendingBadge {{
                background: rgba(0, 0, 0, 0.06);
                color: {Theme.SECONDARY};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
            }}
        """)
