from __future__ import annotations

from typing import Any, cast

import html
import os
import socket
import time
from threading import Thread

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QGraphicsDropShadowEffect, QLabel, QMainWindow, QPushButton, QSizePolicy, QVBoxLayout


class CameraConnectionControllerMixin:
    def camera_debug(self: Any, action: str, **fields):
        """Write high-signal camera action/debug events to the terminal."""
        try:
            parts = []
            for key, value in fields.items():
                if value is None:
                    continue
                text = str(value).replace("\n", " ").strip()
                if len(text) > 180:
                    text = text[:177] + "..."
                parts.append(f"{key}={text}")
            suffix = " | " + " | ".join(parts) if parts else ""
            self.append_system_log(f"[CAMERA DEBUG] {action}{suffix}")
        except Exception:
            try:
                print("[CAMERA DEBUG]", action, fields)
            except Exception:
                pass
    def is_login_popup_active(self: Any) -> bool:
        """Return True while the login dialog is open.

        Startup camera checks are still allowed to run, but disconnect warning
        popups are deferred until login finishes so the login UI stays clean.
        """
        try:
            return bool(getattr(self, "_login_popup_active", False))
        except Exception:
            return False

    def defer_pi_disconnect_until_after_login(self: Any, reason: str = "", origin: str = "auto"):
        """Remember a camera disconnect warning that happened during login."""
        self._pi_disconnect_deferred_during_login = True
        self._pi_disconnect_deferred_reason = reason or getattr(self, "_pi_disconnect_reason", "") or "RTSP camera disconnected."
        self._pi_disconnect_deferred_origin = origin or "auto"
        try:
            self.append_system_log(f"CAMERA_DISCONNECT_POPUP_DEFERRED_DURING_LOGIN: {self._pi_disconnect_deferred_reason}")
        except Exception:
            pass

    def consume_deferred_pi_disconnect_reason(self: Any) -> str:
        """Return and clear any camera disconnect warning deferred during login."""
        reason = str(getattr(self, "_pi_disconnect_deferred_reason", "") or "").strip()
        self._pi_disconnect_deferred_during_login = False
        self._pi_disconnect_deferred_reason = ""
        self._pi_disconnect_deferred_origin = ""
        return reason

    def handle_missing_pi_host_disconnect_state(self: Any, *, origin: str = "auto", force_popup: bool = False):
        """Treat blank saved camera hostname as a disconnected/not-configured state.

        Server credentials may already exist, so SAS can start/minimize, but the
        camera host is still required for runtime protection. Do not silently ignore
        a blank camera hostname.
        """
        reason = "RTSP camera hostname/IP is not configured. Please go to Settings and enter the camera hostname/IP."
        self.pi_connected = False
        self.pi_connection_checked = True
        self.pi_system_user = ""
        self.pi_device_hostname = ""
        self.sas_oneconnect_session = None
        try:
            self.set_face_controls_connection_enabled(False)
        except Exception:
            pass
        try:
            self.stop_local_unlock("camera host not configured")
        except Exception:
            pass
        try:
            self.set_pi_status_label(connected=False, message="Status: camera host not configured")
        except Exception:
            pass
        self.suspend_locking_for_pi_disconnect(reason)
        if force_popup or not self.is_login_popup_active():
            self.show_pi_disconnect_alert_if_needed(reason, force=bool(force_popup), origin=origin)
        else:
            self.defer_pi_disconnect_until_after_login(reason, origin)
        return reason

    def run_post_login_pi_connection_check(self: Any):
        """After login closes, re-check/show the saved camera state.

        Startup checks are allowed before login, but any warning shown during
        login is deferred. This method shows the deferred warning or starts one
        clean post-login check for the saved host.
        """
        try:
            if getattr(self, "first_launch_setup_mode", False) or not getattr(self, "server_configured", False):
                return
            if getattr(self, "_camera_manual_disconnected", False):
                return

            host = str(getattr(self, "pi_api_host", "") or "").strip()
            if not host:
                self.handle_missing_pi_host_disconnect_state(origin="post-login", force_popup=True)
                return

            if getattr(self, "pi_connected", False):
                self.consume_deferred_pi_disconnect_reason()
                return

            deferred_reason = self.consume_deferred_pi_disconnect_reason()
            if deferred_reason:
                self.suspend_locking_for_pi_disconnect(deferred_reason)
                try:
                    self.append_system_log(f"POST_LOGIN_CAMERA_WARNING_DEFERRED: {deferred_reason}")
                except Exception:
                    pass

            # Run a clean quiet check after login so a camera that came online
            # while the login dialog was open can reconnect without a startup
            # false-warning card.
            self._startup_background_check_pending = True
            self._local_face_test_connection(
                show_disconnect_popup=False,
                show_progress=False,
                origin="post-login",
            )
        except Exception as e:
            try:
                self.append_system_log(f"POST_LOGIN_CAMERA_CHECK_ERROR: {e}")
            except Exception:
                pass

    def is_settings_tab_active(self: Any) -> bool:
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
            # Fallback: visible camera/settings widgets mean user is in Settings.
            widget = getattr(self, "pi_host_input", None)
            if widget is not None and widget.isVisible():
                return True
        except Exception:
            pass

        return False

    def return_to_settings_from_pi_disconnect(self: Any):
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

            self.append_system_log("RETURN_TO_SETTINGS_FROM_CAMERA_DISCONNECT")
        except Exception as e:
            print("[RETURN SETTINGS ERROR]", e)

    def should_auto_show_pi_disconnect_popup(self: Any) -> bool:
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

    def is_sas_minimized_or_background(self: Any) -> bool:
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

    def should_suppress_auto_pi_disconnect_popup(self: Any, origin: str = "") -> bool:
        """Suppress automatic camera disconnect popups while user is editing Settings.

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

    def can_show_pi_disconnect_popup_now(self: Any, source: str = "auto") -> bool:
        """Prevent duplicate camera disconnect popups from overlapping startup/retry paths."""
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

    def show_pi_disconnect_alert_if_needed(self: Any, reason: str = "", *, force: bool = False, origin: str = "auto"):
        """Show camera disconnect popup only when it should not block Settings typing/login."""
        self.camera_debug(
            "POPUP_CHECK",
            origin=origin,
            force=force,
            minimized=getattr(self, "_minimized_by_sas", False),
            settings_active=self.is_settings_tab_active(),
            reason=reason or getattr(self, "_pi_disconnect_reason", ""),
        )

        if self.is_login_popup_active():
            self.camera_debug("POPUP_SUPPRESSED_LOGIN", origin=origin)
            self.defer_pi_disconnect_until_after_login(reason or self._pi_disconnect_reason, origin)
            return False

        startup_quiet_origins = {"startup", "post-login", "retry", "auto", "pi-retry", "minimize"}
        quiet_until = float(getattr(self, "_startup_disconnect_warning_suppressed_until", 0.0) or 0.0)
        if str(origin or "").lower() in startup_quiet_origins and time.monotonic() < quiet_until:
            self.camera_debug("POPUP_SUPPRESSED_STARTUP_GRACE", origin=origin, quiet_left=round(quiet_until - time.monotonic(), 1))
            return False

        if self.should_suppress_auto_pi_disconnect_popup(origin) and not force:
            self.camera_debug("POPUP_SUPPRESSED_SETTINGS", origin=origin)
            return False

        if force or self.should_auto_show_pi_disconnect_popup():
            if not force and not self.can_show_pi_disconnect_popup_now(origin):
                self.camera_debug("POPUP_SUPPRESSED_DUPLICATE", origin=origin)
                return False
            self._pi_disconnect_popup_user_closed = False
            self.camera_debug("POPUP_SHOW", origin=origin, force=force)
            self.show_pi_disconnected_popup(reason or self._pi_disconnect_reason)
            return True

        self.camera_debug("POPUP_SUPPRESSED_AUTO_RULE", origin=origin)
        return False

    def suspend_locking_for_pi_disconnect(self: Any, reason: str = ""):
        """Suspend inactivity auto-lock while RTSP camera is disconnected."""
        self._pi_disconnect_lock_suspended = True
        self._pi_disconnect_reason = reason or "RTSP camera disconnected."
        self._pending_auto_lock = False
        try:
            self.mark_user_activity(reset_countdown=True)
        except Exception:
            pass
        try:
            self.append_system_log(f"CAMERA_DISCONNECTED_AUTO_LOCK_SUSPENDED: {self._pi_disconnect_reason}")
        except Exception:
            pass

    def resume_locking_after_pi_reconnect(self: Any):
        """Resume normal inactivity locking after local recognition reconnects."""
        was_suspended = getattr(self, "_pi_disconnect_lock_suspended", False)
        self._pi_disconnect_lock_suspended = False
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._pi_disconnect_reason = ""
        self._pi_disconnect_popup_visible = False
        self._pi_disconnect_popup_user_closed = False
        self._startup_disconnect_warning_suppressed_until = 0.0
        try:
            self.mark_user_activity(reset_countdown=True)
        except Exception:
            pass
        if was_suspended:
            try:
                self.append_system_log("CAMERA_RECONNECTED_AUTO_LOCK_RESUMED")
            except Exception:
                pass

    def should_suspend_inactivity_lock(self: Any) -> bool:
        """Automatic inactivity lock must not run when camera is disconnected."""
        if getattr(self, "first_launch_setup_mode", False):
            return True
        if getattr(self, "_pi_disconnect_lock_suspended", False):
            return True
        if not getattr(self, "pi_connected", True):
            return True
        return False

    def start_pi_disconnect_retry_loop(self: Any, reason: str = ""):
        """Keep retrying camera connection until it is restored."""
        self.camera_debug("RETRY_LOOP_START_REQUEST", active=getattr(self, "_pi_disconnect_retry_active", False), reason=reason)
        if getattr(self, "_camera_manual_disconnected", False):
            self.camera_debug("RETRY_LOOP_SKIPPED_MANUAL_DISCONNECT")
            return
        self.suspend_locking_for_pi_disconnect(reason)
        if getattr(self, "_pi_disconnect_retry_active", False):
            return
        self._pi_disconnect_retry_active = True
        QTimer.singleShot(5000, self.retry_pi_connection_until_restored)

    def retry_pi_connection_until_restored(self: Any):
        """Retry local status while disconnected and re-show warning if needed."""
        self.camera_debug("RETRY_TICK", active=getattr(self, "_pi_disconnect_retry_active", False), connected=getattr(self, "pi_connected", False), host=getattr(self, "pi_api_host", ""))
        if getattr(self, "_camera_manual_disconnected", False):
            self._pi_disconnect_retry_active = False
            self._pi_disconnect_retry_running = False
            self.camera_debug("RETRY_STOPPED_MANUAL_DISCONNECT")
            return
        if not getattr(self, "_pi_disconnect_retry_active", False):
            return
        if getattr(self, "pi_connected", False):
            self.resume_locking_after_pi_reconnect()
            return
        if getattr(self, "_pi_disconnect_retry_running", False):
            QTimer.singleShot(3000, self.retry_pi_connection_until_restored)
            return

        # v122: never let the background retry loop compete with an explicit
        # Settings Connect attempt.  The user may be testing a wrong hostname
        # or an offline camera; if retry starts another request it can invalidate
        # the manual attempt token and leave the connection card stuck at
        # "Connecting...".  Wait until the manual attempt finishes or the card
        # is closed.
        if self.is_manual_settings_connect_in_progress():
            self.camera_debug("RETRY_PAUSED_MANUAL_CONNECT")
            self._pi_disconnect_retry_running = False
            QTimer.singleShot(3000, self.retry_pi_connection_until_restored)
            return

        # Background retry must use only the last successfully connected/saved camera host.
        # Do not read Settings text while the user is typing; otherwise SAS can
        # auto-connect to a half-entered hostname and show conflict popups too early.
        if self.is_pi_host_editing_blocking_auto_connect():
            self.camera_debug("RETRY_PAUSED_HOST_EDITING")
            self._pi_disconnect_retry_running = False
            QTimer.singleShot(3000, self.retry_pi_connection_until_restored)
            return

        host = str(getattr(self, "pi_api_host", "") or "").strip()

        if not host:
            reason = "camera hostname/IP is not configured."
            self.suspend_locking_for_pi_disconnect(reason)
            self.show_pi_disconnect_alert_if_needed(reason, origin="retry")
            QTimer.singleShot(5000, self.retry_pi_connection_until_restored)
            return

        self._pi_disconnect_retry_running = True
        try:
            self._local_face_test_connection(
                show_disconnect_popup=False,
                show_progress=False,
                origin="pi-retry",
            )
        except Exception:
            self._pi_disconnect_retry_running = False

        QTimer.singleShot(3500, self.finish_pi_disconnect_retry_cycle)

    def finish_pi_disconnect_retry_cycle(self: Any):
        self.camera_debug("RETRY_FINISH", connected=getattr(self, "pi_connected", False), reason=getattr(self, "_pi_disconnect_reason", ""))
        self._pi_disconnect_retry_running = False
        if getattr(self, "pi_connected", False):
            self.resume_locking_after_pi_reconnect()
            # v120: Do not minimize SAS simply because a background retry
            # reconnected.  Startup minimize and face-unlock minimize still have
            # their own explicit paths, but an active user switching pages must
            # not suddenly lose the window.
            try:
                self.append_system_log("CAMERA_RETRY_RECONNECTED: window state preserved")
            except Exception:
                pass
            return

        reason = getattr(self, "_pi_disconnect_reason", "") or "RTSP camera disconnected. Please check camera power/network/source."
        self.suspend_locking_for_pi_disconnect(reason)
        self.show_pi_disconnect_alert_if_needed(reason, origin="retry")
        QTimer.singleShot(5000, self.retry_pi_connection_until_restored)

    def keep_pi_disconnected_warning_active(self: Any, reason: str = ""):
        """Keep retry loop alive and show popup only when appropriate."""
        self.suspend_locking_for_pi_disconnect(reason)
        self.show_pi_disconnect_alert_if_needed(reason, origin="auto")
        self.start_pi_disconnect_retry_loop(reason)

    def ensure_taskbar_window_identity(self: Any):
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

    def restore_main_window_for_attention(self: Any, reason: str = ""):
        """Show/maximize SAS only when the main window is not already visible.

        This avoids repeatedly maximizing/stealing focus when SAS is already
        open. For camera disconnect warnings, the popup can be prepared quietly and
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

    def changeEvent(self: Any, event):
        """Show the normal camera-disconnected warning when SAS is minimized while disconnected."""
        try:
            QMainWindow.changeEvent(cast(QMainWindow, self), event)
        except Exception:
            pass

        try:
            if event is not None and event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
                self._minimized_by_sas = True
                QTimer.singleShot(250, self.handle_minimized_disconnect_state)
        except Exception as e:
            print("[WINDOW STATE CHANGE ERROR]", e)

    def handle_minimized_disconnect_state(self: Any):
        """When minimized/background, warn if the selected camera cannot be used."""
        try:
            if getattr(self, "first_launch_setup_mode", False) or not getattr(self, "server_configured", False):
                return
            if getattr(self, "pi_connected", False):
                return

            host = str(getattr(self, "pi_api_host", "") or "").strip()
            if not host and hasattr(self, "pi_host_input"):
                host = self.pi_host_input.text().strip()
            if not host:
                self.handle_missing_pi_host_disconnect_state(origin="minimize", force_popup=True)
                return

            reason = f"RTSP camera is disconnected or unreachable ({host}). Please check camera power/network/source."
            self.suspend_locking_for_pi_disconnect(reason)
            self.show_pi_disconnect_alert_if_needed(reason, force=True, origin="minimize")
            self.start_pi_disconnect_retry_loop(reason)
        except Exception as e:
            print("[MINIMIZED DISCONNECT CHECK ERROR]", e)

    def minimize_once_after_startup(self: Any, reason: str = "startup"):
        """v207: Startup/background minimize must happen only once.

        After the user manually restores/maximizes SAS, later camera status checks,
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

    def minimize_to_taskbar_if_safe(self: Any, reason: str = ""):
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

    def startup_background_mode_check(self: Any):
        """Startup background mode.

        v208 requirement:
        - If configuration is complete, minimize SAS at startup immediately.
        - Do not wait for RTSP camera connection result before minimizing.
        - If camera is disconnected, the retry/disconnect popup logic will handle it
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

        # camera check/retry can continue in background, but it must not control
        # whether startup minimize happens. Blank camera host is also a disconnected
        # state because the user cannot use Face Recognition until it is set.
        if str(getattr(self, "pi_api_host", "") or "").strip():
            self._startup_background_check_pending = True
            self._startup_disconnect_warning_suppressed_until = time.monotonic() + 30.0
            QTimer.singleShot(33000, self.show_startup_camera_offline_if_needed)
            self.camera_debug("STARTUP_CAMERA_CHECK", host=getattr(self, "pi_api_host", ""))
            self._local_face_test_connection(
                show_disconnect_popup=False,
                show_progress=False,
                origin="startup",
            )
        else:
            self._startup_background_check_pending = False
            reason = self.handle_missing_pi_host_disconnect_state(origin="startup", force_popup=False)
            self.handle_startup_background_check_result(False, reason)

    def show_startup_camera_offline_if_needed(self: Any):
        """After startup grace, warn if the configured camera is still offline."""
        try:
            if getattr(self, "first_launch_setup_mode", False) or not getattr(self, "server_configured", False):
                return
            if getattr(self, "_camera_manual_disconnected", False):
                self.camera_debug("STARTUP_OFFLINE_POPUP_SKIPPED_MANUAL_DISCONNECT")
                return
            if getattr(self, "pi_connected", False):
                self.camera_debug("STARTUP_OFFLINE_POPUP_SKIPPED_CONNECTED")
                return
            host = str(getattr(self, "pi_api_host", "") or "").strip()
            if not host:
                return
            reason = getattr(self, "_pi_disconnect_reason", "") or f"RTSP camera is disconnected or unreachable ({host}). Please check camera hostname/IP, power, or network."
            self.camera_debug("STARTUP_OFFLINE_POPUP_DUE", host=host, reason=reason)
            self.suspend_locking_for_pi_disconnect(reason)
            self.show_pi_disconnect_alert_if_needed(reason, force=True, origin="startup-offline")
            self.start_pi_disconnect_retry_loop(reason)
        except Exception as exc:
            try:
                self.append_system_log(f"STARTUP_OFFLINE_POPUP_CHECK_ERROR: {exc}")
            except Exception:
                pass

    def handle_startup_background_check_result(self: Any, connected: bool, error_text: str = ""):
        """camera result after startup check.

        v208: startup minimize is based on configuration only and already
        happened in startup_background_mode_check(). This method only clears the
        pending flag and logs failure; it must not minimize/restore the window.
        """
        if not getattr(self, "_startup_background_check_pending", False):
            return

        self._startup_background_check_pending = False

        if not connected and error_text:
            self.append_system_log(f"STARTUP_CAMERA_CONNECTION_FAILED: {error_text}")

    def minimize_after_face_unlock(self: Any):
        """After Local face unlocks SAS, return the app to background."""
        self.minimize_to_taskbar_if_safe("face recognised and workstation unlocked")

    def get_sas_client_display_name(self: Any) -> str:
        try:
            user = os.getlogin()
        except Exception:
            user = os.environ.get("USERNAME") or os.environ.get("USER") or "SAS"
        try:
            host = socket.gethostname()
        except Exception:
            host = "WindowsSAS"
        return f"{host}\\{user}"

    def oneconnect_payload(self: Any, force: bool = False) -> dict:
        return {
            "client_name": str(getattr(self, "sas_client_name", "Windows SAS") or "Windows SAS"),
            "client_user": str(getattr(self, "current_user", "") or ""),
            "client_host": str(socket.gethostname() or ""),
            "force": bool(force),
        }

    def format_oneconnect_session_owner(self: Any, session: dict | None) -> str:
        if not isinstance(session, dict) or not session:
            return "another SAS device"
        name = str(session.get("client_name") or "another SAS device").strip()
        host = str(session.get("client_host") or "").strip()
        connected_at = str(session.get("connected_at") or "").strip()
        parts = [name]
        if host and host.lower() not in name.lower():
            parts.append(f"Host: {host}")
        if connected_at:
            parts.append(f"Connected at: {connected_at}")
        return " | ".join(parts)

    def claim_pi_oneconnect_session(self: Any, force: bool = False, timeout: int = 8, host: str | None = None):
        """Reserve this SAS instance for the selected local RTSP camera."""
        self._local_face_base_url(host_override=host)
        data = self.local_face_service.sas_connect(**self.oneconnect_payload(force=force))
        self.sas_oneconnect_session = data.get("session") if isinstance(data.get("session"), dict) else None
        return True, False, str(data.get("message") or "Local camera connection reserved."), data

    def disconnect_pi_oneconnect_session(self: Any, timeout: int = 8, host: str | None = None, stop_engine: bool = False):
        try:
            self._local_face_base_url(host_override=host)
            data = self.local_face_service.sas_disconnect(force=False, stop_engine=stop_engine)
            return True, str(data.get("message") or "Local camera disconnected."), data
        except Exception as exc:
            return False, str(exc), {}

    def send_sas_oneconnect_heartbeat(self: Any):
        if not bool(getattr(self, "pi_connected", False)):
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return

        def worker():
            try:
                self.local_face_service.sas_heartbeat()

                def online():
                    self._sas_heartbeat_failure_count = 0

                self.qt_after(0, online)
            except Exception as exc:
                reason = f"RTSP camera disconnected: {exc}"

                def offline(reason=reason):
                    try:
                        from services.local_recognition_engine import ENGINE

                        status = ENGINE.status()
                        frame_age = status.get("last_frame_age_seconds")
                        recent_frame = bool(
                            ENGINE.latest_frame is not None
                            and frame_age is not None
                            and float(frame_age) <= 45.0
                        )
                        active_or_recovering = bool(
                            status.get("recognition_running", False)
                            or status.get("capture_running", False)
                            or status.get("stream_recovering", False)
                            or recent_frame
                            or str(status.get("connection_state") or "").strip().lower()
                            in {"starting", "connecting", "live", "stale", "restarting"}
                        )
                        in_grace = time.monotonic() < float(getattr(self, "_camera_disconnect_grace_until", 0.0) or 0.0)
                        if active_or_recovering or in_grace:
                            self._sas_heartbeat_failure_count = 0
                            self.pi_connected = True
                            self.pi_connection_checked = True
                            self.set_face_controls_connection_enabled(True)
                            self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                            self.update_pi_connect_ui_state(connected=True)
                            self.camera_debug("HEARTBEAT_RECOVERY_GRACE", reason=reason, state=status.get("connection_state"))
                            return
                    except Exception:
                        pass

                    count = int(getattr(self, "_sas_heartbeat_failure_count", 0) or 0) + 1
                    self._sas_heartbeat_failure_count = count
                    self.append_system_log(f"Local heartbeat failed ({count}/2): {reason}")
                    if count < 2:
                        return
                    if getattr(self, "pi_connected", False):
                        self._sas_heartbeat_failure_count = 0
                        self.handle_pi_runtime_disconnect(reason)

                self.qt_after(0, offline)

        Thread(target=worker, daemon=True).start()

    def set_selected_pi_host_runtime(self: Any, host: str, *, connected: bool = False, configure_backend: bool = True):
        """Commit the user-selected camera hostname/IP into runtime state.

        This is intentionally separate from a successful API connection.  When
        the user types/saves/connects to a wrong hostname, SAS must remember
        that selected host and stay disconnected instead of silently falling
        back to the previous working camera.
        """
        host = str(host or "").strip()
        self.pi_api_host = host
        self.pi_api_port = "5000"

        if host:
            self.camera_debug("SET_SELECTED_HOST", host=host, connected=connected, configure_backend=configure_backend)
            if configure_backend:
                try:
                    self.local_face_service.configure(host, "5000")
                except Exception as exc:
                    self.append_system_log(f"Local face service configure failed: {exc}")
                try:
                    self.configure_local_unlock(host, "5000", start=False)
                except Exception as exc:
                    self.append_system_log(f"Local unlock configure failed: {exc}")
                self.camera_feed_url = self.local_face_service.rtsp_url()
            else:
                self.camera_feed_url = ""
            self.pi_api_base = f"local://{host}"
        else:
            self.pi_api_base = ""
            self.camera_feed_url = ""
            try:
                self.configure_local_unlock("", "5000", start=False)
            except Exception:
                pass

        if not connected:
            self.pi_connected = False
            self.pi_connection_checked = True
            self.pi_system_user = ""
            self.pi_device_hostname = ""
            self.sas_oneconnect_session = None

        try:
            if hasattr(self, "pi_host_input"):
                current = self.pi_host_input.text().strip()
                if current != host:
                    self.pi_host_input.blockSignals(True)
                    self.pi_host_input.setText(host)
                    self.pi_host_input.blockSignals(False)
        except Exception:
            pass

    def handle_pi_host_text_edited(self: Any, _text: str = ""):
        self.camera_debug("HOST_TEXT_EDITED", text=_text)
        """Let users type a camera hostname/IP without triggering background auto-connect.

        Only the explicit Connect button should use the live text in this field.
        Startup/retry/health checks continue to use the last connected/saved host,
        and are paused while the Settings host field is dirty or focused.
        """
        self.mark_settings_modified_by_user()
        self._pi_host_dirty_since_edit = True
        self._pi_host_user_editing = True
        self._pi_selected_host_pending_manual_connect = True
        # Invalidate any in-flight connect/retry worker started for the old host.
        try:
            self._pi_connect_request_token = int(getattr(self, "_pi_connect_request_token", 0)) + 1
        except Exception:
            self._pi_connect_request_token = 1
        self.pi_connected = False
        self.pi_connection_checked = False
        self.sas_oneconnect_session = None
        self._startup_background_check_pending = False
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._pi_disconnect_lock_suspended = False
        try:
            self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
        except Exception:
            pass
        try:
            self.stop_local_unlock("camera host edited")
        except Exception:
            pass
        try:
            self.clear_all_authorized_users_ui()
        except Exception:
            pass
        try:
            self.set_face_controls_connection_enabled(False)
        except Exception:
            pass
        try:
            self.set_pi_status_label(connected=False, message="Status: Disconnected")
        except Exception:
            pass
        try:
            self.update_pi_connect_ui_state(connected=False, checking=False)
        except Exception:
            pass

    def is_manual_settings_connect_in_progress(self: Any) -> bool:
        """True while the user-pressed Settings Connect dialog is still active.

        Background retry must not run during this window.  Otherwise a retry
        request can change the global connect token before the manual failed
        request returns, so the manual failure is ignored as stale and the
        dialog remains stuck in the loading state.
        """
        if getattr(self, "_settings_connect_in_progress", False):
            return True
        dialog = getattr(self, "connection_dialog", None)
        if dialog is None:
            return False
        try:
            if not dialog.isVisible():
                return False
            return str(getattr(dialog, "origin", "") or "").lower() == "settings" and str(getattr(dialog, "state", "") or "").lower() == "loading"
        except Exception:
            return False

    def is_pi_host_editing_blocking_auto_connect(self: Any) -> bool:
        """True when background auto-connect/retry should not read the Settings field."""
        try:
            if not self.is_settings_tab_active():
                return False
        except Exception:
            pass
        host_input = getattr(self, "pi_host_input", None)
        focused = False
        try:
            focused = bool(host_input is not None and host_input.hasFocus())
        except Exception:
            focused = False
        return bool(getattr(self, "_pi_host_dirty_since_edit", False) or focused)

    def get_pi_host_for_connection_origin(self: Any, origin: str = "") -> str:
        """Settings Connect uses the typed field; background checks use active host only."""
        origin_safe = str(origin or "").strip().lower()
        if origin_safe == "settings":
            return self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else str(getattr(self, "pi_api_host", "") or "").strip()
        return str(getattr(self, "pi_api_host", "") or "").strip()

    def update_pi_connect_ui_state(self: Any, connected: bool | None = None, checking: bool = False):
        connected = bool(getattr(self, "pi_connected", False)) if connected is None else bool(connected)
        try:
            if (
                not connected
                and not checking
                and callable(getattr(self, "is_local_rtsp_active_for_ui", None))
                and self.is_local_rtsp_active_for_ui()
            ):
                connected = True
                self.pi_connected = True
                self.pi_connection_checked = True
                self._camera_user_stopped = False
        except Exception:
            pass
        btn = getattr(self, "pi_connect_btn", None)
        host_input = getattr(self, "pi_host_input", None)

        try:
            manual_checking = bool(checking and self.is_manual_settings_connect_in_progress())
        except Exception:
            manual_checking = bool(checking and getattr(self, "_settings_connect_in_progress", False))

        # Background startup/retry checks must not block Settings. Only a
        # user-pressed Connect, or the short manual Disconnect transition,
        # should lock the button/input.
        blocking_check = bool(checking and (manual_checking or connected))

        if btn is not None:
            if blocking_check:
                btn.setText("Disconnecting..." if connected else "Connecting...")
                btn.setEnabled(False)
                btn.setObjectName("SettingsPrimaryButton")
            elif connected:
                btn.setText("Disconnect")
                btn.setEnabled(True)
                btn.setObjectName("SettingsDangerButton")
            else:
                btn.setText("Connect")
                btn.setEnabled(True)
                btn.setObjectName("SettingsPrimaryButton")

            if blocking_check or connected:
                btn.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

        if host_input is not None:
            editable = not connected and not blocking_check
            host_input.setEnabled(editable)
            host_input.setReadOnly(not editable)
            host_input.setToolTip(
                "Disconnect before editing the camera hostname/IP."
                if connected else "Enter the camera hostname or IP address."
            )
    def toggle_pi_connection_from_settings(self: Any):
        self.camera_debug("SETTINGS_CONNECT_BUTTON", connected=getattr(self, "pi_connected", False), host=self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else getattr(self, "pi_api_host", ""))
        if self.is_manual_settings_connect_in_progress():
            self.update_pi_connect_ui_state(connected=False, checking=True)
            return

        if bool(getattr(self, "pi_connected", False)):
            self.disconnect_pi_from_settings()
            return

        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else str(getattr(self, "pi_api_host", "") or "").strip()
        try:
            from services.local_recognition_engine import ENGINE

            configured_host = str(getattr(ENGINE, "host", "") or "").strip().lower()
            selected_host = str(host or "").strip().lower()
            status = ENGINE.status()
            active_for_host = bool(
                selected_host
                and configured_host == selected_host
                and status.get("recognition_running", False)
                and status.get("capture_running", False)
            )
            recent_frame = False
            try:
                frame_age = status.get("last_frame_age_seconds")
                recent_frame = bool(ENGINE.latest_frame is not None and frame_age is not None and float(frame_age) <= 30.0)
            except Exception:
                recent_frame = False

            if active_for_host and (
                status.get("stream_healthy", False)
                or status.get("stream_recovering", False)
                or recent_frame
                or str(status.get("connection_state") or "").strip().lower() in {"starting", "connecting", "live", "stale", "restarting"}
            ):
                self._settings_connect_in_progress = False
                self.pi_api_host = host
                self.pi_api_port = "5000"
                self.pi_connection_checked = True
                self.pi_connected = True
                self._camera_connected_once_this_run = True
                self._pi_selected_host_pending_manual_connect = False
                self._pi_host_dirty_since_edit = False
                self._pi_host_user_editing = False
                try:
                    self.local_face_service.configure(host, "5000")
                except Exception:
                    pass
                self.pi_api_base = f"local://{host}"
                try:
                    self.camera_feed_url = self.local_face_service.rtsp_url()
                except Exception:
                    pass
                self.resume_locking_after_pi_reconnect()
                self.set_face_controls_connection_enabled(True)
                self.configure_local_unlock(host, "5000", start=True)
                self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering" if not status.get("stream_healthy", False) else f"Status: Connected | Host: {host}")
                self.update_pi_connect_ui_state(connected=True)
                if not getattr(self, "_camera_preview_running", False):
                    self.start_camera_preview(force=True)
                self.append_face_log("CAMERA_CONNECT_REUSED: RTSP engine is already active; duplicate Connect skipped.")
                return
        except Exception as exc:
            try:
                self.camera_debug("CONNECT_REUSE_CHECK_FAILED", host=host, error=str(exc))
            except Exception:
                pass

        # v122: a user-pressed Connect must own the connection attempt.
        # Stop any disconnected/background retry first; otherwise the retry
        # can invalidate the manual request token and leave the popup showing
        # "Connecting..." forever for wrong hostnames or powered-off Pis.
        self._settings_connect_in_progress = True
        self._camera_manual_disconnected = False
        self._runtime_disconnect_candidate_since = 0.0
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._manual_connect_failed_popup_active = False
        try:
            self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
        except Exception:
            self._settings_connect_attempt_id = 1

        self._local_face_test_connection(
            show_disconnect_popup=True,
            show_progress=True,
            origin="settings",
        )

    def disconnect_pi_from_settings(self: Any):
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        started_at = time.monotonic()
        self.camera_debug("MANUAL_DISCONNECT_START", host=host)
        self.set_pi_status_label(checking=True, message="Status: Disconnecting...")
        self.update_pi_connect_ui_state(connected=True, checking=True)

        def worker():
            self.camera_debug("MANUAL_DISCONNECT_WORKER_START", host=host)
            ok, message, _data = self.disconnect_pi_oneconnect_session(timeout=8, stop_engine=True)

            def done():
                self._pi_disconnect_retry_active = False
                self._pi_disconnect_retry_running = False
                self._pi_disconnect_lock_suspended = False
                self._camera_manual_disconnected = True
                self._runtime_disconnect_candidate_since = 0.0
                self.pi_connected = False
                self.pi_connection_checked = True
                self._pi_selected_host_pending_manual_connect = True
                self.pi_system_user = ""
                self.pi_device_hostname = ""
                self.sas_oneconnect_session = None
                self.stop_local_unlock("manual disconnect")
                self.set_face_controls_connection_enabled(False)
                self.clear_all_authorized_users_ui()
                self.stop_camera_preview(show_prompt=True)
                self.set_pi_status_label(connected=False, message="Status: Disconnected")
                self.update_pi_connect_ui_state(connected=False)
                self.camera_debug("MANUAL_DISCONNECT_DONE", ok=ok, elapsed=round(time.monotonic() - started_at, 2), message=message)
                self.append_face_log(f"CAMERA_DISCONNECT: {message}")
                self.write_sas_log(
                    "CAMERA DISCONNECTED",
                    actor=self.get_audit_actor(),
                    details={"Camera host": host or "-", "Result": "Manual disconnect" if ok else message},
                )
                # Manual Disconnect is intentionally quiet; Settings status/button already update.

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()

    def close_connection_dialog_silently(self: Any):
        """Close the Settings Connect progress card before showing a conflict-only modal."""
        dialog = getattr(self, "connection_dialog", None)
        if dialog is None:
            return
        try:
            dialog.accept()
        except Exception:
            try:
                dialog.close()
            except Exception:
                pass
        self.connection_dialog = None

    def show_oneconnect_conflict_prompt(self: Any, active_session: dict | None, message: str = ""):
        """Show the premium close-only popup only when another SAS owns the selected camera."""
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else ""
        if not host:
            host = str(getattr(self, "pi_api_host", "") or "").strip()
        if not host and isinstance(active_session, dict):
            host = str(active_session.get("hostname") or active_session.get("host") or "").strip()
        self.show_oneconnect_conflict_dialog(host or "selected hostname")
        self.append_face_log("CAMERA_CONNECT_CANCELLED: camera is already connected with another SAS device.")

    def show_oneconnect_conflict_dialog(self: Any, hostname: str = "selected hostname"):
        """Close-only dialog for the 'hostname already connected by others' case."""
        safe_host = html.escape(str(hostname or "selected hostname").strip() or "selected hostname")

        dialog = QDialog(self)
        dialog.setObjectName("OneConnectConflictDialog")
        dialog.setModal(True)
        dialog.setWindowTitle("Active Connection Detected")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setFixedSize(520 if not self.compact_mode else 460, 390 if not self.compact_mode else 360)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("OneConnectConflictCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        try:
            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(22)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 45))
            card.setGraphicsEffect(shadow)
        except Exception:
            pass

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("OneConnectConflictTopBar")
        top_bar.setFixedHeight(4)
        layout.addWidget(top_bar)

        body = QVBoxLayout()
        body.setContentsMargins(38, 26, 38, 24)
        body.setSpacing(0)

        icon_circle = QLabel("⊘")
        icon_circle.setObjectName("OneConnectConflictIcon")
        icon_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_circle.setFixedSize(64, 64)
        icon_font = QFont("Inter")
        icon_font.setPointSize(32)
        icon_font.setWeight(QFont.Weight.Light)
        icon_circle.setFont(icon_font)
        body.addWidget(icon_circle, 0, Qt.AlignmentFlag.AlignHCenter)
        body.addSpacing(16)

        title = QLabel("Active Connection Detected")
        title.setObjectName("OneConnectConflictTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        body.addWidget(title)
        body.addSpacing(6)

        desc = QLabel(
            'The hostname <span style="font-family: Consolas, Courier New, monospace; '
            'font-weight: 800; color: #000000; background-color: #e8e8e8;">'
            f'&nbsp;{safe_host}&nbsp;</span> is currently occupied by other authorized users.'
        )
        desc.setObjectName("OneConnectConflictDescription")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(desc)
        body.addSpacing(20)

        close_btn = QPushButton("CLOSE")
        close_btn.setObjectName("OneConnectConflictCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(190, 44)
        close_btn.clicked.connect(dialog.accept)
        body.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(body)
        outer.addWidget(card)

        dialog.setStyleSheet("""
            QDialog#OneConnectConflictDialog {
                background: rgba(0, 0, 0, 95);
            }
            QFrame#OneConnectConflictCard {
                background: #ffffff;
                border: 1px solid #c4c7c7;
                border-radius: 12px;
            }
            QFrame#OneConnectConflictTopBar {
                background: #000000;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#OneConnectConflictIcon {
                background: #e8e8e8;
                color: #000000;
                border-radius: 32px;
            }
            QLabel#OneConnectConflictTitle {
                color: #000000;
                font-family: Inter, Segoe UI, Arial;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#OneConnectConflictDescription {
                color: #5e5e5e;
                font-family: Inter, Segoe UI, Arial;
                font-size: 12px;
                line-height: 17px;
            }
            QPushButton#OneConnectConflictCloseButton {
                background: #000000;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 1.2px;
            }
            QPushButton#OneConnectConflictCloseButton:hover {
                background: #00174b;
            }
            QPushButton#OneConnectConflictCloseButton:pressed {
                background: #000000;
                padding-top: 2px;
            }
        """)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

    def handle_oneconnect_connection_lost(self: Any, reason: str = "camera connection ownership lost.", active_session: dict | None = None):
        self.pi_connection_checked = True
        self.pi_connected = False
        self.pi_system_user = ""
        self.pi_device_hostname = ""
        self.sas_oneconnect_session = None
        self.stop_local_unlock("oneconnect lost")
        self.set_face_controls_connection_enabled(False)
        self.clear_all_authorized_users_ui()
        # Silent disconnect only: do not show a modal popup when another SAS
        # takes over the camera connection or when ownership is lost. The Settings
        # status label, Connect button state, and face log are enough feedback.
        self.stop_camera_preview(show_prompt=False)
        self.set_pi_status_label(connected=False, message="Status: Disconnected")
        self.update_pi_connect_ui_state(connected=False)
        self.append_face_log(f"CAMERA_ONECONNECT_LOST: {reason}")
