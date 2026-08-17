from __future__ import annotations

import ctypes
import platform
import time
import uuid
from datetime import datetime
from typing import Any, cast

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency guard
    cv2 = None

from PySide6.QtCore import QDateTime, QEvent, Qt, QTimer
from PySide6.QtWidgets import QApplication

from app_config import *
from dialogs import SystemLockedNotification


class LockRuntimeControllerMixin:
    def install_idle_activity_tracker(self: Any):
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

    def eventFilter(self: Any, obj, event):
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
        return False

    def mark_user_activity(self: Any, reset_countdown: bool = True):
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

    def get_windows_system_idle_seconds(self: Any) -> float | None:
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

    def get_effective_idle_seconds(self: Any) -> float:
        """Return inactivity seconds using Windows OS input plus SAS logical resets."""
        now = time.monotonic()
        system_idle = self.get_windows_system_idle_seconds()
        if system_idle is None:
            return max(0.0, now - getattr(self, "_last_user_activity_ts", now))

        system_last_input_ts = now - max(0.0, system_idle)
        logical_last_input_ts = getattr(self, "_last_user_activity_ts", system_last_input_ts)
        effective_last_input_ts = max(system_last_input_ts, logical_last_input_ts)
        return max(0.0, now - effective_last_input_ts)

    def refresh_emergency_recovery_state(self: Any):
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

    def recover_after_windows_secure_desktop(self: Any, reason: str = "session_recovery", log_once: bool = False):
        """Re-arm lock controls after Windows lock screen / secure desktop returns."""
        if getattr(self, "_closing", False):
            return
        try:
            if log_once:
                now = time.monotonic()
                if now - getattr(self, "_last_session_recovery_log_at", 0.0) > 5.0:
                    self._last_session_recovery_log_at = now
                    self.append_system_log(f"WINDOWS_SESSION_RECOVERY: {reason}")

            self.runtime_lock_service.recover_after_windows_session_change(self)

            if not getattr(self, "is_locked", False):
                return

            notification = getattr(self, "system_locked_notification", None)
            if notification is not None and notification.isVisible():
                try:
                    notification.restart_video_stream()
                except Exception:
                    pass
            else:
                self.show_system_locked_notification()

            host = str(getattr(self, "pi_api_host", "") or "").strip()
            if host:
                if not str(getattr(self, "unlock_session_id", "") or "").strip():
                    self.start_local_unlock_session(reason)
                else:
                    self.configure_local_unlock(host, self.pi_api_port, start=True)
                    self.local_unlock_service.send_lock_session_started(
                        self.unlock_session_id,
                        reason=reason,
                    )
        except Exception as e:
            self.append_system_log(f"Windows session recovery failed: {e}")

    def minimize_to_taskbar_for_lock(self: Any, reason: str = "system locked"):
        """Keep SAS in the taskbar while Windows apps remain visible behind the lock state."""
        try:
            self.ensure_taskbar_window_identity()
            self._minimized_by_sas = True
            self.showMinimized()
            if reason:
                self.append_system_log(f"WINDOW_MINIMIZED_TO_TASKBAR: {reason}")
        except Exception as e:
            print("[LOCK MINIMIZE ERROR]", e)

    def show_system_locked_notification(self: Any):
        """Show a small, no-focus, non-modal desktop notification for the locked state.

        Unlike the removed overlay, this does not blur, darken, restore, maximize,
        or activate the SAS dashboard.
        """
        if getattr(self, "_suppress_lock_notification", False):
            return

        existing = getattr(self, "system_locked_notification", None)
        if existing is not None and existing.isVisible():
            return

        # Local RTSP mode: reuse frames from the recognition engine instead of
        # opening a second RTSP connection from the small lock notification.
        feed_url = ""
        frame_provider = None
        try:
            from services.local_recognition_engine import ENGINE

            def provide_lock_frame():
                frame_rgb = ENGINE.latest_frame
                if frame_rgb is None:
                    return None
                try:
                    frame_age = ENGINE.last_frame_age_seconds()
                except Exception:
                    frame_age = None
                if not ENGINE.stream_healthy() and (frame_age is None or frame_age > 15.0):
                    return None
                try:
                    match = getattr(ENGINE, "latest_match", None)
                    draw_overlay = getattr(self, "_draw_recognition_overlay_rgb", None)
                    if callable(draw_overlay):
                        frame_rgb = draw_overlay(frame_rgb.copy(), match)
                except Exception:
                    pass
                if cv2 is not None:
                    cv2_mod = cast(Any, cv2)
                    return cv2_mod.cvtColor(frame_rgb, cv2_mod.COLOR_RGB2BGR)
                return frame_rgb[:, :, ::-1].copy()

            frame_provider = provide_lock_frame

            # Do not start/connect RTSP before the popup is shown. On first app
            # run or bad DNS this can wait on FFmpeg/network startup and make the
            # lock notification feel delayed. Recognition startup is handled by
            # the local unlock session path; this popup only subscribes to frames.
        except Exception:
            frame_provider = None
            try:
                feed_url = str(getattr(self, "camera_feed_url", "") or "").strip()
            except Exception:
                feed_url = ""

        notification = SystemLockedNotification(
            compact_mode=self.compact_mode,
            video_feed_url=feed_url,
            frame_provider=frame_provider,
        )
        self.system_locked_notification = notification
        notification.show_at_bottom_right()

    def hide_system_locked_notification(self: Any):
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

    def keep_camera_connected_after_unlock(self: Any):
        """Unlock popup cleanup must not look like a camera disconnect."""
        try:
            from services.local_recognition_engine import ENGINE

            status = ENGINE.status()
            frame_age = status.get("last_frame_age_seconds")
            recent_frame = bool(ENGINE.latest_frame is not None and frame_age is not None and float(frame_age) <= 30.0)
            active = bool(
                status.get("recognition_running", False)
                or status.get("capture_running", False)
                or status.get("stream_healthy", False)
                or status.get("stream_recovering", False)
                or recent_frame
            )
            if not active:
                return

            self.pi_connection_checked = True
            self.pi_connected = True
            self._camera_user_stopped = False
            self._camera_manual_disconnected = False
            self._runtime_disconnect_candidate_since = 0.0
            self._camera_disconnect_grace_until = time.monotonic() + 60.0
            self._handling_pi_disconnect = False
            self._sas_heartbeat_failure_count = 0
            self.set_face_controls_connection_enabled(True)
            message = "Status: Connected" if status.get("stream_healthy", False) else "Status: Connected | camera feed recovering"
            self.set_pi_status_label(connected=True, message=message)
            self.update_pi_connect_ui_state(connected=True)
            if getattr(self, "current_top_tab", "") == "Face Recognition" and not getattr(self, "_camera_preview_running", False):
                self.start_camera_preview(force=True)
        except Exception as exc:
            try:
                self.append_system_log(f"Post-unlock camera state restore skipped: {exc}")
            except Exception:
                pass

    def _grant_access(self: Any, name=""):
        self.end_local_unlock_session("unlocked")
        self.runtime_lock_service.grant_access(self, name)
        # Treat a successful unlock as a fresh activity anchor so the system
        # does not instantly re-lock when there has been no physical input yet.
        self.mark_user_activity(reset_countdown=True)

    def _do_logout(self: Any):
        self.runtime_lock_service.lock_system(self)
        self.start_local_unlock_session("manual_lock")

    def start_timers(self: Any):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_time)
        self.clock_timer.start(1000)
        self.update_time()

        self.count_timer = QTimer(self)
        self.count_timer.timeout.connect(self.update_countdown)
        self.count_timer.start(1000)
        self.update_countdown(initial=True)

        # No recognition_result.json polling. Face unlock now arrives via the
        # local unlock API only.
        self.runtime_lock_service.apply_security_options(self)
        self.emergency_recovery_timer = QTimer(self)
        self.emergency_recovery_timer.timeout.connect(self.refresh_emergency_recovery_state)
        self.emergency_recovery_timer.start(500)

    def update_time(self: Any):
        if self.current_top_tab != "Dashboard":
            return
        now = QDateTime.currentDateTime()
        self.time_label.setText(now.toString("HH:mm:ss"))
        self.date_label.setText(now.toString("dddd, MMMM dd, yyyy").upper())

    def configure_local_unlock(self: Any, host: str, port: str = "5000", start: bool = False):
        """Configure the local unlock used for real-time face unlock."""
        try:
            self.local_unlock_service.configure(
                host,
                port or "5000",
                client_name=getattr(self, "sas_client_name", "Windows SAS"),
            )
            if start and str(host or "").strip():
                self.local_unlock_service.start()
        except Exception as e:
            self.append_system_log(f"Local unlock configure error: {e}")

    def stop_local_unlock(self: Any, reason: str = "stopped"):
        try:
            self.local_unlock_service.stop(reason)
        except Exception:
            pass

    def handle_local_unlock_connected(self: Any):
        self.append_system_log("Local unlock channel connected.")
        if getattr(self, "is_locked", False):
            if not getattr(self, "unlock_session_id", ""):
                self.start_local_unlock_session("reconnect_while_locked")
            else:
                self.local_unlock_service.send_lock_session_started(
                    self.unlock_session_id,
                    reason="reconnect_while_locked",
                )

    def handle_local_unlock_disconnected(self: Any, reason: str = "disconnected"):
        reason_text = str(reason or "disconnected")
        if getattr(self, "is_locked", False):
            self.append_system_log(f"Local unlock channel disconnected: {reason_text}")

        # Unexpected local unlock channel close means the local recognition channel is no longer usable.
        # Do not show this for intentional local stops such as manual Disconnect,
        # hostname editing, API-offline cleanup, or OneConnect takeover/lost.
        ignore_tokens = (
            "manual disconnect",
            "pi host edited",
            "oneconnect lost",
            "pi api offline",
            "stopped",
            "unlocked",
            "session ended",
        )
        if any(token in reason_text.lower() for token in ignore_tokens):
            return
        if getattr(self, "pi_connected", False):
            self.handle_pi_runtime_disconnect("Local unlock connection closed. Please check camera network/source.")

    def start_local_unlock_session(self: Any, reason: str = "locked"):
        """Open a fresh unlock session so stale local recognition events cannot unlock SAS."""
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return
        session_id = str(uuid.uuid4())
        self.unlock_session_id = session_id
        try:
            self._unlock_seen_events.clear()
        except Exception:
            self._unlock_seen_events = set()

        self.configure_local_unlock(self.pi_api_host, self.pi_api_port, start=True)
        sent = self.local_unlock_service.send_lock_session_started(session_id, reason=reason)
        if sent:
            self.append_system_log("Local unlock session started.")
        else:
            self.append_system_log("Local unlock session pending until local recognition reconnects.")

    def end_local_unlock_session(self: Any, reason: str = "unlocked"):
        session_id = str(getattr(self, "unlock_session_id", "") or "")
        if not session_id:
            return
        try:
            self.local_unlock_service.send_lock_session_ended(session_id, reason=reason)
        except Exception:
            pass
        self.unlock_session_id = ""

    def _parse_unlock_timestamp(self: Any, value):
        if not value:
            return None
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1]
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                pass
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    def handle_local_unlock_message(self: Any, message: dict):
        """Unlock SAS from a valid local recognition_result event."""
        try:
            if not isinstance(message, dict):
                return

            msg_type = str(message.get("type") or "").strip()
            if msg_type in ("connection_refused", "connection_replaced", "connection_closed"):
                reason = str(message.get("message") or "Camera connection was disconnected.")
                self.handle_oneconnect_connection_lost(reason, message.get("active_session"))
                return
            if msg_type in ("server_hello", "lock_session_ack", "pong"):
                return
            if msg_type != "recognition_result":
                return

            if not getattr(self, "is_locked", False):
                return

            active_session = str(getattr(self, "unlock_session_id", "") or "")
            event_session = str(message.get("lock_session_id") or "")
            if not active_session or event_session != active_session:
                self.append_system_log("Local unlock recognition ignored: stale or mismatched lock session.")
                return

            event_id = str(message.get("event_id") or "")
            if event_id:
                seen = getattr(self, "_unlock_seen_events", set())
                if event_id in seen:
                    return
                seen.add(event_id)
                self._unlock_seen_events = seen

            detected = bool(message.get("detected", True))
            ntid = message.get("ntid") or message.get("user_id") or message.get("user") or message.get("name")
            if not detected or not ntid:
                return

            try:
                confidence = float(str(message.get("confidence", 0)).replace("%", ""))
            except Exception:
                confidence = 0.0

            detected_time = self._parse_unlock_timestamp(
                message.get("occurred_at") or message.get("timestamp") or message.get("time")
            )
            if detected_time is None:
                self.append_system_log("Local unlock recognition ignored: invalid timestamp.")
                return

            age_seconds = (datetime.now() - detected_time).total_seconds()
            if age_seconds > SCAN_VALID_SECONDS:
                self.append_system_log("Local unlock recognition ignored: expired event.")
                return

            self._pending_auto_lock = False
            ntid_text = str(ntid or "").upper()
            self._grant_access(f"{ntid_text} ({confidence}%)")
            self.write_sas_log(
                "UNLOCKED",
                actor=ntid_text,
                details={
                    "Method": "FACE_RECOGNITION_LOCAL",
                    "Confidence": f"{confidence}%",
                    "Camera host": str(message.get("pi_id") or self.pi_api_host or "-").upper(),
                    "Event ID": event_id or "-",
                },
            )
            self.is_locked = False
            self.is_logged_in = True
            self.apply_lock_state()
            self.hide_system_locked_notification()
            self.keep_camera_connected_after_unlock()
            self.set_face_detected(False)
            self.mark_user_activity(reset_countdown=True)
            QTimer.singleShot(450, self.minimize_after_face_unlock)
        except Exception as e:
            self.append_system_log(f"Local unlock recognition handler error: {e}")

    def reset_countdown_after_manual_unlock(self: Any):
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

    def finish_auto_lock_after_ring(self: Any):
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
        self.start_local_unlock_session("inactivity_timeout")
        self.set_face_detected(False)
        self.append_system_log("Auto locked: keyboard and mouse inactive until countdown ended")

    def update_countdown(self: Any, initial=False):
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

        # Locked state stays at 00:00 until a valid local unlock recognition
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
