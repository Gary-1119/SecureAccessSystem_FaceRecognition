"""WebSocket recognition-event bridge for Windows SAS.

This module replaces the old SMB recognition_result.json delivery path for
workstation unlock.  SMB remains available for logs, user.json sync, backups,
import/export, and face-data transfers; recognition unlock events are delivered
in real time through /ws/sas.

Runtime dependency:
    pip install flask-sock

The module is safe to import when flask-sock is not installed.  In that case
HTTP API continues to work and /status reports websocket_available=False.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from flask_sock import Sock
except Exception:  # pragma: no cover - depends on Pi deployment packages
    Sock = None


PROTOCOL_VERSION = 1
CLIENT_QUEUE_LIMIT = 24
CLIENT_SEND_TIMEOUT_SECONDS = 1.5


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@dataclass
class SasWebSocketClient:
    ws: Any
    client_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    connected_at: float = field(default_factory=time.monotonic)
    lock_session_id: Optional[str] = None
    lock_active: bool = False
    outbound: "queue.Queue[Optional[Dict[str, Any]]]" = field(default_factory=lambda: queue.Queue(maxsize=CLIENT_QUEUE_LIMIT))
    closed: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set_lock_session(self, session_id: Optional[str], active: bool) -> None:
        with self.lock:
            self.lock_session_id = str(session_id or "").strip() or None
            self.lock_active = bool(active and self.lock_session_id)

    def get_lock_session(self) -> Optional[str]:
        with self.lock:
            if not self.lock_active:
                return None
            return self.lock_session_id

    def enqueue(self, payload: Dict[str, Any]) -> bool:
        if self.closed:
            return False
        try:
            self.outbound.put_nowait(payload)
            return True
        except queue.Full:
            # Drop one old item and keep the newest real-time event.  Unlock
            # events must be fresh; queueing old recognition messages is unsafe.
            try:
                self.outbound.get_nowait()
            except Exception:
                pass
            try:
                self.outbound.put_nowait(payload)
                return True
            except Exception:
                return False

    def close(self) -> None:
        self.closed = True
        try:
            self.outbound.put_nowait(None)
        except Exception:
            pass


class RecognitionWebSocketHub:
    def __init__(self) -> None:
        self._clients: Dict[str, SasWebSocketClient] = {}
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None
        self.last_event_at: Optional[str] = None

    @property
    def available(self) -> bool:
        return Sock is not None

    def active_client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def active_lock_session_count(self) -> int:
        with self._lock:
            return sum(1 for c in self._clients.values() if c.get_lock_session())

    def _add_client(self, client: SasWebSocketClient) -> None:
        with self._lock:
            self._clients[client.client_id] = client

    def _remove_client(self, client: SasWebSocketClient) -> None:
        client.close()
        with self._lock:
            self._clients.pop(client.client_id, None)

    def _sender_loop(self, client: SasWebSocketClient) -> None:
        while not client.closed:
            payload = client.outbound.get()
            if payload is None:
                break
            try:
                client.ws.send(_json_dumps(payload))
            except Exception as exc:
                self.last_error = str(exc)
                break
        self._remove_client(client)

    def handle_socket(self, ws: Any, gui_app: Any = None) -> None:
        client = SasWebSocketClient(ws=ws)
        self._add_client(client)

        threading.Thread(
            target=self._sender_loop,
            args=(client,),
            daemon=True,
            name=f"SASWebSocketSender-{client.client_id[:8]}",
        ).start()

        client.enqueue({
            "type": "server_hello",
            "protocol_version": PROTOCOL_VERSION,
            "client_id": client.client_id,
            "pi_id": socket.gethostname(),
            "websocket_role": "recognition_unlock",
            "time": _now_iso(),
        })

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    message = json.loads(raw) if isinstance(raw, str) else {}
                except Exception:
                    continue

                msg_type = str(message.get("type") or "").strip()
                if msg_type == "lock_session_started":
                    session_id = str(message.get("lock_session_id") or "").strip()
                    client.set_lock_session(session_id, bool(session_id))
                    client.enqueue({
                        "type": "lock_session_ack",
                        "protocol_version": PROTOCOL_VERSION,
                        "client_id": client.client_id,
                        "lock_session_id": session_id,
                        "pi_id": socket.gethostname(),
                        "time": _now_iso(),
                    })
                elif msg_type in ("lock_session_ended", "unlock_completed"):
                    ended_session = str(message.get("lock_session_id") or "").strip()
                    current = client.get_lock_session()
                    if not ended_session or ended_session == current:
                        client.set_lock_session(None, False)
                elif msg_type == "ping":
                    client.enqueue({
                        "type": "pong",
                        "protocol_version": PROTOCOL_VERSION,
                        "client_id": client.client_id,
                        "time": _now_iso(),
                    })
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            self._remove_client(client)

    def publish_recognition_result(self, data: Dict[str, Any]) -> int:
        """Queue a real-time recognition result to locked SAS clients only.

        Only positive detections are sent because SAS only needs an unlock event.
        Non-detected frames stay local and do not flood the websocket.
        """
        if not isinstance(data, dict) or not bool(data.get("detected")):
            return 0

        ntid = data.get("user_id") or data.get("ntid") or data.get("name")
        if not ntid:
            return 0

        try:
            confidence = float(str(data.get("confidence", 0)).replace("%", ""))
        except Exception:
            confidence = 0.0

        timestamp = str(data.get("timestamp") or _now_iso())
        base_payload = {
            "type": "recognition_result",
            "protocol_version": PROTOCOL_VERSION,
            "event_id": str(uuid.uuid4()),
            "pi_id": socket.gethostname(),
            "detected": True,
            "ntid": str(ntid).strip().lower(),
            "user_id": str(ntid).strip().lower(),
            "confidence": confidence,
            "occurred_at": timestamp,
            "timestamp": timestamp,
            "source": "websocket",
        }

        sent = 0
        with self._lock:
            clients = list(self._clients.values())

        for client in clients:
            session_id = client.get_lock_session()
            if not session_id:
                continue
            payload = dict(base_payload)
            payload["lock_session_id"] = session_id
            if client.enqueue(payload):
                sent += 1

        if sent:
            self.last_event_at = timestamp
        return sent


recognition_ws_hub = RecognitionWebSocketHub()


def publish_recognition_result(data: Dict[str, Any]) -> int:
    return recognition_ws_hub.publish_recognition_result(data)


def attach_websocket_routes(api_app: Any, gui_app: Any = None) -> bool:
    """Attach /ws/sas to the Flask API app when flask-sock is available."""
    if Sock is None:
        try:
            if gui_app is not None:
                gui_app._api_last_error = "WebSocket unavailable: install flask-sock on the Pi."
        except Exception:
            pass
        return False

    sock = Sock(api_app)

    @sock.route("/ws/sas")
    def sas_socket(ws):  # pragma: no cover - exercised on Pi runtime
        recognition_ws_hub.handle_socket(ws, gui_app=gui_app)

    return True
