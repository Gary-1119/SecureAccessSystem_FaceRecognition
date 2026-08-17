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
from threading import Thread, Lock
from datetime import datetime
import uuid
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
    QGraphicsDropShadowEffect,
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
from services.websocket_client_service import WebSocketRecognitionClient
from services.runtime_lock_service import RuntimeLockService


from paths import app_resource_path
from views.widgets import ExportCircleSpinnerWidget, SftpEnterKeyFilter
from controllers.auth_controller import AuthControllerMixin
from controllers.pi_connection_controller import PiConnectionControllerMixin
from controllers.face_recognition_controller import FaceRecognitionControllerMixin
from controllers.settings_controller import SettingsControllerMixin
from controllers.transfer_controller import TransferControllerMixin
from controllers.websocket_runtime_controller import WebSocketRuntimeControllerMixin
from controllers.pi_disconnect_controller import PiDisconnectControllerMixin
from controllers.lock_runtime_controller import LockRuntimeControllerMixin
from controllers.audit_log_controller import AuditLogControllerMixin
from views.shell_layout_view import ShellLayoutViewMixin
from views.dashboard_view import DashboardViewMixin
from views.app_style_view import AppStyleViewMixin


class SecureAccessDashboard(
    AuthControllerMixin,
    PiConnectionControllerMixin,
    FaceRecognitionControllerMixin,
    SettingsControllerMixin,
    TransferControllerMixin,
    WebSocketRuntimeControllerMixin,
    PiDisconnectControllerMixin,
    LockRuntimeControllerMixin,
    AuditLogControllerMixin,
    ShellLayoutViewMixin,
    DashboardViewMixin,
    AppStyleViewMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.ui_bridge = UiBridge()
        self._closing = False
        try:
            self.destroyed.connect(lambda *_: setattr(self, "_closing", True))
        except Exception:
            pass
        self.top_nav_buttons = {}
        # Serialise local/server plain-text audit writes from background workers.
        self._sas_log_lock = Lock()
        self._sas_server_log_lock = Lock()
        self._sas_server_log_write_running = False
        self._sas_server_log_skip_until = 0.0
        self._sas_server_log_last_error = ""
        self._sas_server_log_last_warn_at = 0.0
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
        self.sas_client_id = self.load_or_create_sas_client_id()
        self.sas_client_name = self.get_sas_client_display_name()
        self.sas_oneconnect_session = None
        self.sas_oneconnect_force_takeover_active = False
        # v110: monotonically increasing token used to ignore stale Pi connect
        # workers. This prevents an older retry/result from reconnecting the
        # previous Pi after the user typed a new hostname and pressed Connect.
        self._pi_connect_request_token = 0
        # Settings host typing guard: users must be able to type a hostname/IP
        # without the background retry loop trying to connect to half-typed text.
        self._pi_host_dirty_since_edit = False
        self._pi_host_user_editing = False
        # v111: the hostname shown in Settings is the selected/runtime host.
        # A failed manual Connect or Save Connect must not fall back to the
        # previously connected Pi.  This flag records when the selected host
        # was changed while disconnected.
        self._pi_selected_host_pending_manual_connect = False
        # v112: Settings unsaved-change guard. Leaving Settings or closing SAS
        # prompts the user when current Settings UI values differ from
        # credential.txt, so typed changes are not lost accidentally.
        self._settings_save_prompt_active = False
        self._settings_bypass_unsaved_prompt_once = False
        self._settings_close_after_save = False
        # v113: Unsaved Settings prompt must only appear after real user edits.
        # Programmatic Settings refreshes from credential.txt/Pi must not make the
        # next tab switch look dirty.
        self._settings_unsaved_baseline = None
        self._settings_dirty_since_baseline = False
        self._settings_programmatic_update = False
        # v119: Startup Pi monitoring may run before login, but Pi disconnect
        # warning cards must not block/overlay the login popup. Store the
        # disconnect reason and show/check again after login closes.
        self._login_popup_active = False
        self._pi_disconnect_deferred_during_login = False
        self._pi_disconnect_deferred_reason = ""
        self._pi_disconnect_deferred_origin = ""
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
        try:
            self.credential_service.migrate_plaintext_password_if_needed()
        except Exception as exc:
            print(f"[SAS] Credential password migration skipped: {exc}")
        self.ad_service = ActiveDirectoryService(SOAP_URL, debug_callback=self.login_debug)
        self.face_api_service = FaceApiService(self.pi_api_host, self.pi_api_port, debug_callback=self.append_system_log)
        self.websocket_client_service = WebSocketRecognitionClient(debug_callback=self.append_system_log, parent=self)
        self.websocket_client_service.message_received.connect(self.handle_websocket_recognition_message)
        self.websocket_client_service.connected.connect(self.handle_websocket_connected)
        self.websocket_client_service.disconnected.connect(self.handle_websocket_disconnected)
        self.sas_oneconnect_heartbeat_timer = QTimer(self)
        self.sas_oneconnect_heartbeat_timer.timeout.connect(self.send_sas_oneconnect_heartbeat)
        self.sas_oneconnect_heartbeat_timer.start(20000)
        self.runtime_lock_service = RuntimeLockService()

        self.lock_timeout_seconds = DEFAULT_LOCK_TIMEOUT_SECONDS
        self.disable_keyboard_when_locked = False
        self.disable_mouse_when_locked = False
        self.disable_usb_when_locked = False
        self.enable_hotkey = True

        # Inactivity lock state:
        # The auto-lock countdown follows Windows screen-saver behaviour.
        # It is driven by keyboard/mouse inactivity, not by camera/face state.
        # Face unlock is delivered by Pi WebSocket events while the system is locked.
        # SMB recognition_result.json polling has been removed from SAS.
        self.websocket_lock_session_id = ""
        self._websocket_seen_events = set()
        self._last_websocket_result_state = None
        self.face_detected = False
        self._last_user_activity_ts = time.monotonic()
        self._countdown_activity_anchor_ts = self._last_user_activity_ts
        self._last_windows_input_tick = None
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
        QTimer.singleShot(1000, self.cleanup_expired_sas_logs)

        # Apply after the native window handle is ready.
        QTimer.singleShot(0, self.apply_window_chrome)

        self.start_timers()
        QTimer.singleShot(550, self.show_missing_credentials_setup_popup_if_needed)
        QTimer.singleShot(1200, self.startup_background_mode_check)



