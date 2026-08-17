from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class WebSocketRuntimeControllerMixin(DashboardMixinBase):
    FACE_UNLOCK_MIN_CONFIDENCE_PERCENT = 65.0

    def configure_recognition_websocket(self, host: str, port: str = "5000", start: bool = False):
        """Configure the Pi WebSocket used for real-time face unlock."""
        try:
            self.websocket_client_service.configure(
                host,
                port or "5000",
                client_id=getattr(self, "sas_client_id", ""),
                client_name=getattr(self, "sas_client_name", "Windows SAS"),
            )
            if start and str(host or "").strip():
                self.websocket_client_service.start()
        except Exception as e:
            self.append_system_log(f"WebSocket configure error: {e}")


    def stop_recognition_websocket(self, reason: str = "stopped"):
        try:
            self.websocket_client_service.stop(reason)
        except Exception:
            pass


    def handle_websocket_connected(self):
        self.append_system_log("WebSocket unlock channel connected.")
        if getattr(self, "is_locked", False):
            try:
                self.refresh_locked_notification_camera()
            except Exception:
                pass
            if not getattr(self, "websocket_lock_session_id", ""):
                self.start_websocket_lock_session("reconnect_while_locked")
            else:
                self.websocket_client_service.send_lock_session_started(
                    self.websocket_lock_session_id,
                    reason="reconnect_while_locked",
                )


    def handle_websocket_disconnected(self, reason: str = "disconnected"):
        reason_text = str(reason or "disconnected")
        if getattr(self, "is_locked", False):
            self.append_system_log(f"WebSocket unlock channel disconnected: {reason_text}")

        # Unexpected WebSocket close means the Pi/API channel is no longer usable.
        # Do not show this for intentional local stops such as manual Disconnect,
        # hostname editing, API-offline cleanup, or OneConnect takeover/lost.
        ignore_tokens = (
            "manual disconnect",
            "pi host edited",
            "oneconnect lost",
            "pi api offline",
            "stopped",
        )
        if any(token in reason_text.lower() for token in ignore_tokens):
            return
        if getattr(self, "pi_connected", False):
            self.handle_pi_runtime_disconnect("Pi WebSocket connection closed. Please check Pi power/network.")


    def start_websocket_lock_session(self, reason: str = "locked"):
        """Open a fresh unlock session so stale Pi events cannot unlock SAS."""
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return
        session_id = str(uuid.uuid4())
        self.websocket_lock_session_id = session_id
        try:
            self._websocket_seen_events.clear()
        except Exception:
            self._websocket_seen_events = set()

        self.configure_recognition_websocket(self.pi_api_host, self.pi_api_port, start=True)
        sent = self.websocket_client_service.send_lock_session_started(session_id, reason=reason)
        if sent:
            self.append_system_log("WebSocket lock session started.")
        else:
            self.append_system_log("WebSocket lock session pending until Pi reconnects.")


    def end_websocket_lock_session(self, reason: str = "unlocked"):
        session_id = str(getattr(self, "websocket_lock_session_id", "") or "")
        if not session_id:
            return
        try:
            self.websocket_client_service.send_lock_session_ended(session_id, reason=reason)
        except Exception:
            pass
        self.websocket_lock_session_id = ""


    def _parse_websocket_timestamp(self, value):
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


    def handle_websocket_recognition_message(self, message: dict):
        """Unlock SAS from a valid Pi /ws/sas recognition_result event."""
        try:
            if not isinstance(message, dict):
                return

            msg_type = str(message.get("type") or "").strip()
            if msg_type in ("connection_refused", "connection_replaced", "connection_closed"):
                reason = str(message.get("message") or "Pi connection was disconnected.")
                self.handle_oneconnect_connection_lost(reason, message.get("active_session"))
                return
            if msg_type in ("server_hello", "lock_session_ack", "pong"):
                return
            if msg_type != "recognition_result":
                return

            if not getattr(self, "is_locked", False):
                return

            active_session = str(getattr(self, "websocket_lock_session_id", "") or "")
            event_session = str(message.get("lock_session_id") or "")
            if not active_session or event_session != active_session:
                self.append_system_log("WebSocket recognition ignored: stale or mismatched lock session.")
                return

            event_id = str(message.get("event_id") or "")
            if event_id:
                seen = getattr(self, "_websocket_seen_events", set())
                if event_id in seen:
                    return
                seen.add(event_id)
                self._websocket_seen_events = seen

            detected = bool(message.get("detected", True))
            ntid = message.get("ntid") or message.get("user_id") or message.get("user") or message.get("name")
            if not detected or not ntid:
                return

            try:
                confidence = float(str(message.get("confidence", 0)).replace("%", ""))
            except Exception:
                confidence = 0.0
            if confidence < self.FACE_UNLOCK_MIN_CONFIDENCE_PERCENT:
                self.append_system_log(
                    f"WebSocket recognition ignored: confidence {confidence}% below "
                    f"{self.FACE_UNLOCK_MIN_CONFIDENCE_PERCENT}%."
                )
                return

            detected_time = self._parse_websocket_timestamp(
                message.get("occurred_at") or message.get("timestamp") or message.get("time")
            )
            if detected_time is None:
                self.append_system_log("WebSocket recognition ignored: invalid timestamp.")
                return

            age_seconds = (datetime.now() - detected_time).total_seconds()
            if age_seconds > SCAN_VALID_SECONDS:
                self.append_system_log("WebSocket recognition ignored: expired event.")
                return

            self._pending_auto_lock = False
            ntid_text = str(ntid or "").upper()
            self._grant_access(f"{ntid_text} ({confidence}%)")
            self.write_sas_log(
                "UNLOCKED",
                actor=ntid_text,
                details={
                    "Method": "FACE_RECOGNITION_WEBSOCKET",
                    "Confidence": f"{confidence}%",
                    "Pi host": str(message.get("pi_id") or self.pi_api_host or "-").upper(),
                    "Event ID": event_id or "-",
                },
            )
            self.is_locked = False
            self.is_logged_in = True
            self.apply_lock_state()
            self.hide_system_locked_notification()
            self.set_face_detected(False)
            self.mark_user_activity(reset_countdown=True)
            QTimer.singleShot(450, self.minimize_after_face_unlock)
        except Exception as e:
            self.append_system_log(f"WebSocket recognition handler error: {e}")

