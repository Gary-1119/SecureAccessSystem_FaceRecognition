from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class LockRuntimeControllerMixin(DashboardMixinBase):
    def minimize_after_face_unlock(self):
        """After WebSocket face unlocks SAS, return the app to background."""
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
            if event is not None and event.type() == QEvent.Type.MouseMove:
                try:
                    point = event.globalPosition().toPoint()
                except Exception:
                    try:
                        point = event.globalPos()
                    except Exception:
                        point = None

                if point is not None:
                    last_point = getattr(self, "_last_activity_mouse_pos", None)
                    now = time.monotonic()
                    last_ts = float(getattr(self, "_last_activity_mouse_ts", 0.0) or 0.0)
                    moved = (
                        last_point is None
                        or abs(point.x() - last_point.x()) >= 3
                        or abs(point.y() - last_point.y()) >= 3
                    )
                    if moved and (now - last_ts) >= 0.25:
                        self._last_activity_mouse_pos = point
                        self._last_activity_mouse_ts = now
                        self.mark_user_activity(reset_countdown=True)

            elif event is not None and event.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.KeyPress,
                QEvent.Type.KeyRelease,
                QEvent.Type.Wheel,
                QEvent.Type.TouchBegin,
            ):
                self.mark_user_activity(reset_countdown=True)
        except Exception:
            pass
        return super().eventFilter(obj, event)


    def mark_user_activity(self, reset_countdown: bool = True):
        """Record local activity and optionally refill the visible countdown."""
        self._last_user_activity_ts = time.monotonic()
        self._countdown_activity_anchor_ts = self._last_user_activity_ts
        self._last_windows_input_tick = self.get_windows_last_input_tick()
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


    def get_windows_last_input_tick(self) -> int | None:
        """Return Windows' raw last keyboard/mouse input tick."""
        if platform.system().lower() != "windows":
            return None
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            last_input_info = LASTINPUTINFO()
            last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
                return int(last_input_info.dwTime)
        except Exception:
            pass
        return None


    def get_effective_idle_seconds(self) -> float:
        """Return global keyboard/mouse inactivity like Windows screensaver."""
        now = time.monotonic()
        anchor_ts = float(getattr(self, "_countdown_activity_anchor_ts", getattr(self, "_last_user_activity_ts", now)) or now)
        anchor_idle = max(0.0, now - anchor_ts)

        last_input_tick = self.get_windows_last_input_tick()
        if last_input_tick is None:
            return anchor_idle

        previous_input_tick = getattr(self, "_last_windows_input_tick", None)
        if previous_input_tick is None:
            self._last_windows_input_tick = int(last_input_tick)
            return anchor_idle

        # If Windows' raw last-input tick changed, keyboard/mouse activity
        # happened anywhere on the workstation, even outside the SAS window.
        if int(last_input_tick) != int(previous_input_tick):
            self._last_windows_input_tick = int(last_input_tick)
            self._last_user_activity_ts = now
            self._countdown_activity_anchor_ts = now
            return 0.0

        return anchor_idle


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
            if bool(getattr(self, "pi_connected", False)) and base_url:
                feed_url = f"{base_url}/video-feed"
        except Exception:
            feed_url = ""

        notification = SystemLockedNotification(
            compact_mode=self.compact_mode,
            video_feed_url=feed_url,
        )
        self.system_locked_notification = notification
        notification.show_at_bottom_right()
        if bool(getattr(self, "pi_connected", False)):
            self.start_locked_pi_watchdog()
        else:
            try:
                notification.mark_camera_unavailable("Pi not connected")
            except Exception:
                pass


    def hide_system_locked_notification(self):
        """Remove the desktop lock notification after face/manual/emergency unlock."""
        self.stop_locked_pi_watchdog()
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


    def start_locked_pi_watchdog(self):
        """Poll Pi status while locked so power loss shows a disconnect popup."""
        try:
            timer = getattr(self, "_locked_pi_watchdog_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setInterval(3000)
                timer.timeout.connect(self.check_locked_pi_status)
                self._locked_pi_watchdog_timer = timer
            if not timer.isActive():
                timer.start()
            QTimer.singleShot(500, self.check_locked_pi_status)
        except Exception:
            pass


    def stop_locked_pi_watchdog(self):
        try:
            timer = getattr(self, "_locked_pi_watchdog_timer", None)
            if timer is not None:
                timer.stop()
        except Exception:
            pass
        try:
            self._locked_pi_status_failures = 0
            self._locked_pi_status_check_running = False
        except Exception:
            pass


    def check_locked_pi_status(self):
        if not getattr(self, "is_locked", False):
            self.stop_locked_pi_watchdog()
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return
        if getattr(self, "_locked_pi_status_check_running", False):
            return

        self._locked_pi_status_check_running = True

        def worker():
            try:
                self._face_api_request("GET", "/status", timeout=3)
                def online():
                    self._locked_pi_status_check_running = False
                    self._locked_pi_status_failures = 0
                self.qt_after(0, online)
            except Exception:
                def offline():
                    self._locked_pi_status_check_running = False
                    failures = int(getattr(self, "_locked_pi_status_failures", 0) or 0) + 1
                    self._locked_pi_status_failures = failures
                    if failures < 3:
                        try:
                            self.append_system_log(f"LOCKED_PI_STATUS_RETRY: /status failed {failures}/3 before disconnect warning.")
                        except Exception:
                            pass
                        return

                    self.handle_pi_runtime_disconnect(
                        "Pi disconnected while SAS is locked. Please check Pi power/network."
                    )
                self.qt_after(0, offline)

        Thread(target=worker, daemon=True).start()


    def mark_locked_notification_camera_unavailable(self, reason: str = "Camera unavailable"):
        notification = getattr(self, "system_locked_notification", None)
        if notification is None:
            return
        try:
            if notification.isVisible() and hasattr(notification, "mark_camera_unavailable"):
                notification.mark_camera_unavailable(reason)
        except Exception:
            pass


    def refresh_locked_notification_camera(self):
        notification = getattr(self, "system_locked_notification", None)
        if notification is None:
            return
        try:
            if not notification.isVisible():
                return
            if not bool(getattr(self, "pi_connected", False)):
                if hasattr(notification, "mark_camera_unavailable"):
                    notification.mark_camera_unavailable("Pi not connected")
                return
            base_url = str(getattr(self, "pi_api_base", "") or "").rstrip("/")
            if not base_url:
                return
            feed_url = f"{base_url}/video-feed"
            if hasattr(notification, "restart_video_stream"):
                notification.restart_video_stream(feed_url)
        except Exception:
            pass

    # --------------------------------------------------------
    # Login popup
    # --------------------------------------------------------

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
            self.write_sas_log(
                "UNLOCKED",
                actor=str(unlock_user).upper(),
                details={"Method": "MANUAL"},
            )
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


    def close_after_settings_save(self):
        """Close the window after async Settings save completes successfully."""
        self._settings_close_after_save = True
        self.close()


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
        if getattr(self, "pi_connected", False):
            self.start_websocket_lock_session("inactivity_timeout")
        else:
            self.append_system_log("LOCK_SESSION_SKIPPED: Pi is not connected to this SAS.")
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

        # Locked state stays at 00:00 until a valid Pi WebSocket recognition
        # event unlocks the system.
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
        remaining = max(0, int(self.total_seconds - float(idle_seconds) + 0.999))
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

