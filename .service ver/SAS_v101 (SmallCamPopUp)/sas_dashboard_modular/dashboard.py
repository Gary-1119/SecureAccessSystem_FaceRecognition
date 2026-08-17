import sys
import ctypes
import platform
import os
import time
import json
import html
import requests
import subprocess
import socket
from urllib.parse import quote
try:
    import paramiko
except Exception:
    paramiko = None
import xml.etree.ElementTree as ET
from threading import Thread
from datetime import datetime
from typing import Any, cast

try:
    import cv2
except Exception:
    cv2 = None

from PySide6.QtCore import (
    Qt, QTimer, QDateTime, QRectF, QRect, QPoint, QEvent,
    QPropertyAnimation, QEasingCurve, Property, QObject, Signal
)
from PySide6.QtGui import (
    QFont, QPainter, QPen, QColor, QIcon, QPixmap, QImage, QPainterPath, QIntValidator
)
from PySide6.QtWidgets import (
    QGraphicsEffect,
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
    QInputDialog,
    QMessageBox,
    QSystemTrayIcon,
    QListWidget,
    QProgressBar,
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


def app_resource_path(*parts: str) -> str:
    """Resolve bundled/static app resources for source and PyInstaller builds."""
    candidates = []
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(module_dir, *parts))

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(os.path.join(bundle_dir, *parts))
        candidates.append(os.path.join(bundle_dir, "sas_dashboard_modular", *parts))

    candidates.append(os.path.join(os.getcwd(), *parts))
    candidates.append(os.path.join(os.getcwd(), "sas_dashboard_modular", *parts))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return os.path.join(module_dir, *parts)


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


class SecureAccessDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui_bridge = UiBridge()
        self._closing = False
        try:
            self.destroyed.connect(lambda *_: setattr(self, "_closing", True))
        except Exception:
            pass
        self.top_nav_buttons = {}
        self.current_top_tab = "Dashboard"
        self.pending_restricted_tab = None
        self.time_left = 17
        self.total_seconds = 60
        self.is_locked = False
        self.is_logged_in = False
        self.first_launch_setup_mode = False
        self.server_configured = False
        self._suppress_lock_notification = False
        self.current_user = None
        self.clear_session_credentials_on_logout()
        self.current_user_role = "Guest"
        self.is_admin = False
        self.server_path = SERVER_PATH
        # Do not hard-code a Pi IP for EXE distribution.
        # New users must configure hostname/IP in Settings before SAS can connect.
        self.pi_api_host = ""
        self.pi_api_port = "5000"
        self.pi_api_base = ""
        self.pi_connected = False
        # The Pi owns the persisted camera orientation. SAS pulls it from
        # /settings and can update it without remounting the SMB server path.
        self.camera_rotation = 0
        self._camera_rotation_sync_in_progress = False
        self._camera_rotation_poll_in_progress = False
        self._pi_storage_poll_in_progress = False
        self._pi_storage_last_snapshot = None
        self._pi_disconnect_popup_visible = False
        self._pi_disconnect_popup_last_shown_at = 0.0
        self._startup_disconnect_popup_shown = False
        self._settings_connect_attempt_id = 0
        self._manual_connect_failed_popup_active = False
        self._settings_validation_passed = False
        self._session_settings_ntid = ""
        self._session_settings_password = ""
        self._session_settings_server = ""
        self._keep_session_credentials_visible = False
        self._pi_disconnect_lock_suspended = False
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._pi_disconnect_reason = ""
        self._pi_disconnect_last_auto_popup_ts = 0.0
        self._pi_disconnect_popup_user_closed = False
        self.connection_dialog = None
        self.pi_connection_checked = False
        self.pi_system_user = ""
        self.pi_device_hostname = ""
        self.sas_received_badge_label = None
        self.sas_check_received_btn = None
        self.sas_received_seen_files = set()
        self.sas_received_poll_initialized = False
        self.sas_received_popup_visible = False
        self.sas_received_tray_icon = None
        self.camera_feed_url = ""
        self.camera_capture = None
        self.camera_timer = None
        self._camera_preview_running = False
        self._handling_pi_disconnect = False
        self.camera_frame_count = 0
        self.camera_last_tick = None
        self.camera_fps = 0
        self._camera_user_stopped = False
        self._modal_open_count = 0
        # In-app card dialogs can overlap (example: SFTP success popup +
        # Pending Received popup).  Keep one shared blur/dim layer alive until
        # the last card closes, otherwise the dashboard can stay dimmed or be
        # cleared while another card is still open.
        self._card_dialog_open_count = 0
        self._card_dialog_dim_overlays = []
        self._missing_credentials_popup_shown = False
        self._camera_resume_after_modal = False
        self.manual_capture_active = False
        self.manual_capture_user = None
        # True from the moment SAS starts a capture request until the Pi reports
        # that capture has fully stopped.  This prevents a second camera mode
        # (Recognition) from being requested while PiCamera2 is still in use.
        self.face_capture_in_progress = False

        # v188 background mode:
        # When SAS starts with completed configuration and Pi is online, keep the
        # dashboard running minimized in the Windows taskbar. Bring it back when
        # locked, Pi disconnects, or first-launch setup is required.
        self._startup_background_check_done = False
        self._startup_background_check_pending = False
        self._startup_minimize_done = False
        self._auto_minimize_enabled = True
        self._minimized_by_sas = False

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

        # Inactivity lock state:
        # The auto-lock countdown follows Windows screen-saver behaviour.
        # It is driven by keyboard/mouse inactivity, not by camera/face state.
        # recognition_result.json is only used after the system is already locked.
        self.face_detected = False
        self._last_user_activity_ts = time.monotonic()
        self._idle_event_filter_installed = False
        self._countdown_flip_anim_1 = None
        self._countdown_flip_anim_2 = None
        self._circle_flip_animating = False
        self._pending_face_detected_state = None
        self._pending_auto_lock = False
        self.system_locked_notification = None
        self.ui_scale = 1.0
        self.compact_mode = False

        self.build_window()
        self.build_ui()
        self.apply_styles()
        self.apply_app_icon()
        self.install_idle_activity_tracker()
        self.load_settings_from_credentials()

        # Apply after the native window handle is ready.
        QTimer.singleShot(0, self.apply_window_chrome)

        self.start_timers()
        QTimer.singleShot(550, self.show_missing_credentials_setup_popup_if_needed)
        QTimer.singleShot(1200, self.startup_background_mode_check)





    def is_settings_tab_active(self) -> bool:
        """Return True when the user is currently working in Settings.

        v208: Do not rely only on current_top_tab, because that value can become
        stale during popup/worker transitions. Also check the active page object,
        visible Settings widgets, and keyboard focus.
        """
        try:
            if str(getattr(self, "current_top_tab", "") or "").lower() == "settings":
                return True
        except Exception:
            pass

        try:
            stack = getattr(self, "page_stack", None)
            settings_page = getattr(self, "settings_page", None)
            if stack is not None and settings_page is not None and stack.currentWidget() is settings_page:
                return True
        except Exception:
            pass

        try:
            # Some builds use a dictionary of pages instead of self.settings_page.
            pages = getattr(self, "pages", None)
            stack = getattr(self, "page_stack", None)
            if isinstance(pages, dict) and stack is not None:
                settings_page = pages.get("Settings") or pages.get("settings")
                if settings_page is not None and stack.currentWidget() is settings_page:
                    return True
        except Exception:
            pass

        try:
            # If keyboard focus is inside a Settings input field, suppress auto popups.
            focused = QApplication.focusWidget()
            settings_inputs = (
                "pi_host_input",
                "server_path_input",
                "ntid_input",
                "password_input",
                "lock_hours_spin",
                "lock_minutes_spin",
                "lock_seconds_spin",
            )
            for attr in settings_inputs:
                widget = getattr(self, attr, None)
                if widget is not None and focused is not None:
                    if focused is widget or widget.isAncestorOf(focused):
                        return True
        except Exception:
            pass

        try:
            # Fallback: visible Pi/settings widgets mean user is in Settings.
            widget = getattr(self, "pi_host_input", None)
            if widget is not None and widget.isVisible():
                return True
        except Exception:
            pass

        return False


    def return_to_settings_from_pi_disconnect(self):
        """Restore/maximize SAS and open Settings only after user clicks the button."""
        try:
            self.ensure_taskbar_window_identity()
            self._minimized_by_sas = False

            self.setWindowState(
                (self.windowState() & ~Qt.WindowState.WindowMinimized)
                | Qt.WindowState.WindowActive
            )
            self.show()
            self.showMaximized()
            self.raise_()
            self.activateWindow()

            try:
                QApplication.setActiveWindow(self)
            except Exception:
                pass

            try:
                self.clear_disconnect_popup_overlay()
            except Exception:
                pass

            self.switch_top_tab("Settings")

            try:
                dialog = getattr(self, "connection_dialog", None)
                if dialog is not None:
                    dialog.close()
            except Exception:
                pass

            self.append_system_log("RETURN_TO_SETTINGS_FROM_PI_DISCONNECT")
        except Exception as e:
            print("[RETURN SETTINGS ERROR]", e)

    def should_auto_show_pi_disconnect_popup(self) -> bool:
        """Return True when an automatic disconnect popup may be shown."""
        if getattr(self, "_pi_disconnect_popup_visible", False):
            try:
                existing = getattr(self, "connection_dialog", None)
                if existing is not None and existing.isVisible():
                    return False
                self._pi_disconnect_popup_visible = False
            except Exception:
                self._pi_disconnect_popup_visible = False

        # Suppress only when Settings is visible/active. If SAS is minimized,
        # still show the disconnect warning popup.
        if self.is_settings_tab_active() and not self.is_sas_minimized_or_background():
            return False

        return True



    def is_sas_minimized_or_background(self) -> bool:
        """Return True when SAS is minimized/background.

        Settings-tab popup suppression only applies when the user is actually
        viewing Settings and typing. If SAS is minimized, the user still needs
        the disconnect warning popup.
        """
        try:
            if self.isMinimized():
                return True
        except Exception:
            pass
        try:
            if getattr(self, "_minimized_by_sas", False):
                return True
        except Exception:
            pass
        try:
            if not self.isVisible():
                return True
        except Exception:
            pass
        return False

    def should_suppress_auto_pi_disconnect_popup(self, origin: str = "") -> bool:
        """Suppress automatic Pi disconnect popups while user is editing Settings.

        If SAS is visible and user is in Settings, suppress auto popups so
        hostname/IP typing is not interrupted. If SAS is minimized/background,
        allow the disconnect popup even if the last active tab was Settings.
        """
        try:
            manual_origins = ("manual-connect", "settings-connect")
            if (
                self.is_settings_tab_active()
                and not self.is_sas_minimized_or_background()
                and origin not in manual_origins
            ):
                return True
        except Exception:
            pass
        return False


    def can_show_pi_disconnect_popup_now(self, source: str = "auto") -> bool:
        """Prevent duplicate Pi disconnect popups from overlapping startup/retry paths."""
        try:
            existing = getattr(self, "connection_dialog", None)
            if existing is not None and existing.isVisible():
                return False
        except Exception:
            pass

        try:
            now = time.monotonic()
            last = float(getattr(self, "_pi_disconnect_popup_last_shown_at", 0.0) or 0.0)
            if now - last < 2.5:
                return False
            self._pi_disconnect_popup_last_shown_at = now
        except Exception:
            pass

        return True

    def show_pi_disconnect_alert_if_needed(self, reason: str = "", *, force: bool = False, origin: str = "auto"):
        """Show Pi disconnect popup only when it should not block Settings typing."""
        if self.should_suppress_auto_pi_disconnect_popup(origin) and not force:
            return False

        if force or self.should_auto_show_pi_disconnect_popup():
            if not force and not self.can_show_pi_disconnect_popup_now(origin):
                return False
            self._pi_disconnect_popup_user_closed = False
            self.show_pi_disconnected_popup(reason or self._pi_disconnect_reason)
            return True

        return False

        if force or self.should_auto_show_pi_disconnect_popup():
            self._pi_disconnect_popup_user_closed = False
            self.show_pi_disconnected_popup(reason or self._pi_disconnect_reason)
            return True

        return False

        if force or self.should_auto_show_pi_disconnect_popup():
            self._pi_disconnect_popup_user_closed = False
            self.show_pi_disconnected_popup(reason or self._pi_disconnect_reason)
            return True

        return False

        if force or self.should_auto_show_pi_disconnect_popup():
            self._pi_disconnect_popup_user_closed = False
            self.show_pi_disconnected_popup(reason or self._pi_disconnect_reason)
            return True

        return False

    def suspend_locking_for_pi_disconnect(self, reason: str = ""):
        """Suspend inactivity auto-lock while Raspberry Pi is disconnected."""
        self._pi_disconnect_lock_suspended = True
        self._pi_disconnect_reason = reason or "Raspberry Pi disconnected."
        self._pending_auto_lock = False
        try:
            self.mark_user_activity(reset_countdown=True)
        except Exception:
            pass
        try:
            self.append_system_log(f"PI_DISCONNECTED_AUTO_LOCK_SUSPENDED: {self._pi_disconnect_reason}")
        except Exception:
            pass

    def resume_locking_after_pi_reconnect(self):
        """Resume normal inactivity locking after Pi reconnects."""
        was_suspended = getattr(self, "_pi_disconnect_lock_suspended", False)
        self._pi_disconnect_lock_suspended = False
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._pi_disconnect_reason = ""
        self._pi_disconnect_popup_visible = False
        self._pi_disconnect_popup_user_closed = False
        try:
            self.mark_user_activity(reset_countdown=True)
        except Exception:
            pass
        if was_suspended:
            try:
                self.append_system_log("PI_RECONNECTED_AUTO_LOCK_RESUMED")
            except Exception:
                pass

    def should_suspend_inactivity_lock(self) -> bool:
        """Automatic inactivity lock must not run when Pi is disconnected."""
        if getattr(self, "first_launch_setup_mode", False):
            return True
        if getattr(self, "_pi_disconnect_lock_suspended", False):
            return True
        if not getattr(self, "pi_connected", True):
            return True
        return False

    def start_pi_disconnect_retry_loop(self, reason: str = ""):
        """Keep retrying Pi connection until it is restored."""
        self.suspend_locking_for_pi_disconnect(reason)
        if getattr(self, "_pi_disconnect_retry_active", False):
            return
        self._pi_disconnect_retry_active = True
        QTimer.singleShot(5000, self.retry_pi_connection_until_restored)

    def retry_pi_connection_until_restored(self):
        """Retry Pi /status while disconnected and re-show warning if needed."""
        if not getattr(self, "_pi_disconnect_retry_active", False):
            return
        if getattr(self, "pi_connected", False):
            self.resume_locking_after_pi_reconnect()
            return
        if getattr(self, "_pi_disconnect_retry_running", False):
            QTimer.singleShot(3000, self.retry_pi_connection_until_restored)
            return

        host = str(getattr(self, "pi_api_host", "") or "").strip()
        if not host and hasattr(self, "pi_host_input"):
            host = self.pi_host_input.text().strip()

        if not host:
            reason = "Pi hostname/IP is not configured."
            self.suspend_locking_for_pi_disconnect(reason)
            self.show_pi_disconnect_alert_if_needed(reason, origin="retry")
            QTimer.singleShot(5000, self.retry_pi_connection_until_restored)
            return

        self._pi_disconnect_retry_running = True
        try:
            self._face_api_test_connection(
                show_disconnect_popup=False,
                show_progress=False,
                origin="pi-retry",
            )
        except Exception:
            self._pi_disconnect_retry_running = False

        QTimer.singleShot(3500, self.finish_pi_disconnect_retry_cycle)

    def finish_pi_disconnect_retry_cycle(self):
        self._pi_disconnect_retry_running = False
        if getattr(self, "pi_connected", False):
            self.resume_locking_after_pi_reconnect()
            try:
                self.minimize_to_taskbar_if_safe("Pi reconnected")
            except Exception:
                pass
            return

        reason = getattr(self, "_pi_disconnect_reason", "") or "Raspberry Pi disconnected. Please check Pi power/network."
        self.suspend_locking_for_pi_disconnect(reason)
        self.show_pi_disconnect_alert_if_needed(reason, origin="retry")
        QTimer.singleShot(5000, self.retry_pi_connection_until_restored)

    def keep_pi_disconnected_warning_active(self, reason: str = ""):
        """Keep retry loop alive and show popup only when appropriate."""
        self.suspend_locking_for_pi_disconnect(reason)
        self.show_pi_disconnect_alert_if_needed(reason, origin="auto")
        self.start_pi_disconnect_retry_loop(reason)

    def ensure_taskbar_window_identity(self):
        """Force the main SAS window to remain a normal Windows taskbar window."""
        try:
            current_flags = self.windowFlags()
            fixed_flags = current_flags | Qt.WindowType.Window
            fixed_flags = fixed_flags & ~Qt.WindowType.Tool
            fixed_flags = fixed_flags & ~Qt.WindowType.Dialog
            fixed_flags = fixed_flags & ~Qt.WindowType.SplashScreen

            if fixed_flags != current_flags:
                was_visible = self.isVisible()
                was_minimized = self.isMinimized()
                self.setWindowFlags(fixed_flags)
                if was_visible:
                    if was_minimized:
                        self.showMinimized()
                    else:
                        self.show()
            self.setWindowTitle("Secure Access System")
        except Exception as e:
            print("[TASKBAR IDENTITY ERROR]", e)

    def restore_main_window_for_attention(self, reason: str = ""):
        """Show/maximize SAS only when the main window is not already visible.

        This avoids repeatedly maximizing/stealing focus when SAS is already
        open. For Pi disconnect warnings, the popup can be prepared quietly and
        the window is brought forward only when the user chooses Return to
        Settings.
        """
        try:
            self.ensure_taskbar_window_identity()
            self._minimized_by_sas = False

            already_visible = self.isVisible() and not self.isMinimized()
            already_maximized = self.isMaximized()

            if not already_visible:
                self.showMaximized()
                self.raise_()
                self.activateWindow()
                if reason:
                    self.append_system_log(f"WINDOW_RESTORED: {reason}")
                return

            if not already_maximized:
                self.showMaximized()
                self.raise_()
                self.activateWindow()
                if reason:
                    self.append_system_log(f"WINDOW_MAXIMIZED: {reason}")
                return

            # Already maximized: do not maximize/activate again.
        except Exception as e:
            print("[WINDOW RESTORE ERROR]", e)


    def minimize_once_after_startup(self, reason: str = "startup"):
        """v207: Startup/background minimize must happen only once.

        After the user manually restores/maximizes SAS, later Pi status checks,
        retry success, or Settings Connect actions must not minimize it again.
        """
        if getattr(self, "_startup_minimize_done", False):
            return
        if getattr(self, "first_launch_setup_mode", False):
            return
        if not getattr(self, "server_configured", False):
            return
        self._startup_minimize_done = True
        self._minimized_by_sas = True
        try:
            self.ensure_taskbar_window_identity()
        except Exception:
            pass
        try:
            self.showMinimized()
            if reason:
                self.append_system_log(f"WINDOW_MINIMIZED_TO_TASKBAR_ONCE: {reason}")
        except Exception as e:
            print("[STARTUP MINIMIZE ONCE ERROR]", e)

    def minimize_to_taskbar_if_safe(self, reason: str = ""):
        """Minimize SAS to the Windows taskbar only when the system is healthy."""
        try:
            self.ensure_taskbar_window_identity()
            if not getattr(self, "_auto_minimize_enabled", True):
                return
            if getattr(self, "first_launch_setup_mode", False):
                return
            if getattr(self, "is_locked", False):
                return
            if not getattr(self, "server_configured", False):
                return
            if not getattr(self, "pi_connected", False):
                return
            self._minimized_by_sas = True
            self.ensure_taskbar_window_identity()
            self.showMinimized()
            if reason:
                self.append_system_log(f"WINDOW_MINIMIZED_TO_TASKBAR: {reason}")
        except Exception as e:
            print("[WINDOW MINIMIZE ERROR]", e)

    def startup_background_mode_check(self):
        """Startup background mode.

        v208 requirement:
        - If configuration is complete, minimize SAS at startup immediately.
        - Do not wait for Raspberry Pi connection result before minimizing.
        - If Pi is disconnected, the retry/disconnect popup logic will handle it
          separately without changing this startup minimize decision.
        - First launch or missing configuration stays visible.
        """
        if getattr(self, "_startup_background_check_done", False):
            return

        self._startup_background_check_done = True

        if getattr(self, "first_launch_setup_mode", False) or not getattr(self, "server_configured", False):
            self.restore_main_window_for_attention("first launch setup required")
            return

        # Configuration exists, so run in background immediately.
        QTimer.singleShot(500, lambda: self.minimize_once_after_startup("startup configuration complete"))

        # Pi check/retry can continue in background, but it must not control
        # whether startup minimize happens.
        if str(getattr(self, "pi_api_host", "") or "").strip():
            self._startup_background_check_pending = True
            self._face_api_test_connection(
                show_disconnect_popup=True,
                show_progress=False,
                origin="startup",
            )

    def handle_startup_background_check_result(self, connected: bool, error_text: str = ""):
        """Pi result after startup check.

        v208: startup minimize is based on configuration only and already
        happened in startup_background_mode_check(). This method only clears the
        pending flag and logs failure; it must not minimize/restore the window.
        """
        if not getattr(self, "_startup_background_check_pending", False):
            return

        self._startup_background_check_pending = False

        if not connected and error_text:
            self.append_system_log(f"STARTUP_PI_CONNECTION_FAILED: {error_text}")

    def minimize_after_face_unlock(self):
        """After recognition_result.json unlocks SAS, return the app to background."""
        self.minimize_to_taskbar_if_safe("face recognised and workstation unlocked")

    def install_idle_activity_tracker(self):
        """Install a lightweight activity tracker for inactivity locking.

        Windows screen-saver logic is based on mouse/keyboard inactivity. On
        Windows we read the OS last-input timestamp; this event filter is a
        fallback and also lets SAS reset the logical timer after actions such as
        face unlock or manual unlock.
        """
        if getattr(self, "_idle_event_filter_installed", False):
            return
        try:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._idle_event_filter_installed = True
        except Exception as e:
            print("[IDLE TRACKER ERROR]", e)

    def eventFilter(self, obj, event):
        try:
            if event is not None and obj is getattr(self, "sas_check_received_btn", None) and event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.LayoutRequest,
            ):
                QTimer.singleShot(0, self._position_sas_received_badge)
        except Exception:
            pass
        try:
            if event is not None and event.type() in (
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.KeyPress,
                QEvent.Type.KeyRelease,
                QEvent.Type.Wheel,
                QEvent.Type.TouchBegin,
                QEvent.Type.TouchUpdate,
            ):
                self.mark_user_activity(reset_countdown=True)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def mark_user_activity(self, reset_countdown: bool = True):
        """Record local activity and optionally refill the visible countdown."""
        self._last_user_activity_ts = time.monotonic()
        if not reset_countdown:
            return
        if getattr(self, "is_locked", False) or getattr(self, "first_launch_setup_mode", False):
            return
        if getattr(self, "_pending_auto_lock", False):
            self._pending_auto_lock = False
        self.total_seconds = max(1, int(getattr(self, "lock_timeout_seconds", DEFAULT_LOCK_TIMEOUT_SECONDS)))
        self.time_left = self.total_seconds
        if hasattr(self, "ring"):
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)
        if hasattr(self, "countdown_label"):
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
        if getattr(self, "face_detected", False):
            self.set_face_detected(False)

    def get_windows_system_idle_seconds(self) -> float | None:
        """Return seconds since the last keyboard/mouse input reported by Windows."""
        if platform.system().lower() != "windows":
            return None
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            last_input_info = LASTINPUTINFO()
            last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
                return None
            tick_count = ctypes.windll.kernel32.GetTickCount64()
            idle_ms = int(tick_count) - int(last_input_info.dwTime)
            return max(0.0, idle_ms / 1000.0)
        except Exception:
            return None

    def get_effective_idle_seconds(self) -> float:
        """Return inactivity seconds using Windows OS input plus SAS logical resets."""
        now = time.monotonic()
        system_idle = self.get_windows_system_idle_seconds()
        if system_idle is None:
            return max(0.0, now - getattr(self, "_last_user_activity_ts", now))

        system_last_input_ts = now - max(0.0, system_idle)
        logical_last_input_ts = getattr(self, "_last_user_activity_ts", system_last_input_ts)
        effective_last_input_ts = max(system_last_input_ts, logical_last_input_ts)
        return max(0.0, now - effective_last_input_ts)

    def refresh_emergency_recovery_state(self):
        """Keep emergency unlock alive after Windows lock screen/resume.

        This periodically re-applies runtime controls and refreshes the hotkey
        registration while the app is locked. It prevents the app from staying
        permanently locked when Windows secure desktop breaks the keyboard hook.
        """
        try:
            if getattr(self, "enable_hotkey", True):
                self.runtime_lock_service.start_emergency_hotkey_watchdog(self)

            if getattr(self, "is_locked", False):
                self.runtime_lock_service.refresh_emergency_hotkey_if_needed(self)
        except Exception as e:
            print("[EMERGENCY RECOVERY ERROR]", e)

    def closeEvent_legacy_unused(self, event):
        """Always release keyboard/mouse hooks when the app closes."""
        try:
            self.stop_camera_preview()
        except Exception:
            pass
        try:
            self.runtime_lock_service.shutdown(self)
        except Exception:
            pass
        super().closeEvent(event)


    # --------------------------------------------------------
    # Window - keep this responsive size
    # --------------------------------------------------------
    def build_window(self):
        self.setWindowTitle("Secure Access System")
        self.ensure_taskbar_window_identity()
        screen = QApplication.primaryScreen().availableGeometry()
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


    # --------------------------------------------------------
    # Window chrome / app icon
    # --------------------------------------------------------
    def apply_app_icon(self):
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
    def content_max_width(self) -> int:
        """Responsive maximum content width for maximised startup."""
        w = max(1, self.width())

        if w >= 2200:
            return min(2600, int(w * 0.92))

        if w >= 1700:
            return min(1900, int(w * 0.90))

        if w >= 1300:
            return min(1500, int(w * 0.88))

        return 1220



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

        # Give the brand enough space so "SECURE ACCESS SYSTEM" never clips.
        side_width = 420 if not self.compact_mode else 320

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
        brand.setMinimumWidth(340 if not self.compact_mode else 265)
        brand.setObjectName("Brand")

        brand_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        brand_layout.addWidget(brand, alignment=Qt.AlignmentFlag.AlignVCenter)
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

    def has_restricted_tab_access(self) -> bool:
        """Return True only for an authenticated SAS Admin session.

        Unlocking the Windows desktop by face recognition or by the emergency
        hotkey is not an SAS Admin login.  Settings and Face Recognition stay
        protected until an Admin completes the normal login flow.
        """
        return bool(getattr(self, "is_admin", False))

    def require_admin_for_tab(self, tab_name: str) -> bool:
        """Return True when access is allowed.

        Face Recognition and Settings are restricted to Admin login.
        """
        restricted_tabs = {"Face Recognition", "Settings"}

        if tab_name not in restricted_tabs:
            return True

        if self.has_restricted_tab_access():
            return True

        self.pending_restricted_tab = tab_name

        # Keep user on current allowed page.
        if hasattr(self, "top_nav_buttons"):
            current_name = getattr(self, "current_top_tab", "Dashboard")
            for btn_name, btn in self.top_nav_buttons.items():
                btn.set_active(btn_name == current_name)
            if current_name in self.top_nav_buttons:
                self.animate_tab_indicator(current_name, animate=True)

        self.append_system_log(
            f"Restricted tab requested: {tab_name}. Admin login required."
        )

        # Non-admin user should switch account; guest should login.
        self.open_login_popup()
        return False

    def open_pending_restricted_tab_if_allowed(self):
        """After successful login, open the requested restricted tab only if allowed."""
        tab_name = getattr(self, "pending_restricted_tab", None)

        if not tab_name:
            return

        if self.has_restricted_tab_access():
            self.pending_restricted_tab = None
            self.qt_after(250, lambda: self.switch_top_tab(tab_name))
        else:
            self.append_system_log(
                f"Access denied for {tab_name}: Admin role required."
            )
            self.pending_restricted_tab = None

    def switch_top_tab(self, name: str):
        if not self.require_admin_for_tab(name):
            return

        # Face Recognition should only open after a successful Settings connection.
        # Do not reconnect here. If connection failed/not configured, guide user to Settings.
        if name == "Face Recognition" and not getattr(self, "pi_connected", False):
            reason = (
                "Pi connection is not available. Please set the hostname/IP and press Connect in Settings."
                if getattr(self, "pi_connection_checked", False)
                else "Please connect the Pi hostname/IP in Settings before using Face Recognition."
            )
            self.show_face_tab_pi_disconnect_popup(reason)
            return

        self.current_top_tab = name

        if name in {"Face Recognition", "Settings"}:
            actor = self.get_audit_actor()
            self.write_sas_log(f"RESTRICTED PAGE OPENED | USER={actor} | PAGE={name.upper()}")

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
            self._face_api_refresh_users()

            # Refresh camera panel state on entry.
            # If API is online but camera is stopped, show "Camera stopped".
            # If recognition is already running on Pi, show video feed.
            self.check_pi_camera_status_and_update_panel()
        elif name == "Settings":
            self.set_footer_mode("settings")
            if str(getattr(self, "pi_api_host", "") or "").strip():
                self.pull_pi_settings_to_sas(silent=True)
                self.refresh_pi_storage_from_pi(silent=True)
            else:
                self.set_pi_storage_unavailable("Connect to the Pi to view its storage.")
            self.refresh_admin_list_ui()
            self.stack.fade_to(self.settings_page)
        elif name == "Login":
            self.stack.fade_to(self.login_page)


    # --------------------------------------------------------
    # System locked desktop notification
    # --------------------------------------------------------
    def minimize_to_taskbar_for_lock(self, reason: str = "system locked"):
        """Keep SAS in the taskbar while Windows apps remain visible behind the lock state."""
        try:
            self.ensure_taskbar_window_identity()
            self._minimized_by_sas = True
            self.showMinimized()
            if reason:
                self.append_system_log(f"WINDOW_MINIMIZED_TO_TASKBAR: {reason}")
        except Exception as e:
            print("[LOCK MINIMIZE ERROR]", e)

    def show_system_locked_notification(self):
        """Show a small, no-focus, non-modal desktop notification for the locked state.

        Unlike the removed overlay, this does not blur, darken, restore, maximize,
        or activate the SAS dashboard.
        """
        if getattr(self, "_suppress_lock_notification", False):
            return

        existing = getattr(self, "system_locked_notification", None)
        if existing is not None and existing.isVisible():
            return

        # The lock notification has its own read-only subscription to the Pi
        # MJPEG endpoint.  It remains visible after SAS minimizes and never
        # sends camera-control commands.
        feed_url = ""
        try:
            base_url = str(getattr(self, "pi_api_base", "") or "").rstrip("/")
            if base_url:
                feed_url = f"{base_url}/video-feed"
        except Exception:
            feed_url = ""

        notification = SystemLockedNotification(
            compact_mode=self.compact_mode,
            video_feed_url=feed_url,
        )
        self.system_locked_notification = notification
        notification.show_at_bottom_right()

    def hide_system_locked_notification(self):
        """Remove the desktop lock notification after face/manual/emergency unlock."""
        notification = getattr(self, "system_locked_notification", None)
        if notification is None:
            return
        try:
            notification.dismiss()
        except Exception:
            try:
                notification.hide()
                notification.deleteLater()
            except Exception:
                pass
        self.system_locked_notification = None

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
        if root is None:
            return

        # Build the popup first.  If its UI construction ever fails, do not
        # leave the dashboard blurred without a visible dialog.
        try:
            dialog = LoginPopupDialog(self, self.compact_mode)
        except Exception as exc:
            self.append_system_log(f"LOGIN_POPUP_ERROR: {exc}")
            print(f"[LOGIN POPUP ERROR] {exc}")
            return

        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(0)
        root.setGraphicsEffect(blur)

        # Smooth background blur.
        self._blur_anim = QPropertyAnimation(blur, b"blurRadius", self)
        self._blur_anim.setDuration(220)
        self._blur_anim.setStartValue(0)
        self._blur_anim.setEndValue(5)
        self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._blur_anim.start()

        # Centre popup relative to the main window.
        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        dialog.finished.connect(lambda _: self.clear_blur_effect(root))
        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

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
            display_user = self.current_user.upper()
            role = self.current_user_role
            if display_user == "ADMIN":
                self.account_menu_user.setText("ADMIN")
            else:
                self.account_menu_user.setText(f"{display_user} • {role}")
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
        self.clear_session_credentials_on_logout()
        """Complete logout flow and return to Dashboard page."""
        old_user = self.current_user.upper() if self.current_user else "Unknown"

        self.hide_account_menu()

        self.is_logged_in = False
        self.current_user = None
        self.clear_session_credentials_on_logout()
        self.current_user_role = "Guest"
        self.is_admin = False
        self.pending_restricted_tab = None

        self.update_account_ui()

        # After logout, always navigate back to Dashboard.
        self.switch_top_tab("Dashboard")

        # After logout, stay on the normal unlocked dashboard.
        # Auto-lock will only occur later through inactivity countdown.
        self.is_locked = False
        self._pending_auto_lock = False
        self.mark_user_activity(reset_countdown=True)
        self.apply_lock_state()

        self.set_face_detected(False)
        self.write_sas_log(f"LOGOUT | USER={old_user}")
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
        # Website-style centred page content. On maximised screens, keep moderate side spacing.
        main.setMaximumWidth(self.content_max_width())
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(main)
        mx = 24 if not self.compact_mode else 16
        mt = 12 if not self.compact_mode else 8
        mb = 6 if not self.compact_mode else 4
        sp = 12 if not self.compact_mode else 8

        main_layout.setContentsMargins(mx, mt, mx, mb)
        main_layout.setSpacing(sp)
        main_layout.addWidget(self.build_time_section())
        main_layout.addWidget(self.build_unified_dashboard_card(), 1, Qt.AlignmentFlag.AlignHCenter)
        # No large bottom stretch; the card height is calculated to use the space above the footer.
        main_layout.addStretch(0)

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
        main.setMaximumWidth(self.content_max_width())
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(main)
        mx = 28 if not self.compact_mode else 18
        # Match the provided Face Recognition console composition:
        # compact top gap, left control/directory column and large right camera/log area.
        mt = 8 if not self.compact_mode else 5
        mb = 8 if not self.compact_mode else 5
        main_layout.setContentsMargins(mx, mt, mx, mb)
        main_layout.setSpacing(0)

        console = QHBoxLayout()
        console.setSpacing(24 if not self.compact_mode else 16)
        console.setContentsMargins(0, 0, 0, 0)

        # Left column, similar to the HTML reference:
        # [ Control Panel ]
        # [ Authorized Personnel / Users ]
        left_column = QVBoxLayout()
        left_column.setSpacing(16 if not self.compact_mode else 12)
        left_column.setContentsMargins(0, 0, 0, 0)

        # Right column, similar to the HTML reference:
        # [ Large camera console ]
        # [ Activity terminal / System Log ]
        right_column = QVBoxLayout()
        right_column.setSpacing(16 if not self.compact_mode else 12)
        right_column.setContentsMargins(0, 0, 0, 0)

        controls = self.face_controls_card()
        users = self.face_users_card()
        camera = self.camera_feed_card()
        logs = self.system_log_card()

        self.face_cards = [camera, controls, logs, users]
        self.update_face_card_sizes()

        left_column.addWidget(controls, 0)
        left_column.addWidget(users, 1)
        right_column.addWidget(camera, 1)
        right_column.addWidget(logs, 0)

        console.addLayout(left_column, 3)
        console.addLayout(right_column, 9)
        main_layout.addLayout(console, 1)

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
        # Settings has many form controls, so keep it slightly narrower than
        # the dashboard/face pages and give it wider side padding. This prevents
        # the cards/inputs from looking over-stretched on wide monitors.
        settings_max_width = min(self.content_max_width(), 1420 if not self.compact_mode else 1180)
        main.setMaximumWidth(settings_max_width)
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(main)
        layout.setContentsMargins(
            58 if not self.compact_mode else 28,
            28 if not self.compact_mode else 18,
            58 if not self.compact_mode else 28,
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
        self.settings_save_connect_btn = save
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

        grid.addWidget(self.pi_connectivity_card(), 0, 0)
        grid.addWidget(self.auto_capture_card(), 0, 1)
        grid.addWidget(self.server_credentials_card(), 1, 0)
        grid.addWidget(self.camera_rotation_card(), 1, 1)
        grid.addWidget(self.face_data_transfer_card(), 2, 0)
        grid.addWidget(self.security_options_card(), 2, 1)
        grid.addWidget(self.pi_storage_card(), 3, 0)
        grid.addWidget(self.admin_management_card(), 3, 1)

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
        icon.setFixedSize(48 if not self.compact_mode else 42, 48 if not self.compact_mode else 42)

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
        self.login_ntid_input.setPlaceholderText("e.g. 1234567")
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

        self.login_status_label = QLabel("First valid login becomes Admin if no admin has been registered yet.")
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

        # Settings text fields only: make typed/displayed text thinner.
        # Buttons keep their original bold style.
        font = field.font()
        font.setWeight(QFont.Weight.Normal)
        field.setFont(font)

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
        self.settings_ntid_input = self.settings_input("", "Enter NTID", readonly=False)
        ntid_box.addWidget(self.settings_ntid_input)

        pass_box = QVBoxLayout()
        pass_box.addWidget(self.settings_label("Password"))
        self.settings_password_input = self.settings_input("", password=True)
        pass_box.addWidget(self.settings_password_input)

        two_col.addLayout(ntid_box, 0, 0)
        two_col.addLayout(pass_box, 0, 1)
        layout.addLayout(two_col)

        # Domain is fixed internally and is not shown to users.

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.settings_server_path_input = self.settings_input("", "Select or enter shared server path")
        browse = self.settings_button("Browse")
        browse.clicked.connect(self.browse_server_path)
        path_row.addWidget(self.settings_server_path_input, 1)
        path_row.addWidget(browse)
        layout.addWidget(self.settings_label("Server Path"))
        layout.addLayout(path_row)

        self.clear_sensitive_server_credentials_ui(clear_server_path=False)

        return card

    def set_pi_status_label(self, connected: bool = False, checking: bool = False, message: str = ""):
        """Keep Settings > Pi Connectivity status aligned with actual Pi connection state."""
        if not hasattr(self, "pi_status_label"):
            return

        if checking:
            text = message or "Status: Checking..."
            obj = "SettingsDisconnected"
        elif connected:
            text = message or "Status: Connected"
            obj = "SettingsConnected"
        else:
            text = message or "Status: Disconnected"
            obj = "SettingsDisconnected"

        self.pi_status_label.setText("●  " + text)
        self.pi_status_label.setObjectName(obj)
        self.pi_status_label.style().unpolish(self.pi_status_label)
        self.pi_status_label.style().polish(self.pi_status_label)
        self.pi_status_label.update()


    def pi_connectivity_card(self):
        card, layout = self.settings_card_base("Pi Connectivity", "⌁")

        host_row = QHBoxLayout()
        host_row.setSpacing(8)

        # Port is fixed to 5000 for safety. User only enters hostname/IP.
        self.pi_host_input = self.settings_input(self.pi_api_host, "e.g. 192.168.1.50")
        self.pi_host_input.textEdited.connect(lambda _: (setattr(self, "pi_connected", False), setattr(self, "pi_connection_checked", False), self.clear_all_authorized_users_ui()))
        self.pi_api_port = "5000"

        connect = self.settings_button("Connect", primary=True)
        connect.clicked.connect(
            lambda checked=False: self._face_api_test_connection(
                show_disconnect_popup=True,
                show_progress=True,
                origin="settings",
            )
        )

        host_row.addWidget(self.pi_host_input, 1)
        host_row.addWidget(connect)

        layout.addWidget(self.settings_label("Pi Hostname / IP"))
        layout.addLayout(host_row)

        # API port is fixed internally and is not shown to users.

        initial_status = "●  Status: Connected" if getattr(self, "pi_connected", False) else "●  Status: Disconnected"
        self.pi_status_label = QLabel(initial_status)
        self.pi_status_label.setObjectName("SettingsConnected" if getattr(self, "pi_connected", False) else "SettingsDisconnected")
        layout.addWidget(self.pi_status_label)

        # Keep the label object for internal compatibility, but do not show the
        # connected Pi identity summary line in the Settings UI.
        self.pi_identity_label = QLabel("")
        self.pi_identity_label.setObjectName("SettingsHint")
        self.pi_identity_label.setWordWrap(True)
        self.pi_identity_label.setVisible(False)

        return card

    def face_data_transfer_card(self):
        card, layout = self.settings_card_base("Face Data Transfer", "◎")

        # Main import/export panel. Export and Import popups now contain
        # separate Server Path and SFTP/Local tabs.
        server_panel = QFrame()
        server_panel.setObjectName("SettingsInnerPanel")
        server_layout = QVBoxLayout(server_panel)
        server_layout.setContentsMargins(16, 14, 16, 14)
        server_layout.setSpacing(10)

        server_title = QLabel("Import and Export Data")
        server_title.setObjectName("SettingsMiniTitle")
        server_desc = QLabel("Export or import dataset and encoding packages through Server Path, SFTP download, or local ZIP import.")
        server_desc.setObjectName("SettingsMiniDesc")
        server_desc.setWordWrap(True)

        server_actions = QHBoxLayout()
        export_btn = self.settings_button("⇧  Export")
        import_btn = self.settings_button("⇩  Import")
        export_btn.clicked.connect(self._face_api_export_data)
        import_btn.clicked.connect(self._face_api_import_data)
        server_actions.addWidget(export_btn)
        server_actions.addWidget(import_btn)

        server_layout.addWidget(server_title)
        server_layout.addWidget(server_desc)
        server_layout.addLayout(server_actions)
        layout.addWidget(server_panel)

        # SFTP node-to-node tools stay here only. Transfer to Windows is now
        # located inside Export -> Local Path.
        sftp_panel = QFrame()
        sftp_panel.setObjectName("SettingsInnerPanel")
        sftp_layout = QVBoxLayout(sftp_panel)
        sftp_layout.setContentsMargins(16, 14, 16, 14)
        sftp_layout.setSpacing(10)

        title = QLabel("Transfer Face Data via SFTP")
        title.setObjectName("SettingsMiniTitle")
        desc = QLabel("Securely send dataset packages to another Pi and review received packages.")
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)

        actions = QHBoxLayout()
        send = self.settings_button("Send to Another Pi", primary=True)
        check = self.settings_button("Check Received")
        self.sas_check_received_btn = check
        check_badge = QLabel("", check)
        check_badge.setObjectName("ReceivedBadge")
        check_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check_badge.setFixedSize(24, 24)
        check_badge.hide()
        self.sas_received_badge_label = check_badge
        self._sas_received_badge_count = 0
        try:
            check.installEventFilter(self)
        except Exception:
            pass
        send.clicked.connect(self._face_api_sftp_send)
        check.clicked.connect(self._face_api_check_received)
        actions.addWidget(send)
        actions.addWidget(check)

        sftp_layout.addWidget(title)
        sftp_layout.addWidget(desc)
        sftp_layout.addLayout(actions)
        layout.addWidget(sftp_panel)

        return card

    def create_timeout_input(self, value: str = "0", max_value: int = 59):
        """Create a numeric timeout field.

        Minutes and seconds are restricted to 0-59 so users cannot enter values
        like 100 seconds or 100 minutes.
        """
        inp = self.settings_input(value, "0")
        inp.setValidator(QIntValidator(0, max_value, inp))
        inp.setFixedWidth(90 if not self.compact_mode else 70)
        inp.setToolTip(f"Allowed range: 0-{max_value}")
        inp.editingFinished.connect(lambda field=inp, max_v=max_value: self.normalize_timeout_input(field, max_v))
        return inp

    def normalize_timeout_input(self, field, max_value: int = 59):
        """Clamp empty/out-of-range timeout values for a friendlier UI."""
        try:
            raw = field.text().strip()
            value = int(raw) if raw else 0
        except Exception:
            value = 0

        value = max(0, min(value, max_value))
        field.setText(str(value))

    def security_options_card(self):
        card, layout = self.settings_card_base("Security Options", "◈")

        self.security_option_buttons = {}

        for key, text, default in [
            ("disable_keyboard", "Disable Keyboard When Locked", True),
            ("disable_mouse", "Disable Mouse When Locked", True),
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
        for col, (key, label, value, max_value) in enumerate([
            ("hours", "Hours", "0", 23),
            ("minutes", "Minutes", "5", 59),
            ("seconds", "Seconds", "0", 59),
        ]):
            box = QVBoxLayout()
            inp = self.create_timeout_input(value, max_value)
            self.timeout_inputs[key] = inp
            cap = QLabel(f"{label} (0-{max_value})" if key in ("minutes", "seconds") else label)
            cap.setObjectName("SettingsLabel")
            box.addWidget(inp)
            box.addWidget(cap)
            time_grid.addLayout(box, 0, col)

        layout.addLayout(time_grid)
        layout.addStretch()
        return card

    def auto_capture_card(self):
        card, layout = self.settings_card_base("Auto-Capture", "▣")

        desc = QLabel(
            "Auto-captures up to 10 photos when one face is detected."
        )
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.auto_capture_toggle = AutoCaptureSegment(self, self.compact_mode)
        self.auto_capture_toggle.on_state_changed = self.on_auto_capture_toggle_changed  # type: ignore[assignment]
        layout.addWidget(self.auto_capture_toggle)

        layout.addStretch()
        return card

    # --------------------------------------------------------
    # Pi storage monitoring
    # --------------------------------------------------------
    @staticmethod
    def format_storage_bytes(value) -> str:
        """Format an API byte count for the SAS Settings display."""
        try:
            amount = max(0, int(value))
        except Exception:
            amount = 0

        units = ("B", "KB", "MB", "GB", "TB")
        number = float(amount)
        unit = units[0]
        for unit in units:
            if number < 1024.0 or unit == units[-1]:
                break
            number /= 1024.0
        return f"{int(number)} {unit}" if unit == "B" else f"{number:.1f} {unit}"

    def pi_storage_card(self):
        """Show current SD-card/root-filesystem usage read from the Pi API."""
        card, layout = self.settings_card_base("Pi Storage", "▤")

        desc = QLabel(
            "Live Raspberry Pi SD-card storage. Dataset photos, encodings, logs and face-data packages share this space."
        )
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.pi_storage_summary_label = QLabel("Storage information has not been loaded.")
        self.pi_storage_summary_label.setObjectName("SettingsMiniTitle")
        self.pi_storage_summary_label.setWordWrap(True)
        layout.addWidget(self.pi_storage_summary_label)

        self.pi_storage_progress = QProgressBar()
        self.pi_storage_progress.setObjectName("PiStorageProgressBar")
        self.pi_storage_progress.setRange(0, 1000)
        self.pi_storage_progress.setValue(0)
        self.pi_storage_progress.setTextVisible(False)
        self.pi_storage_progress.setMinimumHeight(14 if not self.compact_mode else 12)
        layout.addWidget(self.pi_storage_progress)

        self.pi_storage_detail_label = QLabel("Connect to the Pi to view its storage.")
        self.pi_storage_detail_label.setObjectName("SettingsHint")
        self.pi_storage_detail_label.setWordWrap(True)
        layout.addWidget(self.pi_storage_detail_label)

        footer = QHBoxLayout()
        self.pi_storage_status_label = QLabel("●  Waiting for Pi connection")
        self.pi_storage_status_label.setObjectName("SettingsHint")
        self.pi_storage_status_label.setWordWrap(True)
        refresh = self.settings_button("↻  Refresh")
        refresh.clicked.connect(lambda checked=False: self.refresh_pi_storage_from_pi(silent=False))
        self.pi_storage_refresh_button = refresh
        footer.addWidget(self.pi_storage_status_label, 1)
        footer.addWidget(refresh, 0)
        layout.addLayout(footer)

        self.set_pi_storage_unavailable("Connect to the Pi to view its storage.")

        # Poll only while Settings is being viewed. A manual refresh is always
        # available, and an immediate refresh is performed after successful Pi
        # connection or opening the Settings tab.
        if not hasattr(self, "pi_storage_poll_timer"):
            self.pi_storage_poll_timer = QTimer(self)
            self.pi_storage_poll_timer.setInterval(30000)
            self.pi_storage_poll_timer.timeout.connect(lambda: self.refresh_pi_storage_from_pi(silent=True))
            self.pi_storage_poll_timer.start()

        layout.addStretch()
        return card

    def set_pi_storage_unavailable(self, message: str = "Storage information unavailable."):
        """Show a safe non-fatal state when Pi storage cannot be fetched."""
        summary = getattr(self, "pi_storage_summary_label", None)
        detail = getattr(self, "pi_storage_detail_label", None)
        status = getattr(self, "pi_storage_status_label", None)
        progress = getattr(self, "pi_storage_progress", None)
        refresh = getattr(self, "pi_storage_refresh_button", None)

        if summary is not None:
            summary.setText("Storage information unavailable")
        if detail is not None:
            detail.setText(str(message or "Storage information unavailable."))
            detail.setObjectName("SettingsHint")
            detail.style().unpolish(detail)
            detail.style().polish(detail)
        if status is not None:
            status.setText("●  Storage not loaded")
            status.setObjectName("SettingsHint")
            status.style().unpolish(status)
            status.style().polish(status)
        if progress is not None:
            progress.setValue(0)
            progress.setStyleSheet(
                "QProgressBar { background: #E3EAF4; border: 1px solid #D9E2EC; border-radius: 7px; }"
                "QProgressBar::chunk { background: #0B72FF; border-radius: 6px; }"
            )
        if refresh is not None and not getattr(self, "_pi_storage_poll_in_progress", False):
            refresh.setEnabled(True)

    def update_pi_storage_ui(self, snapshot: dict, message: str | None = None, ok: bool = True):
        """Render one /system/storage snapshot in the SAS Settings card."""
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        try:
            used_percent = max(0.0, min(100.0, float(snapshot.get("used_percent", 0.0))))
        except Exception:
            used_percent = 0.0

        total_human = str(snapshot.get("total_human") or self.format_storage_bytes(snapshot.get("total_bytes", 0)))
        used_human = str(snapshot.get("used_human") or self.format_storage_bytes(snapshot.get("used_bytes", 0)))
        available_human = str(snapshot.get("available_human") or self.format_storage_bytes(snapshot.get("available_bytes", 0)))
        mount_point = str(snapshot.get("mount_point") or "/")
        updated_at = str(snapshot.get("updated_at") or "")

        if used_percent >= 90.0:
            color = "#DC2626"
            state_label = "Storage critical"
            detail_object = "SettingsDisconnected"
        elif used_percent >= 80.0:
            color = "#EA580C"
            state_label = "Storage warning"
            detail_object = "SettingsHint"
        else:
            color = "#0B72FF"
            state_label = "Storage healthy"
            detail_object = "SettingsHint"

        summary = getattr(self, "pi_storage_summary_label", None)
        detail = getattr(self, "pi_storage_detail_label", None)
        status = getattr(self, "pi_storage_status_label", None)
        progress = getattr(self, "pi_storage_progress", None)
        refresh = getattr(self, "pi_storage_refresh_button", None)

        if summary is not None:
            summary.setText(f"{used_human} used of {total_human}")
        if detail is not None:
            detail.setText(
                f"{available_human} available  •  {used_percent:.1f}% used  •  Root filesystem: {mount_point}"
            )
            detail.setObjectName(detail_object)
            detail.style().unpolish(detail)
            detail.style().polish(detail)
        if progress is not None:
            progress.setValue(int(round(used_percent * 10)))
            progress.setStyleSheet(
                "QProgressBar { background: #E3EAF4; border: 1px solid #D9E2EC; border-radius: 7px; }"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 6px; }}"
            )
        if status is not None:
            status_text = message or f"●  {state_label}"
            if updated_at:
                status_text += f"  •  Updated: {updated_at}"
            status.setText(status_text)
            status.setObjectName("SettingsConnected" if ok else "SettingsDisconnected")
            status.style().unpolish(status)
            status.style().polish(status)
        if refresh is not None:
            refresh.setEnabled(True)

    def refresh_pi_storage_from_pi(self, silent: bool = True):
        """Fetch current Pi storage in a background thread, never blocking SAS UI."""
        if str(getattr(self, "current_top_tab", "") or "").lower() != "settings" and silent:
            return
        if not bool(getattr(self, "pi_connected", False)):
            self.set_pi_storage_unavailable("Connect to the Pi to view its storage.")
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.set_pi_storage_unavailable("Pi hostname/IP is not configured.")
            return
        if getattr(self, "_pi_storage_poll_in_progress", False):
            return

        self._pi_storage_poll_in_progress = True
        refresh = getattr(self, "pi_storage_refresh_button", None)
        status = getattr(self, "pi_storage_status_label", None)
        if refresh is not None:
            refresh.setEnabled(False)
        if status is not None:
            status.setText("●  Refreshing Pi storage...")
            status.setObjectName("SettingsHint")
            status.style().unpolish(status)
            status.style().polish(status)

        def worker():
            try:
                data = self._face_api_request("GET", "/system/storage", timeout=8)
                if not isinstance(data, dict) or not bool(data.get("ok", True)):
                    raise RuntimeError(str(data.get("message", "Invalid Pi storage response.")) if isinstance(data, dict) else "Invalid Pi storage response.")

                def done():
                    self._pi_storage_poll_in_progress = False
                    self._pi_storage_last_snapshot = data
                    self.update_pi_storage_ui(data, ok=True)
                    if not silent:
                        self.append_system_log(
                            f"PI_STORAGE_REFRESHED: USED={data.get('used_human', '-')} | "
                            f"AVAILABLE={data.get('available_human', '-')} | "
                            f"PERCENT={data.get('used_percent', '-')}"
                        )

                self.qt_after(0, done)
            except Exception as exc:
                error = str(exc)

                def failed():
                    self._pi_storage_poll_in_progress = False
                    self.set_pi_storage_unavailable(f"Could not load Pi storage: {error}")
                    if not silent:
                        self.append_system_log(f"PI_STORAGE_REFRESH_FAILED: {error}")

                self.qt_after(0, failed)

        Thread(target=worker, daemon=True, name="PiStoragePoll").start()

    # --------------------------------------------------------
    # Pi camera orientation
    # --------------------------------------------------------
    @staticmethod
    def normalize_camera_rotation(value, default: int = 0) -> int:
        """Normalize a Pi camera rotation to 0/90/180/270 degrees clockwise."""
        try:
            rotation = int(str(value).strip())
        except Exception:
            rotation = int(default)
        rotation %= 360
        return rotation if rotation in (0, 90, 180, 270) else int(default)

    @staticmethod
    def camera_rotation_label(value) -> str:
        rotation = SecureAccessDashboard.normalize_camera_rotation(value)
        return {
            0: "0° (Normal)",
            90: "90° Clockwise",
            180: "180°",
            270: "270° Clockwise",
        }[rotation]

    def camera_rotation_card(self):
        """Create the SAS control that persists camera orientation on the Pi."""
        card, layout = self.settings_card_base("Camera Orientation", "↻")

        desc = QLabel(
            "Correct the image when the Pi camera is mounted sideways or upside down. "
            "The setting is saved on the Pi, so the Pi preview and SAS live camera panel match."
        )
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.camera_rotation_buttons = {}

        for rotation, text in ((0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")):
            button = self.settings_button(text, primary=False)
            button.setCheckable(True)
            button.setMinimumWidth(54 if not self.compact_mode else 46)
            button.clicked.connect(
                lambda _checked=False, degrees=rotation: self.set_camera_rotation_from_ui(degrees)
            )
            row.addWidget(button)
            self.camera_rotation_buttons[rotation] = button

        row.addStretch()
        layout.addLayout(row)

        self.camera_rotation_status_label = QLabel("●  Pi setting: not loaded")
        self.camera_rotation_status_label.setObjectName("SettingsHint")
        self.camera_rotation_status_label.setWordWrap(True)
        layout.addWidget(self.camera_rotation_status_label)

        self.update_camera_rotation_ui(self.camera_rotation, status="●  Pi setting: not loaded", ok=False)

        # While Settings is active, poll the Pi every few seconds. This allows a
        # rotation chosen directly on the Pi screen to appear in SAS without a
        # reconnect or a page reload.
        if not hasattr(self, "camera_rotation_poll_timer"):
            self.camera_rotation_poll_timer = QTimer(self)
            self.camera_rotation_poll_timer.setInterval(3500)
            self.camera_rotation_poll_timer.timeout.connect(self.poll_camera_rotation_from_pi)
            self.camera_rotation_poll_timer.start()

        layout.addStretch()
        return card

    def poll_camera_rotation_from_pi(self):
        """Refresh Pi rotation silently while the SAS Settings page is visible."""
        if str(getattr(self, "current_top_tab", "") or "").lower() != "settings":
            return
        if not bool(getattr(self, "pi_connected", False)):
            return
        if getattr(self, "_camera_rotation_poll_in_progress", False):
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return

        self._camera_rotation_poll_in_progress = True

        def worker():
            try:
                data = self._face_api_request("GET", "/settings", timeout=8)
                nested = data.get("settings", {}) if isinstance(data, dict) else {}
                if not isinstance(nested, dict):
                    nested = {}
                rotation = data.get("camera_rotation", nested.get("camera_rotation")) if isinstance(data, dict) else None

                def done():
                    self._camera_rotation_poll_in_progress = False
                    if rotation is not None and not getattr(self, "_camera_rotation_sync_in_progress", False):
                        self.update_camera_rotation_ui(
                            rotation,
                            status=f"●  Pi setting: {self.camera_rotation_label(rotation)}",
                            ok=True,
                        )

                self.qt_after(0, done)
            except Exception:
                self.qt_after(0, lambda: setattr(self, "_camera_rotation_poll_in_progress", False))

        Thread(target=worker, daemon=True, name="PiCameraRotationPoll").start()

    def update_camera_rotation_ui(self, rotation, status: str | None = None, ok: bool = True):
        """Reflect the Pi rotation value in the Settings page without changing it."""
        degrees = self.normalize_camera_rotation(rotation, default=getattr(self, "camera_rotation", 0))
        self.camera_rotation = degrees

        for value, button in getattr(self, "camera_rotation_buttons", {}).items():
            selected = value == degrees
            button.setChecked(selected)
            button.setObjectName("SettingsPrimaryButton" if selected else "SettingsSecondaryButton")
            try:
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
            except Exception:
                pass

        label = getattr(self, "camera_rotation_status_label", None)
        if label is not None:
            label.setText(status or f"●  Pi setting: {self.camera_rotation_label(degrees)}")
            label.setObjectName("SettingsConnected" if ok else "SettingsHint")
            try:
                label.style().unpolish(label)
                label.style().polish(label)
                label.update()
            except Exception:
                pass

    def set_camera_rotation_from_ui(self, rotation):
        """Save the selected rotation directly to Pi settings.json via /settings."""
        requested = self.normalize_camera_rotation(rotation, default=self.camera_rotation)
        previous = self.camera_rotation

        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.update_camera_rotation_ui(
                previous,
                status="●  Pi sync: Hostname/IP is not configured",
                ok=False,
            )
            self.append_system_log("CAMERA_ROTATION_SYNC_FAILED: Pi hostname/IP is not configured.")
            return

        if getattr(self, "_camera_rotation_sync_in_progress", False):
            return

        self._camera_rotation_sync_in_progress = True
        self.update_camera_rotation_ui(requested, status="●  Pi sync: Applying camera rotation...", ok=False)

        def worker():
            try:
                data = self._face_api_request(
                    "POST",
                    "/settings",
                    {
                        "camera_rotation": requested,
                        "source": "Windows SAS",
                    },
                    timeout=15,
                )

                nested = data.get("settings", {}) if isinstance(data, dict) else {}
                applied = self.normalize_camera_rotation(
                    data.get("camera_rotation", nested.get("camera_rotation", requested))
                    if isinstance(data, dict) else requested,
                    default=requested,
                )
                message = data.get("message", "Pi camera orientation saved.") if isinstance(data, dict) else "Pi camera orientation saved."

                def done():
                    self._camera_rotation_sync_in_progress = False
                    self.update_camera_rotation_ui(
                        applied,
                        status=f"●  Pi synced: {self.camera_rotation_label(applied)}",
                        ok=True,
                    )
                    actor = self.get_audit_actor()
                    self.write_sas_log(
                        f"CAMERA ROTATION CHANGED | ACTOR={actor} | ROTATION={applied} | TARGET=PI | METHOD=SETTINGS"
                    )
                    self.append_system_log(f"CAMERA_ROTATION_SYNCED: {self.camera_rotation_label(applied)} | {message}")

                self.qt_after(0, done)
            except Exception as exc:
                error = str(exc)

                def failed():
                    self._camera_rotation_sync_in_progress = False
                    self.update_camera_rotation_ui(
                        previous,
                        status="●  Pi sync: Failed",
                        ok=False,
                    )
                    self.append_system_log(f"CAMERA_ROTATION_SYNC_FAILED: {error}")

                self.qt_after(0, failed)

        Thread(target=worker, daemon=True, name="PiCameraRotationSync").start()


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

        # Keep the Admin Management card stable.
        # If more than 5 admins are added, the list scrolls instead of making the box/card taller.
        self.admin_list_scroll = QScrollArea()
        self.admin_list_scroll.setObjectName("AdminListScroll")
        self.admin_list_scroll.setWidgetResizable(True)
        self.admin_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.admin_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.admin_list_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.admin_list_scroll.setFixedHeight((40 * 5) + 2 if not self.compact_mode else (36 * 5) + 2)
        self.admin_list_scroll.setWidget(admin_box)

        # Visible thin scrollbar, same style as the Face Recognition System Log.
        self.admin_list_scroll.setStyleSheet(self.admin_list_scroll.styleSheet() + """
            QScrollBar:vertical {
                width: 7px;
                background: transparent;
                margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.22);
                border-radius: 3px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        layout.addWidget(self.admin_list_scroll)
        QTimer.singleShot(0, self.refresh_admin_list_ui)
        layout.addStretch()
        return card

    def admin_row(self, ntid: str, tag: str = "", removable: bool = False):
        row = QFrame()
        row.setObjectName("AdminRow")
        row_h = 36 if self.compact_mode else 40
        row.setMinimumHeight(row_h)
        row.setMaximumHeight(row_h)
        row.setFixedHeight(row_h)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
            remove.clicked.connect(lambda _=False, admin_ntid=ntid: self.remove_admin_from_ui(admin_ntid))
            layout.addWidget(remove)

        return row

    # --------------------------------------------------------
    # Dashboard page parts
    # --------------------------------------------------------
    def build_time_section(self):
        section = QWidget()
        self.time_section = section
        section.setObjectName("TimeSection")
        section.setFixedHeight(190 if not self.compact_mode else 130)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(8 if not self.compact_mode else 5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.time_label = QLabel("08:16:23")
        self.time_label.setObjectName("TerminalTime")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.date_label = QLabel("THURSDAY, OCTOBER 24, 2024")
        self.date_label.setObjectName("TerminalDate")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)
        return section

    def build_unified_dashboard_card(self):
        """Unified one-card dashboard using the provided locked/unlocked concept."""
        card = QFrame()
        card.setObjectName("StatusCard")
        self.status_card_widget = card
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.setMinimumHeight(430 if not self.compact_mode else 360)
        card.setMaximumHeight(720 if not self.compact_mode else 560)
        card.setMinimumWidth(980 if not self.compact_mode else 820)
        card.setMaximumWidth(2200 if not self.compact_mode else 1500)

        self.status_watermark = QLabel("🔓", card)
        self.status_watermark.setObjectName("FadeLockBgWhite")
        self.status_watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_watermark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_watermark.lower()

        def move_watermark(event):
            size = 320 if not self.compact_mode else 230
            self.status_watermark.setFixedSize(size, size)
            self.status_watermark.move(card.width() - size + 26, -28)

            # Keep the Authorized Users action as a compact floating icon at
            # the bottom-left of the green/red status card. It stays outside
            # the main centered status composition, so it does not change the
            # timer/title alignment or existing animations.
            auth_btn = getattr(self, "dashboard_authorized_users_btn", None)
            if auth_btn is not None:
                btn_size = 48 if not self.compact_mode else 40
                pad = 34 if not self.compact_mode else 24
                auth_btn.setFixedSize(btn_size, btn_size)
                auth_btn.move(pad, max(pad, card.height() - btn_size - pad))
                auth_btn.raise_()

            QFrame.resizeEvent(card, event)

        card.resizeEvent = move_watermark

        root = QVBoxLayout(card)
        root.setContentsMargins(44 if not self.compact_mode else 30, 24 if not self.compact_mode else 18,
                                44 if not self.compact_mode else 30, 24 if not self.compact_mode else 18)
        root.setSpacing(10 if not self.compact_mode else 7)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Protocol Status label removed from the Dashboard card per latest UI
        # direction. Keep the attribute for compatibility with older resize
        # styling code, but do not add it to the card layout.
        self.dashboard_protocol_label = QLabel("")
        self.dashboard_protocol_label.setObjectName("CardEyebrowWhite")
        self.dashboard_protocol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dashboard_protocol_label.setVisible(False)

        self.status_title = QLabel("SYSTEM UNLOCKED")
        self.status_title.setObjectName("UnlockedTitleWhite")
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Hidden compatibility widgets used by apply_lock_state().
        self.status_lock_icon = QLabel("🔓")
        self.status_lock_icon.setObjectName("WhiteLockIcon")
        self.status_lock_icon.setVisible(False)

        self.status_pill = QLabel("●  UNLOCKED")
        self.status_pill.setObjectName("UnlockedPillGreen")
        self.status_pill.setVisible(False)

        self.circle_flip_container = QWidget()
        self.circle_flip_container.setObjectName("CircleFlipContainer")
        circle_size = 210 if not self.compact_mode else 150
        self.circle_flip_container.setFixedSize(circle_size, circle_size)

        self.circle_stack = QStackedWidget(self.circle_flip_container)
        self.circle_stack.setObjectName("CircleStack")
        self.circle_stack.setGeometry(0, 0, circle_size, circle_size)
        self.circle_stack.setFixedSize(circle_size, circle_size)

        self.timer_circle_front = self.build_timer_circle_front(circle_size)
        self.face_circle_back = self.build_face_circle_back(circle_size)
        self.circle_stack.addWidget(self.timer_circle_front)
        self.circle_stack.addWidget(self.face_circle_back)

        self.circle_flip_overlay = FlipCircleLabel(self.circle_flip_container)
        self.circle_flip_overlay.setGeometry(0, 0, circle_size, circle_size)
        self.circle_flip_overlay.hide()

        self.countdown_title_label = QLabel("AUTO-LOCK SEQUENCE")
        self.countdown_title_label.setObjectName("CountdownTitle")
        self.countdown_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_title_label.setVisible(False)

        self.face_state_label = QLabel("Active session expires soon")
        self.face_state_label.setObjectName("CountdownDesc")
        self.face_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        actions = QHBoxLayout()
        actions.setSpacing(18 if not self.compact_mode else 12)
        actions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.manual_lock_btn = QPushButton("MANUAL LOCK")
        self.manual_lock_btn.setObjectName("ManualLockButtonWhite")
        self.manual_lock_btn.setFixedHeight(50 if not self.compact_mode else 42)
        self.manual_lock_btn.setMinimumWidth(170 if not self.compact_mode else 140)
        self.manual_lock_btn.setMaximumWidth(220 if not self.compact_mode else 180)
        self.manual_lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_lock_btn.clicked.connect(self.toggle_lock_state)

        self.dashboard_authorized_users_btn = QPushButton("👥", card)
        self.dashboard_authorized_users_btn.setObjectName("AuthorizedUsersDashboardIconButton")
        self.dashboard_authorized_users_btn.setToolTip("Authorized Users")
        self.dashboard_authorized_users_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dashboard_authorized_users_btn.clicked.connect(self.open_authorized_users_popup)

        actions.addWidget(self.manual_lock_btn)

        root.addStretch(1)
        root.addWidget(self.status_title)
        root.addSpacing(2)
        root.addWidget(self.circle_flip_container, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.face_state_label)
        root.addSpacing(6)
        root.addLayout(actions)
        root.addStretch(1)

        # Old Dashboard authorised users card is removed, but the popup uses cache.
        self.dashboard_users_box = None
        self.dashboard_users_status = None
        self.dashboard_cards = [card]

        self.apply_lock_state()
        return card


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
        if getattr(self, "first_launch_setup_mode", False):
            self.face_action_feedback("SETUP_REQUIRED: Configure server credentials before locking.")
            self.show_settings_message(
                "Setup Required",
                "Please login as Admin and configure Server Credentials first.",
                success=False,
                issues=[("MISSING CONFIGURATION", "Server credentials are not configured yet.")],
                server_path=self.server_path,
            )
            return

        if self.is_locked:
            unlock_user = self.current_user or "MANUAL"
            self._grant_access(unlock_user)
            self.write_sas_log(f"UNLOCKED | USER={str(unlock_user).upper()} | METHOD=MANUAL | CONFIDENCE=N/A")
        else:
            self._do_logout()

    def apply_lock_state(self):
        """Update unified dashboard card colour and status based on locked/unlocked state."""
        if not hasattr(self, "status_card_widget"):
            return

        radius = 48 if not self.compact_mode else 34

        if self.is_locked:
            self.status_card_widget.setStyleSheet(
                f"""
                QFrame#StatusCard {{
                    background-color: #DC143C;
                    border: none;
                    border-radius: {radius}px;
                }}
                """
            )
            self.status_title.setText("SYSTEM LOCKED")
            self.status_lock_icon.setText("🔒")
            self.status_watermark.setText("▣")
            self.status_pill.setText("●  LOCKED")
            self.status_pill.setObjectName("LockedPillRed")
            self.manual_lock_btn.setText("UNLOCK")
            self.manual_lock_btn.setProperty("lockState", "locked")
        else:
            self.status_card_widget.setStyleSheet(
                f"""
                QFrame#StatusCard {{
                    background-color: #10B981;
                    border: none;
                    border-radius: {radius}px;
                }}
                """
            )
            self.status_title.setText("SYSTEM UNLOCKED")
            self.status_lock_icon.setText("🔓")
            self.status_watermark.setText("▢")
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
            getattr(self, "dashboard_authorized_users_btn", None),
        ):
            if not isinstance(widget, QWidget):
                continue
            try:
                style = widget.style()
                style.unpolish(widget)
                style.polish(widget)
                widget.update()
            except Exception:
                pass

        self.status_card_widget.update()
        self.runtime_lock_service.apply_lock_controls(self)

        if self.is_locked:
            # Keep the dashboard minimized. The desktop stays visible and a
            # no-focus notification provides the locked-state message.
            self.minimize_to_taskbar_for_lock("system locked")
            QTimer.singleShot(120, self.show_system_locked_notification)
        else:
            self.hide_system_locked_notification()

    def countdown_card(self):
        card = GlassCard()
        self.countdown_card_widget = card
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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
        front.setStyleSheet("background: transparent; border: none;")

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

        self.face_detected_icon = QLabel("☻")
        self.face_detected_icon.setObjectName("FaceDetectedIcon")
        self.face_detected_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_detected_circle_text = QLabel("FACE DETECTED")
        self.face_detected_circle_text.setObjectName("FaceDetectedCircleText")
        self.face_detected_circle_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Slightly move the face icon and text upward for better visual balance.
        layout.addStretch(2)
        layout.addWidget(self.face_detected_icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.face_detected_circle_text, 0, Qt.AlignmentFlag.AlignCenter)
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
        self.dashboard_users_status = QLabel("STATUS     Connect Pi")
        self.dashboard_users_status.setObjectName("UsersStatus")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.dashboard_users_status)
        layout.addLayout(header)

        users_divider = QFrame()
        users_divider.setObjectName("UsersDivider")
        users_divider.setFixedHeight(1)
        layout.addWidget(users_divider)

        self.dashboard_users_box = QVBoxLayout()
        self.dashboard_users_box.setSpacing(18 if not self.compact_mode else 10)
        layout.addLayout(self.dashboard_users_box)
        layout.addStretch()

        view_all = QPushButton("VIEW ALL")
        view_all.setObjectName("ManageAccessButton")
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.setFixedHeight(42 if not self.compact_mode else 34)
        view_all.clicked.connect(self.open_authorized_users_popup)
        layout.addWidget(view_all)

        self.render_dashboard_users([])
        return card

    def clear_layout_widgets(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout_widgets(child_layout)

    def clear_all_authorized_users_ui(self):
        """Clear cached authorised users when Pi is offline/disconnected."""
        self.face_users_cache = []

        if hasattr(self, "dashboard_users_box"):
            self.render_dashboard_users([])

        if hasattr(self, "face_users_layout"):
            self.render_face_users([])


    def render_dashboard_users(self, users):
        """Render authorised users on Dashboard card.

        Show only the amount that can fit in the dashboard box.
        The full list is available through View All.
        """
        self.face_users_cache = users or []

        if not hasattr(self, "dashboard_users_box") or self.dashboard_users_box is None:
            self.face_users_cache = users or []
            return

        self.clear_layout_widgets(self.dashboard_users_box)

        if not users:
            status_label = getattr(self, "dashboard_users_status", None)
            if isinstance(status_label, QLabel):
                status_label.setText("STATUS     Connect Pi")

            hint = QLabel("Please connect Pi hostname/IP to fetch authorised users.")
            hint.setObjectName("UserDetail")
            hint.setWordWrap(True)
            self.dashboard_users_box.addWidget(hint)
            return

        active_count = len(users)
        status_label = getattr(self, "dashboard_users_status", None)
        if isinstance(status_label, QLabel):
            status_label.setText(f"STATUS     {active_count} active")

        # Show as many as the card can comfortably fit.
        # Normal desktop card fits around 6 rows; compact laptop layout fits fewer.
        max_visible = 6 if not self.compact_mode else 4

        for user in users[:max_visible]:
            uid = str(user.get("id", "")).upper()
            photos = int(user.get("photos", 0) or 0)
            trained = bool(user.get("trained", False))
            self.dashboard_users_box.addWidget(self.user_row(uid, f"{photos} Photos", trained))

        remaining = active_count - max_visible
        if remaining > 0:
            more = QLabel(f"+ {remaining} more users. Click View All.")
            more.setObjectName("UserDetail")
            self.dashboard_users_box.addWidget(more)


    def open_authorized_users_popup(self):
        """Show full authorised users list with search.

        Important: this should only open because the user clicked View All.
        It must not re-open later from a background refresh.
        """
        users = getattr(self, "face_users_cache", [])

        if not getattr(self, "pi_connected", False):
            self.show_authorized_users_dialog([], connected=False)
            return

        self.show_authorized_users_dialog(users, connected=True)


    def show_authorized_users_dialog(self, users, connected=True):
        """Stable Authorized Users popup.

        Shows up to 6 rows in the visible area. If more than 6 users exist,
        the list scrolls inside the popup instead of enlarging the popup.
        """
        dialog = QDialog(self)
        dialog.setObjectName("AuthorizedUsersDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(650 if not self.compact_mode else 560, 640 if not self.compact_mode else 570)
        dialog.setWindowOpacity(0.0)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("AuthorizedUsersCard")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 58))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(34 if not self.compact_mode else 26, 26 if not self.compact_mode else 22, 34 if not self.compact_mode else 26, 24 if not self.compact_mode else 20)
        root.setSpacing(14 if not self.compact_mode else 12)

        top = QHBoxLayout()
        top_left = QVBoxLayout()
        top_left.setSpacing(6)

        eyebrow = QLabel("▣  SYSTEM REGISTRY")
        eyebrow.setObjectName("AuthorizedUsersEyebrow")
        title = QLabel("Authorized Users")
        title.setObjectName("AuthorizedUsersTitle")

        top_left.addWidget(eyebrow)
        top_left.addWidget(title)

        count = QLabel(f"{len(users)} RECORDS" if connected else "DISCONNECTED")
        count.setObjectName("AuthorizedUsersCount")
        count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        close_top = QPushButton("×")
        close_top.setObjectName("AuthorizedRoundCloseButton")
        close_top.setCursor(Qt.CursorShape.PointingHandCursor)
        close_top.setFixedSize(44 if not self.compact_mode else 38, 44 if not self.compact_mode else 38)
        close_top.clicked.connect(dialog.accept)

        right_top = QVBoxLayout()
        right_top.setSpacing(12)
        right_top.addWidget(count, alignment=Qt.AlignmentFlag.AlignRight)
        right_top.addWidget(close_top, alignment=Qt.AlignmentFlag.AlignRight)

        top.addLayout(top_left, 1)
        top.addLayout(right_top)
        root.addLayout(top)

        search_box = QFrame()
        search_box.setObjectName("AuthorizedSearchBox")
        search_box.setFixedHeight(52 if not self.compact_mode else 46)
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(14, 0, 12, 0)
        search_layout.setSpacing(10)

        search_icon = QLabel("⌕")
        search_icon.setObjectName("AuthorizedSearchIcon")

        search = QLineEdit()
        search.setObjectName("AuthorizedSearchInput")
        search.setPlaceholderText("Search NTID...")
        search.setClearButtonEnabled(True)

        search_layout.addWidget(search_icon)
        search_layout.addWidget(search, 1)

        root.addWidget(search_box)

        scroll = QScrollArea()
        scroll.setObjectName("AuthorizedUsersScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.make_scrollbar_invisible(scroll)

        row_h = 64 if not self.compact_mode else 56
        max_visible_rows = 6
        scroll.setFixedHeight((row_h * max_visible_rows) + 22)

        body = QWidget()
        body.setObjectName("AuthorizedUsersBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 8, 0, 8)
        body_layout.setSpacing(0)
        scroll.setWidget(body)

        root.addWidget(scroll)

        def clear_rows():
            while body_layout.count():
                item = body_layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                child_layout = item.layout()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                elif child_layout is not None:
                    self.clear_layout_widgets(child_layout)

        def popup_row(user, display_no: int):
            uid = str(user.get("id", "")).upper()
            photos = int(user.get("photos", 0) or 0)
            trained = bool(user.get("trained", False))

            row = QFrame()
            row.setObjectName("AuthorizedPopupRow")
            row.setMinimumHeight(row_h)
            row.setMaximumHeight(row_h)

            lay = QHBoxLayout(row)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.setSpacing(12)

            avatar = QLabel(str(display_no))
            avatar.setObjectName("AuthorizedUserAvatar")
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFixedSize(38 if not self.compact_mode else 34, 38 if not self.compact_mode else 34)

            text = QVBoxLayout()
            text.setSpacing(4)

            name = QLabel(uid)
            name.setObjectName("AuthorizedPopupName")

            detail = QLabel(f"{photos} Capture frames stored")
            detail.setObjectName("AuthorizedPopupDetail")

            text.addWidget(name)
            text.addWidget(detail)

            if trained:
                badge = QLabel("TRAINED  <span style='color:#10B981;'>●</span>")
                badge.setObjectName("AuthorizedPopupTrainedBadge")
            else:
                badge = QLabel("PENDING")
                badge.setObjectName("AuthorizedPopupPendingBadge")

            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setMinimumWidth(78 if not self.compact_mode else 66)
            badge.setMaximumWidth(92 if not self.compact_mode else 78)

            lay.addWidget(avatar)
            lay.addLayout(text, 1)
            lay.addWidget(badge)

            return row

        def render_list():
            clear_rows()
            keyword = search.text().strip().lower()

            if not connected:
                count.setText("DISCONNECTED")
                msg = QLabel("Please connect Pi hostname/IP first to fetch authorised users.")
                msg.setObjectName("AuthorizedPopupEmpty")
                msg.setWordWrap(True)
                body_layout.addWidget(msg)
                body_layout.addStretch()
                return

            filtered = [
                u for u in users
                if keyword in str(u.get("id", "")).lower()
            ] if keyword else list(users)

            if keyword:
                count.setText(f"{len(filtered)} / {len(users)} MATCHED")
            else:
                count.setText(f"{len(users)} RECORDS")

            if not filtered:
                msg = QLabel("No matching user found.")
                msg.setObjectName("AuthorizedPopupEmpty")
                body_layout.addWidget(msg)
            else:
                for index, user in enumerate(filtered, start=1):
                    body_layout.addWidget(popup_row(user, index))

            body_layout.addStretch()
            body.updateGeometry()
            scroll.viewport().update()
            QTimer.singleShot(0, lambda: scroll.verticalScrollBar().setValue(0))

        search.textChanged.connect(render_list)
        render_list()

        close_btn = QPushButton("CLOSE")
        close_btn.setObjectName("AuthorizedCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        popup_opacity_anim = QPropertyAnimation(dialog, b"windowOpacity", dialog)
        popup_opacity_anim.setDuration(150)
        popup_opacity_anim.setStartValue(0.0)
        popup_opacity_anim.setEndValue(1.0)
        popup_opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.pause_camera_for_modal()
        try:
            QTimer.singleShot(0, popup_opacity_anim.start)
            dialog.exec()
        finally:
            self.resume_camera_after_modal()


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
        card.setMinimumHeight(250 if not self.compact_mode else 215)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addStretch()

        self.camera_state_badge = QLabel("●  End")
        self.camera_state_badge.setObjectName("CameraStateEndBadge")
        self.camera_state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_state_badge.setFixedHeight(24 if not self.compact_mode else 22)
        self.camera_state_badge.setMinimumWidth(72 if not self.compact_mode else 64)

        top.addWidget(self.camera_state_badge)

        self.camera_preview_label = QLabel("Camera preview loading...")
        self.camera_preview_label.setObjectName("CameraPreviewLabel")
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setScaledContents(False)
        self.camera_preview_label.setMinimumHeight(170 if not self.compact_mode else 135)
        self.camera_preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        layout.addLayout(top)
        layout.addWidget(self.camera_preview_label, 1)

        QTimer.singleShot(300, self.check_pi_camera_status_and_update_panel)
        return card


    def check_pi_camera_status_and_update_panel(self):
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("PI_SKIPPED: Pi hostname/IP is not configured.")
            return

        """Check Pi /status before opening /video-feed.

        This prevents startup from showing a stale MJPEG frame when the Pi camera
        is already stopped.
        """
        # If Pi is connected, always verify /status instead of trusting old
        # _camera_user_stopped state from a previous disconnect.
        if getattr(self, "_camera_user_stopped", False) and not getattr(self, "pi_connected", False):
            self.show_camera_stopped_prompt("Camera stopped")
            return

        self.set_pi_status_label(checking=True)

        def worker():
            try:
                self._face_api_base_url()
                data = self._face_api_request("GET", "/status", timeout=8)

                rec = bool(data.get("recognition_running", False))
                cap = bool(data.get("capture_running", False))

                def done():
                    if str(locals().get("origin", locals().get("origin_safe", "")) or "") == "settings":
                        self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self.resume_locking_after_pi_reconnect()
                    self.set_face_capture_in_progress(cap)
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self._handling_pi_disconnect = False

                    # An explicit SAS Stop must remain stopped in the Windows UI.
                    # The Pi can need a short cleanup interval before /status changes,
                    # so do not re-open the preview just because one status response
                    # still reports an active camera mode.
                    if getattr(self, "_camera_user_stopped", False):
                        self.stop_camera_preview(show_prompt=True)
                    elif rec or cap:
                        self.stop_camera_preview()
                        QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))
                    else:
                        self.stop_camera_preview(show_prompt=True)
                        self.append_face_log("CAMERA_STATUS: Pi API online, camera is stopped.")

                    # Keep Dashboard and Face Recognition authorised users aligned.
                    self._face_api_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.stop_camera_preview(show_prompt=True)
                    self.append_face_log(f"CAMERA_STATUS_FAILED: {err}")
                    self.handle_pi_runtime_disconnect("Pi disconnected or unreachable. Please check Pi.")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()

    def set_camera_state_badge(self, live: bool = False, stopped: bool = False):
        if not hasattr(self, "camera_state_badge"):
            return

        if stopped:
            self.camera_state_badge.setText("●  Stop")
            self.camera_state_badge.setObjectName("CameraStateStopBadge")
        elif live:
            self.camera_state_badge.setText("●  Live")
            self.camera_state_badge.setObjectName("CameraStateLiveBadge")
        else:
            self.camera_state_badge.setText("●  End")
            self.camera_state_badge.setObjectName("CameraStateEndBadge")

        self.camera_state_badge.style().unpolish(self.camera_state_badge)
        self.camera_state_badge.style().polish(self.camera_state_badge)
        self.camera_state_badge.update()


    def show_camera_stopped_prompt(self, message: str = "Camera stopped"):
        """Blacken camera panel and prompt user after Stop is pressed.

        Important: clear the QLabel pixmap first. Otherwise the last video frame
        can remain painted until the second Stop click.
        """
        if not hasattr(self, "camera_preview_label"):
            return

        self.camera_preview_label.clear()
        self.camera_preview_label.setPixmap(QPixmap())
        self.camera_preview_label.setObjectName("CameraPreviewStoppedLabel")
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setText(
            f"{message}\n\nPress Recognize to start camera again."
        )

        self.camera_preview_label.style().unpolish(self.camera_preview_label)
        self.camera_preview_label.style().polish(self.camera_preview_label)
        self.camera_preview_label.repaint()
        self.camera_preview_label.update()

        self.set_camera_state_badge(stopped=True)
        QApplication.processEvents()


    def pause_camera_for_modal(self):
        """Temporarily pause camera repainting while a heavy popup animation is shown."""
        self._modal_open_count = getattr(self, "_modal_open_count", 0) + 1

        timer = getattr(self, "camera_timer", None)
        if timer is not None:
            self._camera_resume_after_modal = True
            try:
                timer.stop()
            except Exception:
                pass

    def resume_camera_after_modal(self):
        """Resume camera repainting after popup closes if it was active before."""
        self._modal_open_count = max(0, getattr(self, "_modal_open_count", 0) - 1)

        if self._modal_open_count > 0:
            return

        if getattr(self, "_camera_resume_after_modal", False):
            self._camera_resume_after_modal = False

            timer = getattr(self, "camera_timer", None)
            if (
                getattr(self, "camera_capture", None) is not None
                and timer is not None
                and not getattr(self, "_camera_user_stopped", False)
            ):
                try:
                    timer.start(66)
                except Exception:
                    pass

    def handle_camera_feed_unavailable(self, reason: str = "Pi camera feed unavailable."):
        """Camera feed failure is not always Pi disconnect.

        The Pi API can be online while /video-feed is unavailable or stopped.
        In that case, keep Pi connected and only show the camera-stopped prompt.
        Only mark Pi disconnected if /status also fails.
        """
        def worker():
            try:
                data = self._face_api_request("GET", "/status", timeout=5)
                rec = bool(data.get("recognition_running", False))
                cap = bool(data.get("capture_running", False))
                users = data.get("users", None)

                def api_online():
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self._handling_pi_disconnect = False

                    self._camera_preview_running = False
                    self.camera_capture = None
                    self.set_camera_state_badge(False)

                    if hasattr(self, "camera_preview_label"):
                        self.camera_preview_label.setPixmap(QPixmap())
                        if rec or cap:
                            self.camera_preview_label.setText("Camera feed unavailable.\nPi API is online. Please retry Recognize or check camera.")
                        else:
                            self.show_camera_stopped_prompt("Camera stopped")

                    self.append_face_log(f"CAMERA_FEED_UNAVAILABLE: {reason} | API online")

                    # Keep authorised users/dashboard consistent if /status only returns count.
                    try:
                        self._face_api_refresh_users()
                    except Exception:
                        pass

                self.qt_after(0, api_online)

            except Exception:
                self.qt_after(0, lambda: self.handle_pi_runtime_disconnect("Pi disconnected or unreachable. Please check Pi power/network."))

        Thread(target=worker, daemon=True).start()


    def handle_pi_runtime_disconnect(self, reason: str = "Pi disconnected. Please check Pi power/network and reconnect from Settings."):
        """Handle Pi shutdown / network loss without freezing the SAS UI."""
        if getattr(self, "_handling_pi_disconnect", False):
            return

        self._handling_pi_disconnect = True

        try:
            self.pi_connection_checked = True
            self.pi_connected = False
            self.set_face_controls_connection_enabled(False)
            self.set_pi_status_label(connected=False)
            self._camera_user_stopped = True

            # Stop preview state without doing blocking OpenCV work on the UI thread.
            self._camera_preview_running = False
            if hasattr(self, "camera_timer") and self.camera_timer is not None:
                try:
                    self.camera_timer.stop()
                except Exception:
                    pass
                self.camera_timer = None

            self.camera_capture = None

            if hasattr(self, "camera_preview_label"):
                self.camera_preview_label.setPixmap(QPixmap())
                self.camera_preview_label.setText("Pi disconnected.\nPlease check Pi power/network and reconnect from Settings.")

            self.set_camera_state_badge(False)
            self.clear_all_authorized_users_ui()
            self.append_face_log(f"PI_DISCONNECTED: {reason}")
            self.keep_pi_disconnected_warning_active(reason)

        finally:
            # Allow a future disconnect popup after user reconnects/fails again.
            self.qt_after(1200, lambda: setattr(self, "_handling_pi_disconnect", False))


    def render_camera_frame_from_worker(self, frame):
        """Render camera frame sent from background camera worker.

        This keeps OpenCV read() away from the Qt UI thread, preventing
        the whole SAS app from becoming Not Responding when Pi power/network drops.
        """
        if getattr(self, "_modal_open_count", 0) > 0:
            return

        if frame is None or not hasattr(self, "camera_preview_label"):
            return

        if cv2 is None:
            return

        cv2_mod = cv2

        try:
            frame = cv2_mod.cvtColor(frame, cv2_mod.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w

            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimg).scaled(
                self.camera_preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            self.camera_preview_label.setPixmap(pixmap)

            self.camera_frame_count += 1
            now = datetime.now()
            if self.camera_last_tick is not None:
                elapsed = (now - self.camera_last_tick).total_seconds()
                if elapsed >= 1.0:
                    self.camera_fps = int(self.camera_frame_count / elapsed)
                    self.camera_frame_count = 0
                    self.camera_last_tick = now

            self.set_camera_state_badge(True)

        except Exception as e:
            self.append_face_log(f"CAMERA_RENDER_FAILED: {e}")


    def start_camera_preview(self, force: bool = False):
        """Start camera preview from Raspberry Pi API /video-feed.

        v113:
        OpenCV VideoCapture/read is moved to a background thread.
        This prevents the whole SAS application from freezing if the Pi is
        powered off while recognition/video-feed is running.
        """
        if not hasattr(self, "camera_preview_label"):
            return

        if getattr(self, "_camera_user_stopped", False) and not force:
            self.show_camera_stopped_prompt("Camera stopped")
            return

        if cv2 is None:
            self.camera_preview_label.setText(
                "OpenCV is required for API video-feed preview.\n"
                "Install opencv-python on this Windows app."
            )
            self.set_camera_state_badge(False)
            return

        if getattr(self, "_camera_preview_running", False):
            return

        cv2_mod = cv2

        self._face_api_base_url()
        self.camera_feed_url = f"{self.pi_api_base}/video-feed"

        self.camera_preview_label.setObjectName("CameraPreviewLabel")
        self.camera_preview_label.style().unpolish(self.camera_preview_label)
        self.camera_preview_label.style().polish(self.camera_preview_label)
        self.camera_preview_label.setPixmap(QPixmap())
        self.camera_preview_label.setText("Connecting to Pi camera feed...")
        self.set_camera_state_badge(False)

        self._camera_preview_running = True
        self.camera_frame_count = 0
        self.camera_last_tick = datetime.now()

        def camera_worker(feed_url=self.camera_feed_url):
            cap = None
            fail_count = 0
            reconnect_count = 0
            first_frame_received = False

            def open_capture():
                new_cap = cv2_mod.VideoCapture(feed_url)

                # Best effort timeout settings. Some OpenCV builds ignore these,
                # but when supported they prevent long blocking during Pi shutdown.
                try:
                    new_cap.set(cv2_mod.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
                    new_cap.set(cv2_mod.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
                    new_cap.set(cv2_mod.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass

                return new_cap

            try:
                cap = open_capture()
                self.camera_capture = cap

                if not cap.isOpened():
                    # Do not instantly mark unavailable. Pi recognition may still be warming up.
                    time.sleep(0.6)
                    try:
                        cap.release()
                    except Exception:
                        pass

                    cap = open_capture()
                    self.camera_capture = cap

                    if not cap.isOpened():
                        self.qt_after(0, lambda: self.handle_camera_feed_unavailable(f"Unable to open Pi camera feed: {feed_url}"))
                        return

                self.qt_after(0, lambda: self.append_face_log("CAMERA_FEED: Connected to Pi /video-feed"))
                self.qt_after(0, lambda: self.set_camera_state_badge(True))

                while getattr(self, "_camera_preview_running", False):
                    ok, frame = cap.read()

                    if not ok or frame is None:
                        fail_count += 1

                        # Early frames can fail when Pi recognition is already running but
                        # Flask/OpenCV stream is still warming up. Retry longer before showing
                        # unavailable.
                        max_fail = 18 if not first_frame_received else 10

                        if fail_count >= max_fail:
                            reconnect_count += 1
                            fail_count = 0

                            try:
                                cap.release()
                            except Exception:
                                pass

                            time.sleep(0.35)

                            cap = open_capture()
                            self.camera_capture = cap

                            if cap.isOpened() and reconnect_count <= 3:
                                self.qt_after(0, lambda n=reconnect_count: self.append_face_log(f"CAMERA_FEED: Reconnected stream attempt {n}"))
                                continue

                            self.qt_after(0, lambda: self.handle_camera_feed_unavailable("Pi camera feed lost after retry."))
                            break

                        time.sleep(0.12)
                        continue

                    first_frame_received = True
                    fail_count = 0
                    reconnect_count = 0

                    # Copy because OpenCV reuses frame memory.
                    frame_copy = frame.copy()
                    self.qt_after(0, lambda f=frame_copy: self.render_camera_frame_from_worker(f))

                    # Limit UI updates; video preview does not need 30 FPS.
                    time.sleep(0.06)

            except Exception as e:
                err = str(e)
                self.qt_after(0, lambda err=err: self.handle_camera_feed_unavailable(f"Pi camera feed error: {err}"))

            finally:
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass

                self.camera_capture = None
                self._camera_preview_running = False

        Thread(target=camera_worker, daemon=True).start()



    def update_camera_frame(self):
        """Compatibility no-op.

        Camera frames are now read in a background worker thread to avoid UI
        freeze when Pi is powered off or network drops.
        """
        return


    def closeEvent(self, event):
        self._closing = True
        try:
            self.hide_system_locked_notification()
        except Exception:
            pass
        if hasattr(self, "camera_timer") and self.camera_timer is not None:
            self.camera_timer.stop()

        if hasattr(self, "camera_capture") and self.camera_capture is not None:
            self.camera_capture.release()
            self.camera_capture = None

        self.set_camera_state_badge(False)

        super().closeEvent(event)

    def face_controls_card(self):
        card = GlassCard()
        card.setMinimumHeight(185 if not self.compact_mode else 165)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            20 if not self.compact_mode else 14,
            16 if not self.compact_mode else 12,
            20 if not self.compact_mode else 14,
            14 if not self.compact_mode else 10,
        )
        layout.setSpacing(7)

        title = QLabel("PRIMARY CONTROLS")
        title.setObjectName("FaceSectionTitle")
        layout.addWidget(title)

        self.ntid_input = QLineEdit()
        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter valid NTID for capture / delete")
        self.ntid_input.setClearButtonEnabled(True)
        self.ntid_input.setFixedHeight(34 if not self.compact_mode else 30)
        self.ntid_input.textChanged.connect(self.clear_ntid_input_error)
        layout.addWidget(self.ntid_input)

        # Compact action area.
        # Row 1: Capture + Train
        # Row 2: Recognize full width
        # Row 3: Stop + Delete
        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(8)
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

        self.face_capture_btn = capture
        self.face_train_btn = train
        self.face_recognize_btn = recognize
        self.face_stop_btn = stop
        self.face_delete_btn = delete

        for btn in (capture, train, recognize, stop, delete):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        small_h = 32 if not self.compact_mode else 28
        main_h = 34 if not self.compact_mode else 30

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

        # Disabled until Pi API connection is confirmed.
        QTimer.singleShot(0, lambda: self.set_face_controls_connection_enabled(getattr(self, "pi_connected", False)))
        return card

    def system_log_card(self):
        card = GlassCard()
        card.setObjectName("SystemLogCard")
        card.setMinimumHeight(205 if not self.compact_mode else 185)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16 if not self.compact_mode else 12, 12 if not self.compact_mode else 10, 16 if not self.compact_mode else 12, 10 if not self.compact_mode else 8)
        layout.setSpacing(5)

        top = QHBoxLayout()
        title = QLabel("SYSTEM LOG")
        title.setObjectName("FaceSectionTitle")
        dot = QLabel("●")
        dot.setObjectName("GreenDot")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(dot)
        layout.addLayout(top)

        # Scrollable Face Recognition System Log.
        # This section should show action status, not dashboard/settings noise.
        self.system_log_scroll = QScrollArea()
        self.system_log_scroll.setObjectName("FaceSystemLogScroll")
        self.system_log_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.system_log_scroll.setWidgetResizable(True)
        self.system_log_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.system_log_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Keep the System Log scrollable and visible. Do not hide this scrollbar,
        # because operators need to review older log entries.
        self.system_log_scroll.setStyleSheet(self.system_log_scroll.styleSheet() + """
            QScrollBar:vertical {
                width: 7px;
                background: transparent;
                margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.22);
                border-radius: 3px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        log_body = QWidget()
        self.system_log_body = log_body
        log_body.setObjectName("FaceSystemLogBody")
        log_layout = QVBoxLayout(log_body)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(0)

        logs = QLabel(
            "&gt; FACE RECOGNITION SYSTEM LOG READY<br>"
            "&gt; WAITING FOR PI CONNECTION"
        )
        self.system_log_label = logs
        logs.setObjectName("LogText")
        logs.setWordWrap(True)
        logs.setTextFormat(Qt.TextFormat.RichText)
        logs.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        logs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        log_layout.addWidget(logs)
        # No bottom stretch here; the QLabel should define the scrollable height.

        self.system_log_scroll.setWidget(log_body)
        layout.addWidget(self.system_log_scroll, 1)
        return card

    def face_users_card(self):
        card = GlassCard()
        card.setMinimumHeight(0)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            16 if not self.compact_mode else 12,
            16 if not self.compact_mode else 12,
            16 if not self.compact_mode else 12,
            16 if not self.compact_mode else 12,
        )
        layout.setSpacing(8 if not self.compact_mode else 6)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AUTHORIZED USERS")
        title.setObjectName("UsersTitle")
        sub = QLabel("CONNECT PI FIRST")
        sub.setObjectName("UsersStatus")
        title_box.addWidget(title)
        title_box.addWidget(sub)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setObjectName("SmallIconButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setFixedSize(30 if not self.compact_mode else 26, 30 if not self.compact_mode else 26)
        refresh_btn.clicked.connect(self._face_api_refresh_users)

        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        # Search bar for large user lists.
        search_box = QFrame()
        search_box.setObjectName("FaceUserSearchBox")
        search_box.setFixedHeight(36 if not self.compact_mode else 32)
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 0, 10, 0)
        search_layout.setSpacing(8)

        search_icon = QLabel("⌕")
        search_icon.setObjectName("FaceUserSearchIcon")

        self.face_user_search_input = QLineEdit()
        self.face_user_search_input.setObjectName("FaceUserSearchInput")
        self.face_user_search_input.setPlaceholderText("Search NTID...")
        self.face_user_search_input.setClearButtonEnabled(True)
        self.face_user_search_input.textChanged.connect(lambda _: self.render_face_users(getattr(self, "face_users_cache", [])))

        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.face_user_search_input, 1)
        layout.addWidget(search_box)

        # Scrollable list. The card size stays fixed even for 100+ users.
        self.face_users_scroll = QScrollArea()
        self.face_users_scroll.setObjectName("FaceUsersScroll")
        self.face_users_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.face_users_scroll.setWidgetResizable(True)
        self.face_users_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.face_users_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.make_scrollbar_invisible(self.face_users_scroll)

        self.face_users_body = QWidget()
        self.face_users_body.setObjectName("FaceUsersBody")
        self.face_users_list_layout = QVBoxLayout(self.face_users_body)
        self.face_users_list_layout.setContentsMargins(0, 2, 0, 2)
        self.face_users_list_layout.setSpacing(10 if not self.compact_mode else 8)

        self.face_users_scroll.setWidget(self.face_users_body)
        layout.addWidget(self.face_users_scroll, 1)

        self.face_users_layout = layout
        self.face_users_subtitle = sub

        self.render_face_users(getattr(self, "face_users_cache", []))
        QTimer.singleShot(300, self._face_api_refresh_users)

        return card

    def face_user_row(self, user_id, frames, status, active=True):
        """Expandable authorised user card using the uploaded card UI concept.

        Click row to smoothly expand the card and reveal Capture/Delete actions.
        Expanding/collapsing does not write into System Log.
        """
        user_id = str(user_id or "").strip().upper()

        # Enough height for header + frames + two action buttons.
        # Keep compact mode slightly smaller but still not clipped.
        expanded_h = 166 if not self.compact_mode else 154
        collapsed_h = 84 if not self.compact_mode else 74

        card = QFrame()
        card.setObjectName("FaceUserExpandCard")
        card.setProperty("expanded", False)
        card.setMinimumHeight(collapsed_h)
        card.setMaximumHeight(collapsed_h)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout(card)
        root.setContentsMargins(14 if not self.compact_mode else 12, 12 if not self.compact_mode else 10, 14 if not self.compact_mode else 12, 14 if not self.compact_mode else 12)
        root.setSpacing(7 if not self.compact_mode else 5)

        top = QHBoxLayout()
        top.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(4)

        ntid_label = QLabel("NTID IDENTIFIER")
        ntid_label.setObjectName("FaceUserCardLabel")

        name = QLabel(user_id)
        name.setObjectName("FaceUserCardNtid")

        left.addWidget(ntid_label)
        left.addWidget(name)

        badge = QLabel(("●  TRAINED" if active else "●  PENDING"))
        badge.setObjectName("FaceUserCardTrainedBadge" if active else "FaceUserCardPendingBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(94 if not self.compact_mode else 82)
        badge.setMaximumWidth(108 if not self.compact_mode else 94)

        top.addLayout(left, 1)
        top.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        frames_row = QHBoxLayout()
        frames_row.setSpacing(6)

        frames_icon = QLabel("▦")
        frames_icon.setObjectName("FaceUserFramesIcon")
        frames_icon.setFixedWidth(16)

        detail = QLabel(frames)
        detail.setObjectName("FaceUserCardDetail")

        frames_row.addWidget(frames_icon)
        frames_row.addWidget(detail)
        frames_row.addStretch()

        actions = QFrame()
        actions.setObjectName("FaceUserCardActions")
        actions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions.setVisible(False)
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 2 if not self.compact_mode else 2)
        actions_layout.setSpacing(6 if not self.compact_mode else 5)

        capture_btn = QPushButton("+ CAPTURE")
        capture_btn.setObjectName("FaceUserCardCaptureButton")
        capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        capture_btn.setMinimumHeight(32 if not self.compact_mode else 30)

        delete_btn = QPushButton("DELETE USER")
        delete_btn.setObjectName("FaceUserCardDeleteButton")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setMinimumHeight(34 if not self.compact_mode else 32)

        actions_layout.addWidget(capture_btn)
        actions_layout.addWidget(delete_btn)

        root.addLayout(top)
        root.addLayout(frames_row)
        root.addWidget(actions)

        def animate_card_height(target_h: int, expanding: bool):
            """Animate both min and max height to avoid clipping/jumping."""
            old_min = card.minimumHeight()
            old_max = card.maximumHeight()

            if expanding:
                actions.setVisible(True)

            min_anim = QPropertyAnimation(card, b"minimumHeight", card)
            min_anim.setDuration(230)
            min_anim.setStartValue(old_min)
            min_anim.setEndValue(target_h)
            min_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            max_anim = QPropertyAnimation(card, b"maximumHeight", card)
            max_anim.setDuration(230)
            max_anim.setStartValue(old_max)
            max_anim.setEndValue(target_h)
            max_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            # Keep references so Qt does not garbage-collect the animations.
            card.setProperty("_min_height_anim", min_anim)
            card.setProperty("_max_height_anim", max_anim)

            def finish():
                card.setMinimumHeight(target_h)
                card.setMaximumHeight(target_h)
                if not expanding:
                    actions.setVisible(False)

            max_anim.finished.connect(finish)
            min_anim.start()
            max_anim.start()

        def collapse_other_card():
            old_card = getattr(self, "_open_face_user_expand_card", None)
            if old_card is not None and old_card is not card:
                try:
                    old_actions = old_card.property("_actions_frame")
                    old_min_anim = old_card.property("_min_height_anim")
                    old_max_anim = old_card.property("_max_height_anim")

                    if isinstance(old_min_anim, QPropertyAnimation):
                        old_min_anim.stop()
                    if isinstance(old_max_anim, QPropertyAnimation):
                        old_max_anim.stop()

                    old_card.setProperty("expanded", False)
                    old_card.style().unpolish(old_card)
                    old_card.style().polish(old_card)

                    # Collapse old card smoothly too.
                    old_card.setMinimumHeight(collapsed_h)
                    old_card.setMaximumHeight(collapsed_h)
                    if isinstance(old_actions, QWidget):
                        old_actions.setVisible(False)
                except Exception:
                    pass

        def set_expanded(expand: bool):
            if user_id in ("CONNECT PI", "OFFLINE", ""):
                return

            if expand:
                collapse_other_card()

            card.setProperty("expanded", expand)
            card.style().unpolish(card)
            card.style().polish(card)

            animate_card_height(expanded_h if expand else collapsed_h, expand)

            if expand:
                self._open_face_user_expand_card = card

        def toggle_card():
            set_expanded(not bool(card.property("expanded")))

        def capture_this_user():
            if hasattr(self, "ntid_input"):
                self.ntid_input.setText(user_id)
                self.clear_ntid_input_error()
            self.face_action_feedback(f"QUICK_CAPTURE: {user_id}")
            self._face_api_capture_user()

        def delete_this_user():
            if hasattr(self, "ntid_input"):
                self.ntid_input.setText(user_id)
                self.clear_ntid_input_error()
            self.face_action_feedback(f"QUICK_DELETE: {user_id}")
            self._face_api_delete_user()

        card.mousePressEvent = lambda event: toggle_card()
        capture_btn.clicked.connect(lambda checked=False: capture_this_user())
        delete_btn.clicked.connect(lambda checked=False: delete_this_user())

        # Prevent button clicks from toggling the parent card.
        capture_btn.mousePressEvent = lambda event, old=capture_btn.mousePressEvent: (event.accept(), old(event))[1]
        delete_btn.mousePressEvent = lambda event, old=delete_btn.mousePressEvent: (event.accept(), old(event))[1]

        card.setProperty("_actions_frame", actions)

        return card

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
        """Run callback on Qt main thread safely.

        Worker threads may finish after the dashboard has been closed. In that
        case PySide can delete the signal source before the worker emits, causing
        ``RuntimeError: Signal source has been deleted``. This guard silently
        drops late callbacks during shutdown while keeping normal worker-to-UI
        updates unchanged.
        """
        def emit_callback():
            if getattr(self, "_closing", False):
                return
            bridge = getattr(self, "ui_bridge", None)
            if bridge is None:
                return
            try:
                bridge.run_callback.emit(callback)
            except RuntimeError:
                # The Qt object was already destroyed during application exit.
                return
            except Exception as e:
                print(f"[SAS] qt_after callback emit skipped: {e}")

        if ms <= 0:
            emit_callback()
        else:
            try:
                QTimer.singleShot(ms, emit_callback)
            except RuntimeError:
                return

    def append_system_log(self, message: str):
        """General internal log.

        The visible System Log card is reserved for Face Recognition system logs.
        Dashboard/settings/login messages are printed to terminal only.
        """
        print("[SAS]", message)

    def append_face_log(self, message: str):
        """Visible Face Recognition System Log.

        Shows all Face Recognition actions/status:
        connection, camera, capture, train, recognise, stop, delete,
        users refresh, import/export, SFTP, received data and errors.
        """
        now = datetime.now().strftime("%H:%M:%S")
        line = f"<span style='color:#1F7A45'>{now}</span> &gt; {html.escape(str(message))}"

        if not hasattr(self, "_system_log_lines"):
            self._system_log_lines = [
                "&gt; FACE RECOGNITION SYSTEM LOG READY",
                "&gt; WAITING FOR PI CONNECTION",
            ]

        self._system_log_lines.append(line)

        # Keep enough history for scrolling without making the UI too heavy.
        self._system_log_lines = self._system_log_lines[-120:]

        if not getattr(self, "_log_update_pending", False):
            self._log_update_pending = True
            self.qt_after(50, self.flush_face_log_label)

        print("[FACE]", message)

    def flush_face_log_label(self):
        self._log_update_pending = False
        if hasattr(self, "system_log_label") and hasattr(self, "_system_log_lines"):
            should_follow_bottom = True
            if hasattr(self, "system_log_scroll"):
                bar = self.system_log_scroll.verticalScrollBar()
                should_follow_bottom = bar.value() >= max(0, bar.maximum() - 24)

            self.system_log_label.setText("<br>".join(self._system_log_lines))
            self.system_log_label.adjustSize()

            if hasattr(self, "system_log_body"):
                self.system_log_body.adjustSize()
                self.system_log_body.setMinimumHeight(self.system_log_label.sizeHint().height() + 8)

            if hasattr(self, "system_log_scroll") and should_follow_bottom:
                # Follow latest status only when user was already near the bottom.
                # If user scrolls up to review older logs, do not force jump down.
                QTimer.singleShot(
                    0,
                    lambda: self.system_log_scroll.verticalScrollBar().setValue(
                        self.system_log_scroll.verticalScrollBar().maximum()
                    )
                )


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

    def _remove_admin(self, ntid):
        if hasattr(self.admin_service, "remove_admin"):
            return self.admin_service.remove_admin(ntid)

        # Fallback for older service object.
        target = str(ntid).strip().lower()
        admins = self._load_admins()
        if not target or target not in admins:
            return False, "Admin not found."
        if admins and target == admins[0]:
            return False, "The first/root admin cannot be removed."
        admins = [admin for admin in admins if admin != target]
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            for admin in admins:
                f.write(admin + "\n")
        return True, "Admin removed."

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
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        admins = self._load_admins()

        if not admins:
            self.admin_list_layout.addWidget(
                self.admin_row(
                    "No admin yet",
                    f"admins.txt not loaded or empty",
                    removable=False
                )
            )
            self.admin_list_layout.addStretch(1)
            return

        for index, admin in enumerate(admins):
            admin_key = str(admin).strip().lower()
            tag = "(you)" if self.current_user and admin_key == self.current_user.lower() else ""
            self.admin_list_layout.addWidget(self.admin_row(admin_key.upper(), tag, removable=(index != 0)))

        # Important: this stretch consumes the remaining space.
        # Without it, Qt stretches each admin row when there are only 1-2 admins.
        self.admin_list_layout.addStretch(1)

        if hasattr(self, "admin_list_scroll"):
            self.admin_list_scroll.viewport().update()
            QTimer.singleShot(0, lambda: self.admin_list_scroll.verticalScrollBar().setValue(0))

    def remove_admin_from_ui(self, ntid: str):
        """Remove admin from admins.txt and refresh the scroll list."""
        target = str(ntid).replace("(you)", "").strip().lower()
        if not target:
            self.append_system_log("Remove admin failed: missing NTID")
            return

        ok, message = self._remove_admin(target)
        if ok:
            actor = self.get_audit_actor()
            self.write_sas_log(f"ADMIN REMOVED | ACTOR={actor} | TARGET={target.upper()}")
            self.append_system_log(f"Admin removed: {target.upper()}")
            self.refresh_admin_list_ui()

            # If current signed-in admin removed himself through an edge case,
            # downgrade role immediately.
            if self.current_user and target == self.current_user.lower():
                self.is_admin = False
                self.update_account_button()
        else:
            self.append_system_log(f"Remove admin failed: {target.upper()} - {message}")


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
                actor = self.get_audit_actor()
                self.write_sas_log(f"ADMIN ADDED | ACTOR={actor} | TARGET={ntid.upper()}")
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
        if not getattr(self, "_settings_validation_passed", False):
            self.append_system_log("CREDENTIAL_SAVE_BLOCKED: strict validation was not completed.")
            return
        self._settings_validation_passed = False

        pi_host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        pi_port = "5000"
        auto_capture = self.auto_capture_toggle.is_enabled() if hasattr(self, "auto_capture_toggle") else bool(getattr(self, "auto_capture_enabled", False))

        self.credential_service.save_credentials(
            ntid,
            password,
            server,
            timeout,
            disable_keyboard=disable_keyboard,
            disable_mouse=disable_mouse,
            disable_usb=disable_usb,
            enable_hotkey=enable_hotkey,
            pi_host=pi_host,
            pi_port=pi_port,
            auto_capture=auto_capture,
            video_source="pi",
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
        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()


    def show_missing_credentials_setup_popup_if_needed(self):
        """Show first-launch setup guidance when credential.txt is blank/incomplete."""
        if getattr(self, "_missing_credentials_popup_shown", False):
            return

        if getattr(self, "server_configured", False):
            return

        if not getattr(self, "first_launch_setup_mode", False):
            return

        self._missing_credentials_popup_shown = True
        self.append_system_log("FIRST_LAUNCH_SETUP: Missing credentials popup shown.")

        dialog = MissingCredentialsSetupDialog(self, self.compact_mode)
        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

        # User must login first because Settings is an Admin-restricted tab.
        self.pending_restricted_tab = "Settings"
        if self.has_restricted_tab_access():
            self.switch_top_tab("Settings")
        else:
            self.open_login_popup()


    def get_audit_actor(self, fallback: str = "UNAUTHENTICATED") -> str:
        """Return the current authenticated SAS user for audit records."""
        actor = str(getattr(self, "current_user", "") or "").strip().upper()
        return actor or fallback

    def write_sas_log(self, message: str):
        """Write an SAS audit event to local and configured-server SAS_LOG folders.

        Audit events include workstation unlocks, emergency-hotkey use, login
        outcomes, restricted-page access, settings changes, and Admin-list
        changes. Passwords are never written to SAS_LOG.
        """
        message = str(message or "").strip()
        if not message:
            return

        date_str = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        # 1) Local SAS_LOG beside dashboard.py / inside sas_dashboard_modular
        try:
            local_root = LOCAL_SAS_LOG_DIR
            os.makedirs(local_root, exist_ok=True)
            local_log_file = os.path.join(local_root, f"{date_str}.txt")
            with open(local_log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            self.append_system_log(f"Local SAS_LOG write failed: {e}")

        # 2) Server SAS_LOG under configured server path.
        # Refresh from credentials as a fallback because Settings may update credential.txt.
        try:
            server_path = str(getattr(self, "server_path", "") or "").strip()

            if not server_path:
                try:
                    creds = self._read_credentials()
                    server_path = str(creds.get("server", "") or "").strip()
                except Exception:
                    server_path = ""

            if server_path:
                server_root = os.path.join(server_path, "SAS_LOG")
                os.makedirs(server_root, exist_ok=True)
                server_log_file = os.path.join(server_root, f"{date_str}.txt")
                with open(server_log_file, "a", encoding="utf-8") as f:
                    f.write(line)
            else:
                self.append_system_log("Server SAS_LOG write skipped: server path is empty")
        except Exception as e:
            self.append_system_log(f"Server SAS_LOG write failed: {e}")


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
        """Apply saved security option flags using runtime_lock_service."""
        self.append_system_log(
            "Security options applied: "
            f"keyboard={self.disable_keyboard_when_locked}, "
            f"mouse={self.disable_mouse_when_locked}, "
            f"usb={self.disable_usb_when_locked}, "
            f"hotkey={self.enable_hotkey}"
        )
        self.runtime_lock_service.apply_security_options(self)


    def is_server_configured(self, creds: dict | None = None) -> bool:
        """Return True only when usable server credentials exist.

        On first EXE launch, credential.txt may not exist yet. In that case
        SAS should enter setup mode instead of trying to lock against a missing
        recognition_result.json path.
        """
        creds = creds if creds is not None else self._read_credentials()
        ntid = str(creds.get("ntid", "") or "").strip()
        password = str(creds.get("password", "") or "").strip()
        server = str(creds.get("server", "") or "").strip()

        if not ntid or not password or not server:
            return False

        # C:\temp is only the built-in placeholder/default, not a real saved setup.
        if server.replace("/", "\\").rstrip("\\").lower() == str(SERVER_PATH).replace("/", "\\").rstrip("\\").lower():
            return False

        return True

    def enter_first_launch_setup_mode(self):
        """Safe startup mode for newly copied EXE / blank configuration.

        Behaviour:
        - Do not show a system-lock notification.
        - Do not depend on recognition_result.json.
        - Allow the first valid AD login to become Admin.
        - Keep Face Recognition blocked until Pi/server settings are configured.
        """
        self.first_launch_setup_mode = True
        self.server_configured = False
        self.is_locked = False
        self.face_detected = False
        self._pending_auto_lock = False
        self.time_left = max(1, int(self.lock_timeout_seconds))

        if hasattr(self, "status_title"):
            self.status_title.setText("SETUP REQUIRED")
        if hasattr(self, "face_state_label"):
            self.face_state_label.setText("Login as Admin and configure Settings first.")

        self.hide_system_locked_notification()
        self.apply_lock_state()
        self.update_account_ui()
        self.append_system_log("FIRST_LAUNCH_SETUP: Missing server credentials. System-lock notification suppressed until setup is saved.")

    def exit_first_launch_setup_mode(self):
        """Leave setup mode after Save & Connect succeeds."""
        self.first_launch_setup_mode = False
        self.server_configured = True
        self._suppress_lock_notification = False
        self.append_system_log("FIRST_LAUNCH_SETUP: Configuration completed.")

    def load_settings_from_credentials(self):
        creds = self._read_credentials()
        self.server_configured = self.is_server_configured(creds)

        # Use saved server only when it is real/configured. Otherwise keep blank
        # in Settings UI instead of showing the placeholder C:\temp as if it was configured.
        if self.server_configured:
            self.server_path = creds.get("server", self.server_path)
        else:
            self.server_path = ""

        try:
            self.lock_timeout_seconds = int(creds.get("timeout", self.lock_timeout_seconds))
        except Exception:
            self.lock_timeout_seconds = DEFAULT_LOCK_TIMEOUT_SECONDS

        self.disable_keyboard_when_locked = creds.get("disable_keyboard", "false").lower() == "true"
        self.disable_mouse_when_locked = creds.get("disable_mouse", "false").lower() == "true"
        self.disable_usb_when_locked = creds.get("disable_usb", "false").lower() == "true"
        self.enable_hotkey = creds.get("enable_hotkey", "true").lower() == "true"
        saved_pi_host = str(creds.get("pi_host", "") or "").strip()
        self.pi_api_host = saved_pi_host
        self.pi_api_port = "5000"
        self.auto_capture_enabled = creds.get("auto_capture", "false").lower() == "true"

        if self.pi_api_host:
            self.face_api_service.configure(self.pi_api_host, self.pi_api_port)
            self.pi_api_base = f"http://{self.pi_api_host}:{self.pi_api_port}" if not str(self.pi_api_host).startswith("http") else str(self.pi_api_host).rstrip("/")
            self.camera_feed_url = f"{self.pi_api_base}/video-feed"
        else:
            self.pi_api_base = ""
            self.camera_feed_url = ""
            self.pi_connected = False
            self.pi_connection_checked = False

        if hasattr(self, "settings_ntid_input"):
            self.settings_ntid_input.setText("")
        if hasattr(self, "settings_password_input"):
            self.settings_password_input.setText("")
        if hasattr(self, "settings_server_path_input"):
            self.settings_server_path_input.setText(self.server_path)
            if not self.server_configured:
                self.settings_server_path_input.setPlaceholderText("Enter server path, e.g. \\\\server\\share\\folder")
        if hasattr(self, "pi_host_input"):
            self.pi_host_input.setText(self.pi_api_host)
            if not self.pi_api_host:
                self.pi_host_input.setPlaceholderText("Enter Pi hostname or IP")
        if hasattr(self, "pi_identity_label"):
            self.pi_identity_label.setText("")
            self.pi_identity_label.setVisible(False)
        # Pi port is fixed to 5000, so no editable port field is shown.
        if hasattr(self, "auto_capture_toggle"):
            self.auto_capture_toggle.set_checked(self.auto_capture_enabled)
        if hasattr(self, "auto_capture_sync_label"):
            self.set_auto_capture_sync_status(
                f"●  Pi sync: {'Enabled' if self.auto_capture_enabled else 'Disabled'}",
                ok=True,
            )
        if hasattr(self, "security_option_buttons"):
            if "disable_keyboard" in self.security_option_buttons:
                self.security_option_buttons["disable_keyboard"].setChecked(self.disable_keyboard_when_locked)
            if "disable_mouse" in self.security_option_buttons:
                self.security_option_buttons["disable_mouse"].setChecked(self.disable_mouse_when_locked)

            # Hidden developer-only settings:
            # USB storage control is not exposed to normal users.
            # Emergency hotkey is always enabled internally and is not user-configurable.
            self.disable_usb_when_locked = creds.get("disable_usb", "false").lower() == "true"
            self.enable_hotkey = True
        if hasattr(self, "timeout_inputs"):
            total = int(self.lock_timeout_seconds)
            self.timeout_inputs["hours"].setText(str(total // 3600))
            self.timeout_inputs["minutes"].setText(str((total % 3600) // 60))
            self.timeout_inputs["seconds"].setText(str(total % 60))

        self.apply_timeout_to_countdown(reset=True)
        self.apply_security_options_runtime()
        self.update_footer_info()

        if not self.server_configured:
            self._suppress_lock_notification = True
            self.enter_first_launch_setup_mode()
        else:
            self.first_launch_setup_mode = False
            self._suppress_lock_notification = False

        self.clear_sensitive_server_credentials_ui(clear_server_path=False)

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

    def validate_settings_credentials_strict(self, ntid: str, password: str, server: str):
        """Strict validation before writing credential.txt.

        This is used for first-time setup too. Credentials must not be saved
        unless AD user check, AD password check, and server path write-test all
        pass in the same Save Connect attempt.
        """
        issues = []

        ntid = (ntid or "").strip()
        password = password or ""
        server = (server or "").strip()

        if not ntid:
            issues.append(("INVALID NTID", "Please enter a valid NTID before saving settings."))
        if not password:
            issues.append(("PASSWORD REQUIRED", "Please enter the password before saving settings."))
        if not server:
            issues.append(("SERVER PATH MISSING", "Please select or enter the shared server path."))

        if issues:
            return False, issues

        ntid_ok = self._validate_ntid_in_ad(ntid)
        if not ntid_ok:
            issues.append(("INVALID NTID", "Subject token verification failed. The NTID does not exist or AD is unreachable."))

        password_ok = False
        if ntid_ok:
            password_ok = self._validate_ntid_password_in_ad(ntid, password)
            if not password_ok:
                issues.append(("CREDENTIAL MISMATCH", "Password validation failed. Please check the password and try again."))

        server_ok, server_issues = self.validate_server_path_for_settings(server)
        if not server_ok:
            issues.extend(server_issues)

        return len(issues) == 0, issues


    def set_save_connect_busy(self, busy: bool):
        btn = getattr(self, "settings_save_connect_btn", None)
        if btn is None:
            return

        btn.setEnabled(not busy)
        btn.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.PointingHandCursor)
        btn.setText("Saving..." if busy else "Save Connect")

        try:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
        except Exception:
            pass


    def sync_settings_to_pi_async(
        self,
        ntid: str,
        password: str,
        server: str,
        auto_capture: bool,
        camera_rotation: int | None = None,
    ):
        """Sync Settings to Pi without blocking the UI.

        Save & Connect already validates NTID/password/server path in a worker.
        The Pi sync must also run in a worker because HTTP requests to the Pi
        can take several seconds or time out if the Pi is offline.
        """
        self.set_auto_capture_sync_status("●  Pi sync: Syncing...", ok=False)

        def worker():
            ok = self._face_api_sync_settings_to_pi(
                ntid, password, server, auto_capture, camera_rotation
            )

            def done():
                if ok:
                    self.set_auto_capture_sync_status(
                        f"●  Pi sync: {'Enabled' if auto_capture else 'Disabled'}",
                        ok=True,
                    )
                else:
                    self.set_auto_capture_sync_status("●  Pi sync: Failed", ok=False)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()


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
            h = max(0, min(int(self.timeout_inputs["hours"].text() or 0), 23))
            m = max(0, min(int(self.timeout_inputs["minutes"].text() or 0), 59))
            s = max(0, min(int(self.timeout_inputs["seconds"].text() or 0), 59))

            # Reflect clamped values back to UI, so the user sees the corrected range.
            self.timeout_inputs["hours"].setText(str(h))
            self.timeout_inputs["minutes"].setText(str(m))
            self.timeout_inputs["seconds"].setText(str(s))

            timeout = max(1, h * 3600 + m * 60 + s)
        except Exception:
            timeout = DEFAULT_LOCK_TIMEOUT_SECONDS

        disable_keyboard = self.security_option_buttons["disable_keyboard"].isChecked()
        disable_mouse = self.security_option_buttons["disable_mouse"].isChecked()

        # Hidden developer-only settings.
        # Do not expose to users in the Settings UI.
        disable_usb = getattr(self, "disable_usb_when_locked", False)
        enable_hotkey = True

        auto_capture = self.auto_capture_toggle.is_enabled() if hasattr(self, "auto_capture_toggle") else False
        camera_rotation = self.normalize_camera_rotation(getattr(self, "camera_rotation", 0))

        self.append_system_log("Validating settings NTID/password/server path before saving...")
        self.set_save_connect_busy(True)

        def worker():
            validation_ok, issues = self.validate_settings_credentials_strict(ntid, password, server)

            def done():
                if issues or not validation_ok:
                    self._settings_validation_passed = False
                    self.set_save_connect_busy(False)
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

                self._settings_validation_passed = True

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
                self.remember_session_credentials_after_save(ntid, password, server)
                self._keep_session_credentials_visible = True
                self.apply_session_credentials_to_settings_ui()
                self.exit_first_launch_setup_mode()
                self.lock_timeout_seconds = timeout
                self.disable_keyboard_when_locked = disable_keyboard
                self.disable_mouse_when_locked = disable_mouse
                self.disable_usb_when_locked = disable_usb
                self.enable_hotkey = True

                self.apply_timeout_to_countdown(reset=True)
                self.apply_security_options_runtime()
                self.update_footer_info()

                # Do not call the Pi API on the UI thread.
                # If Pi is slow/offline, this avoids "window not responding".
                if str(getattr(self, "pi_api_host", "") or "").strip():
                    self.sync_settings_to_pi_async(
                        ntid, password, server, auto_capture, camera_rotation
                    )
                else:
                    self.set_auto_capture_sync_status("●  Pi sync: Host not configured", ok=False)

                actor = self.get_audit_actor()
                self.write_sas_log(
                    f"SETTINGS SAVED | ACTOR={actor} | SERVER={server} | TIMEOUT={timeout}s | "
                    f"DISABLE_KEYBOARD={disable_keyboard} | DISABLE_MOUSE={disable_mouse} | "
                    f"AUTO_CAPTURE={auto_capture} | CAMERA_ROTATION={camera_rotation}"
                )
                self.append_system_log("Settings saved and connection established")
                self.set_save_connect_busy(False)

                self.show_settings_message(
                    "Connection Established",
                    "Server linked successfully",
                    success=True,
                    server_path=server,
                    timeout_seconds=timeout,
                )

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()



    def set_footer_mode(self, mode: str):
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

    def adjust_footer_width(self):
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

    def format_lock_interval(self, seconds: int) -> str:
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

    def update_footer_info(self):
        if hasattr(self, "footer_server_label"):
            self.footer_server_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 2}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>SERVER PATH</span><br><span style='font-size:{max(10, int(12 * self.ui_scale))}px; line-height:{max(10, int(12 * self.ui_scale)) + 3}px; color:{Theme.TEXT}; font-weight:700;'>{"Not configured" if not self.server_path else html.escape(self.server_path)}</span>")

        if hasattr(self, "footer_state_label"):
            self.footer_state_label.setText(f"<span style='font-size:{max(8, int(10 * self.ui_scale))}px; line-height:{max(8, int(10 * self.ui_scale)) + 2}px; color:{Theme.SECONDARY}; letter-spacing:1px;'>STATE FILE</span><br><span style='font-size:{max(10, int(12 * self.ui_scale))}px; line-height:{max(10, int(12 * self.ui_scale)) + 3}px; color:{Theme.TEXT}; font-weight:700;'>{html.escape(RECOGNITION_RESULT_FILE)}</span>")

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

    def _is_hardcoded_admin_login(self, ntid: str, password: str) -> bool:
        """Return True for the built-in local admin login account."""
        configured_id = str(globals().get("HARDCODED_ADMIN_ID", "admin")).strip().lower()
        configured_password = str(globals().get("HARDCODED_ADMIN_PASSWORD", "penAteam"))
        return str(ntid).strip().lower() == configured_id and str(password) == configured_password

    def _handle_successful_login(
        self,
        ntid: str,
        is_admin: bool,
        role_msg: str,
        debug_text: str,
        dialog,
        login_method: str = "ACTIVE_DIRECTORY",
    ):
        previous_user_for_credentials = str(getattr(self, "current_user", "") or "").strip().lower()
        incoming_user_for_credentials = str(ntid or "").strip().lower()
        if previous_user_for_credentials and previous_user_for_credentials != incoming_user_for_credentials:
            self.clear_session_credentials_on_logout()

        """Apply shared successful login state for AD and built-in admin login."""
        self.current_user = ntid.lower()
        self.is_admin = bool(is_admin)
        self.current_user_role = "Admin" if self.is_admin else "User"
        self.is_logged_in = True

        self.update_account_ui()
        self.refresh_admin_list_ui()

        success_debug = debug_text + f"\nAdmin role check: {role_msg}\nFinal login role: {self.current_user_role}"
        self.login_debug(f"Admin check result: {role_msg}")
        self.append_system_log(f"Login successful: {ntid.upper()} ({self.current_user_role})")
        self.write_sas_log(
            f"LOGIN SUCCESS | USER={ntid.upper()} | ROLE={self.current_user_role.upper()} | METHOD={login_method}"
        )

        self.login_debug("Validation success. Switching login popup to success state.")
        dialog.show_success_state(ntid, self.current_user_role, success_debug)

        # If login was requested because user clicked Face Recognition / Settings,
        # open it only after Admin validation succeeds.
        self.open_pending_restricted_tab_if_allowed()

    def _handle_login_from_popup(self, ntid: str, password: str, dialog):
        dialog.set_validation_state("Starting login validation...")
        self.login_debug("Login button clicked.")
        self.login_debug(f"Received NTID from login popup: {ntid}")

        # Built-in local admin fallback. This account bypasses AD validation and
        # always receives Admin role. The login ID/password are configurable from
        # app_config.py / environment variables.
        if self._is_hardcoded_admin_login(ntid, password):
            debug_text = (
                "Built-in local admin login matched.\n"
                "Active Directory validation skipped for this fallback account."
            )
            self.login_debug("Built-in local admin login accepted.")
            self._handle_successful_login(
                "admin",
                True,
                "Built-in local Admin login successful.",
                debug_text,
                dialog,
                login_method="BUILT_IN_LOCAL_ADMIN",
            )
            return

        def set_dialog_status(message: str):
            if dialog is not None:
                dialog.set_validation_message(message)

        def worker():
            self.qt_after(0, lambda: set_dialog_status("Checking NTID in Active Directory..."))
            valid, reason, debug_text = self._validate_ntid_password_in_ad_with_debug(ntid, password)

            def done():
                if not valid:
                    self.login_debug(f"Login failed: {reason}")
                    self.write_sas_log(
                        f"LOGIN FAILED | USER={str(ntid).strip().upper() or 'UNKNOWN'} | METHOD=ACTIVE_DIRECTORY | REASON=INVALID_CREDENTIALS_OR_AD_UNAVAILABLE"
                    )
                    user_reason = "Invalid NTID or password. Please check your credentials and try again."
                    dialog.show_failed_state(user_reason, debug_text)
                    return

                is_admin, role_msg = self._check_admin_login(ntid)
                self._handle_successful_login(ntid, is_admin, role_msg, debug_text, dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()

    def update_account_button(self):
        """Compatibility wrapper for older calls."""
        self.update_account_ui()

    def update_account_ui(self):
        if hasattr(self, "login_btn"):
            if self.current_user:
                display_user = self.current_user.upper()
                display_role = self.current_user_role

                self.login_btn.setText(f"{display_user} ▾")
                self.login_btn.setFixedWidth(122 if not self.compact_mode else 104)

                if display_user == "ADMIN":
                    self.login_btn.setToolTip("Logged in as ADMIN")
                else:
                    self.login_btn.setToolTip(f"Logged in as {display_user} ({display_role})")
                self.login_btn.setObjectName("LoginButtonLoggedIn")
            else:
                self.login_btn.setText("Login")
                self.login_btn.setToolTip("")
                self.login_btn.setObjectName("LoginButton")
                self.login_btn.setFixedWidth(96 if not self.compact_mode else 82)

            self.login_btn.style().unpolish(self.login_btn)
            self.login_btn.style().polish(self.login_btn)
            self.login_btn.update()

    def stop_camera_preview(self, show_prompt: bool = False):
        """Stop camera preview reliably without blocking UI."""
        self._camera_preview_running = False

        if show_prompt:
            self.show_camera_stopped_prompt("Camera stopped")
        else:
            self.set_camera_state_badge(False)

        if hasattr(self, "camera_timer") and self.camera_timer is not None:
            try:
                self.camera_timer.stop()
            except Exception:
                pass
            self.camera_timer = None

        old_capture = getattr(self, "camera_capture", None)
        self.camera_capture = None

        if old_capture is not None:
            try:
                old_capture.release()
            except Exception:
                pass


    def _face_api_base_url(self):
        # Pi API port is fixed to 5000. User only configures hostname/IP.
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        host = str(host or "").strip()
        port = "5000"

        if not host:
            raise RuntimeError("Pi hostname/IP is not configured. Please set it in Settings first.")

        if host.startswith("http"):
            self.pi_api_base = host.rstrip("/")
            self.face_api_service.configure(host, port)
            self.pi_api_host = host
            self.pi_api_port = port
            self.camera_feed_url = f"{self.pi_api_base}/video-feed"
            return self.pi_api_base

        self.pi_api_host = host
        self.pi_api_port = port
        self.pi_api_base = f"http://{host}:{port}"
        self.camera_feed_url = f"{self.pi_api_base}/video-feed"
        self.face_api_service.configure(host, port)
        return self.pi_api_base


    def _face_api_request(self, method, endpoint, payload=None, timeout=10):
        self._face_api_base_url()
        return self.face_api_service.request(method, endpoint, payload=payload, timeout=timeout)


    def set_face_controls_connection_enabled(self, enabled: bool):
        """Enable Face Recognition actions only when Pi API is reachable.

        Recognition is deliberately kept disabled while a capture is active.
        PiCamera2 cannot safely run capture and recognition at the same time.
        """
        self.pi_connected = bool(enabled)
        capture_busy = bool(getattr(self, "face_capture_in_progress", False))

        for name in ("face_capture_btn", "face_train_btn", "face_recognize_btn", "face_delete_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                button_enabled = bool(enabled)
                if name == "face_recognize_btn" and capture_busy:
                    button_enabled = False
                    btn.setToolTip("Recognition is disabled while capture is running. Press STOP before starting recognition.")
                elif name == "face_recognize_btn":
                    btn.setToolTip("Start face recognition.")

                btn.setEnabled(button_enabled)
                btn.setCursor(Qt.CursorShape.PointingHandCursor if button_enabled else Qt.CursorShape.ForbiddenCursor)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()

        # Stop can remain clickable only when connected. If Pi is offline it cannot stop anything.
        stop_btn = getattr(self, "face_stop_btn", None)
        if stop_btn is not None:
            stop_btn.setEnabled(bool(enabled))
            stop_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)

        if hasattr(self, "ntid_input"):
            self.ntid_input.setEnabled(bool(enabled))

    def set_face_capture_in_progress(self, active: bool):
        """Track Pi capture state and block Recognition until capture is stopped."""
        self.face_capture_in_progress = bool(active)

        recognize_btn = getattr(self, "face_recognize_btn", None)
        if recognize_btn is None:
            return

        allow_recognition = bool(getattr(self, "pi_connected", False)) and not bool(active)
        recognize_btn.setEnabled(allow_recognition)
        recognize_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
            if allow_recognition
            else Qt.CursorShape.ForbiddenCursor
        )
        recognize_btn.setToolTip(
            "Recognition is disabled while capture is running. Press STOP before starting recognition."
            if active
            else "Start face recognition."
        )
        recognize_btn.style().unpolish(recognize_btn)
        recognize_btn.style().polish(recognize_btn)
        recognize_btn.update()

    def show_connection_dialog(self, origin: str = "settings"):
        """Show card-style connection popup.

        The card uses blurred background and blocks clicks behind it.
        """
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        if not host:
            host = self.pi_api_host

        # Close any old connection card before opening a new one.
        try:
            if self.connection_dialog is not None:
                self.connection_dialog.accept()
        except Exception:
            pass

        root = self.centralWidget()
        blur = None
        if root is not None:
            try:
                root.setEnabled(False)
                blur = QGraphicsBlurEffect(self)
                blur.setBlurRadius(0)
                root.setGraphicsEffect(blur)

                self._connection_blur_anim = QPropertyAnimation(blur, b"blurRadius", self)
                self._connection_blur_anim.setDuration(220)
                self._connection_blur_anim.setStartValue(0)
                self._connection_blur_anim.setEndValue(5)
                self._connection_blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._connection_blur_anim.start()
            except Exception:
                blur = None

        dialog = PiConnectionDialog(
            self,
            host=host,
            origin=origin,
            compact_mode=self.compact_mode,
        )
        self.connection_dialog = dialog

        def on_finished(*args):
            if self.connection_dialog is dialog:
                self.connection_dialog = None
            if root is not None:
                try:
                    root.setEnabled(True)
                except Exception:
                    pass
            if root is not None and blur is not None:
                try:
                    self.clear_blur_effect(root)
                except Exception:
                    try:
                        root.setGraphicsEffect(cast(QGraphicsEffect, None))  # type: ignore[arg-type]
                    except Exception:
                        pass

        dialog.finished.connect(on_finished)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def finish_connection_dialog_success(self, users: int = 0, recognition: bool = False, capture: bool = False):
        dialog = getattr(self, "connection_dialog", None)
        if dialog is not None:
            dialog.set_success(users=users, recognition=recognition, capture=capture)

    def finish_connection_dialog_failed(self, error_text: str = ""):
        # v200: If this is a Pi-disconnect condition, use the single no-close
        # disconnect popup instead of the older failed dialog with a close button.
        if getattr(self, "_pi_disconnect_lock_suspended", False) or getattr(self, "_pi_disconnect_retry_active", False):
            self.show_pi_disconnected_popup(error_text)
            return

        dialog = getattr(self, "connection_dialog", None)
        if dialog is not None:
            dialog.set_failed(error_text)



    def clear_disconnect_popup_overlay(self):
        """Clear modal overlay safely without direct unknown-method access."""
        try:
            hide_overlay = getattr(self, "hide_modal_overlay", None)
            if callable(hide_overlay):
                hide_overlay()
        except Exception:
            pass
        try:
            clear_overlay = getattr(self, "clear_modal_overlay", None)
            if callable(clear_overlay):
                clear_overlay()
        except Exception:
            pass
        try:
            self._modal_open_count = 0
        except Exception:
            pass
        try:
            self.setEnabled(True)
        except Exception:
            pass


    def wire_pi_disconnect_return_button(self, dialog):
        """Connect the Pi disconnect dialog's visible action button to restore SAS."""
        try:
            buttons = dialog.findChildren(QPushButton)
        except Exception:
            buttons = []

        for btn in buttons:
            try:
                label = btn.text().strip().lower()
            except Exception:
                label = ""

            if "setting" in label or "return" in label or "connect" in label:
                try:
                    btn.setText("Return to Settings")
                except Exception:
                    pass
                try:
                    btn.clicked.disconnect()
                except Exception:
                    pass
                try:
                    btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                except Exception:
                    pass
                try:
                    btn.setDefault(True)
                    btn.setAutoDefault(True)
                except Exception:
                    pass
                return True

        return False


    def show_face_tab_pi_disconnect_popup(self, reason: str = ""):
        """Show Pi disconnected popup when user tries to open Face Recognition.

        This is a user action, so it must bypass Settings-tab auto-popup
        suppression and stale popup flags.
        """
        try:
            self._allow_settings_disconnect_popup_once = True
            self._pi_disconnect_popup_visible = False
            self.suspend_locking_for_pi_disconnect(reason or "Please connect Pi hostname/IP from Settings first.")
            self.show_pi_disconnected_popup(reason or "Please connect Pi hostname/IP from Settings first.")
        except Exception as e:
            print("[FACE TAB DISCONNECT POPUP ERROR]", e)


    def convert_connection_dialog_to_disconnect_failed(self, error_text: str = ""):
        """Convert the current Settings Connect progress dialog to failed state.

        Used when the user manually presses Connect in Settings. This prevents
        the dialog from staying stuck at "Connecting..." and reuses the existing
        popup/card UI.
        """
        if getattr(self, "_manual_connect_failed_popup_active", False):
            return
        self._manual_connect_failed_popup_active = True

        dialog = getattr(self, "connection_dialog", None)
        if dialog is None:
            self._allow_settings_disconnect_popup_once = True
            self.show_pi_disconnected_popup(error_text or "Raspberry Pi disconnected.")
            self._manual_connect_failed_popup_active = False
            return

        try:
            dialog.set_failed(error_text or "Raspberry Pi disconnected. Please check Pi power/network.")
        except Exception:
            pass

        try:
            dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
            dialog.setModal(False)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
        except Exception:
            pass

        def _prepare_failed_dialog():
            try:
                for btn in dialog.findChildren(QPushButton):
                    label = (btn.text() or "").strip().lower()
                    obj = (btn.objectName() or "").strip().lower()

                    if label in ("x", "×", "close", "cancel") or "close" in obj or "cancel" in obj:
                        btn.hide()
                        btn.setEnabled(False)
                        continue

                    if (
                        "setting" in label
                        or "return" in label
                        or "connect" in label
                        or "retry" in label
                        or "ok" in label
                        or not label
                    ):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.setDefault(True)
                        btn.setAutoDefault(True)
                        btn.show()
                        btn.setEnabled(True)

                for attr in ("settings_btn", "return_settings_btn", "primary_btn", "retry_btn", "ok_btn"):
                    btn = getattr(dialog, attr, None)
                    if isinstance(btn, QPushButton):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.show()
                        btn.setEnabled(True)
            except Exception:
                pass

        _prepare_failed_dialog()
        QTimer.singleShot(0, _prepare_failed_dialog)
        QTimer.singleShot(200, _prepare_failed_dialog)
        QTimer.singleShot(600, _prepare_failed_dialog)

        self._pi_disconnect_popup_visible = True
        try:
            self._pi_disconnect_popup_last_shown_at = time.monotonic()
        except Exception:
            pass

        def reset_flag(*_args):
            self._pi_disconnect_popup_visible = False
            self._manual_connect_failed_popup_active = False
            if not getattr(self, "pi_connected", False):
                self.suspend_locking_for_pi_disconnect(error_text or "Raspberry Pi disconnected.")
                self.start_pi_disconnect_retry_loop(error_text or "Raspberry Pi disconnected.")

        try:
            dialog.finished.connect(reset_flag)
        except Exception:
            pass

        try:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass

    def show_pi_disconnected_popup(self, error_text: str = ""):
        """Show Pi disconnected popup using the original connection card UI.

        v213:
        - Restores the previous disconnect UI/card style.
        - Removes the custom v212 white-card popup.
        - Does not create a separate top-level/new window for minimized mode.
        - Keeps no-close behaviour and Return to Settings action.
        """
        if (
            self.is_settings_tab_active()
            and not self.is_sas_minimized_or_background()
            and not getattr(self, "_allow_settings_disconnect_popup_once", False)
        ):
            return
        self._allow_settings_disconnect_popup_once = False

        existing = getattr(self, "connection_dialog", None)
        try:
            if existing is not None and existing.isVisible():
                return
        except Exception:
            pass

        try:
            now = time.monotonic()
            last = float(getattr(self, "_pi_disconnect_popup_last_shown_at", 0.0) or 0.0)
            if now - last < 2.5:
                return
            self._pi_disconnect_popup_last_shown_at = now
        except Exception:
            pass

        try:
            if existing is not None:
                existing.blockSignals(True)
                existing.close()
                existing.deleteLater()
        except Exception:
            pass
        self.connection_dialog = None
        self._pi_disconnect_popup_visible = True

        # Use the original connection status card/popup. Do not detach it into a
        # new top-level dialog, because that caused the UI to look different.
        dialog = self.show_connection_dialog(origin="settings")
        dialog.set_failed(error_text or "Raspberry Pi disconnected. Please check Pi power/network.")

        try:
            dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
            dialog.setModal(False)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
        except Exception:
            pass

        def _prepare_disconnect_dialog():
            try:
                for btn in dialog.findChildren(QPushButton):
                    label = (btn.text() or "").strip().lower()
                    obj = (btn.objectName() or "").strip().lower()

                    if label in ("x", "×", "close", "cancel") or "close" in obj or "cancel" in obj:
                        btn.hide()
                        btn.setEnabled(False)
                        continue

                    if (
                        "setting" in label
                        or "return" in label
                        or "connect" in label
                        or "retry" in label
                        or "ok" in label
                        or not label
                    ):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.setDefault(True)
                        btn.setAutoDefault(True)
                        btn.show()
                        btn.setEnabled(True)

                for attr in ("settings_btn", "return_settings_btn", "primary_btn", "retry_btn", "ok_btn"):
                    btn = getattr(dialog, attr, None)
                    if isinstance(btn, QPushButton):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.show()
                        btn.setEnabled(True)
            except Exception:
                pass

        _prepare_disconnect_dialog()
        QTimer.singleShot(0, _prepare_disconnect_dialog)
        QTimer.singleShot(200, _prepare_disconnect_dialog)
        QTimer.singleShot(600, _prepare_disconnect_dialog)

        def reset_flag(*_args):
            self._pi_disconnect_popup_visible = False
            if not getattr(self, "pi_connected", False):
                self.suspend_locking_for_pi_disconnect(error_text or "Raspberry Pi disconnected.")
                self.start_pi_disconnect_retry_loop(error_text or "Raspberry Pi disconnected.")

        try:
            dialog.finished.connect(reset_flag)
        except Exception:
            pass

        self.connection_dialog = dialog

        try:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass


    def auto_connect_pi_for_face_tab(self):
        """Compatibility wrapper.

        Face Recognition tab no longer reconnects automatically.
        Users connect from Settings, then Face Recognition uses that successful connection.
        """
        if not getattr(self, "pi_connected", False):
            self.show_face_tab_pi_disconnect_popup("Please connect Pi hostname/IP from Settings first.")


    def _face_api_test_connection(self, show_disconnect_popup: bool = False, show_progress: bool = True, origin: str = "settings"):
        origin_safe = str(origin or "")
        """Connect to Pi Face Recognition API and load status/users/logs."""
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        if not host:
            self.pi_connected = False
            self.pi_connection_checked = False
            self.set_pi_status_label(connected=False)
            self.append_face_log("SERVER_STATUS: SKIPPED | Pi hostname/IP is not configured.")
            self.show_settings_message(
                "Pi Host Required",
                "Please enter the Raspberry Pi hostname or IP address before connecting.",
                success=False,
                issues=[("MISSING PI HOST", "Pi hostname/IP is required to connect to the Face Recognition API.")],
                server_path=self.server_path,
            )
            return

        attempt_id = 0
        if show_progress:
            self.show_connection_dialog(origin=origin)
            if origin_safe == "settings":
                self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                attempt_id = self._settings_connect_attempt_id

                def settings_connect_timeout_guard(expected_id=attempt_id):
                    try:
                        if expected_id != getattr(self, "_settings_connect_attempt_id", 0):
                            return
                        if getattr(self, "pi_connected", False):
                            return
                        dialog = getattr(self, "connection_dialog", None)
                        if dialog is not None and dialog.isVisible():
                            self.suspend_locking_for_pi_disconnect("Pi connection timed out. Please check Pi hostname/IP and network.")
                            self.convert_connection_dialog_to_disconnect_failed(
                                "Pi connection timed out. Please check Pi hostname/IP and network."
                            )
                    except Exception as e:
                        print("[SETTINGS CONNECT TIMEOUT GUARD ERROR]", e)

                QTimer.singleShot(10000, settings_connect_timeout_guard)

        self.set_pi_status_label(checking=True)

        def worker():
            try:
                data = self._face_api_request("GET", "/status", timeout=8)
                users = data.get("users", 0)
                rec = data.get("recognition_running", False)
                cap = data.get("capture_running", False)
                pi_hostname = str(data.get("hostname") or data.get("device_name") or "").strip()
                pi_user = str(data.get("system_user") or data.get("ssh_username") or "").strip()
                msg = f"SERVER_STATUS: ONLINE | USERS={users} | RECOGNITION={rec} | CAPTURE={cap} | HOSTNAME={pi_hostname or '-'} | USER={pi_user or '-'}"

                def done():
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self.resume_locking_after_pi_reconnect()
                    self.pi_device_hostname = pi_hostname
                    self.pi_system_user = pi_user
                    self.set_face_controls_connection_enabled(True)
                    self.append_face_log(msg)

                    self.set_pi_status_label(connected=True, message=f"Status: Connected | Hostname: {pi_hostname or '-'} | Username: {pi_user or '-'}")
                    if hasattr(self, "pi_identity_label"):
                        self.pi_identity_label.setText("")
                        self.pi_identity_label.setVisible(False)

                    # Important:
                    # A previous Pi disconnect may have left the camera panel showing
                    # "Pi disconnected". After a successful reconnect, reset that stale
                    # state immediately.
                    self._camera_user_stopped = False
                    self._handling_pi_disconnect = False

                    self.finish_connection_dialog_success(users=users, recognition=rec, capture=cap)

                    self._face_api_refresh_users()
                    self._face_api_load_logs()
                    self.pull_pi_settings_to_sas(silent=True)
                    self.refresh_pi_storage_from_pi(silent=True)

                    # If Pi is already recognising/capturing, show the feed immediately.
                    # If not, show a normal camera-stopped prompt, not "Pi disconnected".
                    if rec or cap:
                        self.stop_camera_preview()
                        self.start_camera_preview(force=True)
                    else:
                        self.stop_camera_preview(show_prompt=True)

                    self.handle_startup_background_check_result(True)

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    if origin_safe == "settings":
                        self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                    self.pi_connection_checked = True
                    self.pi_connected = False
                    self.pi_system_user = ""
                    self.pi_device_hostname = ""
                    self.set_face_controls_connection_enabled(False)
                    self.append_face_log(f"SERVER_STATUS: OFFLINE | {err}")

                    self.set_pi_status_label(connected=False)
                    if hasattr(self, "pi_identity_label"):
                        self.pi_identity_label.setText("")
                        self.pi_identity_label.setVisible(False)

                    try:
                        self.clear_all_authorized_users_ui()
                        self._camera_user_stopped = True
                        self.stop_camera_preview(show_prompt=True)
                    except Exception:
                        pass

                    self.finish_connection_dialog_failed(err)

                    if show_disconnect_popup:
                        # Manual/user-visible connection failure.
                        # For Settings Connect, keep the active progress dialog
                        # and convert it to failed. Closing it first can leave the
                        # UI visually stuck at "Connecting...".
                        if not (origin_safe == "settings" and self.is_settings_tab_active()):
                            try:
                                existing = getattr(self, "connection_dialog", None)
                                if existing is not None:
                                    existing.blockSignals(True)
                                    existing.close()
                                    existing.deleteLater()
                            except Exception:
                                pass
                            self.connection_dialog = None

                        if origin_safe == "settings" and self.is_settings_tab_active():
                            # User pressed Connect while already in Settings:
                            # update the SAME progress dialog to failed state.
                            # Do not close/delete it, otherwise it can remain stuck
                            # visually at "Connecting...".
                            self.suspend_locking_for_pi_disconnect(err)
                            self.convert_connection_dialog_to_disconnect_failed(err)
                            self.start_pi_disconnect_retry_loop(err)
                        elif origin_safe == "startup":
                            self.suspend_locking_for_pi_disconnect(err)
                            if not getattr(self, "_startup_disconnect_popup_shown", False):
                                self._startup_disconnect_popup_shown = True
                                self.show_pi_disconnect_alert_if_needed(err, origin="startup")
                            self.start_pi_disconnect_retry_loop(err)
                        else:
                            self.keep_pi_disconnected_warning_active(err)
                    else:
                        self.suspend_locking_for_pi_disconnect(err)
                        if origin_safe == "settings" and show_progress:
                            self.convert_connection_dialog_to_disconnect_failed(err)
                        self.start_pi_disconnect_retry_loop(err)

                    self.handle_startup_background_check_result(False, err)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def verify_pi_status_after_action(self, action_name: str = "ACTION"):
        """Check whether Pi API is still online after a failed action.

        Some Pi endpoints can fail because the camera process is busy/stopping,
        but the API is still online. In that case SAS should stay connected and
        should not force the user back to Settings.
        """
        def worker():
            try:
                status = self._face_api_request("GET", "/status", timeout=5)

                def online(status=status):
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_capture_in_progress(bool(status.get("capture_running", False)))
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self.append_face_log(f"{action_name}_STATUS: API online")

                self.qt_after(0, online)

            except Exception as e:
                err = str(e)

                def offline(err=err):
                    self.handle_pi_runtime_disconnect(
                        f"Pi disconnected or unreachable after {action_name}. Please check Pi. {err}"
                    )

                self.qt_after(0, offline)

        Thread(target=worker, daemon=True).start()


    def _face_api_stop_recognition(self):
        """Handle the SAS STOP button without stopping Pi unlock recognition.

        Normal recognition:
        - STOP closes only the Windows SAS preview. The Pi camera continues face
          recognition in the background, so a locked workstation can still unlock.

        Capture:
        - STOP asks the Pi to end capture, waits for the Pi camera to be released,
          then asks the Pi to restart background recognition. The SAS preview stays
          closed and the user does not need to remember to press Recognize again.
        """
        self.face_action_feedback("STOP: Stop requested by user")
        if not getattr(self, "pi_connected", False):
            self.face_action_feedback("STOP_FAILED: Pi API is not connected")
            self.show_pi_disconnected_popup("Pi API is not connected. Please connect from Settings first.")
            return

        was_manual_capture = bool(getattr(self, "manual_capture_active", False))
        was_capture_active = bool(getattr(self, "face_capture_in_progress", False))
        manual_user = getattr(self, "manual_capture_user", None)

        # STOP in SAS always closes the local Windows preview immediately.
        # It must not stop Pi recognition unless an SAS capture is active.
        self._camera_user_stopped = True
        self.stop_camera_preview(show_prompt=True)

        if not was_capture_active:
            self.face_action_feedback(
                "STOP: SAS video preview stopped. Pi face recognition remains active for workstation unlock."
            )
            return

        self.face_action_feedback(
            "STOP: Ending Pi capture. Pi recognition will restart automatically; SAS preview stays closed."
        )

        def worker():
            try:
                # /stop-capture affects only the Pi capture process. It does not
                # call the Pi's full STOP action, so normal recognition can return.
                data = self._face_api_request("POST", "/stop-capture", timeout=20)
                message = str(data.get("message", "Capture stop requested.")).strip()

                capture_stopped, _ = self.wait_until_pi_capture_complete(timeout_seconds=18)
                if not capture_stopped:
                    raise RuntimeError("Pi capture did not stop in time. Please wait and try STOP again.")

                # PiCamera2 may take a moment to release the device after capture.
                # Retry the normal recognition request instead of treating a brief
                # camera-busy response as a Pi disconnection.
                recognition_ready = False
                last_start_error = ""
                for _attempt in range(6):
                    try:
                        self._face_api_request("POST", "/start-recognition", timeout=20)
                    except Exception as start_error:
                        last_start_error = str(start_error)

                    recognition_ready, _ = self.wait_until_pi_recognition_running(timeout_seconds=4)
                    if recognition_ready:
                        break

                    time.sleep(0.8)

                if not recognition_ready:
                    detail = f" Last Pi response: {last_start_error}" if last_start_error else ""
                    raise RuntimeError("Pi capture stopped, but Pi recognition did not restart in time." + detail)

                def done():
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_capture_in_progress(False)
                    self.set_capture_button_manual_mode(False)
                    self.manual_capture_user = None
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)

                    self.face_action_feedback(
                        f"STOP: {message} Pi recognition is running in the background; SAS preview remains stopped."
                    )

                    if was_manual_capture or was_capture_active:
                        frames = self.get_user_capture_frames_from_pi(manual_user) if manual_user else 0
                        if manual_user:
                            self.face_action_feedback(
                                f"MANUAL_CAPTURE_COMPLETE: {str(manual_user).upper()} | {frames} capture frames"
                            )
                            self.show_capture_complete_popup(manual_user, frames)
                        self._face_api_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.face_action_feedback(f"STOP_FAILED: {err}")
                    # Keep the preview closed. The status refresh restores the
                    # correct button state without falsely declaring Pi offline.
                    self.verify_pi_status_after_action("STOP")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def _face_api_get_result(self):
        self.face_action_feedback("RECOGNITION: User pressed Recognize")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        # The button is greyed out during capture, but keep this guard as a
        # race-safe fallback in case a click was queued just before it disabled.
        if bool(getattr(self, "face_capture_in_progress", False)):
            self.face_action_feedback(
                "RECOGNITION_BLOCKED: Capture is still running. Press STOP, wait for Pi camera to stop, then press Recognize."
            )
            return

        """Recognize button starts recognition on the Pi."""
        def worker():
            try:
                data = self._face_api_request("POST", "/start-recognition", timeout=20)
                message = data.get("message", "Recognition start requested.")
                def done():
                    self._camera_user_stopped = False
                    self.face_action_feedback(f"RECOGNITION: {message}")
                    self.stop_camera_preview()

                    # Give Pi video-feed a short moment to warm up before OpenCV connects.
                    # This avoids false "feed lost" when recognition is already running.
                    QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))

                    # Do not call _face_api_test_connection() here.
                    # Recognition should not show the connection-success popup again.
                    self._face_api_refresh_users()

                self.qt_after(0, done)
            except Exception as e:
                err = str(e)
                def fail(err=err):
                    self.face_action_feedback(f"RECOGNITION_FAILED: {err}")
                    # A busy camera can reject /start-recognition while the Pi API
                    # is still healthy. Recheck /status instead of treating it as a
                    # network disconnect.
                    self.verify_pi_status_after_action("RECOGNITION")
                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def parse_training_progress_details(self, data: dict):
        """Parse Pi /train response progress.

        Pi train_model emits messages such as:
        "Trained: /image_0.jpg"
        We extract NTID and image count so the popup can show who was trained.
        """
        progress = data.get("progress", []) or []
        trained = []

        for msg in progress:
            text = str(msg).strip()
            if text.lower().startswith("trained:"):
                file_key = text.split(":", 1)[1].strip()
                trained.append(file_key)

        users = {}
        for file_key in trained:
            parts = file_key.replace("\\", "/").split("/")
            ntid = parts[0].strip().upper() if parts and parts[0].strip() else "UNKNOWN"
            users.setdefault(ntid, 0)
            users[ntid] += 1

        # Some Pi APIs may return trained users directly instead of progress lines.
        for key in ("users", "trained_users", "trained_user_ids"):
            api_users = data.get(key, None)
            if isinstance(api_users, list):
                for uid in api_users:
                    uid = str(uid).strip().upper()
                    if uid:
                        users.setdefault(uid, 0)
            elif isinstance(api_users, dict):
                for uid, count in api_users.items():
                    uid = str(uid).strip().upper()
                    if uid:
                        try:
                            users[uid] = int(count)
                        except Exception:
                            users.setdefault(uid, 0)

        new_faces = int(data.get("new_faces", 0) or 0)

        if users:
            owner_text = ", ".join([f"{ntid} ({count} image{'s' if count != 1 else ''})" for ntid, count in users.items()])
            return f"Trained image owner: {owner_text}", users, trained

        if new_faces == 0:
            return "No new image was trained. Dataset is already up to date.", {}, []

        return f"Training completed. New faces trained: {new_faces}", {}, trained

    def wait_until_pi_camera_stopped(self, timeout_seconds: int = 14):
        """Wait until Pi API reports recognition/capture is stopped before training."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status

                rec = bool(status.get("recognition_running", False))
                cap = bool(status.get("capture_running", False))
                training = bool(status.get("training_running", False))

                if not rec and not cap and not training:
                    return True, status
            except Exception:
                pass

            time.sleep(0.25)

        return False, last_status or {}

    def wait_until_pi_training_finished(
        self,
        timeout_seconds: int = 300,
        training_id: str = "",
        progress_callback=None,
    ):
        """Wait for the specific asynchronous Pi /train operation to finish.

        New Pi builds expose ``last_training_id`` and ``training_state``.  The
        ID avoids a polling race where SAS sees an old idle status before the
        newly requested training thread reports itself as running.
        """
        import time
        start = time.time()
        last_status = None
        seen_training = False
        expected_id = str(training_id or "").strip()

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status

                if callable(progress_callback):
                    try:
                        progress_callback(status)
                    except Exception:
                        pass

                reported_id = str(status.get("last_training_id") or "").strip()
                if expected_id and reported_id and reported_id != expected_id:
                    time.sleep(0.35)
                    continue

                training = bool(status.get("training_running", False))
                state = str(status.get("training_state") or "").strip().lower()

                if state in ("completed", "failed"):
                    return True, status
                if training:
                    seen_training = True
                elif seen_training or (not expected_id and time.time() - start >= 1.0):
                    return True, status
            except Exception:
                pass

            time.sleep(0.35)

        return False, last_status or {}

    def update_training_dialog_progress_from_status(self, status: dict):
        """Forward real Pi train counters to the SAS modal on the Qt thread."""
        if not isinstance(status, dict):
            return

        try:
            processed = int(status.get("training_processed", 0) or 0)
            total = int(status.get("training_total", 0) or 0)
            percent = int(status.get("training_percent", 0) or 0)
            message = str(status.get("training_message", "") or "")
            phase = str(status.get("training_phase", "training") or "training")
            skipped = int(status.get("training_skipped_images", 0) or 0)
            already_trained = int(status.get("training_already_trained", 0) or 0)
            dataset_total = int(status.get("training_dataset_total", 0) or 0)
        except Exception:
            return

        def apply():
            dialog = getattr(self, "training_dialog", None)
            if dialog is None:
                return
            updater = getattr(dialog, "set_live_progress", None)
            if callable(updater):
                updater(
                    processed=processed,
                    total=total,
                    percent=percent,
                    message=message,
                    phase=phase,
                    skipped=skipped,
                    already_trained=already_trained,
                    dataset_total=dataset_total,
                )

        self.qt_after(0, apply)

    def ensure_pi_recognition_after_training(self, timeout_seconds: int = 35):
        """Confirm Pi recognition is running, requesting a safe restart if needed.

        The Pi normally restores recognition itself after training.  SAS also
        performs this controlled fallback so a workstation cannot be left
        unable to unlock when a short camera-release delay prevents the first
        Pi restart attempt.
        """
        import time
        start = time.time()
        last_error = ""

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                if (
                    bool(status.get("recognition_running", False))
                    and not bool(status.get("capture_running", False))
                    and not bool(status.get("training_running", False))
                ):
                    return True, status

                # Never start recognition while the Pi is still training or
                # releasing a capture session.  Retry after a short delay.
                if bool(status.get("training_running", False)) or bool(status.get("capture_running", False)):
                    time.sleep(0.7)
                    continue

                try:
                    self._face_api_request("POST", "/start-recognition", timeout=15)
                except Exception as e:
                    last_error = str(e)

            except Exception as e:
                last_error = str(e)

            time.sleep(1.0)

        status = {"last_start_error": last_error} if last_error else {}
        return False, status

    def wait_until_pi_recognition_running(self, timeout_seconds: int = 20):
        """Confirm that Pi recognition has resumed after a camera workflow."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status
                if (
                    bool(status.get("recognition_running", False))
                    and not bool(status.get("capture_running", False))
                    and not bool(status.get("training_running", False))
                ):
                    return True, status
            except Exception:
                pass

            time.sleep(0.35)

        return False, last_status or {}

    def set_face_controls_training_busy(self, busy: bool):
        """Grey out controls while training is running."""
        for name in ("face_capture_btn", "face_train_btn", "face_recognize_btn", "face_stop_btn", "face_delete_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setEnabled(not busy)
                btn.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.PointingHandCursor)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()

        if hasattr(self, "ntid_input"):
            self.ntid_input.setEnabled(not busy)

    def _face_api_train(self):
        self.face_action_feedback("TRAIN: User pressed Train")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        ntid = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""

        # Train works on the whole dataset.
        # NTID field is ignored for Train, because training does not depend on one user ID.
        if hasattr(self, "clear_ntid_input_error"):
            self.clear_ntid_input_error()

        self.set_face_controls_training_busy(True)

        self.training_dialog = TrainingProgressDialog(
            self,
            ntid="DATASET",
            compact_mode=self.compact_mode
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - self.training_dialog.width()) // 2
        y = geo.y() + (geo.height() - self.training_dialog.height()) // 2
        self.training_dialog.move(x, y)
        self.pause_camera_for_modal()
        self.training_dialog.finished.connect(lambda _: self.resume_camera_after_modal())
        self.training_dialog.show()

        # This flag lets an in-flight auto-capture worker finish cleanly without
        # opening a separate Capture Complete card while the user is moving
        # directly from Capture to Train.
        self._training_waiting_for_capture_stop = bool(
            getattr(self, "face_capture_in_progress", False)
        )
        self.face_action_feedback("TRAIN: preparing Pi dataset training while recognition remains active...")

        def worker():
            try:
                # A Train request is allowed during SAS capture. End the capture
                # first, wait until the Pi releases its camera, then start the
                # dataset-only training job. This works for both manual and
                # auto-capture without requiring the user to press STOP first.
                capture_active = bool(getattr(self, "face_capture_in_progress", False))
                try:
                    status_before_train = self._face_api_request("GET", "/status", timeout=10)
                    capture_active = capture_active or bool(
                        status_before_train.get("capture_running", False)
                    )
                except Exception:
                    # The /train request below still gives a clear API error if
                    # the Pi cannot be reached. Keep the local state as fallback.
                    pass

                if capture_active:
                    self._training_waiting_for_capture_stop = True
                    self.qt_after(0, lambda: self.training_dialog.status_label.setText(
                        "Ending active capture before training..."
                    ))
                    self.qt_after(0, lambda: self.stop_camera_preview(show_prompt=True))
                    self.face_action_feedback(
                        "TRAIN: Capture is active. Ending capture before starting training..."
                    )

                    stop_data = self._face_api_request("POST", "/stop-capture", timeout=20)
                    stop_message = str(stop_data.get("message", "Capture stop requested.")).strip()
                    capture_stopped, _capture_status = self.wait_until_pi_capture_complete(
                        timeout_seconds=25
                    )
                    if not capture_stopped:
                        raise RuntimeError(
                            "Pi capture did not stop in time. Training was not started."
                        )

                    def capture_ended_for_training():
                        self.set_face_capture_in_progress(False)
                        self.set_capture_button_manual_mode(False)
                        self.manual_capture_user = None
                        self.face_action_feedback(
                            f"TRAIN: {stop_message} Capture ended; starting training now."
                        )

                    self.qt_after(0, capture_ended_for_training)

                # Training works on stored dataset images, not Picamera2. Close
                # only the SAS preview modal; Pi recognition continues running
                # so the workstation can still be unlocked while training runs.
                self.qt_after(0, lambda: self.training_dialog.status_label.setText("Preparing dataset training on Pi..."))
                self.qt_after(0, lambda: self.stop_camera_preview(show_prompt=True))
                self.face_action_feedback("TRAIN: Pi recognition remains active while dataset training runs")

                self.qt_after(0, lambda: self.training_dialog.status_label.setText("Calling Pi /train API..."))
                self.face_action_feedback("TRAIN: Pi /train request submitted")

                # Pi /train starts an asynchronous task. Wait for the specific
                # operation to finish, then ensure recognition is available for
                # workstation unlock again.
                data = self._face_api_request("POST", "/train", timeout=30)
                ok = bool(data.get("ok", True))
                message = data.get("message", "Training started.")
                detail = ""
                users = {}
                trained_files = []
                new_faces = 0

                if ok:
                    training_id = str(data.get("training_id") or "").strip()
                    self.qt_after(0, lambda: self.training_dialog.status_label.setText("Training face data on Pi..."))
                    training_finished, final_status = self.wait_until_pi_training_finished(
                        timeout_seconds=300,
                        training_id=training_id,
                        progress_callback=self.update_training_dialog_progress_from_status,
                    )
                    if not training_finished:
                        raise RuntimeError("Pi training did not finish in time.")

                    training_error = str(final_status.get("last_training_error") or "").strip()
                    if training_error:
                        raise RuntimeError(f"Pi training failed: {training_error}")

                    # Normal path: recognition never stopped. If the camera was
                    # interrupted externally, recover it only as a safety net.
                    recognition_running = bool(final_status.get("recognition_running", False))
                    if not recognition_running:
                        self.qt_after(0, lambda: self.training_dialog.status_label.setText("Restoring interrupted Pi recognition..."))
                        recognition_resumed, resume_status = self.ensure_pi_recognition_after_training(timeout_seconds=35)
                        if not recognition_resumed:
                            last_start_error = str(resume_status.get("last_start_error") or "").strip()
                            suffix = f" Last Pi response: {last_start_error}" if last_start_error else ""
                            raise RuntimeError("Training finished, but Pi recognition could not be restored." + suffix)

                    new_faces = int(final_status.get("last_training_new_faces", 0) or 0)
                    checked_images = int(final_status.get("training_processed", 0) or 0)
                    new_image_total = int(final_status.get("training_total", 0) or 0)
                    skipped_images = int(final_status.get("training_skipped_images", 0) or 0)
                    already_trained = int(final_status.get("training_already_trained", 0) or 0)
                    dataset_total = int(final_status.get("training_dataset_total", 0) or 0)

                    if new_image_total == 0:
                        # The completion title and dataset summary already make
                        # this state clear. Keep the main result line empty so
                        # the popup does not show a redundant "No new images"
                        # sentence under "Training Complete".
                        message = ""
                    elif new_faces > 0:
                        message = f"{new_faces} valid face image(s) trained."
                    else:
                        message = "No new image produced a valid face encoding."

                    summary_parts = []
                    if dataset_total:
                        summary_parts.append(
                            f"Dataset scan: {dataset_total} image{'s' if dataset_total != 1 else ''}."
                        )
                    if new_image_total:
                        summary_parts.append(
                            f"New images checked: {checked_images}/{new_image_total}."
                        )
                    if skipped_images:
                        summary_parts.append(
                            f"Skipped: {skipped_images} image{'s' if skipped_images != 1 else ''} did not produce one usable face encoding."
                        )
                    if already_trained:
                        summary_parts.append(
                            f"Already trained: {already_trained} image{'s' if already_trained != 1 else ''} not reprocessed."
                        )
                    summary_parts.append(
                        "Pi recognition remained active and reloaded the updated face model without reopening the camera."
                    )
                    detail = " ".join(summary_parts)

                if ok:
                    def success_done():
                        self._training_waiting_for_capture_stop = False
                        self.face_action_feedback(f"TRAIN_COMPLETE: {message} | new_faces={new_faces}")
                        if trained_files:
                            for file_key in trained_files[-8:]:
                                self.face_action_feedback(f"TRAINED_IMAGE: {file_key}")
                        if hasattr(self, "training_dialog") and self.training_dialog is not None:
                            self.training_dialog.set_processing_users(users)
                            self.training_dialog.complete_success(message, detail=detail)
                        self.set_face_controls_training_busy(False)
                        self._face_api_refresh_users()
                        self._face_api_load_logs()

                    self.qt_after(0, success_done)
                else:
                    def fail_done():
                        self._training_waiting_for_capture_stop = False
                        self.face_action_feedback(f"TRAIN_FAILED: {message}")
                        if hasattr(self, "training_dialog") and self.training_dialog is not None:
                            self.training_dialog.complete_failed(message, detail=detail)
                        self.set_face_controls_training_busy(False)
                        self._face_api_load_logs()

                    self.qt_after(0, fail_done)

            except Exception as e:
                # Exception variables are cleared once an ``except`` block ends.
                # Capture the text now, otherwise the deferred Qt callback can
                # raise NameError and leave the progress dialog stuck forever.
                err = str(e)

                def error_done(err=err):
                    self._training_waiting_for_capture_stop = False
                    self.face_action_feedback(f"TRAIN_FAILED: {err}")
                    if hasattr(self, "training_dialog") and self.training_dialog is not None:
                        self.training_dialog.complete_failed(err, detail="Training did not complete on the Pi.")
                    self.set_face_controls_training_busy(False)
                    self._face_api_load_logs()

                self.qt_after(0, error_done)

        Thread(target=worker, daemon=True).start()


    def set_ntid_input_error(self, message: str = "Please enter NTID before capture"):
        """Highlight NTID field red and show a short prompt in the input."""
        if not hasattr(self, "ntid_input"):
            return

        self.ntid_input.setObjectName("NtidInputError")
        self.ntid_input.setPlaceholderText(message)
        self.ntid_input.style().unpolish(self.ntid_input)
        self.ntid_input.style().polish(self.ntid_input)
        self.ntid_input.update()
        self.ntid_input.setFocus()

    def clear_ntid_input_error(self):
        """Restore NTID field style when user starts typing again."""
        if not hasattr(self, "ntid_input"):
            return

        if self.ntid_input.objectName() != "NtidInputError":
            return

        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter valid NTID for capture / delete")
        self.ntid_input.style().unpolish(self.ntid_input)
        self.ntid_input.style().polish(self.ntid_input)
        self.ntid_input.update()

    def validate_primary_ntid(self, action_name: str = "this action") -> str:
        """Validate NTID before Capture / Delete.

        Only NTIDs that pass Active Directory validation can continue.
        """
        user_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""

        if not user_id:
            self.append_face_log(f"{action_name.upper()}_FAILED: Please enter NTID first")
            self.set_ntid_input_error(f"Please enter NTID before {action_name.lower()}")
            return ""

        # Basic input guard before calling AD.
        if not user_id.isdigit():
            self.append_face_log(f"{action_name.upper()}_FAILED: Invalid NTID format {user_id}")
            self.set_ntid_input_error("Invalid NTID format")
            return ""

        self.face_action_feedback(f"{action_name.upper()}: Validating NTID {user_id.upper()}...")

        try:
            valid = self._validate_ntid_in_ad(user_id)
        except Exception as e:
            valid = False
            self.append_face_log(f"{action_name.upper()}_FAILED: NTID validation error: {e}")

        if not valid:
            self.append_face_log(f"{action_name.upper()}_FAILED: Invalid NTID {user_id.upper()}")
            self.set_ntid_input_error("Invalid NTID. Please enter a valid NTID.")
            return ""

        self.clear_ntid_input_error()
        return user_id


    def set_capture_button_manual_mode(self, active: bool):
        """Switch Capture button between CAPTURE and TAKE PHOTO."""
        self.manual_capture_active = bool(active)

        btn = getattr(self, "face_capture_btn", None)
        if btn is None:
            return

        if active:
            btn.setText("◎  TAKE PHOTO")
            btn.setObjectName("GreenActionButton")
            btn.setToolTip("Manual capture mode: click once for each photo.")
        else:
            btn.setText("＋  CAPTURE")
            btn.setObjectName("OutlineActionButton")
            btn.setToolTip("Start face capture.")

        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    def _face_api_take_photo(self):
        """Save one photo while manual capture mode is active."""
        if not getattr(self, "manual_capture_active", False):
            self.face_action_feedback("TAKE_PHOTO_FAILED: Manual capture is not active. Press Capture first.")
            return

        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        manual_user = getattr(self, "manual_capture_user", None)

        def worker():
            try:
                data = self._face_api_request("POST", "/capture-photo", timeout=25)
                message = data.get("message", "Take Photo requested.")
                count = data.get("manual_capture_count", data.get("count", ""))
                suffix = f" | photo #{count}" if count != "" else ""

                def done():
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self.face_action_feedback(f"TAKE_PHOTO: {message}{suffix}")
                    self._face_api_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.face_action_feedback(f"TAKE_PHOTO_FAILED: {err}")
                    # Keep manual mode active; user can try again or press Stop.
                    if manual_user:
                        self.manual_capture_user = manual_user
                    self.set_capture_button_manual_mode(True)
                    self.verify_pi_status_after_action("TAKE_PHOTO")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def _face_api_capture_user(self):
        self.face_action_feedback("CAPTURE: User pressed Capture")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        # If manual capture is already running, Capture button behaves as Take Photo.
        if getattr(self, "manual_capture_active", False):
            self._face_api_take_photo()
            return

        if bool(getattr(self, "face_capture_in_progress", False)):
            self.face_action_feedback("CAPTURE_BLOCKED: Capture is already starting or running. Use STOP before starting another camera action.")
            return

        user_id = self.validate_primary_ntid("capture")
        if not user_id:
            return

        initial_auto_capture = self.auto_capture_toggle.is_enabled() if hasattr(self, "auto_capture_toggle") else bool(getattr(self, "auto_capture_enabled", False))

        # Disable Recognize before the HTTP request starts, so a fast second
        # click cannot queue recognition while PiCamera2 is entering capture.
        self.set_face_capture_in_progress(True)

        def worker():
            try:
                # SAS Settings toggle is the source of truth.
                # Do not re-read Pi settings here, because a delayed/stale Pi setting can
                # turn manual capture back into auto-capture after the user disabled it.
                auto_capture = bool(initial_auto_capture)

                # Best effort sync to Pi before starting capture.
                try:
                    ntid_saved, password_saved, server_saved = self.get_saved_server_credentials()
                    if ntid_saved and password_saved and server_saved:
                        self._face_api_sync_settings_to_pi(
                            ntid_saved,
                            password_saved,
                            server_saved,
                            auto_capture,
                        )
                except Exception as sync_err:
                    self.append_face_log(f"AUTO_CAPTURE_PRE_CAPTURE_SYNC_WARNING: {sync_err}")

                data = self._face_api_request(
                    "POST",
                    "/capture-user",
                    {"user_id": user_id, "mode": "add", "auto_capture": bool(auto_capture)},
                    timeout=90,
                )
                message = data.get("message", "Capture requested.")

                def started():
                    self.auto_capture_enabled = bool(auto_capture)
                    if hasattr(self, "auto_capture_toggle"):
                        self.auto_capture_toggle.set_checked(bool(auto_capture))

                    self._camera_user_stopped = False
                    self.set_face_capture_in_progress(True)
                    self.face_action_feedback(f"CAPTURE: {user_id.upper()} | {message}")
                    self.stop_camera_preview()
                    QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))

                    if not auto_capture:
                        self.manual_capture_user = user_id
                        self.set_capture_button_manual_mode(True)
                        self.face_action_feedback("MANUAL_CAPTURE: Click TAKE PHOTO for each image, then press STOP when finished.")

                self.qt_after(0, started)

                # Auto mode completes automatically after Pi captures up to AUTO_LIMIT.
                if auto_capture:
                    capture_done, status = self.wait_until_pi_capture_complete(timeout_seconds=90)
                    if not capture_done:
                        raise RuntimeError("Capture did not complete in time. Please check the Pi camera.")

                    frames = self.get_user_capture_frames_from_pi(user_id)
                    recognition_resumed, _resume_status = self.wait_until_pi_recognition_running(timeout_seconds=25)
                    if not recognition_resumed:
                        raise RuntimeError("Capture completed, but Pi recognition did not restart in time.")

                    def complete():
                        self.set_face_capture_in_progress(False)
                        if bool(getattr(self, "_training_waiting_for_capture_stop", False)):
                            self.face_action_feedback(
                                f"CAPTURE_ENDED_FOR_TRAINING: {user_id.upper()} | {frames} capture frames"
                            )
                        else:
                            self.face_action_feedback(f"CAPTURE_COMPLETE: {user_id.upper()} | {frames} capture frames")
                            self.show_capture_complete_popup(user_id, frames)
                            self.face_action_feedback(
                                "CAPTURE_COMPLETE: Pi recognition is running again in the background. "
                                "Press Recognize only when you want to reopen the SAS video preview."
                            )
                        self._face_api_refresh_users()

                    self.qt_after(0, complete)

            except Exception as e:
                err = str(e)
                def fail(err=err):
                    self.face_action_feedback(f"CAPTURE_FAILED: {err}")
                    self.set_face_capture_in_progress(False)
                    self.set_capture_button_manual_mode(False)
                    self.manual_capture_user = None
                    # Do not mark Pi disconnected just because capture start failed.
                    # API may still be online; keep Face tab usable.
                    self.verify_pi_status_after_action("CAPTURE")
                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def _face_api_delete_user(self):
        self.face_action_feedback("DELETE: User pressed Delete")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        user_id = self.validate_primary_ntid("delete")
        if not user_id:
            return

        # Prevent repeated clicks while stopping/deleting.
        self.set_face_controls_training_busy(True)
        self.face_action_feedback(f"DELETE: Stopping active processes before deleting {user_id.upper()}...")

        def worker():
            try:
                # Stop all Pi camera processes first.
                # Pi delete API refuses deletion when recognition/capture/training is still running.
                for endpoint in ("/stop-recognition", "/stop-capture", "/stop"):
                    try:
                        self._face_api_request("POST", endpoint, timeout=15)
                    except Exception:
                        pass

                self.qt_after(0, lambda: self.stop_camera_preview(show_prompt=True))

                stopped_ok, status = self.wait_until_pi_camera_stopped(timeout_seconds=14)
                if not stopped_ok:
                    raise RuntimeError(
                        "Pi process did not stop in time. Please press Stop and try Delete again."
                    )

                self.qt_after(0, lambda: self.face_action_feedback(
                    f"DELETE: Pi processes stopped. Deleting {user_id.upper()}..."
                ))

                data = self._face_api_request("POST", "/delete-user", {"user_id": user_id}, timeout=60)
                message = data.get("message", "Delete requested.")

                dataset_removed = bool(data.get("dataset_removed", False))
                encodings_removed = int(data.get("encodings_removed", 0) or 0)

                def done():
                    self.face_action_feedback(f"DELETE_COMPLETE: {user_id.upper()} | {message}")
                    self.show_delete_complete_popup(
                        ntid=user_id,
                        dataset_removed=dataset_removed,
                        encodings_removed=encodings_removed,
                    )
                    self._face_api_refresh_users()
                    self._face_api_load_logs()
                    self.set_face_controls_training_busy(False)

                    if hasattr(self, "ntid_input"):
                        self.ntid_input.clear()

                self.qt_after(0, done)

            except Exception as e:
                def fail():
                    self.face_action_feedback(f"DELETE_FAILED: {e}")
                    self.set_face_controls_training_busy(False)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def _face_api_refresh_users(self, show_popup_after: bool = False):
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("PI_SKIPPED: Pi hostname/IP is not configured.")
            return

        """Fetch authorised users from Pi API /users.

        Background refresh updates UI only. It never opens the View All popup,
        because that caused unstable popups appearing without user action.
        """
        def worker():
            try:
                data = self._face_api_request("GET", "/users")
                users = data.get("users", [])

                def done():
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self.face_users_cache = users
                    self.render_dashboard_users(users)

                    if hasattr(self, "face_users_layout"):
                        self.render_face_users(users)

                    self.append_face_log(f"USERS_REFRESHED: {len(users)} records")

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    was_connected = getattr(self, "pi_connected", False)
                    self.pi_connection_checked = True
                    self.pi_connected = False
                    self.set_face_controls_connection_enabled(False)
                    self.set_pi_status_label(connected=False)
                    self.clear_all_authorized_users_ui()
                    if hasattr(self, "face_users_subtitle"):
                        self.face_users_subtitle.setText("CONNECT PI FIRST")
                    self.append_face_log(f"USERS_REFRESH_FAILED: {err}")
                    if was_connected:
                        self.handle_pi_runtime_disconnect("Pi disconnected while refreshing users. Please check Pi.")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def set_auto_capture_sync_status(self, text: str, ok: bool = False):
        """Auto-Capture sync status is no longer shown in the UI."""
        return


    def coerce_bool(self, value, default=False) -> bool:
        """Parse bool from Pi/SAS JSON safely."""
        if isinstance(value, bool):
            return value
        if value is None:
            return bool(default)
        if isinstance(value, (int, float)):
            return value != 0

        text = str(value).strip().lower()
        if text in ("true", "1", "yes", "y", "enabled", "enable", "on"):
            return True
        if text in ("false", "0", "no", "n", "disabled", "disable", "off"):
            return False

        return bool(default)



    def remember_session_credentials_after_save(self, ntid: str, password: str, server: str):
        """Keep credentials visible only during the current logged-in session."""
        self._session_settings_ntid = (ntid or "").strip()
        self._session_settings_password = password or ""
        self._session_settings_server = (server or "").strip()

    def apply_session_credentials_to_settings_ui(self):
        """Show current-session credentials after successful Save Connect."""
        try:
            if hasattr(self, "settings_ntid_input"):
                self.settings_ntid_input.setText(getattr(self, "_session_settings_ntid", "") or "")
        except Exception:
            pass
        try:
            if hasattr(self, "settings_password_input"):
                self.settings_password_input.setText(getattr(self, "_session_settings_password", "") or "")
        except Exception:
            pass
        try:
            if hasattr(self, "settings_server_path_input"):
                server = getattr(self, "_session_settings_server", "") or self.server_path
                if server:
                    self.settings_server_path_input.setText(server)
        except Exception:
            pass

    def clear_session_credentials_on_logout(self):
        """Clear visible/session NTID and password on logout."""
        self._session_settings_ntid = ""
        self._session_settings_password = ""
        self._session_settings_server = ""
        self._keep_session_credentials_visible = False
        try:
            if hasattr(self, "settings_ntid_input"):
                self.settings_ntid_input.setText("")
        except Exception:
            pass
        try:
            if hasattr(self, "settings_password_input"):
                self.settings_password_input.setText("")
        except Exception:
            pass

    def clear_sensitive_server_credentials_ui(self, clear_server_path: bool = False):
        """Clear sensitive NTID/password while keeping server path visible.

        Server path can remain visible for convenience. NTID/password are only
        shown after the current logged-in user successfully presses Save Connect,
        and are cleared again on logout/restart.
        """
        try:
            if hasattr(self, "settings_ntid_input") and not getattr(self, "_keep_session_credentials_visible", False):
                self.settings_ntid_input.setText("")
                self.settings_ntid_input.setPlaceholderText("Enter NTID")
        except Exception:
            pass

        try:
            if hasattr(self, "settings_password_input") and not getattr(self, "_keep_session_credentials_visible", False):
                self.settings_password_input.setText("")
                self.settings_password_input.setPlaceholderText("Enter password")
        except Exception:
            pass

        if clear_server_path:
            try:
                if hasattr(self, "settings_server_path_input"):
                    self.settings_server_path_input.setText("")
                    self.settings_server_path_input.setPlaceholderText("Select or enter shared server path")
            except Exception:
                pass


    def pull_pi_settings_to_sas(self, silent: bool = True):
        """Read non-sensitive Pi settings only.

        Security: do not auto-fill Server Credentials from the Pi API.
        Another user may start SAS on the same workstation, so NTID/password/
        server path must not appear just because Pi /settings returned them.
        """
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("PI_SKIPPED: Pi hostname/IP is not configured.")
            return

        def worker():
            try:
                data = self._face_api_request("GET", "/settings", timeout=10)

                def done():
                    try:
                        if isinstance(data, dict):
                            nested = data.get("settings", {})
                            if not isinstance(nested, dict):
                                nested = {}

                            # Non-sensitive setting only: auto_capture.
                            auto_capture = data.get("auto_capture", nested.get("auto_capture"))
                            if auto_capture is not None and hasattr(self, "auto_capture_toggle"):
                                self.auto_capture_enabled = bool(auto_capture)
                                self.auto_capture_toggle.set_enabled(self.auto_capture_enabled)

                            # Camera rotation is also non-sensitive. It is stored on
                            # the Pi so its local preview and SAS camera feed agree.
                            rotation = data.get("camera_rotation", nested.get("camera_rotation"))
                            if rotation is not None:
                                self.update_camera_rotation_ui(
                                    rotation,
                                    status=f"●  Pi setting: {self.camera_rotation_label(rotation)}",
                                    ok=True,
                                )

                        # Never show credentials fetched from Pi.
                        self.clear_sensitive_server_credentials_ui(clear_server_path=False)

                        if not silent:
                            self.append_system_log("Pi settings pulled securely. Server credentials were not displayed.")
                    except Exception as e:
                        self.append_system_log(f"Pi settings UI update skipped: {e}")

                self.qt_after(0, done)
            except Exception as e:
                def failed(err=e):
                    if not silent:
                        self.append_system_log(f"Unable to pull Pi settings: {err}")
                self.qt_after(0, failed)

        Thread(target=worker, daemon=True).start()


    def pull_auto_capture_setting_from_pi(self, silent: bool = True):
        """Backward-compatible wrapper. Now pulls full Pi settings."""
        self.pull_pi_settings_to_sas(silent=silent)



    def get_saved_server_credentials(self):
        """Read NTID/password/server path from the Settings page first, then credential.txt."""
        creds = self._read_credentials()

        ntid = self.settings_ntid_input.text().strip() if hasattr(self, "settings_ntid_input") else creds.get("ntid", "")
        password = self.settings_password_input.text().strip() if hasattr(self, "settings_password_input") else creds.get("password", "")
        server = self.settings_server_path_input.text().strip() if hasattr(self, "settings_server_path_input") else creds.get("server", self.server_path)

        if not ntid:
            ntid = creds.get("ntid", "")
        if not password:
            password = creds.get("password", "")
        if not server:
            server = creds.get("server", self.server_path)

        return ntid, password, server

    def validate_transfer_inputs(self, ntid: str, password: str, server: str, status_label=None) -> bool:
        """Validate transfer fields before export/import server action."""
        if not ntid.strip():
            if status_label is not None:
                self.set_transfer_status(status_label, "NTID / Username is required.", "error")
            return False

        if not password.strip():
            if status_label is not None:
                self.set_transfer_status(status_label, "Password is required.", "error")
            return False

        if not server.strip():
            if status_label is not None:
                self.set_transfer_status(status_label, "Server Path is required.", "error")
            return False

        if not (server.startswith("//") or server.startswith("\\") or ":" in server):
            if status_label is not None:
                self.set_transfer_status(status_label, "Server Path looks invalid. Please browse/select or enter a valid path.", "error")
            return False

        return True


    def set_transfer_status(self, label, text: str, state: str = "normal"):
        """Set Import/Export popup status colour."""
        if label is None:
            return

        label.setText(text)

        if state == "success":
            label.setObjectName("TransferStatusSuccess")
        elif state == "error":
            label.setObjectName("TransferStatusError")
        else:
            label.setObjectName("TransferStatus")

        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def start_transfer_button_loading(self, button, base_text: str):
        """Animate a loading icon inside a transfer button."""
        self.stop_transfer_button_loading(button)

        button.setEnabled(False)
        button._transfer_base_text = base_text
        button._transfer_spinner_index = 0
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        timer = QTimer(button)

        def tick():
            frame = frames[button._transfer_spinner_index % len(frames)]
            button._transfer_spinner_index += 1
            button.setText(f"{frame}  {base_text}")

        timer.timeout.connect(tick)
        timer.start(90)
        button._transfer_loading_timer = timer
        tick()


    def stop_transfer_button_loading(self, button):
        timer = getattr(button, "_transfer_loading_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        button._transfer_loading_timer = None

    def show_transfer_button_success(self, button, success_text: str, normal_text: str):
        """Show tick icon briefly, then return button to normal."""
        self.stop_transfer_button_loading(button)
        button.setEnabled(False)
        button.setText(f"✓  {success_text}")

        def restore():
            button.setText(normal_text)
            button.setEnabled(True)

        QTimer.singleShot(1300, restore)


    def show_transfer_button_failed(self, button, normal_text: str):
        """Return failed button to normal state."""
        self.stop_transfer_button_loading(button)
        button.setText(normal_text)
        button.setEnabled(True)


    def on_auto_capture_toggle_changed(self, enabled: bool):
        """When user changes Auto-Capture, save locally and sync to Pi if credentials exist."""
        self.auto_capture_enabled = bool(enabled)
        self.set_auto_capture_sync_status("●  Pi sync: Auto syncing...", ok=False)

        # Save locally immediately so the toggle persists even before Save Connect.
        try:
            creds = self._read_credentials()
            ntid = creds.get("ntid", "")
            password = creds.get("password", "")
            server = creds.get("server", self.server_path)
            timeout = int(creds.get("timeout", self.lock_timeout_seconds))

            self.credential_service.save_credentials(
                ntid,
                password,
                server,
                timeout,
                disable_keyboard=self.disable_keyboard_when_locked,
                disable_mouse=self.disable_mouse_when_locked,
                disable_usb=self.disable_usb_when_locked,
                enable_hotkey=self.enable_hotkey,
                pi_host=self.pi_api_host,
                pi_port="5000",
                auto_capture=bool(enabled),
                video_source="pi",
            )
        except Exception as e:
            print("[AUTO CAPTURE LOCAL SAVE ERROR]", e)

        # If credentials are already available, sync right away.
        # Otherwise, Save Connect will sync the value together with server credentials.
        ntid, password, server = self.get_saved_server_credentials()
        if ntid and password and server:
            self.sync_auto_capture_setting_now()
        else:
            self.set_auto_capture_sync_status("●  Pi sync: Save Connect required", ok=False)

    def sync_auto_capture_setting_now(self):
        """Auto-sync the Auto-Capture state to Pi using the same /settings endpoint.

        The Pi service stores auto_capture in settings.json and uses it as
        self.auto_capture_enabled, while capture_faces receives auto_capture=True/False.
        """
        auto_capture = self.auto_capture_toggle.is_enabled() if hasattr(self, "auto_capture_toggle") else False
        ntid, password, server = self.get_saved_server_credentials()

        if not ntid or not password or not server:
            self.set_auto_capture_sync_status("●  Pi sync: Save Connect required", ok=False)
            self.append_face_log("AUTO_CAPTURE_SYNC_FAILED: Server credentials are missing.")
            return

        self.set_auto_capture_sync_status("●  Pi sync: Syncing...", ok=False)

        def worker():
            ok = self._face_api_sync_settings_to_pi(
                ntid, password, server, auto_capture, self.camera_rotation
            )

            def done():
                if ok:
                    state = "Enabled" if auto_capture else "Disabled"
                    self.set_auto_capture_sync_status(f"●  Pi sync: {state}", ok=True)
                    self.append_face_log(f"AUTO_CAPTURE_SYNCED: {state}")
                else:
                    self.set_auto_capture_sync_status("●  Pi sync: Failed", ok=False)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()

    def _face_api_sync_settings_to_pi(
        self,
        ntid: str,
        password: str,
        server: str,
        auto_capture: bool,
        camera_rotation: int | None = None,
    ):
        """Sync Windows SAS Settings page to the Pi settings.json.

        This method may run in a worker thread. Any UI updates are scheduled
        through qt_after to keep the Qt UI responsive and thread-safe.
        """
        try:
            rotation = self.normalize_camera_rotation(
                getattr(self, "camera_rotation", 0) if camera_rotation is None else camera_rotation
            )
            payload = {
                "username": ntid,
                "password": password,
                "pc_save_path": server,
                "auto_capture": bool(auto_capture),
                "camera_rotation": rotation,
                "recognition_result_file": "recognition_result.json",
                "source": "Windows SAS",
            }

            data = self._face_api_request(
                "POST",
                "/settings",
                payload,
                timeout=45,
            )

            state = "Enabled" if auto_capture else "Disabled"
            message = data.get("message", "settings saved")

            def ui_done():
                self.auto_capture_enabled = bool(auto_capture)
                returned_settings = data.get("settings", {}) if isinstance(data, dict) else {}
                applied_rotation = self.normalize_camera_rotation(
                    data.get("camera_rotation", returned_settings.get("camera_rotation", rotation))
                    if isinstance(data, dict) else rotation,
                    default=rotation,
                )
                self.update_camera_rotation_ui(
                    applied_rotation,
                    status=f"●  Pi synced: {self.camera_rotation_label(applied_rotation)}",
                    ok=True,
                )

                if hasattr(self, "auto_capture_toggle"):
                    self.auto_capture_toggle.set_checked(bool(auto_capture))

                self.append_face_log(
                    f"PI_SETTINGS_SYNC: {message} | "
                    f"AUTO_CAPTURE={state} | CAMERA_ROTATION={applied_rotation} | "
                    "STATE_FILE=recognition_result.json"
                )

            self.qt_after(0, ui_done)
            return True

        except Exception as e:
            err = str(e)
            self.qt_after(0, lambda err=err: self.append_face_log(f"PI_SETTINGS_SYNC_FAILED: {err}"))
            return False


    def _face_api_load_logs(self):
        def worker():
            try:
                data = self._face_api_request("GET", "/logs", timeout=20)
                logs = data.get("logs", [])
                if logs:
                    def done():
                        self._system_log_lines = []
                        for line in logs[-8:]:
                            self.append_face_log(str(line))
                    self.qt_after(0, done)
            except Exception as e:
                self.qt_after(0, lambda: self.append_face_log(f"LOG_SYNC_FAILED: {e}"))

        Thread(target=worker, daemon=True).start()

    def clear_transfer_text_selection(self, dialog=None):
        """Prevent NTID / path fields from staying highlighted after button clicks."""
        target = dialog or getattr(self, "active_transfer_dialog", None)
        if target is None:
            return

        try:
            for edit in target.findChildren(QLineEdit):
                edit.deselect()
                edit.setCursorPosition(len(edit.text()))
                edit.clearFocus()
        except Exception:
            pass

    def _force_clear_card_dialog_background(self, force: bool = False):
        """Restore the dashboard after all frameless card popups are closed.

        Multiple card dialogs can overlap.  For example, the user can keep the
        SFTP send/success card open while the Pending Received card appears.
        In that situation closing one card must not clear the blur/dim layer
        for the other card, and closing the last card must clear every leftover
        dim overlay.  The open-count guard prevents stale dark backgrounds.
        """
        if not force and int(getattr(self, "_card_dialog_open_count", 0) or 0) > 0:
            return

        try:
            self._card_dialog_open_count = 0
        except Exception:
            pass

        # Remove every tracked dim overlay.
        overlays = list(getattr(self, "_card_dialog_dim_overlays", []) or [])
        overlay = getattr(self, "_transfer_dim_overlay", None)
        if overlay is not None and overlay not in overlays:
            overlays.append(overlay)
        for overlay in overlays:
            try:
                overlay.hide()
                overlay.deleteLater()
            except Exception:
                pass
        try:
            self._card_dialog_dim_overlays = []
            self._transfer_dim_overlay = None
        except Exception:
            pass

        # Remove any orphan dim overlays that were created before the current
        # tracked-list logic or by a dialog that closed out of order.
        try:
            for orphan in self.findChildren(QFrame, "DialogDimOverlay"):
                try:
                    orphan.hide()
                    orphan.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass

        root = self.centralWidget()
        if root is not None:
            try:
                root.setEnabled(True)
            except Exception:
                pass
            try:
                effect = root.graphicsEffect()
                if effect is not None:
                    root.setGraphicsEffect(cast(QGraphicsEffect, None))
                    effect.deleteLater()
            except Exception:
                try:
                    root.setGraphicsEffect(cast(QGraphicsEffect, None))
                except Exception:
                    pass

    def _show_card_dialog(self, dialog: QDialog):
        """Show a frameless card popup with shared blurred/disabled background."""
        root = self.centralWidget()
        already_open = int(getattr(self, "_card_dialog_open_count", 0) or 0) > 0
        self._card_dialog_open_count = int(getattr(self, "_card_dialog_open_count", 0) or 0) + 1

        if root is not None:
            try:
                root.setEnabled(False)
            except Exception:
                pass

            # Only create the blur/dim layer for the first active card.  If a
            # second card opens while the first one is still active, it shares
            # the same layer.  This fixes the stuck-dark dashboard after closing
            # overlapping SFTP and received-data popups.
            if not already_open:
                try:
                    blur = QGraphicsBlurEffect(self)
                    blur.setBlurRadius(0)
                    root.setGraphicsEffect(blur)
                    anim = QPropertyAnimation(blur, b"blurRadius", self)
                    anim.setDuration(220)
                    anim.setStartValue(0)
                    anim.setEndValue(5)
                    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    self._transfer_blur_anim = anim
                    anim.start()
                except Exception:
                    pass
                try:
                    dim_overlay = QFrame(self)
                    dim_overlay.setObjectName("DialogDimOverlay")
                    dim_overlay.setStyleSheet("background: rgba(0, 0, 0, 42); border: none;")
                    dim_overlay.setGeometry(self.rect())
                    dim_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    dim_overlay.show()
                    dim_overlay.raise_()
                    self._transfer_dim_overlay = dim_overlay
                    overlays = list(getattr(self, "_card_dialog_dim_overlays", []) or [])
                    overlays.append(dim_overlay)
                    self._card_dialog_dim_overlays = overlays
                except Exception:
                    self._transfer_dim_overlay = None
            else:
                try:
                    overlay = getattr(self, "_transfer_dim_overlay", None)
                    if overlay is not None:
                        overlay.setGeometry(self.rect())
                        overlay.show()
                        overlay.raise_()
                except Exception:
                    pass

        self.active_transfer_dialog = dialog

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y_offset = int(getattr(dialog, "_card_dialog_y_offset", 0) or 0)
        y = geo.y() + max(20, (geo.height() - dialog.height()) // 2) + y_offset
        y = max(geo.y() + 20, y)
        dialog.move(x, y)

        cleaned = {"done": False}

        def cleanup(*args):
            if cleaned["done"]:
                return
            cleaned["done"] = True
            try:
                self._card_dialog_open_count = max(0, int(getattr(self, "_card_dialog_open_count", 0) or 0) - 1)
            except Exception:
                self._card_dialog_open_count = 0
            if int(getattr(self, "_card_dialog_open_count", 0) or 0) <= 0:
                self._force_clear_card_dialog_background(force=True)
            else:
                # Keep the shared overlay alive for the remaining card.
                try:
                    root = self.centralWidget()
                    if root is not None:
                        root.setEnabled(False)
                    overlay = getattr(self, "_transfer_dim_overlay", None)
                    if overlay is not None:
                        overlay.setGeometry(self.rect())
                        overlay.show()
                        overlay.raise_()
                except Exception:
                    pass

        dialog.finished.connect(cleanup)
        dialog.destroyed.connect(cleanup)
        QTimer.singleShot(60, lambda: self.clear_transfer_text_selection(dialog))
        try:
            dialog.exec()
        finally:
            cleanup()
            # Run again after Qt processes deferred deleteLater events, but only
            # clear when all card dialogs have closed.
            QTimer.singleShot(0, lambda: self._force_clear_card_dialog_background(force=False))
            QTimer.singleShot(120, lambda: self._force_clear_card_dialog_background(force=False))
            if getattr(self, "active_transfer_dialog", None) is dialog:
                self.active_transfer_dialog = None


    def transfer_input_row(self, label_text: str, value: str = "", readonly: bool = False, password: bool = False, placeholder: str = ""):
        wrapper = QVBoxLayout()
        wrapper.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("TransferFieldLabel")
        wrapper.addWidget(label)

        box = QFrame()
        box.setObjectName("TransferInputBox")
        row = QHBoxLayout(box)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(8)

        edit = QLineEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        edit.setObjectName("TransferInput")
        edit.setText(value or "")
        edit.setReadOnly(readonly)
        edit.setMinimumHeight(34 if not self.compact_mode else 31)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)

        row.addWidget(edit, 1)
        wrapper.addWidget(box)
        return wrapper, edit, box, row

    def add_path_browse_button(self, row_layout, path_edit):
        """Folder icon opens folder picker and writes selected path into the field."""
        browse_btn = QPushButton("⌕")
        browse_btn.setObjectName("TransferIconButton")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip("Browse server folder")
        browse_btn.setFixedSize(28, 28)

        def browse_path():
            start_dir = path_edit.text().strip() or self.server_path or os.path.expanduser("~")
            parent_dialog = browse_btn.window()

            # Do NOT hide the transfer card here.
            # Hiding a modal QDialog can close/finish the dialog event loop,
            # so the Export/Import popup disappears after folder selection.
            selected = QFileDialog.getExistingDirectory(
                parent_dialog,
                "Select Server Path",
                start_dir,
                QFileDialog.Option.ShowDirsOnly,
            )

            if selected:
                path_edit.setText(selected.replace("\\", "/"))

            try:
                parent_dialog.raise_()
                parent_dialog.activateWindow()
            except Exception:
                pass

        browse_btn.clicked.connect(browse_path)
        row_layout.addWidget(browse_btn)
        return browse_btn


    def create_transfer_dialog_base(self, title_text: str, subtitle_text: str, icon_text: str, height: int = 620):
        dialog = QDialog(self)
        dialog.setObjectName("TransferDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(520 if not self.compact_mode else 470, height if not self.compact_mode else max(520, height - 70))

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("TransferCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(30 if not self.compact_mode else 22, 20 if not self.compact_mode else 18, 30 if not self.compact_mode else 22, 20 if not self.compact_mode else 18)
        root.setSpacing(9 if not self.compact_mode else 8)

        top_line = QFrame()
        top_line.setObjectName("TransferTopLine")
        top_line.setFixedHeight(1)
        root.addWidget(top_line)

        icon = QLabel(icon_text)
        icon.setObjectName("TransferHeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(56 if not self.compact_mode else 48, 56 if not self.compact_mode else 48)

        title = QLabel(title_text)
        title.setObjectName("TransferTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("TransferSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        if subtitle_text:
            root.addWidget(subtitle)

        return dialog, root

    def rebuild_export_loading_card(self, root, dialog):
        """Change the existing Export card content into the loading UI."""
        self.clear_layout_widgets(root)

        # Tighter layout to prevent overlay on laptop-sized screens.
        root.setContentsMargins(
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
        )
        root.setSpacing(12 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(6)

        system = QLabel("SECURE ACCESS")
        system.setObjectName("ExportStateEyebrow")

        active = QLabel("●  SYSTEM ACTIVE")
        active.setObjectName("ExportStateActive")

        left.addWidget(system)
        left.addWidget(active)

        shield = QLabel("🛡")
        shield.setObjectName("ExportStateShield")
        shield.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        header.addLayout(left, 1)
        header.addWidget(shield)
        root.addLayout(header)

        root.addSpacing(22 if not self.compact_mode else 16)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(14 if not self.compact_mode else 11)

        spinner_wrap = ExportCircleSpinnerWidget(
            dialog,
            size=112 if not self.compact_mode else 96,
            icon_text="⇧",
        )
        spinner_wrap.setObjectName("ExportCircleSpinner")

        title = QLabel("EXPORTING DATA")
        title.setObjectName("ExportStateTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(False)
        title.setMinimumWidth(360 if not self.compact_mode else 300)

        status = QLabel("Preparing export package...")
        status.setObjectName("ExportStateSubtitle")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setWordWrap(True)
        status.setMaximumWidth(380 if not self.compact_mode else 320)
        status.setMinimumWidth(320 if not self.compact_mode else 280)

        center.addWidget(spinner_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(status, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addLayout(center)

        root.addStretch(1)

        progress_outer = QFrame()
        progress_outer.setObjectName("ExportProgressOuter")
        progress_outer.setFixedHeight(5)

        progress_layout = QHBoxLayout(progress_outer)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        progress_fill = QFrame()
        progress_fill.setObjectName("ExportProgressFill")
        progress_layout.addWidget(progress_fill)
        progress_layout.addStretch(1)

        root.addWidget(progress_outer)

        footer = QHBoxLayout()
        footer.setSpacing(16)

        node_box = QVBoxLayout()
        node_box.setSpacing(3)
        node_lbl = QLabel("NODE")
        node_lbl.setObjectName("ExportMetricLabel")
        node_value = QLabel("PI API")
        node_value.setObjectName("ExportMetricValue")
        node_box.addWidget(node_lbl)
        node_box.addWidget(node_value)

        load_box = QVBoxLayout()
        load_box.setSpacing(3)
        load_lbl = QLabel("LOAD")
        load_lbl.setObjectName("ExportMetricLabel")
        load_value = QLabel("12.4%")
        load_value.setObjectName("ExportMetricValue")
        load_box.addWidget(load_lbl)
        load_box.addWidget(load_value)

        percentage = QLabel("34%")
        percentage.setObjectName("ExportPercentage")
        percentage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        footer.addLayout(node_box)
        footer.addLayout(load_box)
        footer.addStretch()
        footer.addWidget(percentage)

        root.addLayout(footer)

        dialog._export_spinner_widget = spinner_wrap
        dialog._export_spinner_index = 0
        dialog._export_progress = 34
        dialog._export_progress_fill = progress_fill
        dialog._export_progress_outer = progress_outer
        dialog._export_percentage_label = percentage
        dialog._export_status_label = status

        status_messages = [
            "Preparing export package...",
            "Validating dataset...",
            "Compressing files...",
            "Connecting to server...",
            "Writing backup archive...",
            "Finalising transfer..."
        ]
        dialog._export_status_index = 0

        timer = QTimer(dialog)

        def tick():
            try:
                dialog._export_spinner_index += 1
                # Spinner animation is handled by ExportCircleSpinnerWidget.
                # Do not complete before the real export finishes.
                # It can move slowly to 96%, then success will animate 96 → 100.
                if dialog._export_progress < 96 and dialog._export_spinner_index % 2 == 0:
                    dialog._export_progress += 1
                    percentage.setText(f"{dialog._export_progress}%")
                    progress_fill.setFixedWidth(max(8, int(progress_outer.width() * dialog._export_progress / 100)))

                if dialog._export_spinner_index % 10 == 0:
                    dialog._export_status_index = (dialog._export_status_index + 1) % len(status_messages)
                    status = getattr(self, "sftp_status_label", None) or QLabel("")
                    status.setText(status_messages[dialog._export_status_index])
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start(90)
        dialog._export_loading_timer = timer


    def stop_export_loading_timer(self, dialog):
        timer = getattr(dialog, "_export_loading_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
            dialog._export_loading_timer = None

        spinner = getattr(dialog, "_export_spinner_widget", None)
        if spinner is not None:
            try:
                spinner.stop()
            except Exception:
                pass


    def finish_export_progress_then_success(self, root, dialog, message: str, filename: str = ""):
        """Animate progress to 100% before changing to success content."""
        self.stop_export_loading_timer(dialog)

        progress_fill = getattr(dialog, "_export_progress_fill", None)
        progress_outer = getattr(dialog, "_export_progress_outer", None)
        percentage = getattr(dialog, "_export_percentage_label", None)
        status = getattr(dialog, "_export_status_label", None)

        if status is not None:
            status.setText("Finalising export package...")

        finish_timer = QTimer(dialog)

        def tick_finish():
            try:
                current = int(getattr(dialog, "_export_progress", 96))
                if current < 100:
                    current += 2
                    if current > 100:
                        current = 100
                    dialog._export_progress = current

                    if percentage is not None:
                        percentage.setText(f"{current}%")

                    if progress_fill is not None and progress_outer is not None:
                        progress_fill.setFixedWidth(max(8, int(progress_outer.width() * current / 100)))
                    return

                finish_timer.stop()
                finish_timer.deleteLater()

                if status is not None:
                    status.setText("Export completed.")

                QTimer.singleShot(260, lambda: self.rebuild_export_success_card(root, dialog, message, filename))
            except Exception:
                try:
                    finish_timer.stop()
                except Exception:
                    pass
                self.rebuild_export_success_card(root, dialog, message, filename)

        finish_timer.timeout.connect(tick_finish)
        finish_timer.start(70)
        tick_finish()

    def rebuild_export_success_card(self, root, dialog, message: str, filename: str = ""):
        """Change the existing Export card content into the success UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(18 if not self.compact_mode else 14)

        root.addStretch(1)

        icon = QLabel("✓")
        icon.setObjectName("ExportSuccessIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("EXPORT SUCCESSFUL")
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        subtitle = QLabel(message or "Face data exported successfully to server path.")
        subtitle.setObjectName("ExportSuccessSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        detail = QFrame()
        detail.setObjectName("ExportDetailBlock")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(8)

        detail_label = QLabel("TECHNICAL DETAIL")
        detail_label.setObjectName("ExportMetricLabel")

        detail_code = QLabel(f"File: {filename}" if filename else "File: exported backup archive")
        detail_code.setObjectName("ExportDetailCode")
        detail_code.setWordWrap(True)

        detail_layout.addWidget(detail_label)
        detail_layout.addWidget(detail_code)
        root.addWidget(detail)

        root.addStretch(1)

        close_btn = QPushButton("RETURN TO CONSOLE  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)

    def rebuild_export_failed_card(self, root, dialog, error_text: str):
        """Change the existing Export card content into an error UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(18 if not self.compact_mode else 14)

        root.addStretch(1)

        icon = QLabel("×")
        icon.setObjectName("ExportFailedIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("EXPORT FAILED")
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(error_text or "Export failed. Please check NTID, password, server path, and Pi API.")
        subtitle.setObjectName("TransferStatusError")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addStretch(1)

        close_btn = QPushButton("RETURN TO EXPORT  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)


    def rebuild_import_loading_card(self, root, dialog, source_name: str = ""):
        """Change the existing Import card content into the loading UI."""
        self.clear_layout_widgets(root)
        root.setContentsMargins(
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
        )
        root.setSpacing(12 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(6)

        system = QLabel("SECURE ACCESS")
        system.setObjectName("ExportStateEyebrow")

        active = QLabel("●  IMPORT ACTIVE")
        active.setObjectName("ExportStateActive")

        left.addWidget(system)
        left.addWidget(active)

        shield = QLabel("🛡")
        shield.setObjectName("ExportStateShield")
        shield.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        header.addLayout(left, 1)
        header.addWidget(shield)
        root.addLayout(header)

        root.addSpacing(22 if not self.compact_mode else 16)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(14 if not self.compact_mode else 11)

        spinner_wrap = ExportCircleSpinnerWidget(
            dialog,
            size=112 if not self.compact_mode else 96,
            icon_text="⇩",
        )
        spinner_wrap.setObjectName("ExportCircleSpinner")

        title = QLabel("IMPORTING DATA")
        title.setObjectName("ExportStateTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(False)
        title.setMinimumWidth(360 if not self.compact_mode else 300)

        status = QLabel("Reading backup package...")
        status.setObjectName("ExportStateSubtitle")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setWordWrap(True)
        status.setMaximumWidth(380 if not self.compact_mode else 320)
        status.setMinimumWidth(320 if not self.compact_mode else 280)

        if source_name:
            source = QLabel(source_name)
            source.setObjectName("ImportSourceFile")
            source.setAlignment(Qt.AlignmentFlag.AlignCenter)
            source.setWordWrap(True)
            source.setMaximumWidth(380 if not self.compact_mode else 320)
        else:
            source = None

        center.addWidget(spinner_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(status, alignment=Qt.AlignmentFlag.AlignCenter)
        if source is not None:
            center.addWidget(source, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addLayout(center)

        root.addStretch(1)

        progress_outer = QFrame()
        progress_outer.setObjectName("ExportProgressOuter")
        progress_outer.setFixedHeight(5)

        progress_layout = QHBoxLayout(progress_outer)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        progress_fill = QFrame()
        progress_fill.setObjectName("ExportProgressFill")
        progress_layout.addWidget(progress_fill)
        progress_layout.addStretch(1)

        root.addWidget(progress_outer)

        footer = QHBoxLayout()
        footer.setSpacing(16)

        node_box = QVBoxLayout()
        node_box.setSpacing(3)
        node_lbl = QLabel("SOURCE")
        node_lbl.setObjectName("ExportMetricLabel")
        node_value = QLabel("SERVER ZIP")
        node_value.setObjectName("ExportMetricValue")
        node_box.addWidget(node_lbl)
        node_box.addWidget(node_value)

        load_box = QVBoxLayout()
        load_box.setSpacing(3)
        load_lbl = QLabel("MODE")
        load_lbl.setObjectName("ExportMetricLabel")
        load_value = QLabel("SYNC")
        load_value.setObjectName("ExportMetricValue")
        load_box.addWidget(load_lbl)
        load_box.addWidget(load_value)

        percentage = QLabel("34%")
        percentage.setObjectName("ExportPercentage")
        percentage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        footer.addLayout(node_box)
        footer.addLayout(load_box)
        footer.addStretch()
        footer.addWidget(percentage)

        root.addLayout(footer)

        dialog._export_spinner_widget = spinner_wrap
        dialog._export_spinner_index = 0
        dialog._export_progress = 34
        dialog._export_progress_fill = progress_fill
        dialog._export_progress_outer = progress_outer
        dialog._export_percentage_label = percentage
        dialog._export_status_label = status

        status_messages = [
            "Reading backup package...",
            "Checking for duplicate images...",
            "Adding new images only...",
            "Adding new encodings only...",
            "Refreshing user registry...",
            "Finalising import..."
        ]
        dialog._export_status_index = 0

        timer = QTimer(dialog)

        def tick():
            try:
                dialog._export_spinner_index += 1

                if dialog._export_progress < 96 and dialog._export_spinner_index % 2 == 0:
                    dialog._export_progress += 1
                    percentage.setText(f"{dialog._export_progress}%")
                    progress_fill.setFixedWidth(max(8, int(progress_outer.width() * dialog._export_progress / 100)))

                if dialog._export_spinner_index % 10 == 0:
                    dialog._export_status_index = (dialog._export_status_index + 1) % len(status_messages)
                    status = getattr(self, "sftp_status_label", None) or QLabel("")
                    status.setText(status_messages[dialog._export_status_index])
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start(90)
        dialog._export_loading_timer = timer

    def finish_import_progress_then_success(self, root, dialog, source_name: str, imported_users, skipped_users_count: int = 0, message: str = ""):
        """Animate import progress to 100% before changing to success content."""
        self.stop_export_loading_timer(dialog)

        progress_fill = getattr(dialog, "_export_progress_fill", None)
        progress_outer = getattr(dialog, "_export_progress_outer", None)
        percentage = getattr(dialog, "_export_percentage_label", None)
        status = getattr(dialog, "_export_status_label", None)

        if status is not None:
            status.setText("Finalising import...")

        finish_timer = QTimer(dialog)

        def tick_finish():
            try:
                current = int(getattr(dialog, "_export_progress", 96))
                if current < 100:
                    current += 2
                    if current > 100:
                        current = 100
                    dialog._export_progress = current

                    if percentage is not None:
                        percentage.setText(f"{current}%")

                    if progress_fill is not None and progress_outer is not None:
                        progress_fill.setFixedWidth(max(8, int(progress_outer.width() * current / 100)))
                    return

                finish_timer.stop()
                finish_timer.deleteLater()

                if status is not None:
                    status.setText("Import completed.")

                QTimer.singleShot(
                    260,
                    lambda: self.rebuild_import_success_card(
                        root,
                        dialog,
                        source_name,
                        imported_users,
                        skipped_users_count,
                        message,
                    )
                )
            except Exception:
                try:
                    finish_timer.stop()
                except Exception:
                    pass
                self.rebuild_import_success_card(root, dialog, source_name, imported_users, skipped_users_count, message)

        finish_timer.timeout.connect(tick_finish)
        finish_timer.start(70)
        tick_finish()

    def rebuild_import_success_card(self, root, dialog, source_name: str, imported_users, skipped_users_count: int = 0, message: str = ""):
        """Change the existing Import card content into the import completed UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(16 if not self.compact_mode else 13)

        imported_users = imported_users or []
        imported_count = len(imported_users)

        root.addStretch(1)

        icon = QLabel("✓" if imported_count > 0 else "i")
        icon.setObjectName("ExportSuccessIcon" if imported_count > 0 else "ImportInfoIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title_text = "IMPORT SUCCESSFUL" if imported_count > 0 else "IMPORT COMPLETED"
        title = QLabel(title_text)
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        if imported_count > 0:
            subtitle_text = f"{imported_count} user{'s' if imported_count != 1 else ''} processed. New data only was added."
        else:
            subtitle_text = "No valid user data was found to merge from this backup."

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("ExportSuccessSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        detail = QFrame()
        detail.setObjectName("ExportDetailBlock")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(8)

        detail_label = QLabel("TECHNICAL DETAIL")
        detail_label.setObjectName("ExportMetricLabel")

        source_code = QLabel(f"Source: {source_name}" if source_name else "Source: selected backup ZIP")
        source_code.setObjectName("ExportDetailCode")
        source_code.setWordWrap(True)

        detail_layout.addWidget(detail_label)
        detail_layout.addWidget(source_code)

        users_label = QLabel("PROCESSED USERS")
        users_label.setObjectName("ExportMetricLabel")
        detail_layout.addWidget(users_label)

        if imported_count > 0:
            preview = imported_users[:5]
            preview_text = ", ".join(str(u).upper() for u in preview)
            remaining = imported_count - len(preview)
            if remaining > 0:
                preview_text += f"  +{remaining} more"
        else:
            preview_text = "No new data was found in this backup."

        users_code = QLabel(preview_text)
        users_code.setObjectName("ExportDetailCode")
        users_code.setWordWrap(True)
        detail_layout.addWidget(users_code)

        root.addWidget(detail)

        root.addStretch(1)

        close_btn = QPushButton("RETURN TO SETTINGS  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)

    def rebuild_import_failed_card(self, root, dialog, error_text: str):
        """Change the existing Import card content into an error UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(18 if not self.compact_mode else 14)

        root.addStretch(1)

        icon = QLabel("×")
        icon.setObjectName("ExportFailedIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("IMPORT FAILED")
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(error_text or "Import failed. Please check the ZIP file and Pi API.")
        subtitle.setObjectName("TransferStatusError")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addStretch(1)

        close_btn = QPushButton("RETURN TO IMPORT  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)


    def _set_transfer_tab_selected(self, buttons, stack, index: int):
        """Switch a transfer popup between tab pages."""
        try:
            stack.setCurrentIndex(index)
        except Exception:
            pass
        for i, btn in enumerate(buttons):
            try:
                btn.setProperty("selected", i == index)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            except Exception:
                pass

    def _create_transfer_tabs(self, root, names):
        """Create Auto-Capture-style snake tabs and a QStackedWidget for transfer dialogs."""
        stack = QStackedWidget()
        tabs = TransferSnakeTabs(names, self, self.compact_mode)

        def switch_tab(index: int):
            try:
                stack.setCurrentIndex(index)
            except Exception:
                pass

        tabs.on_index_changed = switch_tab  # type: ignore[assignment]
        root.addWidget(tabs)
        root.addWidget(stack, 1)
        return getattr(tabs, "buttons", []), stack

    def _browse_zip_file_into(self, row_layout, path_edit):
        """Add a ZIP file picker to a transfer input row."""
        browse_btn = QPushButton("⌕")
        browse_btn.setObjectName("TransferIconButton")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip("Browse local ZIP file")
        browse_btn.setFixedSize(28, 28)

        def browse_zip():
            start_dir = os.path.dirname(path_edit.text().strip()) if path_edit.text().strip() else os.path.expanduser("~")
            selected, _ = QFileDialog.getOpenFileName(
                browse_btn.window(),
                "Select Face Data ZIP",
                start_dir,
                "ZIP files (*.zip);;All files (*.*)",
            )
            if selected:
                path_edit.setText(selected.replace("/", "\\"))
            try:
                browse_btn.window().raise_()
                browse_btn.window().activateWindow()
            except Exception:
                pass

        browse_btn.clicked.connect(browse_zip)
        row_layout.addWidget(browse_btn)
        return browse_btn

    def _validate_windows_download_inputs(self, windows_username: str, windows_password: str, save_folder: str, status) -> bool:
        if not windows_username.strip():
            self.set_transfer_status(status, "Windows Username / NTID is required.", "error")
            return False
        if not windows_password.strip():
            self.set_transfer_status(status, "Windows Password is required.", "error")
            return False
        if not save_folder.strip():
            self.set_transfer_status(status, "Windows save folder is required.", "error")
            return False
        return True

    def _download_dataset_sftp_to_windows(self, windows_username: str, windows_password: str, save_folder: str, status, button, done_callback=None):
        """Shared Export tab logic: SFTP pull from connected Pi and save ZIP on Windows."""
        if not getattr(self, "pi_connected", False):
            self.set_transfer_status(status, "Pi API is not connected. Please connect from Settings first.", "error")
            return
        if paramiko is None:
            self.set_transfer_status(status, "Paramiko is required for SFTP download in SAS. Please include/install paramiko in the Windows build.", "error")
            return
        if not self._validate_windows_download_inputs(windows_username, windows_password, save_folder, status):
            return

        host, port, username, password = self._get_backend_pi_sftp_config()
        if not host:
            self.set_transfer_status(status, "Pi hostname/IP is not configured. Please connect the Pi in Settings first.", "error")
            return
        if not username:
            self.set_transfer_status(status, "Unable to fetch connected Pi username for SFTP. Please reconnect the Pi and try again.", "error")
            return
        if not password:
            self.set_transfer_status(status, "Unable to derive Pi SFTP password from username. Please reconnect the Pi and try again.", "error")
            return

        self.start_transfer_button_loading(button, "Export")
        self.set_transfer_status(status, "Validating Windows credentials and preparing dataset ZIP on Raspberry Pi...", "normal")

        def worker():
            transport = None
            sftp = None
            try:
                ad_user = windows_username.split("\\")[-1].split("@", 1)[0].strip()
                if not self._validate_ntid_password_in_ad(ad_user, windows_password):
                    raise RuntimeError("Windows credential validation failed. Please check username/password.")

                self._connect_smb_share_if_needed(save_folder, windows_username, windows_password)

                prepare = self._face_api_request("POST", "/face-data/sftp-prepare-download", {}, timeout=90)
                remote_path = prepare.get("remote_path") or prepare.get("zip_path") or ""
                filename = prepare.get("filename") or os.path.basename(str(remote_path))
                if not remote_path or not filename:
                    raise RuntimeError("Pi did not return a downloadable ZIP path.")

                os.makedirs(save_folder, exist_ok=True)
                local_path = os.path.join(save_folder, filename)

                self.qt_after(0, lambda: self.set_transfer_status(status, f"Connecting to current Pi {host}:{port} by SFTP and downloading dataset...", "normal"))

                ssh_lib = cast(Any, paramiko)
                transport = ssh_lib.Transport((host, int(port)))
                transport.connect(username=username, password=password)
                sftp = ssh_lib.SFTPClient.from_transport(transport)
                if sftp is None:
                    raise RuntimeError("SFTP connection was not created.")
                sftp.get(remote_path, local_path)

                message = prepare.get("message", "Dataset ZIP downloaded to Windows successfully.")

                def done():
                    self.show_transfer_button_success(button, "Downloaded", "Export  →")
                    self.set_transfer_status(status, f"{message}\nSaved to: {local_path}", "success")
                    self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS: {remote_path} -> {local_path}")
                    if callable(done_callback):
                        try:
                            done_callback(local_path)
                        except Exception:
                            pass

                self.qt_after(0, done)
            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.show_transfer_button_failed(button, "Export  →")
                    self.set_transfer_status(status, f"Download failed: {err}", "error")
                    self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS_FAILED: {err}")

                self.qt_after(0, fail)
            finally:
                try:
                    if sftp is not None:
                        sftp.close()
                except Exception:
                    pass
                try:
                    if transport is not None:
                        transport.close()
                except Exception:
                    pass

        Thread(target=worker, daemon=True).start()


    def _face_api_export_data(self):
        """Open export popup with Server Path and SFTP download tabs."""
        ntid, password, server = "", "", ""

        dialog, root = self.create_transfer_dialog_base(
            "Export Face Data",
            "",
            "⇧",
            height=540,
        )

        _, stack = self._create_transfer_tabs(root, ["Server Path", "Local Path"])

        server_page = QWidget()
        server_layout = QVBoxLayout(server_page)
        server_layout.setContentsMargins(0, 8, 0, 0)
        server_layout.setSpacing(9)

        ntid_row, ntid_edit, _, _ = self.transfer_input_row("NTID / Username", "", readonly=False, placeholder="e.g. 1234567")
        pwd_row, pwd_edit, _, _ = self.transfer_input_row("Password", "", readonly=False, password=True)
        path_row, path_edit, _, path_row_layout = self.transfer_input_row("Server Path", "", readonly=False, placeholder="e.g. //server/share/SAS_folder")
        self.add_path_browse_button(path_row_layout, path_edit)
        server_layout.addLayout(ntid_row)
        server_layout.addLayout(pwd_row)
        server_layout.addLayout(path_row)
        server_status = QLabel("")
        server_status.setObjectName("TransferStatus")
        server_status.setWordWrap(True)
        server_layout.addWidget(server_status)
        server_actions = QHBoxLayout()
        server_cancel = QPushButton("Cancel")
        server_cancel.setObjectName("TransferCancelButton")
        server_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        server_cancel.clicked.connect(dialog.reject)
        export_btn = QPushButton("Export  →")
        export_btn.setObjectName("TransferPrimaryButton")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        server_actions.addWidget(server_cancel)
        server_actions.addStretch()
        server_actions.addWidget(export_btn)
        server_layout.addLayout(server_actions)
        stack.addWidget(server_page)

        sftp_page = QWidget()
        sftp_layout = QVBoxLayout(sftp_page)
        sftp_layout.setContentsMargins(0, 8, 0, 0)
        sftp_layout.setSpacing(9)
        win_row, win_user_edit, _, _ = self.transfer_input_row("Windows Username / NTID", "", readonly=False, placeholder="e.g. 1234567")
        win_pwd_row, win_pwd_edit, _, _ = self.transfer_input_row("Windows Password", "", readonly=False, password=True)
        save_default = ""
        save_row, save_edit, _, save_row_layout = self.transfer_input_row("Windows Save Folder", "", readonly=False, placeholder="e.g. C:\\Users\\Public\\Documents")
        self.add_path_browse_button(save_row_layout, save_edit)
        sftp_layout.addLayout(win_row)
        sftp_layout.addLayout(win_pwd_row)
        sftp_layout.addLayout(save_row)
        sftp_status = QLabel("")
        sftp_status.setObjectName("TransferStatus")
        sftp_status.setWordWrap(True)
        sftp_layout.addWidget(sftp_status)
        sftp_actions = QHBoxLayout()
        sftp_cancel = QPushButton("Cancel")
        sftp_cancel.setObjectName("TransferCancelButton")
        sftp_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        sftp_cancel.clicked.connect(dialog.reject)
        download_btn = QPushButton("Export  →")
        download_btn.setObjectName("TransferPrimaryButton")
        download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sftp_actions.addWidget(sftp_cancel)
        sftp_actions.addStretch()
        sftp_actions.addWidget(download_btn)
        sftp_layout.addLayout(sftp_actions)
        stack.addWidget(sftp_page)

        def do_export():
            export_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            nt = ntid_edit.text().strip()
            pw = pwd_edit.text().strip()
            sp = path_edit.text().strip()
            if not self.validate_transfer_inputs(nt, pw, sp, server_status):
                return
            self.rebuild_export_loading_card(root, dialog)

            def worker():
                try:
                    data = self._face_api_request("POST", "/face-data/export", {"username": nt, "password": pw, "pc_save_path": sp, "target_folder": None}, timeout=120)
                    message = data.get("message", "Face data exported successfully to server path.")
                    filename = data.get("filename", "")
                    self.qt_after(0, lambda: (self.finish_export_progress_then_success(root, dialog, message, filename), self.append_face_log(f"EXPORT: {message}")))
                except Exception as e:
                    err = str(e)
                    self.qt_after(0, lambda err=err: (self.rebuild_export_failed_card(root, dialog, f"Export failed: {err}"), self.append_face_log(f"EXPORT_FAILED: {err}")))
            Thread(target=worker, daemon=True).start()

        def do_download():
            download_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            self._download_dataset_sftp_to_windows(win_user_edit.text().strip(), win_pwd_edit.text(), save_edit.text().strip(), sftp_status, download_btn)

        export_btn.clicked.connect(do_export)
        download_btn.clicked.connect(do_download)
        self._show_card_dialog(dialog)

    def _face_api_import_data(self):
        """Open import popup with Server Path and Local Path tabs."""
        ntid, password, server = "", "", ""
        dialog, root = self.create_transfer_dialog_base(
            "Import Face Data",
            "",
            "⇩",
            height=590,
        )
        # Import has a tall ZIP-list panel. Place this card slightly higher so
        # its actions remain comfortably visible on typical laptop screens.
        dialog._card_dialog_y_offset = -24
        _, stack = self._create_transfer_tabs(root, ["Server Path", "Local Path"])

        server_page = QWidget()
        server_layout = QVBoxLayout(server_page)
        server_layout.setContentsMargins(0, 8, 0, 0)
        server_layout.setSpacing(8)
        ntid_row, ntid_edit, _, _ = self.transfer_input_row("NTID / Username", "", readonly=False, placeholder="e.g. 1234567")
        pwd_row, pwd_edit, _, _ = self.transfer_input_row("Password", "", readonly=False, password=True)
        path_row, path_edit, _, path_row_layout = self.transfer_input_row("Server Path", "", readonly=False, placeholder="e.g. //server/share/SAS_folder")
        self.add_path_browse_button(path_row_layout, path_edit)
        server_layout.addLayout(ntid_row)
        server_layout.addLayout(pwd_row)
        server_layout.addLayout(path_row)
        zip_label = QLabel("Available ZIP Files")
        zip_label.setObjectName("TransferFieldLabel")
        server_layout.addWidget(zip_label)
        search_box = QFrame()
        search_box.setObjectName("TransferInputBox")
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 0, 10, 0)
        search = QLineEdit()
        search.setObjectName("TransferInput")
        search.setPlaceholderText("Search zip files...")
        search.setMinimumHeight(32 if not self.compact_mode else 30)
        search_icon = QLabel("⌕")
        search_icon.setObjectName("TransferSearchIcon")
        search_layout.addWidget(search, 1)
        search_layout.addWidget(search_icon)
        server_layout.addWidget(search_box)
        list_wrap = QFrame()
        list_wrap.setObjectName("TransferZipList")
        list_layout = QVBoxLayout(list_wrap)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(108 if not self.compact_mode else 96)
        self.make_scrollbar_invisible(scroll)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)
        scroll.setWidget(body)
        list_layout.addWidget(scroll)
        server_layout.addWidget(list_wrap)
        server_status = QLabel("Press Connect to load ZIP files from the server path.")
        server_status.setObjectName("TransferStatus")
        server_status.setWordWrap(True)
        server_layout.addWidget(server_status)
        state = {"files": [], "selected": None, "selected_row": None}

        def clear_body():
            while body_layout.count():
                item = body_layout.takeAt(0)
                if item is None:
                    continue
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        def selected_file_key(file_info):
            return file_info.get("path") or file_info.get("name") or ""

        def render_files():
            clear_body()
            keyword = search.text().strip().lower()
            files = state["files"]
            filtered = [f for f in files if keyword in f.get("name", "").lower()] if keyword else files
            if not filtered:
                msg = QLabel("No ZIP files found." if files else "No server ZIP list loaded.")
                msg.setObjectName("TransferStatus")
                body_layout.addWidget(msg)
                body_layout.addStretch()
                return
            current_selected_key = selected_file_key(state["selected"]) if state.get("selected") else ""
            for file_info in filtered:
                row = QFrame()
                row.setObjectName("TransferZipRow")
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(8, 5, 8, 5)
                row_layout.setSpacing(8)
                icon = QLabel("▣")
                icon.setObjectName("TransferZipIcon")
                icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                name = QLabel(file_info.get("name", ""))
                name.setObjectName("TransferZipName")
                name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                row_layout.addWidget(icon)
                row_layout.addWidget(name, 1)
                is_selected = bool(current_selected_key and selected_file_key(file_info) == current_selected_key)
                row.setProperty("selected", is_selected)
                if is_selected:
                    state["selected_row"] = row

                def select_file(event, fi=file_info, r=row):
                    self.clear_transfer_text_selection(dialog)
                    for i in range(body_layout.count()):
                        item = body_layout.itemAt(i)
                        w = item.widget() if item is not None else None
                        if w is not None and w.objectName() == "TransferZipRow":
                            w.setProperty("selected", False)
                            w.style().unpolish(w)
                            w.style().polish(w)
                    state["selected"] = fi
                    state["selected_row"] = r
                    r.setProperty("selected", True)
                    r.style().unpolish(r)
                    r.style().polish(r)
                    self.set_transfer_status(server_status, f"Selected: {fi.get('name', '')}", "normal")

                row.mousePressEvent = select_file
                body_layout.addWidget(row)
                row.style().unpolish(row)
                row.style().polish(row)
            body_layout.addStretch()

        search.textChanged.connect(render_files)
        render_files()
        server_actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("TransferCancelButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(dialog.reject)
        connect = QPushButton("Connect")
        connect.setObjectName("TransferPrimaryButton")
        connect.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn = QPushButton("Import")
        import_btn.setObjectName("TransferPrimaryButton")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.setEnabled(False)
        server_actions.addWidget(cancel)
        server_actions.addStretch()
        server_actions.addWidget(connect)
        server_actions.addWidget(import_btn)
        server_layout.addLayout(server_actions)
        stack.addWidget(server_page)

        local_page = QWidget()
        local_layout = QVBoxLayout(local_page)
        local_layout.setContentsMargins(0, 8, 0, 0)
        local_layout.setSpacing(9)
        local_ntid_row, local_ntid_edit, _, _ = self.transfer_input_row("Windows Username / NTID", "", readonly=False, placeholder="e.g. 1234567")
        local_pwd_row, local_pwd_edit, _, _ = self.transfer_input_row("Windows Password", "", readonly=False, password=True)
        zip_row, zip_edit, _, zip_row_layout = self.transfer_input_row("Local Path File", "", readonly=False)
        self._browse_zip_file_into(zip_row_layout, zip_edit)
        local_layout.addLayout(local_ntid_row)
        local_layout.addLayout(local_pwd_row)
        local_layout.addLayout(zip_row)
        local_status = QLabel("")
        local_status.setObjectName("TransferStatus")
        local_status.setWordWrap(True)
        local_layout.addWidget(local_status)
        local_actions = QHBoxLayout()
        local_cancel = QPushButton("Cancel")
        local_cancel.setObjectName("TransferCancelButton")
        local_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        local_cancel.clicked.connect(dialog.reject)
        local_import_btn = QPushButton("Import  →")
        local_import_btn.setObjectName("TransferPrimaryButton")
        local_import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        local_actions.addWidget(local_cancel)
        local_actions.addStretch()
        local_actions.addWidget(local_import_btn)
        local_layout.addLayout(local_actions)
        stack.addWidget(local_page)

        def load_zip_files():
            connect.setFocus()
            self.clear_transfer_text_selection(dialog)
            self.start_transfer_button_loading(connect, "Connect")
            self.set_transfer_status(server_status, "Connecting to server path and loading ZIP files...", "normal")
            nt = ntid_edit.text().strip()
            pw = pwd_edit.text().strip()
            sp = path_edit.text().strip()
            if not self.validate_transfer_inputs(nt, pw, sp, server_status):
                self.show_transfer_button_failed(connect, "Connect")
                import_btn.setEnabled(False)
                return

            def worker():
                try:
                    data = self._face_api_request("POST", "/face-data/list-server-zips", {"username": nt, "password": pw, "pc_save_path": sp}, timeout=90)
                    files = data.get("files", [])
                    def done():
                        connect.setFocus()
                        self.clear_transfer_text_selection(dialog)
                        state["files"] = files
                        state["selected"] = None
                        state["selected_row"] = None
                        render_files()
                        self.show_transfer_button_success(connect, "Connected", "Refresh List")
                        self.set_transfer_status(server_status, f"Found {len(files)} ZIP file(s)." if files else "No ZIP backup files found in this server path.", "success" if files else "normal")
                        import_btn.setEnabled(bool(files))
                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)
                    def fail(err=err):
                        connect.setFocus()
                        self.clear_transfer_text_selection(dialog)
                        self.set_transfer_status(server_status, f"Load failed: {err}", "error")
                        self.show_transfer_button_failed(connect, "Connect")
                        import_btn.setEnabled(False)
                    self.qt_after(0, fail)
            Thread(target=worker, daemon=True).start()

        def import_selected():
            import_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            selected = state.get("selected")
            if not selected:
                self.set_transfer_status(server_status, "Please select a ZIP file to import.", "error")
                return
            nt = ntid_edit.text().strip()
            pw = pwd_edit.text().strip()
            sp = path_edit.text().strip()
            if not self.validate_transfer_inputs(nt, pw, sp, server_status):
                return
            selected_name = selected.get("name", "")
            selected_path = selected.get("path", "")
            self.rebuild_import_loading_card(root, dialog, selected_name)
            def worker():
                try:
                    data = self._face_api_request("POST", "/face-data/import", {"zip_path": selected_path}, timeout=120)
                    message = data.get("message", "Face data imported.")
                    imported_users = data.get("imported_users", [])
                    skipped_users_count = int(data.get("skipped_users_count", 0) or 0)
                    if data.get("import_mode") in ("add_on", "add_new_only"):
                        skipped_users_count = 0
                    for k in ("added_ids", "merged_users", "imported_ids"):
                        if not imported_users and isinstance(data.get(k, None), list):
                            imported_users = data.get(k, [])
                    self.qt_after(0, lambda: (self.finish_import_progress_then_success(root, dialog, selected_name, imported_users, skipped_users_count, message), self.append_face_log(f"IMPORT: {message}"), self._face_api_refresh_users()))
                except Exception as e:
                    err = str(e)
                    self.qt_after(0, lambda err=err: (self.rebuild_import_failed_card(root, dialog, f"Import failed: {err}"), self.append_face_log(f"IMPORT_FAILED: {err}")))
            Thread(target=worker, daemon=True).start()

        def import_local_zip():
            local_import_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            if not getattr(self, "pi_connected", False):
                self.set_transfer_status(local_status, "Pi API is not connected. Please connect from Settings first.", "error")
                return
            if paramiko is None:
                self.set_transfer_status(local_status, "Paramiko is required for local ZIP import because SAS uploads the ZIP to Pi by SFTP.", "error")
                return
            windows_username = local_ntid_edit.text().strip()
            windows_password = local_pwd_edit.text()
            local_zip = zip_edit.text().strip()
            if not windows_username:
                self.set_transfer_status(local_status, "Windows Username / NTID is required.", "error")
                return
            if not windows_password:
                self.set_transfer_status(local_status, "Windows Password is required.", "error")
                return
            if not local_zip:
                self.set_transfer_status(local_status, "Local Path file is required.", "error")
                return
            if not os.path.isfile(local_zip):
                self.set_transfer_status(local_status, "Local Path file was not found.", "error")
                return
            if not local_zip.lower().endswith(".zip"):
                self.set_transfer_status(local_status, "Please select a ZIP file.", "error")
                return
            host, port, username, password = self._get_backend_pi_sftp_config()
            if not host or not username or not password:
                self.set_transfer_status(local_status, "Unable to resolve connected Pi SFTP account. Please reconnect the Pi and try again.", "error")
                return
            self.start_transfer_button_loading(local_import_btn, "Import")
            self.set_transfer_status(local_status, "Validating Windows credentials and uploading local ZIP to Pi...", "normal")
            selected_name = os.path.basename(local_zip)

            def worker():
                transport = None
                sftp = None
                try:
                    ad_user = windows_username.split("\\")[-1].split("@", 1)[0].strip()
                    if not self._validate_ntid_password_in_ad(ad_user, windows_password):
                        raise RuntimeError("Windows credential validation failed. Please check username/password.")
                    target = self._face_api_request("POST", "/face-data/sftp-import-target", {}, timeout=45)
                    remote_dir = str(target.get("remote_dir") or target.get("import_dir") or "").replace("\\", "/").rstrip("/")
                    if not remote_dir:
                        raise RuntimeError("Pi did not return an SFTP import target folder.")
                    remote_path = f"{remote_dir}/{selected_name}"
                    ssh_lib = cast(Any, paramiko)
                    transport = ssh_lib.Transport((host, int(port)))
                    transport.connect(username=username, password=password)
                    sftp = ssh_lib.SFTPClient.from_transport(transport)
                    if sftp is None:
                        raise RuntimeError("SFTP connection was not created.")
                    sftp.put(local_zip, remote_path)
                    self.qt_after(0, lambda: self.set_transfer_status(local_status, "ZIP uploaded. Importing on Raspberry Pi...", "normal"))
                    data = self._face_api_request("POST", "/face-data/import", {"zip_path": remote_path}, timeout=120)
                    message = data.get("message", "Face data imported.")
                    imported_users = data.get("imported_users", [])
                    skipped_users_count = int(data.get("skipped_users_count", 0) or 0)
                    if data.get("import_mode") in ("add_on", "add_new_only"):
                        skipped_users_count = 0
                    for k in ("added_ids", "merged_users", "imported_ids"):
                        if not imported_users and isinstance(data.get(k, None), list):
                            imported_users = data.get(k, [])
                    def done():
                        self.finish_import_progress_then_success(root, dialog, selected_name, imported_users, skipped_users_count, message)
                        self.append_face_log(f"LOCAL_IMPORT: {message}")
                        self._face_api_refresh_users()
                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)
                    def fail(err=err):
                        self.show_transfer_button_failed(local_import_btn, "Import  →")
                        self.set_transfer_status(local_status, f"Local import failed: {err}", "error")
                        self.append_face_log(f"LOCAL_IMPORT_FAILED: {err}")
                    self.qt_after(0, fail)
                finally:
                    try:
                        if sftp is not None:
                            sftp.close()
                    except Exception:
                        pass
                    try:
                        if transport is not None:
                            transport.close()
                    except Exception:
                        pass
            Thread(target=worker, daemon=True).start()

        connect.clicked.connect(load_zip_files)
        import_btn.clicked.connect(import_selected)
        local_import_btn.clicked.connect(import_local_zip)
        self._show_card_dialog(dialog)

    def normalize_sftp_pending_path(self, path_text: str) -> str:
        """Return receiver pending folder path.

        User can enter the receiver project folder only, e.g. /home/pi/New.
        The app will automatically append /received_face_data/pending.
        If user already enters the pending folder, it is kept as-is.
        """
        path = str(path_text or "").strip().replace("\\", "/").rstrip("/")
        if not path:
            return ""

        if path.endswith("/received_face_data/pending"):
            return path

        if path.endswith("/received_face_data"):
            return path + "/pending"

        return path + "/received_face_data/pending"

    # --------------------------------------------------------
    # FACE DATA TRANSFER - MULTI-PI SFTP (Pi API owns state)
    # --------------------------------------------------------
    def _multi_sftp_set_status(self, label, text: str, state: str = "normal"):
        """Update a status label only when its visible state actually changes.

        Transfer polling runs in the background. Re-polishing an unchanged Qt
        widget every refresh makes tab animations and dialogs feel sluggish.
        """
        if label is None:
            return

        new_text = str(text or "")
        new_object_name = "MultiSftpStatusError" if state == "error" else "MultiSftpStatus"
        text_changed = label.text() != new_text
        style_changed = label.objectName() != new_object_name

        if text_changed:
            label.setText(new_text)

        if style_changed:
            label.setObjectName(new_object_name)
            try:
                label.style().unpolish(label)
                label.style().polish(label)
            except Exception:
                pass

        if text_changed or style_changed:
            try:
                label.update()
            except Exception:
                pass

    def _multi_sftp_filtered_targets(self, state):
        query = str(state.get("filter", "") or "").strip().casefold()
        targets = list(state.get("targets", []) or [])
        if not query:
            return targets
        return [target for target in targets if query in str(target).casefold()]

    def _multi_sftp_update_select_all(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        checkbox = state.get("select_all")
        if checkbox is None:
            return

        visible = self._multi_sftp_filtered_targets(state)
        selected = set(state.get("selected", set()) or set())
        all_visible_selected = bool(visible) and all(target in selected for target in visible)

        # Programmatic changes must not run select_all_changed(), otherwise
        # updating one target row could accidentally clear the full selection.
        state["updating_select_all"] = True
        try:
            checkbox.setChecked(all_visible_selected)
        finally:
            state["updating_select_all"] = False

    def _multi_sftp_refresh_target_rows(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        layout = state.get("target_layout")
        if layout is None:
            return

        self.clear_layout_widgets(layout)
        visible = self._multi_sftp_filtered_targets(state)
        selected = set(state.get("selected", set()) or set())

        if not visible:
            empty = QLabel("No saved target Pis match this search.")
            empty.setObjectName("MultiSftpHint")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(90)
            layout.addWidget(empty)
        else:
            for index, hostname in enumerate(visible):
                row = QFrame()
                row.setObjectName("MultiSftpTargetRow")
                row.setMinimumHeight(52 if not self.compact_mode else 46)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 8, 10, 8)
                row_layout.setSpacing(10)

                # Use a checkable QPushButton so the selected state always has
                # a visible ✓. The old styled QCheckBox used a black background
                # but did not render a tick on this deployed Windows environment.
                check = QPushButton("✓")
                check.setObjectName("MultiSftpTargetCheck")
                check.setCheckable(True)
                check.setChecked(hostname in selected)
                check.setCursor(Qt.CursorShape.PointingHandCursor)
                check.setToolTip(f"Select {hostname}")
                check.setFixedSize(28 if not self.compact_mode else 25, 28 if not self.compact_mode else 25)

                icon = QLabel("▣")
                icon.setObjectName("MultiSftpTargetIcon")
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon.setFixedSize(34 if not self.compact_mode else 30, 34 if not self.compact_mode else 30)

                name = QLabel(hostname)
                name.setObjectName("MultiSftpTargetName")
                name.setToolTip(hostname)

                delete = QPushButton("×")
                delete.setObjectName("MultiSftpDeleteButton")
                delete.setCursor(Qt.CursorShape.PointingHandCursor)
                delete.setToolTip(f"Remove {hostname} from the Pi target list")
                delete.setFixedSize(30 if not self.compact_mode else 27, 30 if not self.compact_mode else 27)

                def selection_changed(is_checked, host=hostname):
                    live_state = getattr(dialog, "_multi_sftp_state", {})
                    picked = set(live_state.get("selected", set()) or set())
                    if bool(is_checked):
                        picked.add(host)
                    else:
                        picked.discard(host)
                    live_state["selected"] = picked
                    self._multi_sftp_update_select_all(dialog)
                    self._multi_sftp_update_transfer_button(dialog)

                check.toggled.connect(selection_changed)
                delete.clicked.connect(lambda _checked=False, host=hostname: self._multi_sftp_remove_target(dialog, host))

                row_layout.addWidget(check)
                row_layout.addWidget(icon)
                row_layout.addWidget(name, 1)
                row_layout.addWidget(delete)
                layout.addWidget(row)

        layout.addStretch(1)
        self._multi_sftp_update_select_all(dialog)
        self._multi_sftp_update_transfer_button(dialog)

    def _multi_sftp_update_transfer_button(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        button = state.get("transfer_button")
        if button is None:
            return
        count = len(state.get("selected", set()) or set())
        button.setText("Transfer Selected" if count <= 0 else f"Transfer Selected ({count})")
        button.setEnabled(not bool(state.get("loading", False)))

    def _multi_sftp_render_setup(self, dialog):
        root = getattr(dialog, "_multi_sftp_root", None)
        state = getattr(dialog, "_multi_sftp_state", {})
        if root is None:
            return

        self.clear_layout_widgets(root)
        root.setContentsMargins(24 if not self.compact_mode else 20, 20 if not self.compact_mode else 16, 24 if not self.compact_mode else 20, 0)
        root.setSpacing(14 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("SFTP Transfer")
        title.setObjectName("MultiSftpTitle")
        badge = QLabel("Total Nodes: 0")
        badge.setObjectName("MultiSftpCountBadge")
        title_box.addWidget(title)
        title_box.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        close = QPushButton("×")
        close.setObjectName("MultiSftpCloseButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Close")
        close.clicked.connect(lambda: dialog.accept())
        header.addLayout(title_box, 1)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        hint = QLabel("Manage saved target Pis on the connected Raspberry Pi. The Pi creates one ZIP and sends to up to four targets at a time.")
        hint.setObjectName("MultiSftpHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        search = QLineEdit()
        search.setObjectName("MultiSftpSearch")
        search.setPlaceholderText("⌕  Search Nodes...")
        search.setClearButtonEnabled(True)
        # Keep the Select All control separate from its text so the same
        # visible ✓-button style is used as the target Pi rows.
        select_all_wrap = QWidget()
        select_all_wrap.setObjectName("MultiSftpSelectAllWrap")
        select_all_layout = QHBoxLayout(select_all_wrap)
        select_all_layout.setContentsMargins(0, 0, 0, 0)
        select_all_layout.setSpacing(8)

        select_all = QPushButton("✓")
        select_all.setObjectName("MultiSftpSelectAll")
        select_all.setCheckable(True)
        select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all.setToolTip("Select all visible target Pis")
        select_all.setFixedSize(30 if not self.compact_mode else 27, 30 if not self.compact_mode else 27)

        select_all_text = QPushButton("Select All")
        select_all_text.setObjectName("MultiSftpSelectAllText")
        select_all_text.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all_text.setToolTip("Select all visible target Pis")
        select_all_text.setFlat(True)

        select_all_layout.addWidget(select_all)
        select_all_layout.addWidget(select_all_text)

        controls.addWidget(search, 1)
        controls.addWidget(select_all_wrap)
        root.addLayout(controls)

        scroll = QScrollArea()
        scroll.setObjectName("MultiSftpTargetScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(252 if not self.compact_mode else 220)
        scroll.setMaximumHeight(288 if not self.compact_mode else 252)
        target_container = QFrame()
        target_container.setObjectName("MultiSftpTargetList")
        target_layout = QVBoxLayout(target_container)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(0)
        scroll.setWidget(target_container)
        root.addWidget(scroll)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        host_input = QLineEdit()
        host_input.setObjectName("MultiSftpAddInput")
        host_input.setPlaceholderText("Enter Hostname or IP")
        add_btn = QPushButton("＋  Add Hostname")
        add_btn.setObjectName("MultiSftpAddButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_row.addWidget(host_input, 1)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        status = QLabel("")
        status.setObjectName("MultiSftpStatus")
        status.setWordWrap(True)
        root.addWidget(status)

        footer = QFrame()
        footer.setObjectName("MultiSftpFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(8)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("MultiSftpFooterCancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer = QPushButton("Transfer Selected")
        transfer.setObjectName("MultiSftpPrimaryButton")
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_layout.addWidget(cancel)
        footer_layout.addStretch(1)
        footer_layout.addWidget(transfer)
        root.addWidget(footer)

        state.update({
            "title": title,
            "count_badge": badge,
            "search": search,
            "select_all": select_all,
            "target_layout": target_layout,
            "host_input": host_input,
            "add_button": add_btn,
            "status": status,
            "transfer_button": transfer,
            "cancel_button": cancel,
            "loading": False,
            "showing_progress": False,
        })

        def search_changed(text):
            live = getattr(dialog, "_multi_sftp_state", {})
            live["filter"] = str(text or "")
            self._multi_sftp_refresh_target_rows(dialog)

        def select_all_changed(is_checked):
            live = getattr(dialog, "_multi_sftp_state", {})
            if live.get("updating_select_all"):
                return
            visible = self._multi_sftp_filtered_targets(live)
            selected = set(live.get("selected", set()) or set())
            if bool(is_checked):
                selected.update(visible)
            else:
                selected.difference_update(visible)
            live["selected"] = selected
            self._multi_sftp_refresh_target_rows(dialog)

        search.textChanged.connect(search_changed)
        select_all.toggled.connect(select_all_changed)
        select_all_text.clicked.connect(select_all.click)
        add_btn.clicked.connect(lambda: self._multi_sftp_add_target(dialog))
        host_input.returnPressed.connect(lambda: self._multi_sftp_add_target(dialog))
        transfer.clicked.connect(lambda: self._multi_sftp_start_batch(dialog))
        cancel.clicked.connect(dialog.accept)

        self._multi_sftp_refresh_target_rows(dialog)

    def _multi_sftp_load_targets(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        self._multi_sftp_set_status(state.get("status"), "Loading saved target Pis from the Raspberry Pi...", "normal")

        def worker():
            try:
                data = self.face_api_service.list_multi_sftp_targets()
                targets = data.get("targets", []) if isinstance(data, dict) else []
                config = data.get("config", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                targets, config, error = [], {}, str(exc)

            def done():
                # This callback can finish before QDialog.exec() makes the
                # modal card visible, so do not reject it based on isVisible().
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if error:
                    self._multi_sftp_set_status(live.get("status"), f"Could not load SFTP target list: {error}", "error")
                else:
                    live["targets"] = [str(item).strip() for item in targets if str(item).strip()]
                    live["selected"] = set(live.get("selected", set()) or set()).intersection(set(live["targets"]))
                    live["config"] = config if isinstance(config, dict) else {}
                    max_workers = int(live["config"].get("max_concurrent_transfers", 4) or 4)
                    self._multi_sftp_set_status(live.get("status"), f"Loaded {len(live['targets'])} saved target Pi(s). Pi will run up to {max_workers} uploads at one time.", "normal")
                    badge = live.get("count_badge")
                    if badge is not None:
                        badge.setText(f"Total Nodes: {len(live['targets'])}")
                self._multi_sftp_refresh_target_rows(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasLoadMultiSftpTargets").start()

    def _multi_sftp_add_target(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        host_input = state.get("host_input")
        hostname = host_input.text().strip() if host_input is not None else ""
        if not hostname:
            self._multi_sftp_set_status(state.get("status"), "Enter a hostname or IP address first.", "error")
            return
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        if state.get("add_button") is not None:
            state["add_button"].setEnabled(False)
        self._multi_sftp_set_status(state.get("status"), f"Saving {hostname} to the Pi target list...", "normal")

        def worker():
            try:
                data = self.face_api_service.add_multi_sftp_target(hostname)
                targets = data.get("targets", []) if isinstance(data, dict) else []
                message = str(data.get("message", "Target added.")) if isinstance(data, dict) else "Target added."
                error = ""
            except Exception as exc:
                targets, message, error = [], "", str(exc)

            def done():
                if not dialog.isVisible():
                    return
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if live.get("add_button") is not None:
                    live["add_button"].setEnabled(True)
                if error:
                    self._multi_sftp_set_status(live.get("status"), f"Could not add target: {error}", "error")
                else:
                    live["targets"] = [str(item).strip() for item in targets if str(item).strip()]
                    if live.get("host_input") is not None:
                        live["host_input"].clear()
                    self._multi_sftp_set_status(live.get("status"), message, "normal")
                    badge = live.get("count_badge")
                    if badge is not None:
                        badge.setText(f"Total Nodes: {len(live['targets'])}")
                self._multi_sftp_refresh_target_rows(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasAddMultiSftpTarget").start()

    def _multi_sftp_remove_target(self, dialog, hostname: str):
        state = getattr(dialog, "_multi_sftp_state", {})
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        self._multi_sftp_set_status(state.get("status"), f"Removing {hostname} from the Pi target list...", "normal")

        def worker():
            try:
                data = self.face_api_service.remove_multi_sftp_target(hostname)
                targets = data.get("targets", []) if isinstance(data, dict) else []
                message = str(data.get("message", "Target removed.")) if isinstance(data, dict) else "Target removed."
                error = ""
            except Exception as exc:
                targets, message, error = [], "", str(exc)

            def done():
                if not dialog.isVisible():
                    return
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if error:
                    self._multi_sftp_set_status(live.get("status"), f"Could not remove target: {error}", "error")
                else:
                    live["targets"] = [str(item).strip() for item in targets if str(item).strip()]
                    selected = set(live.get("selected", set()) or set())
                    selected.discard(hostname)
                    live["selected"] = selected
                    self._multi_sftp_set_status(live.get("status"), message, "normal")
                    badge = live.get("count_badge")
                    if badge is not None:
                        badge.setText(f"Total Nodes: {len(live['targets'])}")
                self._multi_sftp_refresh_target_rows(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasRemoveMultiSftpTarget").start()

    def _multi_sftp_start_batch(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        targets = [host for host in state.get("targets", []) if host in set(state.get("selected", set()) or set())]
        if not targets:
            self._multi_sftp_set_status(state.get("status"), "Select at least one target Pi before transferring.", "error")
            return
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        self._multi_sftp_set_status(state.get("status"), f"Creating transfer batch for {len(targets)} target Pi(s)...", "normal")

        def worker():
            try:
                data = self.face_api_service.start_multi_sftp_transfer(targets)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                message = str(data.get("message", "Multi-Pi transfer started.")) if isinstance(data, dict) else "Multi-Pi transfer started."
                error = ""
            except Exception as exc:
                snapshot, message, error = {}, "", str(exc)

            def done():
                if not dialog.isVisible():
                    return
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if error or not snapshot.get("batch_id"):
                    self._multi_sftp_set_status(live.get("status"), f"Could not start transfer: {error or 'Pi did not return a transfer batch.'}", "error")
                    self._multi_sftp_update_transfer_button(dialog)
                    return
                live["batch_id"] = str(snapshot.get("batch_id"))
                live["snapshot"] = snapshot
                self.append_face_log(f"SFTP_MULTI_STARTED: {message} | {len(targets)} target Pi(s)")

                # The target-selection popup is finished.  Close it first;
                # _face_api_sftp_send() will open a separate modeless progress
                # window for this same Pi-owned batch immediately afterwards.
                dialog._multi_sftp_launch_progress = {
                    "batch_id": live["batch_id"],
                    "snapshot": snapshot,
                }
                dialog.accept()

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasStartMultiSftpBatch").start()

    def _multi_sftp_render_progress(self, dialog, snapshot):
        root = getattr(dialog, "_multi_sftp_root", None)
        state = getattr(dialog, "_multi_sftp_state", {})
        if root is None:
            return

        self.clear_layout_widgets(root)
        root.setContentsMargins(24 if not self.compact_mode else 20, 20 if not self.compact_mode else 16, 24 if not self.compact_mode else 20, 0)
        root.setSpacing(12 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("SFTP Transfer in Progress")
        title.setObjectName("MultiSftpTitle")
        badge = QLabel("")
        badge.setObjectName("MultiSftpCountBadge")
        title_box.addWidget(title)
        title_box.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        minimize = None
        if state.get("modeless_progress", False):
            minimize = QPushButton("−")
            minimize.setObjectName("MultiSftpMinimizeButton")
            minimize.setCursor(Qt.CursorShape.PointingHandCursor)
            minimize.setToolTip("Hide progress window; transfer continues on the Raspberry Pi")
            minimize.clicked.connect(lambda: self._multi_sftp_minimize_progress(dialog))

        close = QPushButton("×")
        close.setObjectName("MultiSftpCloseButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Close and delete the temporary ZIP when transfers have stopped")
        close.clicked.connect(lambda: self._multi_sftp_request_close(dialog))
        header.addLayout(title_box, 1)
        if minimize is not None:
            header.addWidget(minimize, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        overall = QProgressBar()
        overall.setObjectName("MultiSftpOverallProgress")
        overall.setTextVisible(False)
        overall.setRange(0, 100)
        overall.setFixedHeight(8)
        root.addWidget(overall)

        scroll = QScrollArea()
        scroll.setObjectName("MultiSftpTargetScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(252 if not self.compact_mode else 220)
        scroll.setMaximumHeight(290 if not self.compact_mode else 254)
        list_widget = QFrame()
        list_widget.setObjectName("MultiSftpTargetList")
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        scroll.setWidget(list_widget)
        root.addWidget(scroll)

        status = QLabel("")
        status.setObjectName("MultiSftpStatus")
        status.setWordWrap(True)
        root.addWidget(status)

        footer = QFrame()
        footer.setObjectName("MultiSftpFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(8)

        # The left footer control is used only after a completed batch has
        # failed targets.  During an active transfer it stays hidden so there
        # is one clear cancellation action: Abort Transfer.
        back = QPushButton("Back")
        back.setObjectName("MultiSftpFooterCancel")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.hide()

        action = QPushButton("Abort Transfer")
        action.setObjectName("MultiSftpAbortButton")
        action.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_layout.addWidget(back)
        footer_layout.addStretch(1)
        footer_layout.addWidget(action)
        root.addWidget(footer)

        state.update({
            "showing_progress": True,
            "progress_title": title,
            "progress_badge": badge,
            "overall_progress": overall,
            "progress_list_layout": list_layout,
            "progress_rows": {},
            "progress_status": status,
            "progress_cancel": back,
            "progress_action": action,
            "progress_minimize": minimize,
        })
        # Back safely cleans up the batch and returns to target selection.  It
        # is hidden while a transfer is running; Abort Transfer performs the
        # equivalent cancel-and-return flow for active transfers.
        back.clicked.connect(lambda: self._multi_sftp_request_close(dialog))
        action.clicked.connect(lambda: self._multi_sftp_progress_action(dialog))
        self._multi_sftp_apply_snapshot(dialog, snapshot)

    def _multi_sftp_build_progress_row(self, hostname: str):
        row = QFrame()
        row.setObjectName("MultiSftpProgressRow")
        row.setMinimumHeight(54 if not self.compact_mode else 48)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon = QLabel("▣")
        icon.setObjectName("MultiSftpTargetIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(34 if not self.compact_mode else 30, 34 if not self.compact_mode else 30)

        centre = QVBoxLayout()
        centre.setSpacing(3)
        host_label = QLabel(hostname)
        host_label.setObjectName("MultiSftpProgressHost")
        row_progress = QProgressBar()
        row_progress.setObjectName("MultiSftpRowProgress")
        row_progress.setRange(0, 100)
        row_progress.setTextVisible(False)
        row_progress.setFixedHeight(4)
        row_progress.setFixedWidth(120 if not self.compact_mode else 90)
        row_progress.hide()
        centre.addWidget(host_label)
        centre.addWidget(row_progress)

        status = QLabel("Queued")
        status.setObjectName("MultiSftpStatusQueued")
        status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status.setWordWrap(False)
        status.setMaximumWidth(190 if not self.compact_mode else 145)

        layout.addWidget(icon)
        layout.addLayout(centre, 1)
        layout.addWidget(status)
        return row, {"status": status, "progress": row_progress, "host": host_label}

    def _multi_sftp_apply_snapshot(self, dialog, snapshot):
        """Apply Pi batch state with minimal Qt work.

        The Pi owns transfer state. SAS only needs to redraw parts that changed.
        This avoids restyling every row every polling cycle, which previously
        made tab switches and modal transitions feel heavy.
        """
        state = getattr(dialog, "_multi_sftp_state", {})
        if not isinstance(snapshot, dict):
            return

        state["snapshot"] = snapshot
        jobs = list(snapshot.get("jobs", []) or [])
        summary = dict(snapshot.get("summary", {}) or {})
        total = int(summary.get("total", len(jobs)) or len(jobs))
        success = int(summary.get("success", 0) or 0)
        failed = int(summary.get("failed", 0) or 0)
        cancelled = int(summary.get("cancelled", 0) or 0)
        completed = min(total, success + failed + cancelled)
        running = bool(snapshot.get("running", False))

        title_text = "SFTP Transfer in Progress" if running else "SFTP Transfer Complete"
        title = state.get("progress_title")
        if title is not None and title.text() != title_text:
            title.setText(title_text)

        extra = f" • {failed} Failed" if failed else ""
        if cancelled:
            extra += f" • {cancelled} Cancelled"
        badge_text = f"{completed} / {total} Nodes Completed{extra}"
        badge = state.get("progress_badge")
        if badge is not None and badge.text() != badge_text:
            badge.setText(badge_text)

        overall_percent = int((completed / total) * 100) if total else 0
        overall = state.get("overall_progress")
        if overall is not None and overall.value() != overall_percent:
            overall.setValue(overall_percent)

        layout = state.get("progress_list_layout")
        rows = state.setdefault("progress_rows", {})
        hosts = [
            str(job.get("hostname", "")).strip()
            for job in jobs
            if str(job.get("hostname", "")).strip()
        ]

        # The host list normally stays fixed for a batch. Rebuild only if it
        # genuinely changes, not on every status refresh.
        if layout is not None and set(rows.keys()) != set(hosts):
            self.clear_layout_widgets(layout)
            rows.clear()
            for job in jobs:
                host = str(job.get("hostname", "")).strip()
                if not host:
                    continue
                row, widgets = self._multi_sftp_build_progress_row(host)
                widgets["last_visible_state"] = None
                rows[host] = widgets
                layout.addWidget(row)
            layout.addStretch(1)

        for job in jobs:
            host = str(job.get("hostname", "")).strip()
            widgets = rows.get(host)
            if not widgets:
                continue

            status_value = str(job.get("status", "Waiting") or "Waiting")
            progress_value = max(0, min(100, int(job.get("progress", 0) or 0)))

            # Keep Multi-Pi SFTP results simple for SAS users.  The Pi may
            # return technical details such as timeouts or hostname-resolution
            # errors, but SAS deliberately exposes only the final result:
            # Completed or Failed.  Detailed diagnostics remain available in
            # the Pi-side logs for troubleshooting.
            status_tooltip = ""
            if status_value == "Success":
                display = "✓  Completed"
                object_name = "MultiSftpStatusSuccess"
                show_progress = False
            elif status_value.startswith("Failed") or status_value == "Cancelled":
                display = "Failed"
                object_name = "MultiSftpStatusError"
                show_progress = False
            elif status_value in ("Connecting", "Uploading"):
                display = (
                    f"{status_value} {progress_value}%"
                    if status_value == "Uploading"
                    else "Connecting..."
                )
                object_name = "MultiSftpStatusActive"
                show_progress = True
            else:
                display = "Queued"
                object_name = "MultiSftpStatusQueued"
                show_progress = False

            visible_state = (
                display,
                object_name,
                status_tooltip,
                progress_value if show_progress else None,
                show_progress,
            )

            # A row only changes when Pi reports a different visible state.
            if widgets.get("last_visible_state") == visible_state:
                continue

            status_label = widgets["status"]
            progress = widgets["progress"]

            if status_label.toolTip() != status_tooltip:
                status_label.setToolTip(status_tooltip)

            if status_label.text() != display:
                status_label.setText(display)

            if status_label.objectName() != object_name:
                status_label.setObjectName(object_name)
                try:
                    status_label.style().unpolish(status_label)
                    status_label.style().polish(status_label)
                except Exception:
                    pass

            if show_progress:
                if progress.value() != progress_value:
                    progress.setValue(progress_value)
                if progress.isHidden():
                    progress.show()
            elif progress.isVisible():
                progress.hide()

            try:
                status_label.update()
            except Exception:
                pass

            widgets["last_visible_state"] = visible_state

        status_label = state.get("progress_status")
        batch_state = str(snapshot.get("state", "") or "")
        local_zip = str(snapshot.get("local_zip", "") or "")
        if running:
            progress_status_text = batch_state or "Transfer is running on the Raspberry Pi."
        elif failed or cancelled:
            progress_status_text = (
                "Transfer stopped. Retry failed targets or close this popup "
                "to delete the temporary ZIP."
            )
        else:
            progress_status_text = (
                "All selected target Pis received the package. Close this "
                "popup to delete the temporary ZIP."
            )

        if status_label is not None:
            self._multi_sftp_set_status(status_label, progress_status_text, "normal")
            if status_label.toolTip() != local_zip:
                status_label.setToolTip(local_zip)

        cancel_button = state.get("progress_cancel")
        action = state.get("progress_action")
        cancelling = bool(state.get("cancel_in_progress", False))

        if running:
            # While running there is only one cancellation control: the red
            # Abort Transfer button.  The left Back button stays hidden.
            if cancel_button is not None:
                cancel_button.hide()

            if action is not None:
                action_style_changed = action.objectName() != "MultiSftpAbortButton"
                next_text = "Aborting..." if cancelling else "Abort Transfer"
                if action.text() != next_text:
                    action.setText(next_text)
                if action_style_changed:
                    action.setObjectName("MultiSftpAbortButton")
                    try:
                        action.style().unpolish(action)
                        action.style().polish(action)
                    except Exception:
                        pass
                action.setEnabled(not cancelling)
                action.show()

        else:
            has_retry = bool(failed or cancelled)

            # A failed batch can return to the saved target list.  This is an
            # actual outlined button, not plain hover-only text.
            if cancel_button is not None:
                if has_retry:
                    if cancel_button.text() != "Back":
                        cancel_button.setText("Back")
                    cancel_button.setEnabled(True)
                    cancel_button.show()
                else:
                    cancel_button.hide()

            if action is not None:
                next_text = "Retry Failed" if has_retry else "Close"
                action_style_changed = action.objectName() != "MultiSftpPrimaryButton"
                if action.text() != next_text:
                    action.setText(next_text)
                if action_style_changed:
                    action.setObjectName("MultiSftpPrimaryButton")
                    try:
                        action.style().unpolish(action)
                        action.style().polish(action)
                    except Exception:
                        pass
                action.setEnabled(True)
                action.show()

        minimize_button = state.get("progress_minimize")
        if minimize_button is not None:
            minimize_button.setEnabled(running)
            minimize_button.setToolTip(
                "Hide progress window; transfer continues on the Raspberry Pi"
                if running
                else "Transfer has finished"
            )

        if not running:
            timer = state.get("poll_timer")
            if timer is not None:
                timer.stop()

            # A hidden modeless window returns only after all Pi jobs are done,
            # allowing Retry Failed without disturbing normal SAS use.
            if state.get("modeless_progress") and state.get("minimized"):
                self._multi_sftp_restore_progress_window(dialog)

            if state.get("close_after_cancel"):
                self._multi_sftp_cleanup_and_close(
                    dialog,
                    reopen_targets=bool(
                        state.get("return_to_targets_after_close", True)
                    ),
                )

    def _multi_sftp_poll_interval_ms(self, dialog):
        """Use a gentle poll rate so normal SAS navigation stays smooth."""
        state = getattr(dialog, "_multi_sftp_state", {})
        # When minimized there is no visible progress UI to refresh. A slower
        # check is enough, while still detecting completion and restoring it.
        return 3000 if state.get("minimized") else 1500

    def _multi_sftp_apply_poll_interval(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        timer = state.get("poll_timer")
        if timer is not None:
            timer.setInterval(self._multi_sftp_poll_interval_ms(dialog))

    def _multi_sftp_start_polling(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        timer = state.get("poll_timer")
        if timer is None:
            timer = QTimer(dialog)
            timer.timeout.connect(lambda: self._multi_sftp_poll_batch(dialog))
            state["poll_timer"] = timer

        self._multi_sftp_apply_poll_interval(dialog)
        timer.start()

        # Refresh once immediately when the progress window opens or returns;
        # later refreshes use the calmer adaptive interval.
        self._multi_sftp_poll_batch(dialog)

    def _multi_sftp_poll_batch(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        batch_id = str(state.get("batch_id", "") or "")
        if not batch_id or state.get("poll_in_progress") or state.get("cleanup_requested"):
            return
        state["poll_in_progress"] = True

        def worker():
            try:
                data = self.face_api_service.get_multi_sftp_transfer(batch_id)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                snapshot, error = {}, str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                live["poll_in_progress"] = False
                if live.get("cleanup_requested"):
                    return
                if error:
                    self._multi_sftp_set_status(
                        live.get("progress_status"),
                        f"Could not refresh transfer status: {error}",
                        "error",
                    )
                    return
                self._multi_sftp_apply_snapshot(dialog, snapshot)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasPollMultiSftpBatch").start()

    def _multi_sftp_cancel_batch(self, dialog, close_after: bool = False):
        """Request Pi cancellation once; later close clicks can still queue return."""
        state = getattr(dialog, "_multi_sftp_state", {})
        batch_id = str(state.get("batch_id", "") or "")
        if not batch_id:
            return

        if close_after:
            state["close_after_cancel"] = True
            state["return_to_targets_after_close"] = True

        cancel_button = state.get("progress_cancel")
        action = state.get("progress_action")

        # Abort may already be in flight.  A later × click still marks the
        # dialog to return to the target list after the Pi has stopped.
        if state.get("cancel_in_progress"):
            if close_after:
                self._multi_sftp_set_status(
                    state.get("progress_status"),
                    "Cancellation is already in progress. This window will return to target selection after the Pi stops.",
                    "normal",
                )
            return

        state["cancel_in_progress"] = True
        self._multi_sftp_set_status(
            state.get("progress_status"),
            "Requesting transfer cancellation from the Raspberry Pi...",
            "normal",
        )

        if action is not None:
            action.setText("Aborting...")
            action.setEnabled(False)

        # The left Back button is intentionally hidden during active work.
        # Abort Transfer now owns the cancel-and-return behavior.
        if cancel_button is not None:
            cancel_button.hide()

        def worker():
            try:
                data = self.face_api_service.cancel_multi_sftp_transfer(batch_id)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                snapshot, error = {}, str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                live["cancel_in_progress"] = False
                if live.get("cleanup_requested"):
                    return

                if error:
                    # Cancellation did not reach the Pi. Restore controls so
                    # the user can retry instead of leaving a stuck popup.
                    live["close_after_cancel"] = False
                    live["return_to_targets_after_close"] = False
                    self._multi_sftp_set_status(
                        live.get("progress_status"),
                        f"Could not cancel transfer: {error}",
                        "error",
                    )
                    if live.get("progress_action") is not None:
                        live["progress_action"].setText("Abort Transfer")
                        live["progress_action"].setEnabled(True)
                    if live.get("progress_cancel") is not None:
                        live["progress_cancel"].hide()
                    return

                # A Pi cancel response can arrive before all worker threads
                # have fully stopped. Apply it when available, then continue
                # polling until the Pi reports running=False.
                if isinstance(snapshot, dict) and snapshot:
                    self._multi_sftp_apply_snapshot(dialog, snapshot)
                self._multi_sftp_start_polling(dialog)

            self.qt_after(0, done)

        Thread(
            target=worker,
            daemon=True,
            name="SasCancelMultiSftpBatch",
        ).start()

    def _multi_sftp_progress_action(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        snapshot = dict(state.get("snapshot", {}) or {})
        if bool(snapshot.get("running", False)):
            # Abort Transfer replaces the old separate Cancel & Return control:
            # request cancellation, then clean up and reopen target selection
            # once the Pi reports that all transfer workers have stopped.
            self._multi_sftp_cancel_batch(dialog, close_after=True)
            return

        summary = dict(snapshot.get("summary", {}) or {})
        if int(summary.get("failed", 0) or 0) or int(summary.get("cancelled", 0) or 0):
            self._multi_sftp_retry_failed(dialog)
        else:
            self._multi_sftp_cleanup_and_close(dialog, reopen_targets=True)

    def _multi_sftp_retry_failed(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        batch_id = str(state.get("batch_id", "") or "")
        if not batch_id or state.get("retry_in_progress"):
            return
        state["retry_in_progress"] = True
        state["close_after_cancel"] = False
        self._multi_sftp_set_status(state.get("progress_status"), "Requesting retry for failed target Pis...", "normal")
        if state.get("progress_action") is not None:
            state["progress_action"].setEnabled(False)

        def worker():
            try:
                data = self.face_api_service.retry_multi_sftp_failed(batch_id)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                snapshot, error = {}, str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                live["retry_in_progress"] = False
                if live.get("cleanup_requested"):
                    return
                if error:
                    self._multi_sftp_set_status(live.get("progress_status"), f"Could not retry failed targets: {error}", "error")
                    if live.get("progress_action") is not None:
                        live["progress_action"].setEnabled(True)
                    return
                self.append_face_log("SFTP_MULTI_RETRY: Retry requested for failed target Pi(s).")
                live["minimized"] = False
                self._multi_sftp_apply_snapshot(dialog, snapshot)
                self._multi_sftp_start_polling(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasRetryMultiSftpBatch").start()

    def _multi_sftp_request_close(self, dialog):
        """Close progress safely, then return to the target-selection popup."""
        state = getattr(dialog, "_multi_sftp_state", {})
        snapshot = dict(state.get("snapshot", {}) or {})

        if not state.get("showing_progress"):
            dialog.accept()
            return

        # The user expects × / Close to return to the previous target-selection
        # interface after this Pi-owned batch has been cleaned up.
        state["return_to_targets_after_close"] = True

        if bool(snapshot.get("running", False)):
            self._multi_sftp_cancel_batch(dialog, close_after=True)
            return

        self._multi_sftp_cleanup_and_close(dialog, reopen_targets=True)

    def _multi_sftp_cleanup_and_close(self, dialog, reopen_targets: bool = False):
        """Delete Pi temporary ZIP, close progress, then optionally reopen target selection."""
        state = getattr(dialog, "_multi_sftp_state", {})
        reopen_targets = bool(
            reopen_targets or state.get("return_to_targets_after_close", False)
        )
        batch_id = str(state.get("batch_id", "") or "")

        if not batch_id:
            try:
                dialog.accept()
            finally:
                if reopen_targets:
                    self._multi_sftp_progress_dialog = None
                    QTimer.singleShot(0, self._face_api_sftp_send)
            return

        if state.get("cleanup_requested"):
            # A second click during cleanup should not start a second API call,
            # but it can still request that selection reopens afterward.
            state["return_to_targets_after_close"] = bool(
                state.get("return_to_targets_after_close", False) or reopen_targets
            )
            return

        state["cleanup_requested"] = True
        state["return_to_targets_after_close"] = reopen_targets
        self._multi_sftp_set_status(
            state.get("progress_status"),
            "Deleting temporary ZIP on the Raspberry Pi...",
            "normal",
        )

        for name in ("progress_cancel", "progress_action", "progress_minimize"):
            button = state.get(name)
            if button is not None:
                button.setEnabled(False)

        timer = state.get("poll_timer")
        if timer is not None:
            timer.stop()

        def worker():
            try:
                self.face_api_service.cleanup_multi_sftp_transfer(batch_id)
                error = ""
            except Exception as exc:
                error = str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                reopen = bool(live.get("return_to_targets_after_close", False))

                if error:
                    self.append_face_log(f"SFTP_MULTI_CLEANUP_FAILED: {error}")
                else:
                    self.append_face_log(
                        "SFTP_MULTI_CLEANUP: Temporary ZIP deleted after popup close."
                    )

                try:
                    dialog.accept()
                except Exception:
                    pass

                # Clear the modeless reference before opening a new selection
                # dialog; otherwise _face_api_sftp_send would restore the old
                # closed progress window instead.
                if getattr(self, "_multi_sftp_progress_dialog", None) is dialog:
                    self._multi_sftp_progress_dialog = None

                if reopen:
                    QTimer.singleShot(0, self._face_api_sftp_send)

            self.qt_after(0, done)

        Thread(
            target=worker,
            daemon=True,
            name="SasCleanupMultiSftpBatch",
        ).start()

    def _multi_sftp_position_progress_window(self, dialog):
        """Centre the modeless progress window without disabling SAS."""
        try:
            geo = self.geometry()
            x = geo.x() + (geo.width() - dialog.width()) // 2
            y = geo.y() + max(20, (geo.height() - dialog.height()) // 2)
            dialog.move(x, y)
        except Exception:
            pass

    def _multi_sftp_minimize_progress(self, dialog):
        """Hide the progress window while Pi-side transfers continue."""
        state = getattr(dialog, "_multi_sftp_state", {})
        snapshot = dict(state.get("snapshot", {}) or {})
        if not bool(snapshot.get("running", False)):
            return
        state["minimized"] = True
        self._multi_sftp_apply_poll_interval(dialog)
        dialog.hide()
        self.append_face_log("SFTP_MULTI_PROGRESS_HIDDEN: Pi transfer continues in the background.")

    def _multi_sftp_restore_progress_window(self, dialog):
        """Show hidden transfer progress again, especially after completion."""
        state = getattr(dialog, "_multi_sftp_state", {})
        if state.get("cleanup_requested"):
            return
        state["minimized"] = False
        self._multi_sftp_apply_poll_interval(dialog)
        self._multi_sftp_position_progress_window(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        try:
            QApplication.setActiveWindow(dialog)
        except Exception:
            pass

    def create_multi_sftp_progress_dialog(self, batch_id: str, snapshot: dict):
        """Create a separate modeless transfer-progress popup.

        The target-selection card closes after the Pi starts a batch. This
        popup deliberately does not use _show_card_dialog(), so users can
        continue using SAS while the Raspberry Pi performs uploads.
        """
        dialog = QDialog(self)
        dialog.setObjectName("MultiSftpDialog")
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(620 if not self.compact_mode else 540, 600 if not self.compact_mode else 540)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("MultiSftpCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QVBoxLayout(card)
        dialog._multi_sftp_root = root
        dialog._multi_sftp_state = {
            "targets": [],
            "selected": set(),
            "filter": "",
            "batch_id": str(batch_id or ""),
            "snapshot": dict(snapshot or {}),
            "loading": False,
            "poll_in_progress": False,
            "showing_progress": True,
            "modeless_progress": True,
            "minimized": False,
            "close_after_cancel": False,
            "return_to_targets_after_close": False,
            "cleanup_requested": False,
        }

        def clear_reference(*_args):
            if getattr(self, "_multi_sftp_progress_dialog", None) is dialog:
                self._multi_sftp_progress_dialog = None

        dialog.finished.connect(clear_reference)
        dialog.destroyed.connect(clear_reference)
        self._multi_sftp_render_progress(dialog, dict(snapshot or {}))
        return dialog

    def _multi_sftp_open_progress_window(self, batch_id: str, snapshot: dict):
        """Show and start polling a modeless Pi-owned transfer batch."""
        existing = getattr(self, "_multi_sftp_progress_dialog", None)
        if existing is not None:
            existing_state = getattr(existing, "_multi_sftp_state", {})
            if not existing_state.get("cleanup_requested"):
                self._multi_sftp_restore_progress_window(existing)
                return existing

        progress = self.create_multi_sftp_progress_dialog(batch_id, snapshot)
        self._multi_sftp_progress_dialog = progress
        self._multi_sftp_position_progress_window(progress)
        progress.show()
        progress.raise_()
        progress.activateWindow()
        self._multi_sftp_start_polling(progress)
        return progress

    def create_multi_sftp_transfer_dialog(self):
        dialog = QDialog(self)
        dialog.setObjectName("MultiSftpDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(620 if not self.compact_mode else 540, 610 if not self.compact_mode else 550)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("MultiSftpCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        root = QVBoxLayout(card)

        dialog._multi_sftp_root = root
        dialog._multi_sftp_state = {
            "targets": [],
            "selected": set(),
            "filter": "",
            "batch_id": "",
            "snapshot": {},
            "loading": False,
            "poll_in_progress": False,
            "showing_progress": False,
            "close_after_cancel": False,
            "cleanup_requested": False,
        }
        self._multi_sftp_render_setup(dialog)
        return dialog

    def create_sftp_transfer_dialog(self):
        """Create SFTP transfer popup using the uploaded split-card UI direction."""
        dialog = QDialog(self)
        dialog.setObjectName("SftpTransferDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(760 if not self.compact_mode else 680, 575 if not self.compact_mode else 535)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("SftpMainCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QHBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left dark technical panel
        left = QFrame()
        left.setObjectName("SftpLeftPanel")
        left.setFixedWidth(255 if not self.compact_mode else 220)

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(28 if not self.compact_mode else 22, 30, 24, 26)
        left_layout.setSpacing(18)

        icon = QLabel("🛡")
        icon.setObjectName("SftpLargeIcon")

        title = QLabel("SFTP\nTransfer")
        title.setObjectName("SftpSideTitle")
        title.setWordWrap(True)

        desc = QLabel("Secure File Transfer Protocol authentication for enterprise node synchronisation.")
        desc.setObjectName("SftpSideDesc")
        desc.setWordWrap(True)

        left_layout.addWidget(icon)
        left_layout.addWidget(title)
        left_layout.addWidget(desc)
        left_layout.addStretch()

        hint = QLabel("Select the receiver project folder only.\nThe pending route is fixed automatically.")
        hint.setObjectName("SftpSideHint")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)

        # Right form panel
        right = QFrame()
        right.setObjectName("SftpRightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(38 if not self.compact_mode else 28, 30 if not self.compact_mode else 24, 38 if not self.compact_mode else 28, 26 if not self.compact_mode else 22)
        right_layout.setSpacing(12)

        top = QHBoxLayout()
        top_title = QLabel("Secure Access System")
        top_title.setObjectName("SftpShellTitle")
        close_btn = QPushButton("×")
        close_btn.setObjectName("SftpCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        top.addWidget(top_title)
        top.addStretch()
        top.addWidget(close_btn)
        right_layout.addLayout(top)

        heading = QLabel("Connection Details")
        heading.setObjectName("SftpFormTitle")
        sub = QLabel("Configure receiver endpoint access.")
        sub.setObjectName("SftpFormSubtitle")
        right_layout.addWidget(heading)
        right_layout.addWidget(sub)

        form = QVBoxLayout()
        form.setSpacing(10)

        def field(label_text, placeholder="", value="", password=False, browse=False):
            wrap = QVBoxLayout()
            wrap.setSpacing(5)

            lbl = QLabel(label_text)
            lbl.setObjectName("SftpFieldLabel")

            box = QFrame()
            box.setObjectName("SftpInputBox")
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(12, 0, 10, 0)
            box_layout.setSpacing(8)

            inp = QLineEdit()
            inp.setObjectName("SftpBoxInput")
            font = inp.font()
            font.setWeight(QFont.Weight.Normal)
            inp.setFont(font)
            inp.setPlaceholderText(placeholder)
            inp.setText(value)
            inp.setMinimumHeight(34 if not self.compact_mode else 31)
            box_layout.addWidget(inp, 1)

            if password:
                inp.setEchoMode(QLineEdit.EchoMode.Password)
                show_btn = QPushButton("SHOW")
                show_btn.setObjectName("SftpFieldIconButton")
                show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                show_btn.setToolTip("Show / hide password")
                show_btn.setFixedSize(48, 28)

                def toggle_password():
                    if inp.echoMode() == QLineEdit.EchoMode.Password:
                        inp.setEchoMode(QLineEdit.EchoMode.Normal)
                        show_btn.setText("HIDE")
                    else:
                        inp.setEchoMode(QLineEdit.EchoMode.Password)
                        show_btn.setText("SHOW")

                show_btn.clicked.connect(toggle_password)
                box_layout.addWidget(show_btn)

            if browse:
                browse_btn = QPushButton("⌕")
                browse_btn.setObjectName("SftpFieldIconButton")
                browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                browse_btn.setToolTip("Select receiver project folder")
                browse_btn.setFixedSize(28, 28)

                def browse_folder():
                    start_dir = inp.text().strip() or os.path.expanduser("~")
                    selected = QFileDialog.getExistingDirectory(
                        dialog,
                        "Select Receiver Project Folder",
                        start_dir,
                        QFileDialog.Option.ShowDirsOnly,
                    )
                    if selected:
                        # User selects only the base/project folder.
                        # /received_face_data/pending is fixed by normalize_sftp_pending_path().
                        inp.setText(selected.replace("\\", "/"))

                browse_btn.clicked.connect(browse_folder)
                box_layout.addWidget(browse_btn)

            wrap.addWidget(lbl)
            wrap.addWidget(box)
            return wrap, inp

        host_port = QHBoxLayout()
        host_layout, host_input = field("Receiver Host / IP", "facerecognition2 or 10.121.xxx.xxx")
        port_layout, port_input = field("Port", "", "22")
        port_input.setFixedWidth(58 if not self.compact_mode else 50)
        host_port.addLayout(host_layout, 1)
        host_port.addLayout(port_layout)
        form.addLayout(host_port)

        user_layout, user_input = field("Username", "receiver Pi username", "jbl_facerec")
        pass_layout, pass_input = field("Password", "••••••••••••", "", password=True)
        form.addLayout(user_layout)
        form.addLayout(pass_layout)

        folder_layout, folder_input = field(
            "Receiver Project Folder",
            "/home/jbl_facerec/New",
            "/home/jbl_facerec/New",
            browse=True,
        )
        form.addLayout(folder_layout)

        pending_card = QFrame()
        pending_card.setObjectName("SftpPendingCard")
        pending_layout = QHBoxLayout(pending_card)
        pending_layout.setContentsMargins(12, 12, 12, 12)
        pending_layout.setSpacing(10)

        folder_icon = QLabel("▣")
        folder_icon.setObjectName("SftpFolderIcon")
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setFixedSize(40 if not self.compact_mode else 36, 40 if not self.compact_mode else 36)

        pending_text_box = QVBoxLayout()
        pending_text_box.setSpacing(4)
        pending_label = QLabel("Receiver Pending Folder")
        pending_label.setObjectName("SftpPendingLabel")
        pending_path = QLabel("")
        pending_path.setObjectName("SftpPendingPath")
        pending_path.setWordWrap(True)
        pending_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pending_path.setMinimumHeight(34 if not self.compact_mode else 30)
        pending_path.setMaximumHeight(48 if not self.compact_mode else 42)
        fixed_label = QLabel("Fixed suffix: /received_face_data/pending")
        fixed_label.setObjectName("SftpFixedSuffix")
        fixed_label.setWordWrap(True)

        pending_text_box.addWidget(pending_label)
        pending_text_box.addWidget(pending_path)
        pending_text_box.addWidget(fixed_label)

        pending_layout.addWidget(folder_icon, 0, Qt.AlignmentFlag.AlignTop)
        pending_layout.addLayout(pending_text_box, 1)

        form.addWidget(pending_card)

        status = QLabel("")
        status.setObjectName("SftpStatus")
        status.setWordWrap(True)
        form.addWidget(status)

        right_layout.addLayout(form)
        right_layout.addStretch()

        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SftpCancelButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setAutoDefault(False)
        cancel.setDefault(False)
        cancel.clicked.connect(dialog.reject)

        transfer = QPushButton("Transfer  →")
        transfer.setObjectName("SftpTransferButton")
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer.setAutoDefault(False)
        transfer.setDefault(False)

        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(transfer)
        right_layout.addLayout(actions)

        root.addWidget(left)
        root.addWidget(right, 1)

        def update_pending_path():
            full_path = self.normalize_sftp_pending_path(folder_input.text())
            pending_path.setText(full_path if full_path else "/received_face_data/pending")
            return full_path

        folder_input.textChanged.connect(lambda _: update_pending_path())
        update_pending_path()

        return dialog, {
            "host": host_input,
            "port": port_input,
            "username": user_input,
            "password": pass_input,
            "folder": folder_input,
            "pending_path": pending_path,
            "status": status,
            "transfer": transfer,
            "cancel": cancel,
        }


    def set_sftp_status(self, label, text: str, state: str = "normal"):
        label.setText(text)
        if state == "success":
            label.setObjectName("SftpStatusSuccess")
        elif state == "error":
            label.setObjectName("SftpStatusError")
        else:
            label.setObjectName("SftpStatus")
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def show_sftp_transfer_success(self, dialog, widgets, message: str, remote_path: str):
        """Replace SFTP form content with a success state inside the same card."""
        self.set_sftp_status(widgets["status"], f"{message}\nDestination: {remote_path}", "success")
        self.show_transfer_button_success(widgets["transfer"], "Link Active", "Transfer  →")

    def _face_api_sftp_send(self):
        """Open the Pi-backed multi-target SFTP popup.

        SAS is intentionally only a client/UI here. The connected Pi owns the
        saved target list, creates the one ZIP file, runs the four-worker SFTP
        queue, and exposes live batch state through its HTTP API.
        """
        active_progress = getattr(self, "_multi_sftp_progress_dialog", None)
        if active_progress is not None:
            active_state = getattr(active_progress, "_multi_sftp_state", {})
            if not active_state.get("cleanup_requested"):
                self._multi_sftp_restore_progress_window(active_progress)
                return

        dialog = self.create_multi_sftp_transfer_dialog()
        try:
            # Configure the shared FaceApiService from the currently selected
            # Pi hostname/IP before the popup starts any background API call.
            self._face_api_base_url()
            self._multi_sftp_load_targets(dialog)
        except Exception as exc:
            state = getattr(dialog, "_multi_sftp_state", {})
            self._multi_sftp_set_status(
                state.get("status"),
                f"Pi API is not connected. Please connect the Pi in Settings first. ({exc})",
                "error",
            )

        self._show_card_dialog(dialog)

        # The setup dialog stores this only after the Pi has accepted a new
        # batch. Opening progress here ensures the setup card has closed and
        # released its blur/dim overlay before the modeless window appears.
        launch = getattr(dialog, "_multi_sftp_launch_progress", None)
        if isinstance(launch, dict):
            batch_id = str(launch.get("batch_id", "") or "")
            snapshot = dict(launch.get("snapshot", {}) or {})
            if batch_id:
                QTimer.singleShot(
                    0,
                    lambda batch_id=batch_id, snapshot=snapshot:
                        self._multi_sftp_open_progress_window(batch_id, snapshot),
                )


    def create_sftp_windows_transfer_dialog(self):
        """Create SFTP pull popup for downloading face data from Pi to Windows.

        User-facing fields are Windows identity/save destination only. The Pi SFTP
        credential is treated as a backend/build configuration so normal users do
        not need to know or type the Pi SSH account.
        """
        dialog = QDialog(self)
        dialog.setObjectName("SftpTransferDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(760 if not self.compact_mode else 680, 555 if not self.compact_mode else 520)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("SftpMainCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QHBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QFrame()
        left.setObjectName("SftpLeftPanel")
        left.setFixedWidth(255 if not self.compact_mode else 220)

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(28 if not self.compact_mode else 22, 30, 24, 26)
        left_layout.setSpacing(18)

        icon = QLabel("⇩")
        icon.setObjectName("SftpLargeIcon")

        title = QLabel("SFTP\nWindows")
        title.setObjectName("SftpSideTitle")
        title.setWordWrap(True)

        desc = QLabel("Download face data from the connected Raspberry Pi to this Windows laptop using SFTP pull mode.")
        desc.setObjectName("SftpSideDesc")
        desc.setWordWrap(True)

        left_layout.addWidget(icon)
        left_layout.addWidget(title)
        left_layout.addWidget(desc)
        left_layout.addStretch()

        hint = QLabel("User enters Windows credentials and save path. SAS fetches the connected Pi username automatically and uses username = password for SFTP.")
        hint.setObjectName("SftpSideHint")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)

        right = QFrame()
        right.setObjectName("SftpRightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(38 if not self.compact_mode else 28, 30 if not self.compact_mode else 24, 38 if not self.compact_mode else 28, 26 if not self.compact_mode else 22)
        right_layout.setSpacing(12)

        top = QHBoxLayout()
        top_title = QLabel("Secure Access System")
        top_title.setObjectName("SftpShellTitle")
        close_btn = QPushButton("×")
        close_btn.setObjectName("SftpCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        top.addWidget(top_title)
        top.addStretch()
        top.addWidget(close_btn)
        right_layout.addLayout(top)

        heading = QLabel("Transfer to Windows")
        heading.setObjectName("SftpFormTitle")
        sub = QLabel("SAS downloads the prepared ZIP from the Pi by SFTP, then saves it to the selected Windows local or SMB folder.")
        sub.setObjectName("SftpFormSubtitle")
        sub.setWordWrap(True)
        right_layout.addWidget(heading)
        right_layout.addWidget(sub)

        form = QVBoxLayout()
        form.setSpacing(10)

        def field(label_text, placeholder="", value="", password=False, browse=False):
            wrap = QVBoxLayout()
            wrap.setSpacing(5)

            lbl = QLabel(label_text)
            lbl.setObjectName("SftpFieldLabel")

            box = QFrame()
            box.setObjectName("SftpInputBox")
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(12, 0, 10, 0)
            box_layout.setSpacing(8)

            inp = QLineEdit()
            inp.setObjectName("SftpBoxInput")
            font = inp.font()
            font.setWeight(QFont.Weight.Normal)
            inp.setFont(font)
            inp.setPlaceholderText(placeholder)
            inp.setText(value)
            inp.setMinimumHeight(34 if not self.compact_mode else 31)
            box_layout.addWidget(inp, 1)

            if password:
                inp.setEchoMode(QLineEdit.EchoMode.Password)
                show_btn = QPushButton("SHOW")
                show_btn.setObjectName("SftpFieldIconButton")
                show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                show_btn.setToolTip("Show / hide password")
                show_btn.setFixedSize(48, 28)

                def toggle_password():
                    if inp.echoMode() == QLineEdit.EchoMode.Password:
                        inp.setEchoMode(QLineEdit.EchoMode.Normal)
                        show_btn.setText("HIDE")
                    else:
                        inp.setEchoMode(QLineEdit.EchoMode.Password)
                        show_btn.setText("SHOW")

                show_btn.clicked.connect(toggle_password)
                box_layout.addWidget(show_btn)

            if browse:
                browse_btn = QPushButton("⌕")
                browse_btn.setObjectName("SftpFieldIconButton")
                browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                browse_btn.setToolTip("Select Windows save folder")
                browse_btn.setFixedSize(28, 28)

                def browse_folder():
                    start_dir = inp.text().strip() or os.path.expanduser("~")
                    selected = QFileDialog.getExistingDirectory(
                        dialog,
                        "Select Windows Save Folder",
                        start_dir,
                        QFileDialog.Option.ShowDirsOnly,
                    )
                    if selected:
                        inp.setText(selected)

                browse_btn.clicked.connect(browse_folder)
                box_layout.addWidget(browse_btn)

            wrap.addWidget(lbl)
            wrap.addWidget(box)
            return wrap, inp

        current_user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        username_layout, username_input = field("Windows Username / NTID", "4261233 or DOMAIN\\4261233", current_user)
        password_layout, password_input = field("Windows Password", "••••••••••••", "", password=True)
        form.addLayout(username_layout)
        form.addLayout(password_layout)

        folder_layout, folder_input = field(
            "Windows Save Folder",
            "C:\\JE_SFTP or \\\\server\\share\\folder",
            os.path.join(os.path.expanduser("~"), "Documents"),
            browse=True,
        )
        form.addLayout(folder_layout)

        info_card = QFrame()
        info_card.setObjectName("SftpPendingCard")
        info_layout = QHBoxLayout(info_card)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(10)

        folder_icon = QLabel("▣")
        folder_icon.setObjectName("SftpFolderIcon")
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setFixedSize(40 if not self.compact_mode else 36, 40 if not self.compact_mode else 36)

        info_text_box = QVBoxLayout()
        info_text_box.setSpacing(4)
        info_label = QLabel("Transfer Mode")
        info_label.setObjectName("SftpPendingLabel")
        info_path = QLabel("SFTP pull: SAS fetches the connected Pi username, uses the same value as the Pi SFTP password, downloads ZIP, then saves to the Windows path.")
        info_path.setObjectName("SftpPendingPath")
        info_path.setWordWrap(True)
        fixed_label = QLabel("Supported save destinations: local C drive folder or SMB/UNC shared folder path.")
        fixed_label.setObjectName("SftpFixedSuffix")
        fixed_label.setWordWrap(True)

        info_text_box.addWidget(info_label)
        info_text_box.addWidget(info_path)
        info_text_box.addWidget(fixed_label)

        info_layout.addWidget(folder_icon, 0, Qt.AlignmentFlag.AlignTop)
        info_layout.addLayout(info_text_box, 1)

        form.addWidget(info_card)

        status = QLabel("")
        status.setObjectName("SftpStatus")
        status.setWordWrap(True)
        form.addWidget(status)

        right_layout.addLayout(form)
        right_layout.addStretch()

        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SftpCancelButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(dialog.reject)

        transfer = QPushButton("Export  →")
        transfer.setObjectName("SftpTransferButton")
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)

        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(transfer)
        right_layout.addLayout(actions)

        root.addWidget(left)
        root.addWidget(right, 1)

        return dialog, {
            "windows_username": username_input,
            "windows_password": password_input,
            "folder": folder_input,
            "status": status,
            "transfer": transfer,
            "cancel": cancel,
        }


    def show_sftp_download_success(self, widgets, message: str, local_path: str):
        self.set_sftp_status(widgets["status"], f"{message}\nSaved to: {local_path}", "success")
        self.show_transfer_button_success(widgets["transfer"], "Downloaded", "Export  →")



    def _clean_pi_sftp_host(self, host: str) -> str:
        """Return hostname/IP only, without protocol or API port."""
        host = str(host or "").strip()
        if host.startswith("http://"):
            host = host.replace("http://", "", 1).split(":")[0].strip("/")
        elif host.startswith("https://"):
            host = host.replace("https://", "", 1).split(":")[0].strip("/")
        return host

    def _resolve_connected_pi_sftp_user(self, host: str) -> str:
        """Resolve the connected Pi Linux username for SFTP pull.

        Transfer to Windows rule: SAS gets the Pi username from the connected
        Pi /status API and uses the same value as the SFTP password. This lets
        SAS download from whichever Pi is currently connected without showing
        Pi SSH credentials in the user popup.
        """
        cached = str(getattr(self, "pi_system_user", "") or "").strip()
        if cached:
            return cached

        try:
            base = str(getattr(self, "pi_api_base", "") or "").rstrip("/")
            if base:
                response = requests.get(f"{base}/status", timeout=5)
                response.raise_for_status()
                data = response.json() if response.content else {}
                api_user = str(data.get("system_user") or data.get("ssh_username") or "").strip()
                api_hostname = str(data.get("hostname") or data.get("device_name") or "").strip()
                if api_hostname:
                    self.pi_device_hostname = api_hostname
                if api_user:
                    self.pi_system_user = api_user
                    return api_user
        except Exception:
            pass

        # Final fallback remains configurable for old Pi patches that do not yet
        # return system_user in /status.
        return str(globals().get("PI_SFTP_USERNAME", os.environ.get("SAS_PI_SFTP_USERNAME", "jbl_facerec")) or "").strip()

    def _get_backend_pi_sftp_config(self):
        """Return internal Pi SFTP config for Windows pull download.

        The user should not type Pi SSH credentials in the Windows transfer popup.
        SAS uses the currently connected Pi hostname/IP as the SFTP host, fetches
        the Pi Linux username from /status, and uses that same username as the
        SFTP password.
        """
        host = getattr(self, "pi_api_host", "") or ""
        if hasattr(self, "pi_host_input"):
            host = self.pi_host_input.text().strip() or host
        host = self._clean_pi_sftp_host(host)

        username = self._resolve_connected_pi_sftp_user(host) if host else ""
        password = username
        try:
            port = int(globals().get("PI_SFTP_PORT", os.environ.get("SAS_PI_SFTP_PORT", "22")) or 22)
        except Exception:
            port = 22
        return host, port, username, password

    def _unc_share_root(self, path: str) -> str:
        r"""Return \\server\share root for a UNC path, otherwise empty string."""
        p = (path or "").replace("/", "\\").strip()
        if not p.startswith("\\\\"):
            return ""
        parts = [part for part in p.split("\\") if part]
        if len(parts) < 2:
            return ""
        return "\\\\" + parts[0] + "\\" + parts[1]

    def _connect_smb_share_if_needed(self, save_folder: str, username: str, password: str):
        """Authenticate a UNC share with Windows credentials when needed.

        Local C/D drive paths do not use these credentials; SAS writes using the
        current Windows session. For SMB paths, Windows may require a net use
        session before Python can create/write files there.
        """
        share = self._unc_share_root(save_folder)
        if not share:
            return
        if platform.system().lower() != "windows":
            return
        if not username or not password:
            raise RuntimeError("Windows username/password are required for SMB shared folder saving.")

        cmd = ["net", "use", share, password, f"/user:{username}", "/persistent:no"]
        result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0 and "multiple connections" not in output.lower():
            raise RuntimeError(f"Unable to authenticate SMB share {share}: {output.strip() or 'net use failed'}")

    def _face_api_sftp_download_to_windows(self):
        """Download a prepared face-data ZIP from the connected Pi to this Windows laptop by SFTP."""
        dialog, widgets = self.create_sftp_windows_transfer_dialog()

        def do_transfer():
            if paramiko is None:
                self.set_sftp_status(widgets["status"], "Paramiko is required for SFTP download in SAS. Please include/install paramiko in the Windows build.", "error")
                return

            windows_username = widgets["windows_username"].text().strip()
            windows_password = widgets["windows_password"].text()
            save_folder = widgets["folder"].text().strip()
            host, port, username, password = self._get_backend_pi_sftp_config()

            if not windows_username:
                self.set_sftp_status(widgets["status"], "Windows username / NTID is required.", "error")
                return
            if not windows_password:
                self.set_sftp_status(widgets["status"], "Windows password is required.", "error")
                return
            if not save_folder:
                self.set_sftp_status(widgets["status"], "Windows save folder is required.", "error")
                return
            if not host:
                self.set_sftp_status(widgets["status"], "Pi hostname/IP is not configured. Please set and connect the Pi in Settings first.", "error")
                return
            if not username:
                self.set_sftp_status(widgets["status"], "Unable to fetch connected Pi username for SFTP. Please reconnect the Pi and try again.", "error")
                return
            if not password:
                self.set_sftp_status(widgets["status"], "Unable to derive Pi SFTP password from username. Please reconnect the Pi and try again.", "error")
                return

            self.start_transfer_button_loading(widgets["transfer"], "Export")
            self.set_sftp_status(widgets["status"], "Validating Windows credentials and preparing ZIP on Raspberry Pi...", "normal")

            def worker():
                transport = None
                sftp = None
                try:
                    # Windows credentials are used for user authorisation and SMB save path access.
                    ad_user = windows_username.split("\\")[-1].split("@", 1)[0].strip()
                    if not self._validate_ntid_password_in_ad(ad_user, windows_password):
                        raise RuntimeError("Windows credential validation failed. Please check username/password.")

                    self._connect_smb_share_if_needed(save_folder, windows_username, windows_password)

                    prepare = self._face_api_request(
                        "POST",
                        "/face-data/sftp-prepare-download",
                        {},
                        timeout=90,
                    )
                    remote_path = prepare.get("remote_path") or prepare.get("zip_path") or ""
                    filename = prepare.get("filename") or os.path.basename(str(remote_path))
                    if not remote_path or not filename:
                        raise RuntimeError("Pi did not return a downloadable ZIP path.")

                    os.makedirs(save_folder, exist_ok=True)
                    local_path = os.path.join(save_folder, filename)

                    def connecting():
                        self.set_sftp_status(widgets["status"], f"Connecting to current Pi {host}:{port} by SFTP and downloading package...", "normal")
                    self.qt_after(0, connecting)

                    ssh_lib = cast(Any, paramiko)
                    transport = ssh_lib.Transport((host, int(port)))
                    transport.connect(username=username, password=password)
                    sftp = ssh_lib.SFTPClient.from_transport(transport)
                    if sftp is None:
                        raise RuntimeError("SFTP connection was not created.")

                    sftp.get(remote_path, local_path)

                    message = prepare.get("message", "Face data downloaded to Windows successfully.")

                    def done():
                        self.show_sftp_download_success(widgets, message, local_path)
                        self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS: {remote_path} -> {local_path}")

                    self.qt_after(0, done)

                except Exception as e:
                    err = str(e)

                    def fail(err=err):
                        self.show_transfer_button_failed(widgets["transfer"], "Export  →")
                        self.set_sftp_status(widgets["status"], f"SFTP download failed: {err}", "error")
                        self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS_FAILED: {err}")

                    self.qt_after(0, fail)

                finally:
                    try:
                        if sftp is not None:
                            sftp.close()
                    except Exception:
                        pass
                    try:
                        if transport is not None:
                            transport.close()
                    except Exception:
                        pass

            Thread(target=worker, daemon=True).start()

        widgets["transfer"].clicked.connect(do_transfer)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        self._show_card_dialog(dialog)



    def _position_sas_received_badge(self):
        """Keep Check Received count badge on the right and vertically centred."""
        try:
            count = int(getattr(self, "_sas_received_badge_count", 0) or 0)
            badge = getattr(self, "sas_received_badge_label", None)
            btn = getattr(self, "sas_check_received_btn", None)
            if badge is None or btn is None:
                return
            if count <= 0:
                badge.hide()
                return
            bw = badge.width() or 22
            bh = badge.height() or 22
            btn_w = max(btn.width(), btn.sizeHint().width())
            btn_h = max(btn.height(), btn.sizeHint().height())
            if btn_w <= 0 or btn_h <= 0:
                return
            # Reserve a little breathing room from the right edge and centre
            # the badge with the Check Received label line.
            x = max(0, btn_w - bw - 12)
            y = max(0, int((btn_h - bh) / 2))
            badge.move(x, y)
            badge.raise_()
            badge.show()
        except RuntimeError:
            pass
        except Exception:
            pass

    def _update_sas_received_badge(self, count: int = 0):
        try:
            self._sas_received_badge_count = int(count or 0)
            badge = getattr(self, "sas_received_badge_label", None)
            if badge is None:
                return
            if count <= 0:
                badge.hide()
                return
            text = "99+" if count > 99 else str(count)
            badge.setText(text)
            if len(text) <= 2:
                badge.setFixedSize(22, 22)
                badge.setProperty("pill", False)
            else:
                badge.setFixedSize(30, 22)
                badge.setProperty("pill", True)
            try:
                badge.style().unpolish(badge)
                badge.style().polish(badge)
            except Exception:
                pass
            self._position_sas_received_badge()
            # The button width is not reliable during startup/layout creation.
            # Re-position again after Qt finishes the first layout pass so the
            # badge does not start on the left before the first user click.
            QTimer.singleShot(0, self._position_sas_received_badge)
            QTimer.singleShot(120, self._position_sas_received_badge)
        except Exception:
            pass

    def _show_sas_desktop_notification(self, count: int, filenames=None):
        """Show one Windows notification for pending face data using the SAS app identity."""
        filenames = filenames or []
        if count <= 0:
            return
        title = "New received face data"
        message = "1 pending ZIP is waiting for review." if count == 1 else f"{count} pending ZIP files are waiting for review."
        if filenames:
            preview = ", ".join(map(str, filenames[:2]))
            if len(filenames) > 2:
                preview += ", ..."
            message = f"{message}\n{preview}"

        shown = False
        if platform.system().lower() == "windows":
            try:
                # Make notifications identify as Secure Access System instead of python.exe where Windows allows it.
                try:
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Secure.Access.System")
                except Exception:
                    pass

                import base64
                logo_path = app_resource_path("assets", "sas_logo.png")
                logo_uri = ""
                if os.path.exists(logo_path):
                    try:
                        logo_uri = "file:///" + os.path.abspath(logo_path).replace("\\", "/").replace(" ", "%20")
                    except Exception:
                        logo_uri = ""

                ps_template = r"""
$Title = __TITLE__
$Message = __MESSAGE__
$Logo = __LOGO__
$AppId = "Secure.Access.System"
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$templateType = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
if ($Logo -and $Logo.Length -gt 0) {
    $templateType = [Windows.UI.Notifications.ToastTemplateType]::ToastImageAndText02
}
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($templateType)
if ($Logo -and $Logo.Length -gt 0) {
    $imageNodes = $template.GetElementsByTagName("image")
    if ($imageNodes.Length -gt 0) {
        $imageNodes.Item(0).Attributes.GetNamedItem("src").NodeValue = $Logo
        $imageNodes.Item(0).Attributes.GetNamedItem("alt").NodeValue = "Secure Access System"
    }
}
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode($Title)) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode($Message)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId)
$notifier.Show($toast)
"""
                ps = (
                    ps_template
                    .replace("__TITLE__", repr(title))
                    .replace("__MESSAGE__", repr(message))
                    .replace("__LOGO__", repr(logo_uri))
                )
                encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                shown = True
            except Exception:
                shown = False

        # Do not use Qt tray balloon fallback here. In development/source runs,
        # Qt tray notifications can appear as "Python" in Windows notification
        # centre.  Keep only the Windows toast path so users do not receive a
        # duplicate Python-branded notification.

        try:
            app = QApplication.instance()
            if isinstance(app, QApplication):
                app.alert(self, 5000)
        except Exception:
            pass

    def _normalise_received_pending_items(self, pending):
        """Return [{'filename': str, 'size': int|None, 'modified': float|None}, ...]."""
        items = []
        for item in pending or []:
            if isinstance(item, dict):
                filename = str(item.get("filename") or item.get("name") or "").strip()
                if not filename:
                    continue
                items.append({
                    "filename": filename,
                    "size": item.get("size"),
                    "modified": item.get("modified"),
                })
            else:
                filename = str(item).strip()
                if filename:
                    items.append({"filename": filename, "size": None, "modified": None})
        return items

    def _received_item_display_text(self, item: dict) -> str:
        return str(item.get("filename") or "").strip()

    def _poll_received_face_data_for_sas(self):
        if not getattr(self, "pi_connected", False):
            self._update_sas_received_badge(0)
            return

        def worker():
            try:
                data = self._face_api_request("GET", "/face-data/received", timeout=20)
                pending = self._normalise_received_pending_items(data.get("pending", []))
                self.qt_after(0, lambda pending=pending: self._handle_sas_received_pending(pending, manual=False))
            except Exception:
                # Keep background polling quiet to avoid noisy logs when Pi is temporarily unreachable.
                pass

        Thread(target=worker, daemon=True).start()

    def _handle_sas_received_pending(self, pending, manual: bool = False):
        pending_items = self._normalise_received_pending_items(pending)
        self._update_sas_received_badge(len(pending_items))

        current = {str(item.get("filename") or "").strip() for item in pending_items if item.get("filename")}
        if not getattr(self, "sas_received_poll_initialized", False):
            self.sas_received_seen_files = set(current)
            self.sas_received_poll_initialized = True
            if manual and pending_items:
                self._show_sas_received_popup(pending_items, auto_prompt=False)
            elif manual:
                self.append_face_log("RECEIVED: No pending face data.")
            return

        new_files = [item.get("filename") for item in pending_items if item.get("filename") not in self.sas_received_seen_files]
        self.sas_received_seen_files = set(current)

        if manual:
            if pending_items:
                self._show_sas_received_popup(pending_items, auto_prompt=False)
            else:
                self.append_face_log("RECEIVED: No pending face data.")
            return

        if new_files:
            self.append_face_log(f"RECEIVED: {len(new_files)} new pending package(s): {', '.join(new_files[:5])}")
            self._show_sas_desktop_notification(len(new_files), new_files)
            self._show_sas_received_popup(pending_items, auto_prompt=True)

    def _face_api_check_received(self):
        def worker():
            try:
                data = self._face_api_request("GET", "/face-data/received", timeout=30)
                pending = self._normalise_received_pending_items(data.get("pending", []))
                self.qt_after(0, lambda pending=pending: self._handle_sas_received_pending(pending, manual=True))
            except Exception as e:
                self.qt_after(0, lambda e=e: self.append_face_log(f"RECEIVED_CHECK_FAILED: {e}"))

        Thread(target=worker, daemon=True).start()

    def _show_sas_received_popup(self, pending, auto_prompt: bool = False):
        if getattr(self, "sas_received_popup_visible", False):
            return
        pending_items = self._normalise_received_pending_items(pending)
        if not pending_items:
            return

        self.sas_received_popup_visible = True
        dialog = QDialog(self)
        dialog.setObjectName("TransferDialog")
        dialog.setModal(False)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setFixedSize(680 if not self.compact_mode else 560, 520 if not self.compact_mode else 455)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame(dialog)
        card.setObjectName("TransferCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(18)
        icon = QLabel("⇩")
        icon.setObjectName("TransferHeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(58, 58)
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Pending Received Face Data")
        title.setObjectName("TransferTitle")
        subtitle = QLabel(f"{len(pending_items)} ZIP file(s) waiting for review. Select one to accept or reject.")
        subtitle.setObjectName("TransferHint")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        close_btn = QPushButton("×")
        close_btn.setObjectName("TransferIconButton")
        close_btn.setFixedSize(34, 34)
        close_btn.clicked.connect(dialog.close)
        header.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        source_card = QFrame()
        source_card.setObjectName("ReceivedSourceCard")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(18, 16, 18, 16)
        source_layout.setSpacing(10)

        source_header = QHBoxLayout()
        source_icon = QLabel("▣")
        source_icon.setObjectName("ReceivedSourceIcon")
        source_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source_icon.setFixedSize(26, 26)
        source_header.addWidget(source_icon)
        source_label = QLabel("METADATA SOURCE")
        source_label.setObjectName("TransferSubtitle")
        source_header.addWidget(source_label, 1)
        source_layout.addLayout(source_header)

        search_box = QFrame()
        search_box.setObjectName("TransferInputBox")
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 0, 10, 0)
        search_layout.setSpacing(8)
        search = QLineEdit()
        search.setObjectName("TransferInput")
        search.setPlaceholderText("Search received zip files...")
        search.setMinimumHeight(32 if not self.compact_mode else 30)
        search_icon = QLabel("⌕")
        search_icon.setObjectName("TransferSearchIcon")
        search_layout.addWidget(search, 1)
        search_layout.addWidget(search_icon)
        source_layout.addWidget(search_box)

        list_box = QListWidget()
        list_box.setObjectName("ReceivedZipList")
        list_box.setFrameShape(QFrame.Shape.NoFrame)
        list_box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        list_box.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        list_box.setSpacing(3)
        list_box.setUniformItemSizes(True)
        row_h = 32 if not self.compact_mode else 30
        max_visible_rows = 5
        list_box.setFixedHeight(row_h * max_visible_rows + 10)

        received_state = {"all_items": list(pending_items)}

        def populate_received_list(items, keep_selection: str = ""):
            list_box.blockSignals(True)
            list_box.clear()
            for item in items:
                filename = self._received_item_display_text(item)
                list_box.addItem(filename)
            list_box.clearSelection()
            list_box.setCurrentRow(-1)
            if keep_selection:
                for i in range(list_box.count()):
                    if list_box.item(i).text().strip() == keep_selection:
                        list_box.setCurrentRow(i)
                        break
            list_box.blockSignals(False)

        def apply_received_search():
            query = search.text().strip().lower()
            selected = list_box.currentItem().text().strip() if list_box.currentItem() else ""
            if query:
                filtered = [i for i in received_state["all_items"] if query in self._received_item_display_text(i).lower()]
            else:
                filtered = list(received_state["all_items"])
            populate_received_list(filtered, selected)
            if filtered:
                status = getattr(self, "sftp_status_label", None) or QLabel("")
                status.setText(f"{len(filtered)} ZIP file(s) shown. Select one to accept or reject.")
            else:
                status = getattr(self, "sftp_status_label", None) or QLabel("")
                status.setText("No matching ZIP files found.")

        populate_received_list(received_state["all_items"])
        search.textChanged.connect(apply_received_search)
        source_layout.addWidget(list_box, 0)
        source_card.setMaximumHeight(row_h * max_visible_rows + 132)
        layout.addWidget(source_card, 0)

        status = QLabel("Waiting for manual validation...")
        status.setObjectName("TransferHint")
        status.setWordWrap(True)
        layout.addWidget(status)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("TransferCancelButton")
        reject = QPushButton("Reject")
        reject.setObjectName("TransferSecondaryActionButton")
        accept = QPushButton("Accept")
        accept.setObjectName("TransferPrimaryButton")
        row.addWidget(close)
        row.addWidget(reject)
        row.addWidget(accept)
        layout.addLayout(row)
        accept.setEnabled(False)
        reject.setEnabled(False)

        def update_received_action_state():
            has_selection = list_box.currentItem() is not None
            accept.setEnabled(has_selection)
            reject.setEnabled(has_selection)
            if has_selection:
                status.setText("Selected ZIP is ready for manual validation.")

        list_box.itemSelectionChanged.connect(update_received_action_state)

        def current_filename():
            item = list_box.currentItem()
            if item is None:
                status.setText("Please select a ZIP file first.")
                return ""
            return item.text().strip()

        def refresh_list_from_pi():
            def worker():
                try:
                    data = self._face_api_request("GET", "/face-data/received", timeout=30)
                    latest = self._normalise_received_pending_items(data.get("pending", []))

                    def done():
                        received_state["all_items"] = list(latest)
                        if latest:
                            apply_received_search()
                            status.setText(f"{len(latest)} ZIP file(s) still waiting for review. Select one to accept or reject.")
                        else:
                            status.setText("No pending received ZIP files remain.")
                            dialog.close()
                        self._update_sas_received_badge(len(latest))
                        self.sas_received_seen_files = {str(i.get("filename") or "").strip() for i in latest if i.get("filename")}

                    self.qt_after(0, done)
                except Exception as e:
                    self.qt_after(0, lambda e=e: status.setText(f"Refresh failed: {e}"))

            Thread(target=worker, daemon=True).start()

        def do_action(action: str):
            filename = current_filename()
            if not filename:
                return
            endpoint = "/face-data/received/accept" if action == "accept" else "/face-data/received/reject"
            label = "Accept" if action == "accept" else "Reject"
            accept.setEnabled(False)
            reject.setEnabled(False)

            if action == "accept":
                # Reuse the same import progress/success UI used by the normal Import flow.
                self.rebuild_import_loading_card(layout, dialog, filename)
            else:
                status.setText(f"Rejecting {filename}...")

            def worker():
                try:
                    data = self._face_api_request("POST", endpoint, payload={"filename": filename}, timeout=120)
                    message = data.get("message", f"{label} completed.")
                    imported_users = data.get("imported_users", [])
                    skipped_users_count = int(data.get("skipped_users_count", 0) or 0)
                    if data.get("import_mode") in ("add_on", "add_new_only"):
                        skipped_users_count = 0
                    for k in ("added_ids", "merged_users", "imported_ids"):
                        if not imported_users and isinstance(data.get(k, None), list):
                            imported_users = data.get(k, [])

                    def done():
                        self.append_face_log(f"RECEIVED_{action.upper()}: {filename}")
                        if action == "accept":
                            self.finish_import_progress_then_success(layout, dialog, filename, imported_users, skipped_users_count, message)
                            self._face_api_refresh_users()
                            self._face_api_check_received()
                        else:
                            status = getattr(self, "sftp_status_label", None) or QLabel("")
                            status.setText(message)
                            accept.setEnabled(True)
                            reject.setEnabled(True)
                            refresh_list_from_pi()

                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)

                    def fail():
                        if action == "accept":
                            self.rebuild_import_failed_card(layout, dialog, f"Import failed: {err}")
                        else:
                            status = getattr(self, "sftp_status_label", None) or QLabel("")
                            status.setText(f"{label} failed: {err}")
                            accept.setEnabled(True)
                            reject.setEnabled(True)

                    self.qt_after(0, fail)

            Thread(target=worker, daemon=True).start()

        close.clicked.connect(dialog.close)
        reject.clicked.connect(lambda: do_action("reject"))
        accept.clicked.connect(lambda: do_action("accept"))

        def on_finished(*args):
            self.sas_received_popup_visible = False

        dialog.finished.connect(on_finished)
        self._show_card_dialog(dialog)


    def get_user_capture_frames_from_pi(self, user_id: str) -> int:
        """Read /users and find how many capture frames belong to the NTID."""
        try:
            data = self._face_api_request("GET", "/users", timeout=20)
            users = data.get("users", [])
            for user in users:
                uid = str(user.get("id", "")).strip().lower()
                if uid == str(user_id).strip().lower():
                    return int(user.get("photos", 0) or 0)
        except Exception:
            pass
        return 0

    def wait_until_pi_capture_complete(self, timeout_seconds: int = 90):
        """Wait until the Pi API reports capture is no longer running."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status
                cap = bool(status.get("capture_running", False))
                if not cap:
                    return True, status
            except Exception:
                pass
            time.sleep(0.35)

        return False, last_status or {}

    def wait_until_pi_recognition_running(self, timeout_seconds: int = 18):
        """Wait for the Pi to finish capture and return to background recognition."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status
                recognition = bool(status.get("recognition_running", False))
                capture = bool(status.get("capture_running", False))
                if recognition and not capture:
                    return True, status
            except Exception:
                pass
            time.sleep(0.35)

        return False, last_status or {}

    def show_capture_complete_popup(self, ntid: str, frames: int = 0):
        dialog = CaptureCompleteDialog(
            self,
            ntid=ntid,
            frames=frames,
            compact_mode=self.compact_mode,
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

    def auto_open_recognize_after_capture(self):
        """Legacy compatibility helper kept for older call sites.

        Pi recognition is resumed by the Pi service after an SAS capture ends.
        SAS only opens the Windows preview when the user presses Recognize.
        """
        self.face_action_feedback(
            "CAPTURE_COMPLETE: Pi recognition is running in the background. "
            "Press Recognize only to open the SAS preview."
        )

    def show_delete_complete_popup(self, ntid: str, dataset_removed: bool = False, encodings_removed: int = 0):
        dialog = DeleteCompleteDialog(
            self,
            ntid=ntid,
            dataset_removed=dataset_removed,
            encodings_removed=encodings_removed,
            compact_mode=self.compact_mode,
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

    def render_face_users(self, users):
        """Render Face Recognition authorised users panel.

        Stable repaint version:
        - no row opacity effects
        - no automatic scroll-to-top on every refresh
        - prevents blank/ghost cards after Recognize + scrolling
        """
        if not hasattr(self, "face_users_list_layout"):
            return

        # Preserve current scroll position when refresh is caused by recognition/user refresh.
        current_scroll = 0
        try:
            if hasattr(self, "face_users_scroll"):
                current_scroll = self.face_users_scroll.verticalScrollBar().value()
        except Exception:
            current_scroll = 0

        while self.face_users_list_layout.count():
            item = self.face_users_list_layout.takeAt(0)
            if item is None:
                continue

            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.hide()
                widget.setGraphicsEffect(cast(QGraphicsEffect, None))  # type: ignore[arg-type]
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout_widgets(child_layout)

        users = users or []
        self.face_users_cache = users

        keyword = ""
        if hasattr(self, "face_user_search_input"):
            keyword = self.face_user_search_input.text().strip().lower()

        filtered = [
            u for u in users
            if keyword in str(u.get("id", "")).lower()
        ] if keyword else list(users)

        if hasattr(self, "face_users_subtitle"):
            if users:
                if keyword:
                    self.face_users_subtitle.setText(f"{len(filtered)} / {len(users)} MATCHED")
                else:
                    self.face_users_subtitle.setText(f"{len(users)} ACTIVE RECORDS")
            else:
                self.face_users_subtitle.setText("CONNECT PI FIRST")

        self._open_face_user_expand_card = None

        if not users:
            self.face_users_list_layout.addWidget(
                self.face_user_row("CONNECT PI", "Please connect hostname/IP first", "OFFLINE", False)
            )
            self.face_users_list_layout.addStretch()
            return

        if not filtered:
            msg = QLabel("No matching user found.")
            msg.setObjectName("FaceUserEmptyMessage")
            msg.setWordWrap(True)
            self.face_users_list_layout.addWidget(msg)
            self.face_users_list_layout.addStretch()
            return

        for user in filtered:
            uid = str(user.get("id", ""))
            photos = user.get("photos", 0)
            trained = bool(user.get("trained", False))

            row = self.face_user_row(
                uid.upper(),
                f"{photos} Capture frames",
                "TRAINED" if trained else "PENDING",
                trained,
            )

            # Prevent rows from stretching into large blank blocks inside QScrollArea.
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.setGraphicsEffect(cast(QGraphicsEffect, None))  # type: ignore[arg-type]

            self.face_users_list_layout.addWidget(row)

        self.face_users_list_layout.addStretch()

        if hasattr(self, "face_users_body"):
            self.face_users_body.updateGeometry()
            self.face_users_body.adjustSize()

        if hasattr(self, "face_users_scroll"):
            self.face_users_scroll.viewport().update()
            self.face_users_scroll.update()

            # Restore old position after refresh; only search clear button naturally changes visible content.
            QTimer.singleShot(
                0,
                lambda value=current_scroll: self.face_users_scroll.verticalScrollBar().setValue(
                    min(value, self.face_users_scroll.verticalScrollBar().maximum())
                )
            )

    def _read_recognition_result(self):
        return self.recognition_state_service.read_result(self.server_path)

    def _grant_access(self, name=""):
        self.runtime_lock_service.grant_access(self, name)
        # Treat a successful unlock as a fresh activity anchor so the system
        # does not instantly re-lock when there has been no physical input yet.
        self.mark_user_activity(reset_countdown=True)

    def _do_logout(self):
        self.runtime_lock_service.lock_system(self)

    def face_action_feedback(self, message: str):
        self.append_face_log(message)


    # --------------------------------------------------------
    # Fixed footer
    # --------------------------------------------------------
    def build_footer_area(self):
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

    def build_footer_strip(self):
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
        self.footer_state_label = InfoLabel("STATE FILE", RECOGNITION_RESULT_FILE, self.ui_scale)
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

    def vertical_line(self):
        line = QFrame()
        line.setObjectName("VerticalLine")
        line.setFixedSize(1, 24 if not self.compact_mode else 20)
        return line

    # --------------------------------------------------------
    # Responsive layout scaling
    # --------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Recalculate centred content width when maximising or moving to a large monitor.
        try:
            max_w = self.content_max_width()
            for page in ("dashboard_page", "face_page", "settings_page"):
                p = getattr(self, page, None)
                if p is not None:
                    scroll = p.findChild(QScrollArea)
                    if scroll is not None and scroll.widget() is not None:
                        scroll.widget().setMaximumWidth(max_w)
        except Exception:
            pass

        self.update_dashboard_card_sizes()
        self.update_face_card_sizes()

        if hasattr(self, "account_menu") and self.account_menu.isVisible() and self.account_menu.height() > 0:
            self.position_account_menu()
    def update_dashboard_card_sizes(self):
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


    def update_face_card_sizes(self):
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
            controls_h = 205
            logs_h = 170
        elif w >= 1300:
            left_w = max(300, min(int((available_w - gap_w) * 0.27), 370))
            right_w = max(760, min(available_w - gap_w - left_w, 1030))
            controls_h = 200
            logs_h = 165
        else:
            left_w = 300 if not self.compact_mode else 270
            right_w = max(640 if not self.compact_mode else 560, available_w - gap_w - left_w)
            controls_h = 190 if not self.compact_mode else 172
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
        self.runtime_lock_service.apply_security_options(self)
        self.emergency_recovery_timer = QTimer(self)
        self.emergency_recovery_timer.timeout.connect(self.refresh_emergency_recovery_state)
        self.emergency_recovery_timer.start(3000)

        self.sas_received_timer = QTimer(self)
        self.sas_received_timer.timeout.connect(self._poll_received_face_data_for_sas)
        self.sas_received_timer.start(15000)
        QTimer.singleShot(2500, self._poll_received_face_data_for_sas)

    def update_time(self):
        if self.current_top_tab != "Dashboard":
            return
        now = QDateTime.currentDateTime()
        self.time_label.setText(now.toString("HH:mm:ss"))
        self.date_label.setText(now.toString("dddd, MMMM dd, yyyy").upper())

    def poll_recognition_result(self):
        """Poll recognition_result.json only after SAS is locked.

        Auto-lock now follows Windows screen-saver behaviour:
        mouse/keyboard inactivity triggers the countdown. Face recognition does
        not start the countdown. After SAS is locked, a valid recognition result
        unlocks the system and resets the inactivity timer.
        """
        if getattr(self, "first_launch_setup_mode", False) or not getattr(self, "server_configured", False):
            # New EXE / blank configuration:
            # no server path and no recognition_result.json yet. Keep Dashboard usable.
            self.is_locked = False
            self._pending_auto_lock = False
            self.set_face_detected(False)
            return

        # While unlocked, do not use camera/no-face state to drive auto-lock.
        # The countdown is handled by update_countdown() using keyboard/mouse inactivity.
        if not getattr(self, "is_locked", False):
            if getattr(self, "face_detected", False):
                self.set_face_detected(False)
            return

        result = self._read_recognition_result()
        state, ntid, detected_time, confidence = result

        # Lightweight diagnostic: only log when recognition-result state changes.
        last_state = getattr(self, "_last_recognition_result_state", None)
        state_key = (state, ntid)
        if state_key != last_state:
            self._last_recognition_result_state = state_key
            if state in ("no_file", "no_server_path", "error"):
                self.append_system_log(f"Recognition state: {state} | server={self.server_path}")

        if state == "valid":
            self._pending_auto_lock = False
            ntid_text = str(ntid or "").upper()
            self._grant_access(f"{ntid_text} ({confidence}%)")
            self.write_sas_log(f"UNLOCKED | USER={ntid_text} | CONFIDENCE={confidence}%")
            self.is_locked = False
            self.is_logged_in = True
            self.apply_lock_state()
            self.hide_system_locked_notification()
            self.set_face_detected(False)
            self.mark_user_activity(reset_countdown=True)
            QTimer.singleShot(450, self.minimize_after_face_unlock)
            return

        # Still locked and no valid recognition result yet.
        self.set_face_detected(False)
        self.time_left = 0
        self.apply_timeout_to_countdown(reset=False)

    def reset_countdown_after_manual_unlock(self):
        """Reset countdown to user-configured time after emergency/manual unlock."""
        self._pending_auto_lock = False
        self.mark_user_activity(reset_countdown=False)
        self.total_seconds = max(1, int(self.lock_timeout_seconds))
        self.time_left = self.total_seconds

        if hasattr(self, "ring"):
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)

        if hasattr(self, "countdown_label"):
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")

    def finish_auto_lock_after_ring(self):
        """Lock only after the inactivity countdown ring has reached 00:00."""
        if not getattr(self, "_pending_auto_lock", False):
            return

        if self.is_locked:
            self._pending_auto_lock = False
            return

        if self.should_suspend_inactivity_lock():
            self._pending_auto_lock = False
            self.mark_user_activity(reset_countdown=True)
            return

        # Safety check: if the user moved the mouse or typed during the final
        # ring animation delay, cancel the pending lock and refill the timer.
        idle_seconds = self.get_effective_idle_seconds()
        timeout_seconds = max(1, int(self.lock_timeout_seconds))
        if idle_seconds < timeout_seconds:
            self._pending_auto_lock = False
            self.mark_user_activity(reset_countdown=True)
            return

        self._pending_auto_lock = False
        self.is_locked = True
        self.is_logged_in = False
        self.apply_lock_state()
        self.set_face_detected(False)
        self.append_system_log("Auto locked: keyboard and mouse inactive until countdown ended")

    def update_countdown(self, initial=False):
        if not hasattr(self, "countdown_label") or not hasattr(self, "ring"):
            return

        if getattr(self, "first_launch_setup_mode", False):
            self.is_locked = False
            self._pending_auto_lock = False
            self.total_seconds = max(1, int(self.lock_timeout_seconds))
            self.time_left = self.total_seconds
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)
            return

        if self.should_suspend_inactivity_lock() and not self.is_locked:
            self._pending_auto_lock = False
            self.total_seconds = max(1, int(self.lock_timeout_seconds))
            self.time_left = self.total_seconds
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)
            return

        self.total_seconds = max(1, int(self.lock_timeout_seconds))
        self.ring.set_total_seconds(self.total_seconds)

        # Locked state stays at 00:00 until recognition_result.json contains a
        # valid face result and poll_recognition_result() unlocks the system.
        if self.is_locked:
            self._pending_auto_lock = False
            self.time_left = 0
            self.countdown_label.setText("00:00")
            self.ring.set_time_left(0, animate=False)
            return

        # Screen-saver style countdown: any keyboard or mouse activity refills
        # the timer. Camera/no-face state must not affect this countdown.
        if getattr(self, "face_detected", False):
            self.set_face_detected(False)

        idle_seconds = self.get_effective_idle_seconds()
        remaining = max(0, self.total_seconds - int(idle_seconds))
        self.time_left = remaining

        mins = self.time_left // 60
        secs = self.time_left % 60
        self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
        self.ring.set_time_left(self.time_left, animate=not initial)

        # Important:
        # Do not lock immediately at 00:00. Let the ring line finish its final
        # smooth animation from 00:01 to 00:00, then lock after the ring reaches end.
        if self.time_left <= 0 and not self.is_locked and not self._pending_auto_lock:
            self._pending_auto_lock = True
            QTimer.singleShot(1050, self.finish_auto_lock_after_ring)



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

            #BrandRow {{
                background: transparent;
            }}

            #HeaderLogo {{
                background: transparent;
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
                font-weight: 700;
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
                font-size: {10 if not self.compact_mode else 9}px;
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
                font-size: {10 if not self.compact_mode else 9}px;
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
                font-size: {max(22, int(title_font * 0.72))}px;
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
                color: #10B981;
                border: none;
                border-radius: 16px;
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
                color: #FFFFFF;
                font-size: {countdown_font}px;
                font-weight: 900;
            }}

            #RemainingText {{
                color: rgba(255, 255, 255, 0.78);
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
                letter-spacing: 1px;
            }}

            #CountdownTitle {{
                color: rgba(255, 255, 255, 0.78);
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
            }}

            #CountdownDesc {{
                color: rgba(255, 255, 255, 0.90);
                font-size: {18 if not self.compact_mode else 14}px;
                font-weight: 900;
            }}


            #CircleFlipContainer, #CircleStack, #CircleFace {{
                background: transparent;
                border: none;
            }}

            #FaceDetectedCircle {{
                background: rgba(255, 255, 255, 0.16);
                border: 3px solid rgba(255, 255, 255, 0.32);
                border-radius: {95 if not self.compact_mode else 70}px;
            }}

            #FaceDetectedIcon {{
                color: white;
                background: transparent;
                border: none;
                font-size: {48 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #FaceDetectedCircleText {{
                color: white;
                background: transparent;
                border: none;
                font-size: {13 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 0.5px;
                padding: 3px 8px;
            }}

            #FaceDetectedState {{
                color: #FFFFFF;
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

            #AuthorizedUsersDashboardIconButton {{
                background: rgba(255, 255, 255, 0.18);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.30);
                border-radius: {24 if not self.compact_mode else 20}px;
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 900;
                padding-bottom: 2px;
            }}

            #AuthorizedUsersDashboardIconButton:hover {{
                background: rgba(255, 255, 255, 0.30);
            }}

            #AuthorizedUsersDashboardIconButton:pressed {{
                background: rgba(255, 255, 255, 0.38);
                padding-top: 2px;
            }}

            #AuthorizedUsersDashboardButton {{
                background: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.24);
                border-radius: 16px;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 900;
                letter-spacing: 1.3px;
            }}

            #AuthorizedUsersDashboardButton:hover {{
                background: rgba(255, 255, 255, 0.26);
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

            #MissingCredentialsSetupDialog {{
                background: transparent;
            }}

            #MissingCredentialsPanel {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 30px;
            }}

            #MissingCredentialsIcon {{
                background: #FFDAD6;
                color: #93000A;
                border: 1px solid rgba(186, 26, 26, 0.20);
                border-radius: {36 if not self.compact_mode else 31}px;
                font-size: {36 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #MissingCredentialsTitle {{
                color: {Theme.PRIMARY};
                font-size: {24 if not self.compact_mode else 21}px;
                font-weight: 900;
                letter-spacing: -0.6px;
            }}

            #MissingCredentialsMessage {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
                line-height: 1.45;
            }}

            #MissingCredentialsPrimaryButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 14px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
                letter-spacing: 1.1px;
            }}

            #MissingCredentialsPrimaryButton:hover {{
                background: #1F1F1F;
            }}

            #MissingCredentialsPrimaryButton:pressed {{
                background: #333333;
                padding-top: 2px;
            }}

            #MissingCredentialsWatermark {{
                color: rgba(0, 0, 0, 0.035);
                font-size: {96 if not self.compact_mode else 76}px;
                font-weight: 900;
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


            #SmallIconButton {{
                background: #F3F3F3;
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SmallIconButton:hover {{
                background: #E8E8E8;
            }}




            #ExportStateEyebrow {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 2.2px;
            }}

            #ExportStateActive {{
                color: #000000;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #ExportStateShield {{
                color: #000000;
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 900;
            }}


            #ExportCircleSpinner {{
                background: transparent;
                border: none;
            }}


            #ExportSpinnerWrap {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: {52 if not self.compact_mode else 46}px;
            }}

            #ExportSpinner {{
                color: #000000;
                font-size: {34 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #ExportSpinnerInner {{
                background: #000000;
                color: #FFFFFF;
                border-radius: {17 if not self.compact_mode else 15}px;
                padding: 0px;
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 900;
            }}

            #ExportStateTitle {{
                color: #000000;
                font-size: {19 if not self.compact_mode else 16}px;
                font-weight: 900;
                letter-spacing: 0.6px;
            }}

            #ExportStateSubtitle {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #ExportProgressOuter {{
                background: #EEEEEE;
                border: none;
                border-radius: 3px;
            }}

            #ExportProgressFill {{
                background: #000000;
                border: none;
                border-radius: 3px;
            }}

            #ExportMetricLabel {{
                color: #747878;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 1.4px;
            }}

            #ExportMetricValue {{
                color: #000000;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #ExportPercentage {{
                color: #000000;
                font-size: {24 if not self.compact_mode else 20}px;
                font-weight: 900;
            }}

            #ExportSuccessIcon {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: {34 if not self.compact_mode else 29}px;
                font-size: {44 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #ExportFailedIcon {{
                background: #BA1A1A;
                color: #FFFFFF;
                border: none;
                border-radius: {34 if not self.compact_mode else 29}px;
                font-size: {44 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #ExportSuccessTitle {{
                color: #000000;
                font-size: {26 if not self.compact_mode else 21}px;
                font-weight: 700;
                letter-spacing: -0.3px;
            }}

            #ExportSuccessSubtitle {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}

            #ExportDetailBlock {{
                background: #EEEEEE;
                border: 1px solid #C4C7C7;
                border-radius: 10px;
            }}

            #ExportDetailCode {{
                background: rgba(255,255,255,0.65);
                color: #000000;
                border: 1px solid rgba(196,199,199,0.45);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}


            #ImportSourceFile {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }}

            #ImportInfoIcon {{
                background: #E8E8E8;
                color: #000000;
                border: 1px solid #C4C7C7;
                border-radius: {34 if not self.compact_mode else 29}px;
                font-size: {32 if not self.compact_mode else 26}px;
                font-weight: 900;
            }}


            #ExportReturnButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.3px;
            }}

            #ExportReturnButton:hover {{
                background: #2F3131;
            }}



            #SftpTransferDialog {{
                background: transparent;
            }}

            #SftpMainCard {{
                background: rgba(249, 249, 249, 0.92);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 18px;
            }}

            #SftpLeftPanel {{
                background: #111111;
                border-top-left-radius: 18px;
                border-bottom-left-radius: 18px;
            }}

            #SftpRightPanel {{
                background: rgba(255, 255, 255, 0.96);
                border-top-right-radius: 18px;
                border-bottom-right-radius: 18px;
            }}

            #SftpLargeIcon {{
                color: #FFFFFF;
                font-size: {46 if not self.compact_mode else 38}px;
            }}

            #SftpSideTitle {{
                color: #F4F4F4;
                font-size: {30 if not self.compact_mode else 24}px;
                font-weight: 900;
                letter-spacing: -0.5px;
            }}

            #SftpSideDesc {{
                color: rgba(255, 255, 255, 0.66);
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
                line-height: 18px;
            }}

            #SftpSideHint {{
                color: rgba(255, 255, 255, 0.82);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                padding: 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #SftpShellTitle {{
                color: #3A3D3D;
                font-size: {17 if not self.compact_mode else 15}px;
                font-weight: 900;
            }}

            #SftpCloseButton {{
                background: transparent;
                color: #444748;
                border: none;
                font-size: {22 if not self.compact_mode else 19}px;
                font-weight: 400;
            }}

            #SftpCloseButton:hover {{
                color: #000000;
            }}

            #SftpFormTitle {{
                color: #2F3131;
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 600;
            }}

            #SftpFormSubtitle {{
                color: #747878;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #SftpFieldLabel {{
                color: #444748;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
            }}

            #SftpInputBox {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
            }}

            #SftpInputBox:hover {{
                border: 1px solid #747878;
            }}

            #SftpBoxInput {{
                background: transparent;
                color: #2F3131;
                border: none;
                padding: 0px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}

            #SftpFieldIconButton {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                border-radius: 8px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
                letter-spacing: 0.6px;
            }}

            #SftpFieldIconButton:hover {{
                background: #EEEEEE;
                color: #000000;
            }}

            #SftpPendingCard {{
                background: #F3F3F3;
                border: 1px solid #C4C7C7;
                border-radius: 12px;
            }}

             #SftpFolderIcon {{
                background: #111827;
                color: #FFFFFF;
                border-radius: 9px;
                padding: 0px;
                font-size: {16 if not self.compact_mode else 14}px;
                font-weight: 700;
            }}

            #SftpPendingLabel {{
                color: #1F2933;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #SftpPendingPath {{
                color: #5E5E5E;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 500;
                line-height: 13px;
            }}

            #SftpFixedSuffix {{
                color: #747878;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 700;
            }}

            #SftpStatus {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #SftpStatusSuccess {{
                color: #047857;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
            }}

            #SftpStatusError {{
                color: #BA1A1A;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
            }}

            #SftpCancelButton {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}

            #SftpCancelButton:hover {{
                color: #000000;
            }}

            #SftpTransferButton {{
                background: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 18px;
                padding: 10px 22px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
                letter-spacing: 1px;
            }}

            #SftpTransferButton:hover {{
                background: #2F3131;
            }}

            #SftpTransferButton:disabled {{
                background: #C7C6C6;
                color: #747878;
            }}



            /* Multi-Pi SFTP popup — target selector and live progress */
            #MultiSftpDialog {{
                background: transparent;
            }}

            #MultiSftpCard {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: 14px;
            }}

            #MultiSftpTitle {{
                color: #000000;
                font-size: {22 if not self.compact_mode else 19}px;
                font-weight: 700;
            }}

            #MultiSftpCountBadge {{
                color: #5E5E5E;
                background: #EEEEEE;
                border-radius: 10px;
                padding: 3px 8px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #MultiSftpCloseButton {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                border-radius: 12px;
                font-size: {21 if not self.compact_mode else 18}px;
                font-weight: 500;
                min-width: 28px;
                min-height: 28px;
            }}

            #MultiSftpCloseButton:hover {{
                background: #EEEEEE;
                color: #000000;
            }}

            #MultiSftpMinimizeButton {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                border-radius: 12px;
                font-size: {21 if not self.compact_mode else 18}px;
                font-weight: 700;
                min-width: 28px;
                min-height: 28px;
            }}

            #MultiSftpMinimizeButton:hover {{
                background: #EEEEEE;
                color: #000000;
            }}

            #MultiSftpMinimizeButton:disabled {{
                color: #C4C7C7;
                background: transparent;
            }}

            #MultiSftpHint {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 500;
            }}

            #MultiSftpSearch {{
                background: #F3F3F3;
                color: #1A1C1C;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #MultiSftpSearch:focus {{
                background: #FFFFFF;
                border: 1px solid #000000;
            }}

            #MultiSftpSelectAllWrap {{
                background: transparent;
            }}

            #MultiSftpSelectAll {{
                background: #FFFFFF;
                color: transparent;
                border: 1px solid #747878;
                border-radius: 5px;
                font-size: {16 if not self.compact_mode else 14}px;
                font-weight: 900;
                padding: 0px;
            }}

            #MultiSftpSelectAll:hover {{
                background: #F3F3F3;
                border-color: #000000;
            }}

            #MultiSftpSelectAll:checked {{
                background: #111111;
                color: #FFFFFF;
                border-color: #111111;
            }}

            #MultiSftpSelectAll:checked:hover {{
                background: #333333;
                border-color: #333333;
            }}

            #MultiSftpSelectAllText {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
                text-align: left;
                padding: 0px;
            }}

            #MultiSftpSelectAllText:hover {{
                color: #000000;
            }}

            #MultiSftpTargetScroll {{
                background: transparent;
                border: none;
            }}

            #MultiSftpTargetScroll QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 3px 0px;
            }}

            #MultiSftpTargetScroll QScrollBar::handle:vertical {{
                background: rgba(17, 24, 39, 0.25);
                border-radius: 3px;
                min-height: 30px;
            }}

            #MultiSftpTargetScroll QScrollBar::add-line:vertical,
            #MultiSftpTargetScroll QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            #MultiSftpTargetList {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
            }}

            #MultiSftpTargetRow {{
                background: #FFFFFF;
                border: none;
                border-bottom: 1px solid #E2E2E2;
            }}

            #MultiSftpTargetRow:hover {{
                background: #F9F9F9;
            }}

            #MultiSftpTargetCheck {{
                background: #FFFFFF;
                color: transparent;
                border: 1px solid #747878;
                border-radius: 5px;
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 900;
                padding: 0px;
            }}

            #MultiSftpTargetCheck:hover {{
                background: #F3F3F3;
                border-color: #000000;
            }}

            #MultiSftpTargetCheck:checked {{
                background: #111111;
                color: #FFFFFF;
                border-color: #111111;
            }}

            #MultiSftpTargetCheck:checked:hover {{
                background: #333333;
                border-color: #333333;
            }}

            #MultiSftpTargetIcon {{
                background: #EEEEEE;
                color: #5E5E5E;
                border-radius: 8px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
            }}

            #MultiSftpTargetName {{
                color: #1A1C1C;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #MultiSftpDeleteButton {{
                background: transparent;
                color: #747878;
                border: none;
                border-radius: 8px;
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 700;
                min-width: 28px;
                min-height: 28px;
            }}

            #MultiSftpDeleteButton:hover {{
                background: #FFEBE8;
                color: #BA1A1A;
            }}

            #MultiSftpAddInput {{
                background: #FFFFFF;
                color: #1A1C1C;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
                padding: 8px 10px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #MultiSftpAddInput:focus {{
                border: 1px solid #000000;
            }}

            #MultiSftpAddButton {{
                background: #111111;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #MultiSftpAddButton:hover {{
                background: #2F3131;
            }}

            #MultiSftpFooter {{
                background: #FFFFFF;
                border-top: 1px solid #E2E2E2;
            }}

            #MultiSftpFooterCancel {{
                background: #FFFFFF;
                color: #1A1C1C;
                border: 1px solid #747878;
                border-radius: 8px;
                padding: 9px 18px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #MultiSftpFooterCancel:hover {{
                background: #F3F3F3;
                border-color: #000000;
            }}

            #MultiSftpFooterCancel:disabled {{
                color: #9A9A9A;
                border-color: #C4C7C7;
            }}

            #MultiSftpPrimaryButton {{
                background: #111111;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 9px 18px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #MultiSftpPrimaryButton:hover {{
                background: #2F3131;
            }}

            #MultiSftpAbortButton {{
                background: #BA1A1A;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 9px 18px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #MultiSftpAbortButton:hover {{
                background: #93000A;
            }}

            #MultiSftpStatus {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
            }}

            #MultiSftpStatusError {{
                color: #BA1A1A;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #MultiSftpOverallProgress {{
                background: #EEEEEE;
                border: none;
                border-radius: 4px;
                height: 7px;
            }}

            #MultiSftpOverallProgress::chunk {{
                background: #111111;
                border-radius: 4px;
            }}

            #MultiSftpProgressRow {{
                background: #FFFFFF;
                border: none;
                border-bottom: 1px solid #E2E2E2;
            }}

            #MultiSftpProgressHost {{
                color: #1A1C1C;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #MultiSftpStatusSuccess {{
                color: #1F7A45;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #MultiSftpStatusActive {{
                color: #111111;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #MultiSftpStatusQueued {{
                color: #747878;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
            }}

            #MultiSftpRowProgress {{
                background: #EEEEEE;
                border: none;
                border-radius: 3px;
                height: 4px;
            }}

            #MultiSftpRowProgress::chunk {{
                background: #111111;
                border-radius: 3px;
            }}

            #TransferDialog {{
                background: transparent;
            }}

            #TransferCard {{
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 22px;
            }}

            #TransferTopLine {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.5 rgba(0,0,0,0.14), stop:1 transparent);
            }}

            #TransferHeaderIcon {{
                background: #FFFFFF;
                color: #000000;
                border: 1px solid #C4C7C7;
                border-radius: {28 if not self.compact_mode else 24}px;
                font-size: {20 if not self.compact_mode else 18}px;
                font-weight: 900;
            }}

            #TransferTitle {{
                color: #1A1C1C;
                font-size: {19 if not self.compact_mode else 16}px;
                font-weight: 400;
                letter-spacing: 2.5px;
                text-transform: uppercase;
            }}

            #TransferSubtitle {{
                color: #444748;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.6px;
                text-transform: uppercase;
            }}

            #TransferHint {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}


            #ReceivedSourceCard {{
                background: #F6F3F5;
                border: 1px solid #F1F5F9;
                border-radius: 14px;
            }}

            #ReceivedSourceIcon {{
                background: rgba(208, 225, 251, 0.28);
                color: #505F76;
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #ReceivedZipList {{
                background: transparent;
                color: #1A1C1C;
                border: none;
                border-radius: 10px;
                padding: 4px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
                outline: none;
            }}

            #ReceivedZipList::item {{
                padding: 8px 12px;
                margin: 2px 0px;
                border-radius: 8px;
                border: none;
                background: rgba(255, 255, 255, 0.52);
                color: #111827;
            }}

            #ReceivedZipList::item:hover {{
                background: rgba(219, 234, 254, 0.42);
            }}

            #ReceivedZipList::item:selected {{
                background: #DBEAFE;
                color: #000000;
                border: none;
            }}

            #ReceivedZipList QScrollBar:vertical {{
                width: 4px;
                background: transparent;
                margin: 2px 0 2px 0;
            }}

            #ReceivedZipList QScrollBar::handle:vertical {{
                background: rgba(17, 24, 39, 0.24);
                border-radius: 2px;
                min-height: 26px;
            }}

            #ReceivedZipList QScrollBar::add-line:vertical,
            #ReceivedZipList QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
            }}

            #ReceivedZipList QScrollBar::add-page:vertical,
            #ReceivedZipList QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            #TransferFieldLabel {{
                color: #444748;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.8px;
                text-transform: uppercase;
            }}

            #TransferTabButton {{
                background: #FFFFFF;
                color: #444748;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
                padding: 7px 12px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.4px;
                text-transform: uppercase;
            }}

            #TransferTabButton:hover {{
                background: #F3F3F3;
                color: #000000;
            }}

            #TransferTabButton[selected="true"] {{
                background: #000000;
                color: #FFFFFF;
                border: 1px solid #000000;
            }}

            #TransferInputBox {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
            }}

            #TransferInputBox:hover {{
                border: 1px solid #747878;
            }}

            #TransferInput {{
                background: transparent;
                color: #1A1C1C;
                border: none;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                padding-left: 0px;
            }}

            #TransferIconButton {{
                background: transparent;
                color: #747878;
                border: none;
                border-radius: 8px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #TransferIconButton:hover {{
                background: #E8E8E8;
                color: #000000;
            }}

            #TransferInfo {{
                background: #F3F3F3;
                color: #444748;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #TransferStatus {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
            }}

            #TransferStatusSuccess {{
                color: #047857;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #TransferStatusError {{
                color: #BA1A1A;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #TransferCancelButton {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}

            #TransferCancelButton:hover {{
                color: #000000;
            }}


            #TransferSecondaryActionButton {{
                background: #FFFFFF;
                color: #000000;
                border: 1px solid #C4C7C7;
                border-radius: 12px;
                padding: 12px 24px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.8px;
                text-transform: uppercase;
            }}

            #TransferSecondaryActionButton:hover {{
                background: #BA1A1A;
                color: #FFFFFF;
                border: 1px solid #BA1A1A;
            }}

            #TransferPrimaryButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.8px;
                text-transform: uppercase;
            }}

            #TransferPrimaryButton:hover {{
                background: #2F3131;
            }}

            #TransferPrimaryButton:disabled {{
                background: #C7C6C6;
                color: #747878;
            }}

            #TransferSearchIcon {{
                color: #747878;
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 900;
            }}

            #TransferZipList {{
                background: #F3F3F3;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
            }}

            #TransferZipRow {{
                background: transparent;
                border-bottom: 1px solid rgba(196,199,199,0.55);
                border-radius: 6px;
            }}

            #TransferZipRow:hover {{
                background: rgba(16, 185, 129, 0.08);
            }}

            #TransferZipRow[selected="true"] {{
                background: #D1FAE5;
                border: 1px solid #10B981;
            }}

            #TransferZipIcon {{
                color: #747878;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #TransferZipName {{
                color: #1A1C1C;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #TransferZipRow[selected="true"] #TransferZipName {{
                color: #065F46;
                font-weight: 900;
            }}

            #TransferReadyBadge {{
                background: #ECFDF5;
                color: #047857;
                border: 1px solid #A7F3D0;
                border-radius: 6px;
                padding: 3px 7px;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
            }}


            #PiConnectionDialog {{
                background: transparent;
            }}

            #PiConnectionCard {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.78);
                border-radius: 32px;
            }}

            #PiConnectionVisualLoading {{
                background: #111111;
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
            }}

            #PiConnectionVisualSuccess {{
                background: #008F53;
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
            }}

            #PiConnectionVisualFailed {{
                background: #BA1A1A;
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
            }}

            #PiConnectionLargeIcon {{
                color: #FFFFFF;
                font-size: {72 if not self.compact_mode else 58}px;
                font-weight: 400;
            }}

            #PiConnectionVisualCaption {{
                color: #FFFFFF;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 3px;
            }}

            #PiConnectionContent {{
                background: #F9F9F9;
                border-top-right-radius: 32px;
                border-bottom-right-radius: 32px;
            }}

            #PiConnectionTitle {{
                color: #000000;
                font-size: {30 if not self.compact_mode else 24}px;
                font-weight: 800;
                letter-spacing: 1.4px;
            }}

            #PiConnectionSubtitle {{
                color: #5E5E5E;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}

            #PiConnectionInfoBlock {{
                border-left: 2px solid rgba(0, 0, 0, 0.10);
                background: transparent;
            }}

            #PiConnectionInfoLabel {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.8px;
            }}

            #PiConnectionInfoValue {{
                color: #000000;
                font-size: {16 if not self.compact_mode else 13}px;
                font-weight: 800;
            }}

            #PiConnectionFooter {{
                color: #5E5E5E;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 800;
                letter-spacing: 1.6px;
            }}

            #PiConnectionActionButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.6px;
                text-transform: uppercase;
            }}

            #PiConnectionActionButton:hover {{
                background: #2F3131;
            }}


            #AuthorizedUsersDialog {{
                background: transparent;
            }}

            #AuthorizedUsersCard {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.82);
                border-radius: 24px;
            }}

            #AuthorizedUsersEyebrow {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 2.2px;
            }}

            #AuthorizedUsersTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 24}px;
                font-weight: 500;
                letter-spacing: 1px;
            }}

            #AuthorizedUsersCount {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.8px;
            }}

            #AuthorizedRoundCloseButton {{
                background: #F1F1F1;
                color: #5E5E5E;
                border: 1px solid #C4C7C7;
                border-radius: {22 if not self.compact_mode else 19}px;
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 700;
            }}

            #AuthorizedRoundCloseButton:hover {{
                background: #000000;
                color: #FFFFFF;
                border: 1px solid #000000;
            }}

            #AuthorizedSearchBox {{
                background: rgba(0, 0, 0, 0.05);
                border: 1px solid transparent;
                border-radius: 12px;
            }}

            #AuthorizedSearchBox:hover {{
                background: rgba(0, 0, 0, 0.065);
                border: 1px solid #C4C7C7;
            }}

            #AuthorizedSearchIcon {{
                color: {Theme.SECONDARY};
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 800;
            }}

            #AuthorizedSearchInput {{
                background: transparent;
                color: {Theme.TEXT};
                border: none;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 400;
                padding-left: 4px;
            }}

            #AuthorizedPopupRow {{
                background: transparent;
                border-bottom: 1px solid rgba(0, 0, 0, 0.045);
                border-radius: 10px;
            }}

            #AuthorizedPopupRow:hover {{
                background: rgba(16, 185, 129, 0.04);
            }}

            #AuthorizedUserAvatar {{
                background: #F3F4F6;
                color: #2F3131;
                border: 1px solid rgba(196, 199, 199, 0.75);
                border-radius: {19 if not self.compact_mode else 17}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #AuthorizedPopupName {{
                background: transparent;
                color: {Theme.PRIMARY};
                font-size: {16 if not self.compact_mode else 14}px;
                font-weight: 600;
            }}

            #AuthorizedPopupDetail {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #AuthorizedPopupTrainedBadge {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 9px;
                padding: 5px 8px;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 800;
                letter-spacing: 1px;
            }}

            #AuthorizedPopupTrainedBadge:hover {{
                background: #2F3131;
            }}

            #AuthorizedPopupPendingBadge {{
                background: #E8E8E8;
                color: #464747;
                border: 1px solid #C4C7C7;
                border-radius: 7px;
                padding: 5px 8px;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 1px;
            }}

            #AuthorizedPopupEmpty {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                padding: 18px 6px;
            }}

            #AuthorizedCloseButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #AuthorizedCloseButton:hover {{
                background: #2F3131;
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





            #CaptureCompleteDialog {{
                background: transparent;
            }}

            #CaptureCompleteCard {{
                background: #FFFFFF;
                border: 1px solid {Theme.BORDER};
                border-radius: 22px;
            }}

            #CaptureIconWrap {{
                background: #ECFDF5;
                border: 1px solid #D1FAE5;
                border-radius: {39 if not self.compact_mode else 33}px;
            }}

            #CaptureIconCheck {{
                color: #10B981;
                font-size: {42 if not self.compact_mode else 34}px;
                font-weight: 900;
            }}

            #CaptureTitle {{
                color: {Theme.PRIMARY};
                font-size: {26 if not self.compact_mode else 22}px;
                font-weight: 900;
                letter-spacing: -0.7px;
            }}

            #CaptureDesc {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
                line-height: 1.5;
            }}

            #CaptureReturnButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 12px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #CaptureReturnButton:hover {{
                background: #2F3131;
            }}

            #CaptureFooter {{
                background: rgba(232, 232, 232, 0.45);
                border-top: 1px solid rgba(196, 199, 199, 0.5);
                border-radius: 10px;
            }}

            #CaptureFooterIcon {{
                color: #5E5E5E;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #CaptureFooterText {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}


            #DeleteCompleteDialog {{
                background: transparent;
            }}

            #DeleteCompleteCard {{
                background: #FFFFFF;
                border: 1px solid {Theme.BORDER};
                border-radius: 22px;
            }}

            #DeleteIconWrap {{
                background: #ECFDF5;
                border: 1px solid #D1FAE5;
                border-radius: {41 if not self.compact_mode else 35}px;
            }}

            #DeleteIconCheck {{
                color: #059669;
                font-size: {44 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #DeleteTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 24}px;
                font-weight: 900;
                letter-spacing: -0.8px;
            }}

            #DeleteDesc {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
                line-height: 1.5;
            }}

            #DeleteTrace {{
                color: {Theme.MUTED};
                background: {Theme.SURFACE_LOW};
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
                padding: 8px 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1px;
            }}

            #DeleteReturnButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #DeleteReturnButton:hover {{
                background: #2F3131;
            }}


            #TrainingProgressDialog {{
                background: transparent;
            }}

            #TrainingSolidModal {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 32px;
            }}

            #TrainingSuccessModal {{
                background: #FFFFFF;
                border: 1px solid rgba(22, 163, 74, 0.35);
                border-radius: 32px;
            }}

            #TrainingFailedModal {{
                background: #FFFFFF;
                border: 1px solid rgba(220, 38, 38, 0.35);
                border-radius: 32px;
            }}

            #TrainingTitle {{
                color: {Theme.PRIMARY};
                font-size: {21 if not self.compact_mode else 18}px;
                font-weight: 900;
                letter-spacing: -0.4px;
            }}

            #TrainingStatus {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }}

            #TrainingDetail {{
                color: #1F7A45;
                background: #ECFDF5;
                border: 1px solid rgba(31, 122, 69, 0.18);
                border-radius: 14px;
                padding: 6px 10px;
                font-size: {11 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #TrainingInnerIcon {{
                color: rgba(0, 0, 0, 0.78);
                font-size: {34 if not self.compact_mode else 28}px;
                font-weight: 300;
            }}

            #TrainingProgressText {{
                color: {Theme.PRIMARY};
                font-size: {24 if not self.compact_mode else 20}px;
                font-weight: 900;
            }}

            #TrainingSuccessIcon {{
                color: #16A34A;
                font-size: {32 if not self.compact_mode else 28}px;
                font-weight: 900;
            }}

            #TrainingFailedIcon {{
                color: #DC2626;
                font-size: {36 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #TrainingResultText {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #TrainingTokenCard {{
                background: rgba(255, 255, 255, 0.55);
                border: 1px solid rgba(196, 199, 199, 0.55);
                border-radius: 18px;
            }}

            #TrainingTokenLabel {{
                color: {Theme.MUTED};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.5px;
            }}

            #TrainingTokenValue {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #TrainingDoneButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 14px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #TrainingDoneButton:hover {{
                background: #2F3131;
            }}

            QPushButton:disabled {{
                background: #E5E7EB;
                color: #9CA3AF;
                border-color: #D1D5DB;
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
                font-weight: 400;
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
                font-weight: 400;
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

            #ReceivedBadge {{
                background: #DC2626;
                color: #FFFFFF;
                border: 2px solid #FFFFFF;
                border-radius: 11px;
                font-size: 10px;
                font-weight: 900;
                min-width: 22px;
                min-height: 22px;
                max-width: 22px;
                max-height: 22px;
            }}

            #ReceivedBadge[pill="true"] {{
                border-radius: 11px;
                min-width: 30px;
                max-width: 30px;
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


            #SettingsConnected {{
                color: #16A34A;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsDisconnected {{
                color: {Theme.RED};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #AdminListScroll {{
                background: transparent;
                border: none;
            }}

            #AdminListScroll QWidget {{
                background: transparent;
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




            #CameraPreviewStoppedLabel {{
                background: #020617;
                color: #CBD5E1;
                border-radius: 16px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }}

            #CameraStateStopBadge {{
                background: #DC2626;
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.8px;
                padding: 0 10px;
            }}


            #CameraStateLiveBadge {{
                background: #3F9468;
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.8px;
                padding: 0 10px;
            }}

            #CameraStateEndBadge {{
                background: #20242C;
                color: #B8BEC7;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.8px;
                padding: 0 10px;
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


            #NtidInputError {{
                background: #FFF5F5;
                color: {Theme.TEXT};
                border: 2px solid #DC2626;
                border-radius: 12px;
                padding-left: 14px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #NtidInputError::placeholder {{
                color: #DC2626;
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

            /* Make disabled recognition visibly grey during Capture. */
            #GreenActionButton:disabled {{
                background: #D1D5DB;
                color: #6B7280;
                border: 1px solid #B8C0CC;
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

            #FaceSystemLogScroll {{
                background: transparent;
                border: none;
            }}

            #FaceSystemLogBody {{
                background: transparent;
            }}

            #LogText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {11 if not self.compact_mode else 10}px;
                line-height: 1.8;
            }}

            #FaceUsersScroll {{
                background: transparent;
                border: none;
            }}

            #FaceUsersBody {{
                background: transparent;
            }}

            #FaceUserSearchBox {{
                background: rgba(255, 255, 255, 0.62);
                border: 1px solid rgba(196, 199, 199, 0.75);
                border-radius: 14px;
            }}

            #FaceUserSearchBox:hover {{
                background: rgba(255, 255, 255, 0.86);
                border: 1px solid rgba(0, 0, 0, 0.18);
            }}

            #FaceUserSearchIcon {{
                color: {Theme.SECONDARY};
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 700;
            }}

            #FaceUserSearchInput {{
                background: transparent;
                color: {Theme.TEXT};
                border: none;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 400;
            }}

            #FaceUserExpandCard {{
                background: rgba(255, 255, 255, 0.18);
                border: 1px solid transparent;
                border-radius: 16px;
            }}

            #FaceUserExpandCard:hover {{
                background: rgba(243, 243, 243, 0.92);
                border: 1px solid transparent;
            }}

            #FaceUserExpandCard[expanded="true"] {{
                background: rgba(243, 243, 243, 0.96);
                border: 1px solid transparent;
            }}

            #FaceUserCardLabel {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 700;
                letter-spacing: 1.1px;
            }}

            #FaceUserCardNtid {{
                background: transparent;
                color: {Theme.PRIMARY};
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 800;
            }}

            #FaceUserFramesIcon {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #FaceUserCardDetail {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 500;
            }}

            #FaceUserCardTrainedBadge {{
                background: rgba(16, 185, 129, 0.12);
                color: #047857;
                border: 1px solid rgba(16, 185, 129, 0.12);
                border-radius: 14px;
                padding: 5px 8px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #FaceUserCardPendingBadge {{
                background: rgba(245, 158, 11, 0.14);
                color: #92400E;
                border: 1px solid rgba(245, 158, 11, 0.12);
                border-radius: 14px;
                padding: 5px 8px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #FaceUserCardActions {{
                background: transparent;
                border: none;
            }}

            #FaceUserCardCaptureButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.4px;
                padding: 0px 8px;
            }}

            #FaceUserCardCaptureButton:hover {{
                background: #2F3131;
            }}

            #FaceUserCardDeleteButton {{
                background: rgba(255, 255, 255, 0.78);
                color: #1F2933;
                border: 1px solid rgba(116, 120, 120, 0.72);
                border-radius: 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.2px;
                padding: 0px 8px;
            }}

            #FaceUserCardDeleteButton:hover {{
                background: rgba(186, 26, 26, 0.08);
                color: #BA1A1A;
                border: 1px solid rgba(186, 26, 26, 0.42);
            }}

            #FaceUserEmptyMessage {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 500;
                padding: 10px;
            }}


            #FaceUserRowWrapper {{
                background: transparent;
                border: none;
            }}

            #FaceUserRowWrapper[menuOpen="true"] #FaceUserRow {{
                background: #FFFFFF;
                border: 1px solid rgba(16, 185, 129, 0.22);
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

            #FaceUserMenuChevron {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
                background: transparent;
            }}

            #FaceUserQuickMenu {{
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(196, 199, 199, 0.75);
                border-radius: 16px;
                margin-left: 6px;
                margin-right: 6px;
            }}

            #FaceUserMenuTitle {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.4px;
            }}

            #FaceUserMenuNtid {{
                color: {Theme.PRIMARY};
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #FaceUserCaptureButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 0px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #FaceUserCaptureButton:hover {{
                background: #2F3131;
            }}

            #FaceUserDeleteButton {{
                background: rgba(255, 255, 255, 0.72);
                color: #BA1A1A;
                border: 1px solid rgba(186, 26, 26, 0.32);
                border-radius: 10px;
                padding: 0px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #FaceUserDeleteButton:hover {{
                background: rgba(186, 26, 26, 0.08);
                border: 1px solid rgba(186, 26, 26, 0.55);
            }}
        """)
