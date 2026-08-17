"""WebSocket recognition-event bridge for Windows SAS.

This module replaces the old SMB recognition_result.json delivery path for
workstation unlock.  SMB remains available for logs, user.json sync, backups,
import/export, and face-data transfers; recognition unlock events are delivered
in real time through /ws/sas.

v106 One-Pi Session adds a single-SAS ownership layer:
- only one SAS workstation can own/control one Pi at a time;
- a second SAS receives an already-connected response instead of silently
  sharing the same Pi recognition stream;
- a force takeover can disconnect the previous SAS and allow the new one.

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
from typing import Any, Dict, Optional, Tuple

try:
    from flask import request
except Exception:  # pragma: no cover - only needed inside Flask runtime
    request = None

try:
    from flask_sock import Sock
except Exception:  # pragma: no cover - depends on Pi deployment packages
    Sock = None


PROTOCOL_VERSION = 1
CLIENT_QUEUE_LIMIT = 24
CLIENT_SEND_TIMEOUT_SECONDS = 1.5
SAS_SESSION_TIMEOUT_SECONDS = 90
UNLOCK_CONFIDENCE_MIN_PERCENT = 65.0


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _clean_text(value: Any, default: str = "") -> str:
    return str(value or default).strip()


@dataclass
class SasWebSocketClient:
    ws: Any
    client_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    connected_at: float = field(default_factory=time.monotonic)
    sas_client_id: str = ""
    sas_client_name: str = ""
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
        self._active_session: Optional[Dict[str, Any]] = None
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

    def _session_is_stale_locked(self) -> bool:
        if not self._active_session:
            return False
        last_seen = float(self._active_session.get("last_seen_monotonic") or 0.0)
        return bool(last_seen and (time.monotonic() - last_seen) > SAS_SESSION_TIMEOUT_SECONDS)

    def _session_snapshot_locked(self) -> Optional[Dict[str, Any]]:
        if not self._active_session:
            return None
        item = dict(self._active_session)
        item.pop("last_seen_monotonic", None)
        item["timeout_seconds"] = SAS_SESSION_TIMEOUT_SECONDS
        return item

    def active_session_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._session_is_stale_locked():
                self._active_session = None
            return self._session_snapshot_locked()

    def connect_sas(
        self,
        client_id: str,
        client_name: str = "",
        client_user: str = "",
        client_host: str = "",
        force: bool = False,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Reserve this Pi for one SAS workstation.

        Returns (ok, message, active_session_snapshot).  When another SAS owns
        the Pi, ok is False unless force=True.
        """
        client_id = _clean_text(client_id)
        if not client_id:
            return False, "SAS client ID is required.", self.active_session_snapshot()

        old_clients_to_close = []
        with self._lock:
            if self._session_is_stale_locked():
                self._active_session = None

            current = self._active_session
            if current and current.get("client_id") != client_id and not force:
                return (
                    False,
                    "This Pi is already connected with another SAS device.",
                    self._session_snapshot_locked(),
                )

            if current and current.get("client_id") != client_id and force:
                old_client_id = str(current.get("client_id") or "")
                for ws_client in self._clients.values():
                    if ws_client.sas_client_id == old_client_id:
                        old_clients_to_close.append(ws_client)

            now = time.monotonic()
            self._active_session = {
                "client_id": client_id,
                "client_name": _clean_text(client_name, "Windows SAS"),
                "client_user": _clean_text(client_user),
                "client_host": _clean_text(client_host),
                "connected_at": _now_iso(),
                "last_seen": _now_iso(),
                "last_seen_monotonic": now,
                "forced_takeover": bool(force and current and current.get("client_id") != client_id),
                "websocket_client_id": None,
            }
            snapshot = self._session_snapshot_locked()

        for old_client in old_clients_to_close:
            try:
                old_client.enqueue({
                    "type": "connection_replaced",
                    "protocol_version": PROTOCOL_VERSION,
                    "message": "This Pi connection was taken over by another SAS device.",
                    "pi_id": socket.gethostname(),
                    "time": _now_iso(),
                })
                old_client.close()
            except Exception:
                pass

        return True, "Pi connection reserved for this SAS device.", snapshot

    def disconnect_sas(self, client_id: str = "", force: bool = False) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        client_id = _clean_text(client_id)
        clients_to_close = []
        with self._lock:
            current = self._active_session
            if not current:
                return True, "No active SAS connection.", None
            if not force and client_id and current.get("client_id") != client_id:
                return False, "This SAS device does not own the active Pi connection.", self._session_snapshot_locked()
            if not force and not client_id:
                return False, "SAS client ID is required to disconnect.", self._session_snapshot_locked()

            old_client_id = str(current.get("client_id") or "")
            for ws_client in self._clients.values():
                if ws_client.sas_client_id == old_client_id:
                    clients_to_close.append(ws_client)
            self._active_session = None

        for ws_client in clients_to_close:
            try:
                ws_client.enqueue({
                    "type": "connection_closed",
                    "protocol_version": PROTOCOL_VERSION,
                    "message": "Pi connection was disconnected.",
                    "pi_id": socket.gethostname(),
                    "time": _now_iso(),
                })
                ws_client.close()
            except Exception:
                pass

        return True, "Pi connection disconnected.", None

    def heartbeat_sas(self, client_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        client_id = _clean_text(client_id)
        with self._lock:
            if self._session_is_stale_locked():
                self._active_session = None
            current = self._active_session
            if not current:
                return False, "No active SAS connection.", None
            if current.get("client_id") != client_id:
                return False, "This Pi is connected with another SAS device.", self._session_snapshot_locked()
            current["last_seen"] = _now_iso()
            current["last_seen_monotonic"] = time.monotonic()
            return True, "Heartbeat accepted.", self._session_snapshot_locked()

    def _add_client(self, client: SasWebSocketClient) -> None:
        with self._lock:
            self._clients[client.client_id] = client

    def _remove_client(self, client: SasWebSocketClient) -> None:
        client.close()
        with self._lock:
            self._clients.pop(client.client_id, None)
            current = self._active_session
            if (
                current
                and client.sas_client_id
                and current.get("client_id") == client.sas_client_id
                and current.get("websocket_client_id") == client.client_id
            ):
                # If the owning SAS window closes or the WebSocket drops, release
                # this Pi so another SAS is not blocked forever.
                self._active_session = None

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

    def _accept_websocket_client(self, client: SasWebSocketClient, sas_client_id: str, client_name: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        sas_client_id = _clean_text(sas_client_id)
        client_name = _clean_text(client_name, "Windows SAS")
        if not sas_client_id:
            return False, "SAS client ID is missing from the WebSocket request.", self.active_session_snapshot()

        ok, message, snapshot = self.connect_sas(sas_client_id, client_name=client_name, force=False)
        if not ok:
            return ok, message, snapshot

        with self._lock:
            if self._active_session and self._active_session.get("client_id") == sas_client_id:
                self._active_session["websocket_client_id"] = client.client_id
                self._active_session["last_seen"] = _now_iso()
                self._active_session["last_seen_monotonic"] = time.monotonic()
                snapshot = self._session_snapshot_locked()
        client.sas_client_id = sas_client_id
        client.sas_client_name = client_name
        return True, message, snapshot

    def handle_socket(self, ws: Any, gui_app: Any = None) -> None:
        client = SasWebSocketClient(ws=ws)

        sas_client_id = ""
        sas_client_name = "Windows SAS"
        try:
            if request is not None:
                sas_client_id = _clean_text(request.args.get("client_id"))
                sas_client_name = _clean_text(request.args.get("client_name"), sas_client_name)
        except Exception:
            pass

        accepted, accept_message, active_session = self._accept_websocket_client(client, sas_client_id, sas_client_name)
        if not accepted:
            try:
                ws.send(_json_dumps({
                    "type": "connection_refused",
                    "protocol_version": PROTOCOL_VERSION,
                    "reason": "already_connected",
                    "message": accept_message,
                    "active_session": active_session or {},
                    "pi_id": socket.gethostname(),
                    "time": _now_iso(),
                }))
            except Exception:
                pass
            try:
                ws.close()
            except Exception:
                pass
            return

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
            "sas_client_id": sas_client_id,
            "pi_id": socket.gethostname(),
            "websocket_role": "recognition_unlock",
            "oneconnect": True,
            "active_session": active_session or {},
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
                    self.heartbeat_sas(client.sas_client_id)
                    client.enqueue({
                        "type": "lock_session_ack",
                        "protocol_version": PROTOCOL_VERSION,
                        "client_id": client.client_id,
                        "sas_client_id": client.sas_client_id,
                        "lock_session_id": session_id,
                        "pi_id": socket.gethostname(),
                        "time": _now_iso(),
                    })
                elif msg_type in ("lock_session_ended", "unlock_completed"):
                    ended_session = str(message.get("lock_session_id") or "").strip()
                    current = client.get_lock_session()
                    if not ended_session or ended_session == current:
                        client.set_lock_session(None, False)
                    self.heartbeat_sas(client.sas_client_id)
                elif msg_type == "ping":
                    ok, _, snapshot = self.heartbeat_sas(client.sas_client_id)
                    client.enqueue({
                        "type": "pong",
                        "protocol_version": PROTOCOL_VERSION,
                        "client_id": client.client_id,
                        "sas_client_id": client.sas_client_id,
                        "oneconnect_ok": bool(ok),
                        "active_session": snapshot or {},
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
        if confidence < UNLOCK_CONFIDENCE_MIN_PERCENT:
            return 0

        timestamp = str(data.get("timestamp") or _now_iso())
        display_name = str(data.get("display_name") or data.get("name") or ntid or "").strip()
        base_payload = {
            "type": "recognition_result",
            "protocol_version": PROTOCOL_VERSION,
            "event_id": str(uuid.uuid4()),
            "pi_id": socket.gethostname(),
            "detected": True,
            "ntid": str(ntid).strip().lower(),
            "user_id": str(ntid).strip().lower(),
            "name": display_name,
            "display_name": display_name,
            "confidence": confidence,
            "occurred_at": timestamp,
            "timestamp": timestamp,
            "source": "websocket",
        }

        sent = 0
        with self._lock:
            if self._session_is_stale_locked():
                self._active_session = None
            clients = list(self._clients.values())
            active_client_id = str((self._active_session or {}).get("client_id") or "")

        for client in clients:
            # Only the owning SAS is allowed to receive unlock events.
            if active_client_id and client.sas_client_id != active_client_id:
                continue
            session_id = client.get_lock_session()
            if not session_id:
                continue
            payload = dict(base_payload)
            payload["lock_session_id"] = session_id
            payload["sas_client_id"] = client.sas_client_id
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
