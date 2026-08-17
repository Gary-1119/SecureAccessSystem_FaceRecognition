from __future__ import annotations

from typing import Any, cast

import ctypes
import html
import os
import platform

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsBlurEffect, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app_config import *
from services.resource_service import app_resource_path
from styles.app_styles import apply_dashboard_styles
from ui_components import *


class ShellLayoutMixin:
    def build_window(self: Any):
        self.setWindowTitle("Secure Access System")
        self.ensure_taskbar_window_identity()
        screen_obj = QApplication.primaryScreen()
        if screen_obj is None:
            self.resize(1180, 720)
            self.compact_mode = False
            self.ui_scale = 1.0
            return

        screen = screen_obj.availableGeometry()
        sw, sh = screen.width(), screen.height()

        self.ui_scale = max(0.68, min(1.0, min(sw / 1920, sh / 1080)))
        self.compact_mode = sw < 1500 or sh < 850

        if self.compact_mode:
            min_w, min_h = 900, 600
        else:
            min_w, min_h = 1180, 720

        self.setMinimumSize(min_w, min_h)

        # Supervisor requirement:
        # open in full available desktop size by default.
        # Use maximized instead of borderless fullscreen so the normal Windows title bar remains available.
        self.resize(sw, sh)
        self.move(screen.x(), screen.y())
        QTimer.singleShot(80, self.showMaximized)

    def apply_app_icon(self: Any):
        """Apply the SAS logo to the window, taskbar and Qt application icon."""
        icon_path = app_resource_path("assets", "sas_logo.ico")
        png_path = app_resource_path("assets", "sas_logo.png")

        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        elif os.path.exists(png_path):
            icon = QIcon(png_path)
        else:
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            painter.setBrush(QColor("#0B5FFF"))
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

    def apply_window_chrome(self: Any):
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

    def content_max_width(self: Any) -> int:
        """Responsive maximum content width for maximised startup."""
        w = max(1, self.width())

        if w >= 2200:
            return min(2600, int(w * 0.92))

        if w >= 1700:
            return min(1900, int(w * 0.90))

        if w >= 1300:
            return min(1500, int(w * 0.88))

        return 1220

    def build_ui(self: Any):
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

    def build_header(self: Any):
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(64 if not self.compact_mode else 54)

        layout = QHBoxLayout(header)
        pad = 48 if not self.compact_mode else 26
        layout.setContentsMargins(pad, 0, pad, 0)
        layout.setSpacing(0)

        # Give the brand enough space so "SECURE ACCESS SYSTEM" never clips.
        side_width = 450 if not self.compact_mode else 350

        left_zone = QWidget()
        left_zone.setFixedWidth(side_width)
        left_layout = QHBoxLayout(left_zone)
        left_layout.setContentsMargins(0, 0, 0, 0)

        brand_row = QWidget()
        brand_row.setObjectName("BrandRow")
        brand_layout = QHBoxLayout(brand_row)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(10 if not self.compact_mode else 8)
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        logo_label = QLabel()
        logo_label.setObjectName("HeaderLogo")
        logo_size = 34 if not self.compact_mode else 28
        logo_label.setFixedSize(logo_size, logo_size)
        logo_pixmap = QPixmap(app_resource_path("assets", "sas_logo.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(
                logo_size,
                logo_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        brand = QLabel("SECURE ACCESS SYSTEM")
        brand.setMinimumWidth(318 if not self.compact_mode else 245)
        brand.setObjectName("Brand")

        self.guidelines_help_btn = QPushButton("?")
        self.guidelines_help_btn.setObjectName("GuidelinesHelpButton")
        self.guidelines_help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_size = 28 if not self.compact_mode else 24
        self.guidelines_help_btn.setFixedSize(help_size, help_size)
        self.guidelines_help_btn.setToolTip("Open SAS guidelines")
        self.guidelines_help_btn.clicked.connect(self.show_guidelines_dialog)

        brand_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        brand_layout.addWidget(brand, alignment=Qt.AlignmentFlag.AlignVCenter)
        brand_layout.addWidget(self.guidelines_help_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        brand_layout.addStretch()
        left_layout.addWidget(brand_row, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        center_zone = QWidget()
        center_layout = QHBoxLayout(center_zone)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(28 if not self.compact_mode else 16)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for tab_name in ["Dashboard", "Face Recognition", "Settings"]:
            btn = TopNavButton(tab_name, active=(tab_name == "Dashboard"))
            btn.clicked.connect(lambda checked=False, name=tab_name: self.switch_top_tab(name))
            if tab_name in ("Face Recognition", "Settings"):
                btn.setToolTip("Admin login required.")
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

    def animate_tab_indicator(self: Any, tab_name: str, animate: bool = True):
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

    def switch_top_tab(self: Any, name: str):
        if not self.require_admin_for_tab(name):
            return

        # v112: if the user is leaving Settings with unsaved changes, ask
        # whether to Save, Don't Save, or Cancel before changing page.
        if (
            str(getattr(self, "current_top_tab", "") or "") == "Settings"
            and str(name or "") != "Settings"
            and not getattr(self, "_settings_bypass_unsaved_prompt_once", False)
        ):
            if self.maybe_prompt_unsaved_settings_before_leave(
                lambda target=name: self.switch_top_tab(target),
                context="leave-settings",
            ):
                return

        # Face Recognition should only open after a successful Settings connection.
        # Do not reconnect here. If connection failed/not configured, guide user to Settings.
        if name == "Face Recognition" and not getattr(self, "pi_connected", False):
            reason = (
                "camera connection is not available. Please set the hostname/IP and press Connect in Settings."
                if getattr(self, "pi_connection_checked", False)
                else "Please connect the camera hostname/IP in Settings before using Face Recognition."
            )
            self.show_face_tab_pi_disconnect_popup(reason)
            return

        self.current_top_tab = name

        if name in {"Face Recognition", "Settings"}:
            actor = self.get_audit_actor()
            self.write_sas_log(
                "RESTRICTED PAGE OPENED",
                actor=actor,
                details={"Page": name},
            )

        for tab_name, btn in self.top_nav_buttons.items():
            btn.set_active(tab_name == name)

        if name in self.top_nav_buttons:
            self.animate_tab_indicator(name, animate=True)

        if name == "Dashboard":
            self.set_footer_mode("dashboard")
            self.stack.fade_to(self.dashboard_page)
            self.update_time()
        elif name == "Face Recognition":
            self.set_footer_mode("face")
            # Already connected from Settings; use normally without reconnecting.
            self.stack.fade_to(self.face_page)
            self._local_face_refresh_users()

            # Refresh camera panel state on entry.
            # If API is online but camera is stopped, show "Camera stopped".
            # If recognition is already running on camera, show video feed.
            self.check_pi_camera_status_and_update_panel()
        elif name == "Settings":
            self.set_footer_mode("settings")
            # Do not auto-contact the previous camera when returning to Settings.
            # Settings refreshes camera details only when the current selected host
            # is actually connected.  A wrong/manual host must remain shown in
            # Disconnected state until the user presses Connect again.
            if bool(getattr(self, "pi_connected", False)) and str(getattr(self, "pi_api_host", "") or "").strip():
                self.pull_pi_settings_to_sas(silent=True)
            self.refresh_admin_list_ui()
            self.stack.fade_to(self.settings_page)
        elif name == "Login":
            self.stack.fade_to(self.login_page)

    def clear_blur_effect(self: Any, widget):
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

    def make_scrollbar_invisible(self: Any, scroll: QScrollArea):
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

    def set_footer_mode(self: Any, mode: str):
        """Settings: compact full footer. Dashboard/Face Recognition: no footer."""
        if not hasattr(self, "footer_area"):
            return

        if mode in ("dashboard", "face"):
            self.footer_area.setVisible(False)
            return

        self.footer_area.setVisible(True)
        show_full = (mode == "settings")

        for w in (
            getattr(self, "footer_line_1", None),
            getattr(self, "footer_state_label", None),
            getattr(self, "footer_line_2", None),
            getattr(self, "footer_timeout_label", None),
        ):
            if w is not None:
                w.setVisible(show_full)

        if hasattr(self, "footer_strip"):
            self.adjust_footer_width()

    def adjust_footer_width(self: Any):
        """Resize the footer strip to match visible footer content."""
        footer = getattr(self, "footer_strip", None)
        if footer is None:
            return

        layout = footer.layout()
        if layout is None:
            return

        # Let Qt recompute label widths after visibility/text changes.
        footer.adjustSize()
        content_w = layout.sizeHint().width()
        pad_extra = 6 if not self.compact_mode else 4
        max_w = max(360, self.width() - (96 if not self.compact_mode else 48))
        new_w = max(520 if not self.compact_mode else 460, min(content_w + 36, 820 if not self.compact_mode else 680))
        footer.setMinimumWidth(new_w)
        footer.setMaximumWidth(new_w)
        footer.updateGeometry()

    def format_lock_interval(self: Any, seconds: int) -> str:
        """Format lock timeout for UI footer.

        Examples:
        300 -> 05:00
        3600 -> 01:00:00
        """
        try:
            total = max(0, int(seconds))
        except Exception:
            total = 0

        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"

        return f"{minutes:02d}:{secs:02d}"

    def update_footer_info(self: Any):
        server_path_text = "Not configured" if not self.server_path else html.escape(self.server_path)
        if hasattr(self, "footer_server_label"):
            self.footer_server_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 2}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>SERVER PATH</span><br><span style='font-size:{max(10, int(12 * self.ui_scale))}px; line-height:{max(10, int(12 * self.ui_scale)) + 3}px; color:{Theme.TEXT}; font-weight:700;'>{server_path_text}</span>")

        if hasattr(self, "footer_state_label"):
            self.footer_state_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 2}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>UNLOCK CHANNEL</span><br><span style='font-size:{max(10, int(12 * self.ui_scale))}px; line-height:{max(10, int(12 * self.ui_scale)) + 3}px; color:{Theme.TEXT}; font-weight:700;'>LOCAL</span>")

        if hasattr(self, "footer_timeout_label"):
            lock_time_text = self.format_lock_interval(self.lock_timeout_seconds)
            self.footer_timeout_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 2}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>LOCK TIME INTERVAL</span><br><span style='font-size:{max(10, int(12 * self.ui_scale))}px; line-height:{max(10, int(12 * self.ui_scale)) + 3}px; color:{Theme.TEXT}; font-weight:700;'>{lock_time_text}</span>")

        if hasattr(self, "current_top_tab"):
            if self.current_top_tab == "Dashboard":
                self.set_footer_mode("dashboard")
            elif self.current_top_tab == "Face Recognition":
                self.set_footer_mode("face")
            elif self.current_top_tab == "Settings":
                self.set_footer_mode("settings")

        QTimer.singleShot(0, self.adjust_footer_width)

    def face_action_feedback(self: Any, message: str):
        self.append_face_log(message)

    def build_footer_area(self: Any):
        area = QFrame()
        self.footer_area = area
        area.setObjectName("FooterArea")
        area.setFixedHeight(56 if not self.compact_mode else 48)

        area_layout = QHBoxLayout(area)
        area_layout.setContentsMargins(0, 3, 0, 6)
        area_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        footer = self.build_footer_strip()
        footer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        area_layout.addWidget(footer, 0, Qt.AlignmentFlag.AlignCenter)
        return area

    def build_footer_strip(self: Any):
        footer = QFrame()
        self.footer_strip = footer
        footer.setObjectName("FooterStrip")
        footer.setFixedHeight(44 if not self.compact_mode else 40)
        footer.setStyleSheet(f"""
            QFrame#FooterStrip {{
                background-color: #FFFFFF;
                border: 1px solid {Theme.BORDER};
                border-radius: 22px;
            }}
        """)
        # Width is adjusted dynamically after footer content is updated, so the
        # strip follows the actual visible content instead of using a large
        # fixed/minimum length.
        footer.setMinimumWidth(520 if not self.compact_mode else 460)
        footer.setMaximumWidth(820 if not self.compact_mode else 680)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(
            22 if not self.compact_mode else 16,
            4 if not self.compact_mode else 3,
            22 if not self.compact_mode else 16,
            4 if not self.compact_mode else 3,
        )
        layout.setSpacing(22 if not self.compact_mode else 14)

        self.footer_server_label = InfoLabel("SERVER PATH", self.server_path, self.ui_scale)
        self.footer_state_label = InfoLabel("UNLOCK CHANNEL", "LOCAL", self.ui_scale)
        self.footer_timeout_label = InfoLabel("LOCK TIME INTERVAL", f"{self.lock_timeout_seconds}s", self.ui_scale)

        self.footer_line_1 = self.vertical_line()
        self.footer_line_2 = self.vertical_line()

        layout.addWidget(self.footer_server_label)
        layout.addWidget(self.footer_line_1)
        layout.addWidget(self.footer_state_label)
        layout.addWidget(self.footer_line_2)
        layout.addWidget(self.footer_timeout_label)

        # Copyright text removed per supervisor request.
        QTimer.singleShot(0, self.update_footer_info)
        return footer

    def vertical_line(self: Any):
        line = QFrame()
        line.setObjectName("VerticalLine")
        line.setFixedSize(1, 24 if not self.compact_mode else 20)
        return line

    def resizeEvent(self: Any, event):
        QMainWindow.resizeEvent(cast(QMainWindow, self), event)

        # Recalculate centred content width when maximising or moving to a large monitor.
        try:
            max_w = self.content_max_width()
            for page in ("dashboard_page", "face_page", "settings_page"):
                p = getattr(self, page, None)
                if p is not None:
                    scroll = p.findChild(QScrollArea)
                    if scroll is not None:
                        content = scroll.widget()
                        if content is not None:
                            content.setMaximumWidth(max_w)
        except Exception:
            pass

        self.update_dashboard_card_sizes()
        self.update_face_card_sizes()

        if hasattr(self, "account_menu") and self.account_menu.isVisible() and self.account_menu.height() > 0:
            self.position_account_menu()

    def update_dashboard_card_sizes(self: Any):
        if not hasattr(self, "dashboard_cards"):
            return

        w = max(1, self.width())
        h = max(1, self.height())

        # Dynamically fill the fullscreen space.
        # Monitor and laptop have different ratios, so sizes are calculated from the current window.
        if w >= 2200:
            card_w = int(w * 0.82)
            card_h = int(h * 0.56)
            time_font = 112
            date_font = 16
        elif w >= 1700:
            card_w = int(w * 0.84)
            card_h = int(h * 0.54)
            time_font = 104
            date_font = 15
        elif w >= 1300:
            card_w = int(w * 0.76)
            card_h = int(h * 0.56)
            time_font = 108
            date_font = 14
        else:
            card_w = int(w * 0.86)
            card_h = int(h * 0.48)
            time_font = 84 if self.compact_mode else 96
            date_font = 12

        card_w = max(900 if self.compact_mode else 1080, min(card_w, 2500))
        card_h = max(370 if self.compact_mode else 470, min(card_h, 780))

        for card in self.dashboard_cards:
            card.setMinimumWidth(card_w)
            card.setMaximumWidth(card_w)
            card.setMinimumHeight(card_h)
            card.setMaximumHeight(card_h)

        # Scale the clock according to the screen size.
        if hasattr(self, "time_label"):
            # Avoid clipping by giving the QLabel real height instead of using padding.
            time_h = int(time_font * 1.18)
            self.time_label.setFixedHeight(time_h)
            self.time_label.setStyleSheet(f"font-size: {time_font}px; font-weight: 900; letter-spacing: -4px;")
        if hasattr(self, "date_label"):
            date_h = int(date_font * 2.1)
            self.date_label.setFixedHeight(date_h)
            self.date_label.setStyleSheet(f"font-size: {date_font}px; font-weight: 700; letter-spacing: 2px;")

        if hasattr(self, "time_section") and hasattr(self, "time_label") and hasattr(self, "date_label"):
            safe_h = self.time_label.height() + self.date_label.height() + (22 if not self.compact_mode else 12)
            self.time_section.setFixedHeight(max(145 if self.compact_mode else 175, safe_h))

        # Scale contents inside the unified card so the green panel does not look empty.
        circle_size = int(card_h * 0.42)
        circle_size = max(190 if not self.compact_mode else 140, min(circle_size, 310))

        if hasattr(self, "circle_flip_container"):
            self.circle_flip_container.setFixedSize(circle_size, circle_size)
        if hasattr(self, "circle_stack"):
            self.circle_stack.setFixedSize(circle_size, circle_size)
            self.circle_stack.setGeometry(0, 0, circle_size, circle_size)
        if hasattr(self, "timer_circle_front"):
            self.timer_circle_front.setFixedSize(circle_size, circle_size)
        if hasattr(self, "face_circle_back"):
            self.face_circle_back.setFixedSize(circle_size, circle_size)
            self.face_circle_back.setStyleSheet(
                f"background: rgba(255, 255, 255, 0.16); border: 3px solid rgba(255, 255, 255, 0.32); border-radius: {circle_size // 2}px;"
            )
        if hasattr(self, "ring"):
            self.ring.setFixedSize(circle_size, circle_size)
        if hasattr(self, "circle_flip_overlay"):
            self.circle_flip_overlay.setGeometry(0, 0, circle_size, circle_size)

        # Text and button scaling inside card.
        title_font = max(24, min(int(card_h * 0.075), 48))
        eyebrow_font = max(10, min(int(card_h * 0.030), 17))
        countdown_font = max(24, min(int(circle_size * 0.22), 62))
        remaining_font = max(10, min(int(circle_size * 0.075), 18))
        desc_font = max(18, min(int(card_h * 0.045), 28))
        face_icon_font = max(34, min(int(circle_size * 0.30), 76))
        face_text_font = max(13, min(int(circle_size * 0.080), 24))
        btn_h = max(48, min(int(card_h * 0.105), 70))
        btn_w1 = max(190, min(int(card_w * 0.15), 300))
        btn_w2 = max(220, min(int(card_w * 0.17), 340))

        if hasattr(self, "dashboard_protocol_label"):
            self.dashboard_protocol_label.setStyleSheet(
                f"color: rgba(255,255,255,0.70); font-size: {eyebrow_font}px; font-weight: 800; letter-spacing: 2px;"
            )
        if hasattr(self, "status_title"):
            self.status_title.setStyleSheet(
                f"color: #FFFFFF; font-size: {title_font}px; font-weight: 900; letter-spacing: -0.03em;"
            )
        if hasattr(self, "countdown_label"):
            self.countdown_label.setStyleSheet(
                f"color: #FFFFFF; font-size: {countdown_font}px; font-weight: 900;"
            )
        # RemainingText is a child label inside ring, found by objectName.
        if hasattr(self, "ring"):
            for child in self.ring.findChildren(QLabel):
                if child.objectName() == "RemainingText":
                    child.setStyleSheet(
                        f"color: rgba(255,255,255,0.78); font-size: {remaining_font}px; font-weight: 800; letter-spacing: 1px;"
                    )
        if hasattr(self, "face_state_label"):
            self.face_state_label.setStyleSheet(
                f"color: rgba(255,255,255,0.90); font-size: {desc_font}px; font-weight: 900;"
            )

        if hasattr(self, "face_detected_icon"):
            self.face_detected_icon.setStyleSheet(
                f"color: #FFFFFF; background: transparent; border: none; font-size: {face_icon_font}px; font-weight: 900;"
            )
        if hasattr(self, "face_detected_circle_text"):
            self.face_detected_circle_text.setStyleSheet(
                f"color: #FFFFFF; background: transparent; border: none; padding: 3px 8px; font-size: {face_text_font}px; font-weight: 900; letter-spacing: 1px;"
            )

        manual_btn = getattr(self, "manual_lock_btn", None)
        if manual_btn is not None:
            manual_btn.setFixedHeight(btn_h)
            manual_btn.setMinimumWidth(btn_w1)
            manual_btn.setMaximumWidth(btn_w1)

        auth_btn = getattr(self, "dashboard_authorized_users_btn", None)
        if auth_btn is not None:
            icon_size = max(40, min(int(card_h * 0.095), 58))
            auth_btn.setFixedSize(icon_size, icon_size)
            # Trigger the status-card resize handler so the floating icon stays
            # anchored after responsive card-size recalculation.
            if hasattr(self, "status_card_widget"):
                self.status_card_widget.updateGeometry()

    def update_face_card_sizes(self: Any):
        """Responsive Face Recognition console layout.

        Composition follows the provided reference without removing any existing
        actions or animations:
        [ Controls + Authorised Users ][ Large Camera + System Log ]

        v153 note:
        Keep the right camera/log column inside the page padding. The previous
        fixed width calculation could exceed the visible right padding on wide
        screens because it used too much of the full window width.
        """
        if not hasattr(self, "face_cards"):
            return

        w = max(1, self.width())
        h = max(1, self.height())

        camera, controls, logs, users = self.face_cards

        page_margin = 28 if not self.compact_mode else 18
        gap_w = 24 if not self.compact_mode else 16

        # Safe visual width for the two-column console. This leaves real space
        # at the right edge so the camera panel and System Log never touch or
        # overflow past the page padding.
        max_content_w = max(900, self.content_max_width() - (page_margin * 2))
        viewport_safe_w = max(900, w - (page_margin * 2) - 36)
        visual_safe_w = max(900, int(w * (0.84 if w >= 1700 else 0.88)))
        available_w = min(max_content_w, viewport_safe_w, visual_safe_w)

        if w >= 1700:
            left_w = max(330, min(int((available_w - gap_w) * 0.27), 420))
            right_w = max(860, min(available_w - gap_w - left_w, 1160))
            controls_h = 272
            logs_h = 170
        elif w >= 1300:
            left_w = max(300, min(int((available_w - gap_w) * 0.27), 370))
            right_w = max(760, min(available_w - gap_w - left_w, 1030))
            controls_h = 266
            logs_h = 165
        else:
            left_w = 300 if not self.compact_mode else 270
            right_w = max(640 if not self.compact_mode else 560, available_w - gap_w - left_w)
            controls_h = 258 if not self.compact_mode else 238
            logs_h = 160 if not self.compact_mode else 145

        # Final safety clamp: never let fixed child widths exceed the available
        # layout width. This keeps both camera and log aligned within the right
        # content padding even after resize/maximise.
        total_w = left_w + gap_w + right_w
        if total_w > available_w:
            overflow = total_w - available_w
            right_w = max(620 if not self.compact_mode else 540, right_w - overflow)

        # Use most of the page height, similar to the single-screen HTML console.
        chrome_gap = 150 if not self.compact_mode else 128
        console_h = max(560 if not self.compact_mode else 500, h - chrome_gap)
        column_gap = 16 if not self.compact_mode else 12

        users_h = max(320 if not self.compact_mode else 280, console_h - controls_h - column_gap)
        camera_h = max(360 if not self.compact_mode else 310, console_h - logs_h - column_gap)

        # Prevent very tall cards from making the hidden scroll page feel heavy.
        users_h = min(users_h, 620 if not self.compact_mode else 540)
        camera_h = min(camera_h, 700 if not self.compact_mode else 600)
        logs_h = min(logs_h, 210 if not self.compact_mode else 185)

        camera.setMinimumHeight(camera_h)
        camera.setMaximumHeight(camera_h)

        controls.setMinimumHeight(controls_h)
        controls.setMaximumHeight(controls_h)

        users.setMinimumHeight(users_h)
        users.setMaximumHeight(users_h)

        logs.setMinimumHeight(logs_h)
        logs.setMaximumHeight(logs_h)

        controls.setMinimumWidth(left_w)
        controls.setMaximumWidth(left_w)
        users.setMinimumWidth(left_w)
        users.setMaximumWidth(left_w)

        camera.setMinimumWidth(right_w)
        camera.setMaximumWidth(right_w)
        logs.setMinimumWidth(right_w)
        logs.setMaximumWidth(right_w)

        if hasattr(self, "camera_preview_label"):
            preview_h = max(260 if not self.compact_mode else 220, camera_h - (44 if not self.compact_mode else 38))
            self.camera_preview_label.setMinimumHeight(preview_h)
            self.camera_preview_label.setMaximumHeight(preview_h)

    def apply_styles(self: Any):
        apply_dashboard_styles(self)
