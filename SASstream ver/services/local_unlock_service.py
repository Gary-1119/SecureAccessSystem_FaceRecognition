"""Local Qt signal bridge for real-time face unlock events.

The recognition engine runs on this PC. In the
RTSP-only version this service keeps
the dashboard lock-screen signals while routing events in-process.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from services.local_recognition_engine import ENGINE


class LocalUnlockService(QObject):
    connected = Signal()
    disconnected = Signal(str)
    message_received = Signal(dict)
    status_changed = Signal(str)

    def __init__(self, debug_callback=None, parent=None):
        super().__init__(parent)
        self.debug_callback = debug_callback
        self.host = ""
        self.port = "5000"
        self.client_name = "Windows SAS"
        self._connected = False

    @property
    def available(self) -> bool:
        return True

    @property
    def is_connected(self) -> bool:
        return bool(self._connected)

    def configure(self, host: str, port: str = "5000", client_name: str = "") -> None:
        self.host = str(host or "").strip()
        self.port = str(port or "5000").strip() or "5000"
        self.client_name = str(client_name or "Windows SAS").strip()
        if self.host:
            ENGINE.configure(self.host)

    def start(self) -> None:
        if not self.host:
            self._emit_status("Local unlock channel not started: camera hostname is blank.")
            return
        ENGINE.set_unlock_callback(self._emit_recognition_message)
        if not self._connected:
            self._connected = True
            self._emit_status("Local unlock channel connected.")
            self.connected.emit()

    def reconnect_now(self) -> None:
        self.start()

    def stop(self, reason: str = "stopped") -> None:
        was_connected = self._connected
        self._connected = False
        if was_connected:
            self.disconnected.emit(reason)
        self._emit_status(f"Local unlock channel stopped: {reason}")

    def send_json(self, payload: dict) -> bool:
        return True

    def send_lock_session_started(self, lock_session_id: str, reason: str = "locked") -> bool:
        ENGINE.set_lock_session(lock_session_id)
        self.start()
        try:
            if not ENGINE.running:
                ENGINE.start()
        except Exception as exc:
            self._emit_status(f"Local recognition start failed for lock session: {exc}")
            return False
        self._emit_status(f"Local lock session started: {reason}")
        return True

    def send_lock_session_ended(self, lock_session_id: str, reason: str = "unlocked") -> bool:
        ENGINE.clear_lock_session()
        self._emit_status(f"Local lock session ended: {reason}")
        return True

    def send_ping(self) -> None:
        if self._connected:
            self._emit_status(f"Local unlock heartbeat {time.strftime('%H:%M:%S')}")

    def _emit_recognition_message(self, payload: dict) -> None:
        try:
            self.message_received.emit(dict(payload or {}))
        except Exception as exc:
            self._emit_status(f"Local unlock event failed: {exc}")

    def _emit_status(self, message: str) -> None:
        try:
            if self.debug_callback:
                self.debug_callback(message)
        except Exception:
            pass
        self.status_changed.emit(str(message))

