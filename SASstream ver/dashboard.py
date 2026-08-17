import ctypes
import html
import platform
import time
from datetime import datetime
from threading import Lock

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow

from app_config import *
from views.face_data_transfer_view import FaceDataTransferMixin
from views.face_recognition_view import FaceRecognitionViewMixin
from views.settings_view import SettingsViewMixin
from views.dashboard_view import DashboardViewMixin
from views.shell_layout_view import ShellLayoutMixin
from controllers.camera_connection_controller import CameraConnectionControllerMixin
from controllers.audit_log_controller import AuditLogControllerMixin
from controllers.settings_controller import SettingsControllerMixin
from controllers.auth_controller import AuthControllerMixin
from controllers.lock_runtime_controller import LockRuntimeControllerMixin

from services.admin_service import AdminService
from services.credential_service import CredentialService
from services.ad_service import ActiveDirectoryService
from services.local_face_service import LocalFaceService
from services.local_unlock_service import LocalUnlockService
from services.runtime_lock_service import RuntimeLockService


class SecureAccessDashboard(ShellLayoutMixin, LockRuntimeControllerMixin, AuthControllerMixin, SettingsControllerMixin, AuditLogControllerMixin, CameraConnectionControllerMixin, DashboardViewMixin, SettingsViewMixin, FaceRecognitionViewMixin, FaceDataTransferMixin, QMainWindow):
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
        self._sas_server_log_last_warn_at = 0.0
        self._sas_server_log_last_error = ""
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
        # Do not hard-code a camera IP for EXE distribution.
        # New users must configure hostname/IP in Settings before SAS can connect.
        self.pi_api_host = ""
        self.pi_api_port = "5000"
        self.pi_api_base = ""
        self.pi_connected = False
        self._camera_connected_once_this_run = False
        # The camera owns the persisted camera orientation. SAS pulls it from
        # /settings and can update it without remounting the SMB server path.
        self.camera_rotation = 0
        self._camera_rotation_sync_in_progress = False
        self._camera_rotation_poll_in_progress = False
        self._pi_disconnect_popup_visible = False
        self._pi_disconnect_popup_last_shown_at = 0.0
        self._startup_disconnect_popup_shown = False
        self._startup_disconnect_warning_suppressed_until = time.monotonic() + 30.0
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
        self.sas_client_name = self.get_sas_client_display_name()
        self.sas_oneconnect_session = None
        self.sas_oneconnect_force_takeover_active = False
        # v110: monotonically increasing token used to ignore stale camera connect
        # workers. This prevents an older retry/result from reconnecting the
        # previous camera after the user typed a new hostname and pressed Connect.
        self._pi_connect_request_token = 0
        # Settings host typing guard: users must be able to type a hostname/IP
        # without the background retry loop trying to connect to half-typed text.
        self._pi_host_dirty_since_edit = False
        self._pi_host_user_editing = False
        # v111: the hostname shown in Settings is the selected/runtime host.
        # A failed manual Connect or Save Connect must not fall back to the
        # previously connected camera.  This flag records when the selected host
        # was changed while disconnected.
        self._pi_selected_host_pending_manual_connect = False
        # v112: Settings unsaved-change guard. Leaving Settings or closing SAS
        # prompts the user when current Settings UI values differ from
        # credential.txt, so typed changes are not lost accidentally.
        self._settings_save_prompt_active = False
        self._settings_bypass_unsaved_prompt_once = False
        self._settings_close_after_save = False
        # v113: Unsaved Settings prompt must only appear after real user edits.
        # Programmatic Settings refreshes from credential.txt/camera must not make the
        # next tab switch look dirty.
        self._settings_unsaved_baseline = None
        self._settings_dirty_since_baseline = False
        self._settings_programmatic_update = False
        # v119: Startup camera monitoring may run before login, but camera disconnect
        # warning cards must not block/overlay the login popup. Store the
        # disconnect reason and show/check again after login closes.
        self._login_popup_active = False
        self._pi_disconnect_deferred_during_login = False
        self._pi_disconnect_deferred_reason = ""
        self._pi_disconnect_deferred_origin = ""
        self.sas_check_received_btn = None
        self.camera_feed_url = ""
        self.camera_capture = None
        self.camera_timer = None
        self._camera_preview_running = False
        self._camera_preview_generation = 0
        self._handling_pi_disconnect = False
        self.camera_frame_count = 0
        self.camera_last_tick = None
        self.camera_fps = 0
        self._camera_user_stopped = False
        self._camera_manual_disconnected = False
        self._runtime_disconnect_candidate_since = 0.0
        self._camera_disconnect_grace_until = 0.0
        self._modal_open_count = 0
        # In-app card dialogs can overlap (example: import/export popup +
        # Pending Received popup).  Keep one shared blur/dim layer alive until
        # the last card closes, otherwise the dashboard can stay dimmed or be
        # cleared while another card is still open.
        self._card_dialog_open_count = 0
        self._card_dialog_dim_overlays = []
        self._missing_credentials_popup_shown = False
        self._camera_resume_after_modal = False
        # True from the moment SAS starts a capture request until the camera reports
        # that capture has fully stopped.  This prevents a second camera mode
        # (Recognition) from being requested while camera backend is still in use.
        self.face_capture_in_progress = False

        # v188 background mode:
        # When SAS starts with completed configuration and camera is online, keep the
        # dashboard running minimized in the Windows taskbar. Bring it back when
        # locked, camera disconnects, or first-launch setup is required.
        self._startup_background_check_done = False
        self._startup_background_check_pending = False
        self._startup_minimize_done = False
        self._auto_minimize_enabled = True
        self._minimized_by_sas = False
        self._wts_session_registered = False
        self._last_session_recovery_log_at = 0.0

        # Backend services migrated from lockapp.py.
        # Keep business logic here, not inside the UI methods.
        self.admin_service = AdminService(ADMIN_FILE)
        self.credential_service = CredentialService(CRED_FILE)
        self.credential_service.migrate_plaintext_password_if_needed()
        self.ad_service = ActiveDirectoryService(SOAP_URL, debug_callback=self.login_debug)
        self.local_face_service = LocalFaceService(self.pi_api_host, self.pi_api_port, debug_callback=self.append_system_log)
        self.local_unlock_service = LocalUnlockService(debug_callback=self.append_system_log, parent=self)
        self.local_unlock_service.message_received.connect(self.handle_local_unlock_message)
        self.local_unlock_service.connected.connect(self.handle_local_unlock_connected)
        self.local_unlock_service.disconnected.connect(self.handle_local_unlock_disconnected)
        self.sas_oneconnect_heartbeat_timer = QTimer(self)
        self.sas_oneconnect_heartbeat_timer.timeout.connect(self.send_sas_oneconnect_heartbeat)
        self.sas_oneconnect_heartbeat_timer.start(5000)
        self.runtime_lock_service = RuntimeLockService()

        self.lock_timeout_seconds = DEFAULT_LOCK_TIMEOUT_SECONDS
        self.disable_keyboard_when_locked = False
        self.disable_mouse_when_locked = False
        self.disable_usb_when_locked = False
        self.enable_hotkey = True

        # Inactivity lock state:
        # The auto-lock countdown follows Windows screen-saver behaviour.
        # It is driven by keyboard/mouse inactivity, not by camera/face state.
        # Face unlock is delivered by local unlock events while the system is locked.
        # SMB recognition_result.json polling has been removed from SAS.
        self.unlock_session_id = ""
        self._unlock_seen_events = set()
        self._last_unlock_result_state = None
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
        QTimer.singleShot(0, self.register_windows_session_notifications)

        self.start_timers()
        QTimer.singleShot(550, self.show_missing_credentials_setup_popup_if_needed)
        QTimer.singleShot(1200, self.startup_background_mode_check)


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


    # --------------------------------------------------------
    # Window chrome / app icon
    # --------------------------------------------------------


    def register_windows_session_notifications(self):
        """Receive Windows lock/unlock messages so hooks recover immediately."""
        if platform.system() != "Windows" or getattr(self, "_wts_session_registered", False):
            return
        try:
            hwnd = int(self.winId())
            wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
            wtsapi32.WTSRegisterSessionNotification.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            wtsapi32.WTSRegisterSessionNotification.restype = ctypes.c_int
            if wtsapi32.WTSRegisterSessionNotification(ctypes.c_void_p(hwnd), 0):
                self._wts_session_registered = True
        except Exception as exc:
            self.append_system_log(f"Windows session notification unavailable: {exc}")

    def unregister_windows_session_notifications(self):
        if platform.system() != "Windows" or not getattr(self, "_wts_session_registered", False):
            return
        try:
            hwnd = int(self.winId())
            wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
            wtsapi32.WTSUnRegisterSessionNotification.argtypes = [ctypes.c_void_p]
            wtsapi32.WTSUnRegisterSessionNotification.restype = ctypes.c_int
            wtsapi32.WTSUnRegisterSessionNotification(ctypes.c_void_p(hwnd))
        except Exception:
            pass
        self._wts_session_registered = False

    def nativeEvent(self, eventType, message):
        try:
            if platform.system() == "Windows":
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", ctypes.c_void_p),
                        ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_size_t),
                        ("lParam", ctypes.c_ssize_t),
                        ("time", ctypes.c_ulong),
                        ("pt", POINT),
                    ]

                msg = MSG.from_address(int(message))
                WM_WTSSESSION_CHANGE = 0x02B1
                WTS_SESSION_LOCK = 0x7
                WTS_SESSION_UNLOCK = 0x8
                WTS_SESSION_LOGON = 0x5
                if int(msg.message) == WM_WTSSESSION_CHANGE:
                    event_code = int(msg.wParam)
                    if event_code == WTS_SESSION_LOCK:
                        self.refresh_emergency_recovery_state()
                    elif event_code in (WTS_SESSION_UNLOCK, WTS_SESSION_LOGON):
                        QTimer.singleShot(120, lambda: self.recover_after_windows_secure_desktop("windows_session_unlock", True))
                        QTimer.singleShot(800, lambda: self.recover_after_windows_secure_desktop("windows_session_unlock_retry"))
                        QTimer.singleShot(2000, lambda: self.recover_after_windows_secure_desktop("windows_session_unlock_final"))
        except Exception:
            pass
        return super().nativeEvent(eventType, message)


    # --------------------------------------------------------
    # Build UI
    # --------------------------------------------------------


    # --------------------------------------------------------
    # System locked desktop notification
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Login popup
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Login helpers
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Pages
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Settings page parts
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Dashboard page parts
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Window lifecycle
    # --------------------------------------------------------

    def closeEvent(self, event):
        # v112: closing SAS from Settings must not silently lose unsaved changes.
        if (
            str(getattr(self, "current_top_tab", "") or "") == "Settings"
            and not getattr(self, "_settings_close_after_save", False)
            and self.has_unsaved_settings_changes()
        ):
            choice = self.show_unsaved_settings_dialog()
            if choice == "cancel":
                event.ignore()
                return
            if choice == "save":
                event.ignore()
                self.save_settings_from_ui(
                    after_success=self.close_after_settings_save,
                    show_success_message=False,
                )
                return
            # choice == "dont_save" falls through to normal close.
            self._settings_dirty_since_baseline = False

        self._closing = True
        self._settings_close_after_save = False
        try:
            self.unregister_windows_session_notifications()
        except Exception:
            pass
        try:
            self.hide_system_locked_notification()
        except Exception:
            pass
        try:
            self.runtime_lock_service.shutdown(self)
        except Exception:
            pass
        if hasattr(self, "camera_timer") and self.camera_timer is not None:
            self.camera_timer.stop()

        if hasattr(self, "camera_capture") and self.camera_capture is not None:
            self.camera_capture.release()
            self.camera_capture = None

        try:
            self.local_face_service.stop_recognition()
        except Exception:
            pass

        self.set_camera_state_badge(False)

        super().closeEvent(event)

    def close_after_settings_save(self):
        """Close the window after async Settings save completes successfully."""
        self._settings_close_after_save = True
        self.close()

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
        users refresh, import/export and errors.
        """
        now = datetime.now().strftime("%H:%M:%S")
        line = f"<span style='color:#1F7A45'>{now}</span> &gt; {html.escape(str(message))}"

        if not hasattr(self, "_system_log_lines"):
            self._system_log_lines = [
                "&gt; FACE RECOGNITION SYSTEM LOG READY",
                "&gt; WAITING FOR CAMERA CONNECTION",
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


    # --------------------------------------------------------
    # Fixed footer
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Responsive layout scaling
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Timers
    # --------------------------------------------------------


    # --------------------------------------------------------
    # Style
    # --------------------------------------------------------
