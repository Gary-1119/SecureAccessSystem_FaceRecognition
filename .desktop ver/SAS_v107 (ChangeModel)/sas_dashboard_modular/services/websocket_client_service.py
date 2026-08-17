"""Qt WebSocket client for real-time Pi recognition unlock events.

Windows SAS uses this service to replace SMB recognition_result.json polling.
SMB remains used for logs, import/export, backups, and other file transfers.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

try:
    from PySide6.QtWebSockets import QWebSocket
except Exception:  # pragma: no cover - depends on local PySide6 modules
    QWebSocket = None


class WebSocketRecognitionClient(QObject):
    connected = Signal()
    disconnected = Signal(str)
    message_received = Signal(dict)
    status_changed = Signal(str)

    def __init__(self, debug_callback=None, parent=None):
        super().__init__(parent)
        self.debug_callback = debug_callback
        self.host = ""
        self.port = "5000"
        self.url = ""
        self._closing = False
        self._manual_disconnect = False
        self._last_connect_attempt = 0.0
        self._reconnect_delay_ms = 1500
        self._max_reconnect_delay_ms = 15000
        self._socket: Optional[Any] = None
        self._connected = False
        self.client_id = ""
        self.client_name = ""

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self.send_ping)
        self._ping_timer.start(15000)

        self._create_socket()

    @property
    def available(self) -> bool:
        return QWebSocket is not None

    @property
    def is_connected(self) -> bool:
        return bool(self._connected)

    def configure(self, host: str, port: str = "5000", client_id: str = "", client_name: str = "") -> None:
        self.host = str(host or "").strip()
        self.port = str(port or "5000").strip() or "5000"
        self.client_id = str(client_id or "").strip()
        self.client_name = str(client_name or "Windows SAS").strip()

        def with_identity(url: str) -> str:
            if not self.client_id:
                return url
            sep = "&" if "?" in url else "?"
            return (
                f"{url}{sep}client_id={quote(self.client_id, safe='')}"
                f"&client_name={quote(self.client_name, safe='')}"
            )

        if self.host.startswith("http://"):
            base = self.host.replace("http://", "ws://", 1).rstrip("/")
            self.url = with_identity(f"{base}/ws/sas")
        elif self.host.startswith("https://"):
            base = self.host.replace("https://", "wss://", 1).rstrip("/")
            self.url = with_identity(f"{base}/ws/sas")
        elif self.host.startswith("ws://") or self.host.startswith("wss://"):
            base = self.host.rstrip("/")
            raw_url = base if base.endswith("/ws/sas") else f"{base}/ws/sas"
            self.url = with_identity(raw_url)
        elif self.host:
            self.url = with_identity(f"ws://{self.host}:{self.port}/ws/sas")
        else:
            self.url = ""

    def start(self) -> None:
        if not self.available:
            self._emit_status("WebSocket unavailable: PySide6.QtWebSockets is missing.")
            return
        if not self.url:
            self._emit_status("WebSocket not started: Pi host is blank.")
            return
        self._manual_disconnect = False
        self._open_socket()

    def reconnect_now(self) -> None:
        self._manual_disconnect = False
        self._reconnect_delay_ms = 1500
        self._close_socket()
        self._open_socket()

    def stop(self, reason: str = "stopped") -> None:
        self._manual_disconnect = True
        try:
            self._reconnect_timer.stop()
        except Exception:
            pass
        self._close_socket()
        self._connected = False
        self.disconnected.emit(reason)

    def _create_socket(self) -> None:
        if QWebSocket is None:
            self._socket = None
            return
        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(lambda: self._on_disconnected("disconnected"))
        self._socket.textMessageReceived.connect(self._on_text_message)
        try:
            self._socket.errorOccurred.connect(lambda *_: self._on_disconnected("socket error"))
        except Exception:
            try:
                self._socket.error.connect(lambda *_: self._on_disconnected("socket error"))
            except Exception:
                pass

    def _open_socket(self) -> None:
        if self._manual_disconnect or not self.available or not self.url:
            return
        if self._socket is None:
            self._create_socket()
        socket = self._socket
        if socket is None:
            self._emit_status("WebSocket connect failed: socket could not be created.")
            self._schedule_reconnect()
            return
        try:
            self._last_connect_attempt = time.monotonic()
            self._emit_status(f"WebSocket connecting: {self.url}")
            socket.open(QUrl(self.url))
        except Exception as exc:
            self._emit_status(f"WebSocket connect failed: {exc}")
            self._schedule_reconnect()

    def _close_socket(self) -> None:
        try:
            if self._socket is not None:
                self._socket.close()
        except Exception:
            pass

    def _on_connected(self) -> None:
        self._connected = True
        self._reconnect_delay_ms = 1500
        self._emit_status("WebSocket connected.")
        self.connected.emit()
        self.send_json({
            "type": "hello",
            "client": "Windows SAS",
            "client_id": self.client_id,
            "client_name": self.client_name,
            "role": "recognition_unlock",
        })

    def _on_disconnected(self, reason: str = "disconnected") -> None:
        was_connected = self._connected
        self._connected = False
        if was_connected:
            self.disconnected.emit(reason)
        if not self._manual_disconnect:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._manual_disconnect or not self.url:
            return
        if self._reconnect_timer.isActive():
            return
        delay = self._reconnect_delay_ms
        self._reconnect_delay_ms = min(self._reconnect_delay_ms * 2, self._max_reconnect_delay_ms)
        self._emit_status(f"WebSocket reconnect scheduled in {delay // 1000}s.")
        self._reconnect_timer.start(delay)

    def _try_reconnect(self) -> None:
        if not self._manual_disconnect:
            self._open_socket()

    def _on_text_message(self, text: str) -> None:
        try:
            data = json.loads(text)
        except Exception:
            return
        if isinstance(data, dict):
            self.message_received.emit(data)

    def send_json(self, payload: Dict[str, Any]) -> bool:
        if not self._connected or self._socket is None:
            return False
        try:
            self._socket.sendTextMessage(json.dumps(payload, separators=(",", ":")))
            return True
        except Exception as exc:
            self._emit_status(f"WebSocket send failed: {exc}")
            return False

    def send_lock_session_started(self, lock_session_id: str, reason: str = "locked") -> bool:
        return self.send_json({
            "type": "lock_session_started",
            "lock_session_id": str(lock_session_id or ""),
            "reason": str(reason or "locked"),
            "client_id": self.client_id,
            "client_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    def send_lock_session_ended(self, lock_session_id: str, reason: str = "unlocked") -> bool:
        return self.send_json({
            "type": "lock_session_ended",
            "lock_session_id": str(lock_session_id or ""),
            "reason": str(reason or "unlocked"),
            "client_id": self.client_id,
            "client_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    def send_ping(self) -> None:
        if self._connected:
            self.send_json({
                "type": "ping",
                "client_id": self.client_id,
                "client_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    def _emit_status(self, message: str) -> None:
        try:
            if self.debug_callback:
                self.debug_callback(message)
        except Exception:
            pass
        self.status_changed.emit(str(message))
