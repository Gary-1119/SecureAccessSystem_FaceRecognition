from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class PiDisconnectControllerMixin(DashboardMixinBase):
    def is_login_popup_active(self) -> bool:
        """Return True while the login dialog is open.

        Startup Pi checks are still allowed to run, but disconnect warning
        popups are deferred until login finishes so the login UI stays clean.
        """
        try:
            return bool(getattr(self, "_login_popup_active", False))
        except Exception:
            return False


    def defer_pi_disconnect_until_after_login(self, reason: str = "", origin: str = "auto"):
        """Remember a Pi disconnect warning that happened during login."""
        self._pi_disconnect_deferred_during_login = True
        self._pi_disconnect_deferred_reason = reason or getattr(self, "_pi_disconnect_reason", "") or "Raspberry Pi disconnected."
        self._pi_disconnect_deferred_origin = origin or "auto"
        try:
            self.append_system_log(f"PI_DISCONNECT_POPUP_DEFERRED_DURING_LOGIN: {self._pi_disconnect_deferred_reason}")
        except Exception:
            pass


    def consume_deferred_pi_disconnect_reason(self) -> str:
        """Return and clear any Pi disconnect warning deferred during login."""
        reason = str(getattr(self, "_pi_disconnect_deferred_reason", "") or "").strip()
        self._pi_disconnect_deferred_during_login = False
        self._pi_disconnect_deferred_reason = ""
        self._pi_disconnect_deferred_origin = ""
        return reason


    def handle_missing_pi_host_disconnect_state(self, *, origin: str = "auto", force_popup: bool = False):
        """Treat blank saved Pi hostname as a disconnected/not-configured state.

        Server credentials may already exist, so SAS can start/minimize, but the
        Pi host is still required for runtime protection. Do not silently ignore
        a blank Pi hostname.
        """
        reason = "Raspberry Pi hostname/IP is not configured. Please go to Settings and enter the Pi hostname/IP."
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
            self.stop_recognition_websocket("Pi host not configured")
        except Exception:
            pass
        try:
            self.set_pi_status_label(connected=False, message="Status: Pi host not configured")
        except Exception:
            pass
        self.suspend_locking_for_pi_disconnect(reason)
        if force_popup or not self.is_login_popup_active():
            self.show_pi_disconnect_alert_if_needed(reason, force=bool(force_popup), origin=origin)
        else:
            self.defer_pi_disconnect_until_after_login(reason, origin)
        return reason


    def run_post_login_pi_connection_check(self):
        """After login closes, re-check/show the saved Pi state.

        Startup checks are allowed before login, but any warning shown during
        login is deferred. This method shows the deferred warning or starts one
        clean post-login check for the saved host.
        """
        try:
            if getattr(self, "first_launch_setup_mode", False) or not getattr(self, "server_configured", False):
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
                self.show_pi_disconnect_alert_if_needed(deferred_reason, force=True, origin="post-login")

            # Run a clean check after login so a Pi that came online while the
            # login dialog was open can immediately reconnect.
            self._startup_background_check_pending = True
            self._face_api_test_connection(
                show_disconnect_popup=True,
                show_progress=False,
                origin="post-login",
            )
        except Exception as e:
            try:
                self.append_system_log(f"POST_LOGIN_PI_CHECK_ERROR: {e}")
            except Exception:
                pass


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
        try:
            if not self.isActiveWindow():
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
        """Show Pi disconnect popup only when it should not block Settings typing/login."""
        # v119: Pi monitoring starts during startup, but the disconnected card
        # must not overlay the login popup. Save the reason and show/check again
        # after login closes.
        if self.is_login_popup_active():
            self.defer_pi_disconnect_until_after_login(reason or self._pi_disconnect_reason, origin)
            return False

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
        """Record Pi disconnect state without freezing the inactivity countdown."""
        self._pi_disconnect_lock_suspended = True
        self._pi_disconnect_reason = reason or "Raspberry Pi disconnected."
        self._pending_auto_lock = False
        try:
            self.append_system_log(f"PI_DISCONNECTED: {self._pi_disconnect_reason}")
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
        try:
            if getattr(self, "is_locked", False):
                self.refresh_locked_notification_camera()
        except Exception:
            pass
        if was_suspended:
            try:
                self.append_system_log("PI_RECONNECTED_AUTO_LOCK_RESUMED")
            except Exception:
                pass


    def should_suspend_inactivity_lock(self) -> bool:
        """Return True only for setup states that should freeze auto-lock."""
        if getattr(self, "first_launch_setup_mode", False):
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

        # v122: never let the background retry loop compete with an explicit
        # Settings Connect attempt.  The user may be testing a wrong hostname
        # or an offline Pi; if retry starts another request it can invalidate
        # the manual attempt token and leave the connection card stuck at
        # "Connecting...".  Wait until the manual attempt finishes or the card
        # is closed.
        if self.is_manual_settings_connect_in_progress():
            self._pi_disconnect_retry_running = False
            QTimer.singleShot(3000, self.retry_pi_connection_until_restored)
            return

        # Background retry must use only the last successfully connected/saved Pi host.
        # Do not read Settings text while the user is typing; otherwise SAS can
        # auto-connect to a half-entered hostname and show conflict popups too early.
        if self.is_pi_host_editing_blocking_auto_connect():
            self._pi_disconnect_retry_running = False
            QTimer.singleShot(3000, self.retry_pi_connection_until_restored)
            return

        host = str(getattr(self, "pi_api_host", "") or "").strip()

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
            # v120: Do not minimize SAS simply because a background retry
            # reconnected.  Startup minimize and face-unlock minimize still have
            # their own explicit paths, but an active user switching pages must
            # not suddenly lose the window.
            try:
                self.append_system_log("PI_RETRY_RECONNECTED: window state preserved")
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



    def changeEvent(self, event):
        """Show the normal Pi-disconnected warning when SAS is minimized while disconnected."""
        try:
            super().changeEvent(event)
        except Exception:
            pass

        try:
            if event is not None and event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
                self._minimized_by_sas = True
                QTimer.singleShot(250, self.handle_minimized_disconnect_state)
        except Exception as e:
            print("[WINDOW STATE CHANGE ERROR]", e)


    def handle_minimized_disconnect_state(self):
        """When minimized/background, warn if the selected Pi cannot be used."""
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

            reason = f"Raspberry Pi is disconnected or unreachable ({host}). Please check Pi power/network."
            self.suspend_locking_for_pi_disconnect(reason)
            self.show_pi_disconnect_alert_if_needed(reason, force=True, origin="minimize")
            self.start_pi_disconnect_retry_loop(reason)
        except Exception as e:
            print("[MINIMIZED DISCONNECT CHECK ERROR]", e)



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
        # whether startup minimize happens. Blank Pi host is also a disconnected
        # state because the user cannot use Face Recognition until it is set.
        if str(getattr(self, "pi_api_host", "") or "").strip():
            self._startup_background_check_pending = True
            self._face_api_test_connection(
                show_disconnect_popup=True,
                show_progress=False,
                origin="startup",
            )
        else:
            self._startup_background_check_pending = False
            reason = self.handle_missing_pi_host_disconnect_state(origin="startup", force_popup=False)
            self.handle_startup_background_check_result(False, reason)


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

