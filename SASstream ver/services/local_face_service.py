from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List

from services.local_recognition_engine import ENGINE, FACE_DATA_DIR


class LocalFaceService:
    """Local recognition service used by the dashboard.

    Dashboard actions are routed to the PC-local recognition engine. In this
    RTSP-only version no external camera API server is required.
    """

    def __init__(self, host: str, port: str, debug_callback=None):
        self.host = str(host or "").strip()
        self.port = str(port or "5000").strip() or "5000"
        self.base_url = f"local://{self.host}" if self.host else "local://"
        self.debug_callback = debug_callback
        self.camera_rotation = 0
        self._stream_unhealthy_since = 0.0
        if self.host:
            ENGINE.configure(self.host)

    def debug(self, message: str) -> None:
        if self.debug_callback:
            self.debug_callback(message)
        else:
            print("[LOCAL FACE]", message)

    def configure(self, host: str, port: str = "5000") -> None:
        self.host = str(host or "").strip()
        self.port = str(port or "5000").strip() or "5000"
        self.base_url = f"local://{self.host}" if self.host else "local://"
        if self.host:
            ENGINE.configure(self.host)

    def rtsp_url(self) -> str:
        return ENGINE.rtsp_url(self.host) if self.host else ""

    def request(self, method: str, endpoint: str, payload=None, timeout=10):
        payload = payload or {}
        verb = str(method or "GET").upper()
        endpoint = "/" + str(endpoint or "").lstrip("/")
        self.debug(f"{verb} {endpoint} -> local recognition engine")

        if endpoint == "/status":
            data = ENGINE.status()
            data["user_records"] = data.get("users", [])
            data["users"] = data.get("user_count", 0)
            return data
        if endpoint == "/settings":
            return self._settings(verb, payload)
        if endpoint == "/users":
            return {"ok": True, "users": ENGINE.store.list_users()}
        if endpoint == "/logs":
            return {"ok": True, "logs": self._read_local_logs()}

        if endpoint == "/start-recognition":
            started_at = time.monotonic()
            self.debug(f"START_RECOGNITION_BEGIN host={self.host}")
            fresh_after = time.time()
            result = ENGINE.start()
            self.debug(f"START_RECOGNITION_ENGINE_STARTED host={self.host} elapsed={time.monotonic() - started_at:.2f}s")
            wait_timeout = max(4.0, min(float(timeout or 10), 12.0))
            self._wait_for_frame(wait_timeout, fresh_after=fresh_after)
            status = ENGINE.status()
            self.debug(
                "START_RECOGNITION_FRAME_STABLE "
                f"host={self.host} elapsed={time.monotonic() - started_at:.2f}s "
                f"state={status.get('connection_state')} healthy={status.get('stream_healthy')}"
            )
            status["message"] = "Local RTSP recognition started and stream is live."
            return {**result, **status}
        if endpoint in ("/stop-recognition", "/stop"):
            return ENGINE.stop()
        if endpoint == "/capture-user":
            return self._capture_user(payload, timeout=timeout)
        if endpoint == "/delete-user":
            user_id = payload.get("user_id") or payload.get("employee_id") or payload.get("ntid")
            return ENGINE.delete_user(str(user_id or ""))

        if endpoint == "/face-data/export":
            return self._export_face_data(payload)
        if endpoint == "/face-data/import":
            zip_path = payload.get("zip_path") or payload.get("path")
            return self._import_face_data(str(zip_path or ""))
        if endpoint == "/face-data/backups":
            return ENGINE.list_face_backups()
        if endpoint == "/face-data/restore-backup":
            zip_path = payload.get("zip_path") or payload.get("path")
            return ENGINE.restore_face_backup(str(zip_path or ""))
        if endpoint == "/face-data/delete-backup":
            zip_path = payload.get("zip_path") or payload.get("path")
            return ENGINE.delete_face_backup(str(zip_path or ""))
        if endpoint == "/face-data/list-server-zips":
            return self._list_server_zips(payload)

        raise RuntimeError(f"Local face service does not support endpoint: {endpoint}")

    def _capture_user(self, payload: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
        display_name = str(
            payload.get("display_name")
            or payload.get("name")
            or payload.get("user_name")
            or payload.get("user_id")
            or ""
        ).strip()
        employee_id = str(
            payload.get("employee_id")
            or payload.get("ntid")
            or payload.get("user_id")
            or ""
        ).strip()
        if not employee_id:
            raise RuntimeError("Employee ID is required.")
        if not display_name:
            display_name = employee_id

        if not ENGINE.running:
            ENGINE.start()
        self._wait_for_frame(max(4.0, min(float(timeout or 10), 12.0)))

        before = ENGINE.store.find_by_employee_id(employee_id)
        before_count = int(before.sample_count) if before else 0
        result = ENGINE.register_current_face(display_name, employee_id)
        user = result.get("user", {})
        after_count = int(user.get("sample_count", before_count))
        added = max(after_count - before_count, 0)
        return {
            "ok": True,
            "message": f"Registered {display_name} ({employee_id}).",
            "user": user,
            "photos": after_count,
            "frames": after_count,
            "captured": added,
            "manual_capture_count": after_count,
        }

    def _wait_for_frame(self, timeout_seconds: float, fresh_after: float | None = None) -> None:
        start = time.monotonic()
        self.debug(f"WAIT_FRAME_BEGIN host={self.host} timeout={timeout_seconds:.1f}s")
        stable_since: float | None = None
        last_seen_frame_time = 0.0
        frame_updates = 0
        min_stable_seconds = 2.0
        min_frame_updates = 3
        last_status_check = 0.0
        open_failed_since = 0.0

        while time.monotonic() - start < timeout_seconds:
            frame_time = float(ENGINE.last_frame_at or 0.0)
            fresh_enough = fresh_after is None or frame_time >= fresh_after
            healthy = bool(ENGINE.latest_frame is not None and fresh_enough and ENGINE.stream_healthy())

            if healthy:
                now = time.monotonic()
                if frame_time > last_seen_frame_time:
                    last_seen_frame_time = frame_time
                    frame_updates += 1
                if stable_since is None:
                    stable_since = now
                if now - stable_since >= min_stable_seconds and frame_updates >= min_frame_updates:
                    self.debug(
                        f"WAIT_FRAME_READY host={self.host} elapsed={now - start:.2f}s "
                        f"stable={now - stable_since:.2f}s frames={frame_updates}"
                    )
                    return
            else:
                stable_since = None
                frame_updates = 0
                now = time.monotonic()
                if now - last_status_check >= 0.5:
                    last_status_check = now
                    status = ENGINE.status()
                    resolve_error = str(status.get("resolve_error") or "").strip()
                    state = str(status.get("connection_state") or "unknown").strip()
                    error = str(status.get("last_error") or "waiting for fresh frame").strip()
                    if resolve_error and now - start >= 1.0:
                        self.debug(f"WAIT_FRAME_DNS_FAILED host={self.host} elapsed={now - start:.2f}s error={resolve_error}")
                        host = str(status.get("host") or ENGINE.host or "").strip()
                        raise RuntimeError(
                            f"No fresh RTSP frame is available from {host} ({resolve_error}). "
                            f"State={state}; Error={error}"
                        )

                    if state in ("disconnected", "error") and "Could not open RTSP stream" in error:
                        if open_failed_since <= 0.0:
                            open_failed_since = now
                        if now - open_failed_since >= 2.0:
                            host = str(status.get("host") or ENGINE.host or "").strip()
                            self.debug(
                                f"WAIT_FRAME_OPEN_FAILED host={host} elapsed={now - start:.2f}s "
                                f"state={state} error={error}"
                            )
                            raise RuntimeError(
                                f"RTSP stream is not available from {host}. "
                                f"State={state}; Error={error}. "
                                "The camera responded, but the configured RTSP stream path may not be published yet."
                            )
                    else:
                        open_failed_since = 0.0

            time.sleep(0.05)

        status = ENGINE.status()
        host = str(status.get("host") or ENGINE.host or "").strip()
        resolved_ip = str(status.get("resolved_ip") or "").strip()
        resolve_error = str(status.get("resolve_error") or "").strip()
        state = str(status.get("connection_state") or "unknown").strip()
        error = str(status.get("last_error") or "waiting for fresh frame").strip()
        address = f" ({resolved_ip})" if resolved_ip else (f" ({resolve_error})" if resolve_error else "")
        self.debug(
            f"WAIT_FRAME_TIMEOUT host={host} elapsed={time.monotonic() - start:.2f}s "
            f"state={state} error={error}"
        )
        raise RuntimeError(
            f"No fresh RTSP frame is available from {host}{address}. "
            f"State={state}; Error={error}"
        )
    def _settings(self, verb: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if verb == "POST" and "camera_rotation" in payload:
            try:
                value = int(payload.get("camera_rotation") or 0) % 360
                self.camera_rotation = value if value in (0, 90, 180, 270) else 0
            except Exception:
                self.camera_rotation = 0
            ENGINE.set_camera_rotation(self.camera_rotation)
        return {
            "ok": True,
            "message": "Local settings applied.",
            "settings": {
                "camera_rotation": self.camera_rotation,
                "rtsp_url": self.rtsp_url(),
            },
            "camera_rotation": self.camera_rotation,
        }

    def _read_local_logs(self) -> List[str]:
        candidates = [
            FACE_DATA_DIR.parent / "unlock_log.txt",
            FACE_DATA_DIR.parent / "SAS_LOG",
        ]
        lines: List[str] = []
        for candidate in candidates:
            try:
                if candidate.is_file():
                    lines.extend(candidate.read_text(encoding="utf-8", errors="ignore").splitlines()[-40:])
                elif candidate.is_dir():
                    files = sorted(candidate.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True)
                    for path in files[:3]:
                        lines.extend(path.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:])
            except Exception:
                continue
        return lines[-80:]

    def _export_face_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        target = str(payload.get("target_folder") or payload.get("pc_save_path") or "").strip()
        if not target:
            raise RuntimeError("Export folder is required.")
        data = ENGINE.export_face_data(target)
        zip_path = str(data.get("zip_path") or "")
        data["filename"] = os.path.basename(zip_path)
        data["path"] = zip_path
        return data

    def _import_face_data(self, zip_path: str) -> Dict[str, Any]:
        if not zip_path:
            raise RuntimeError("ZIP path is required.")
        before_ids = {user.employee_id for user in ENGINE.store.users.values()}
        data = ENGINE.import_face_data(zip_path)
        after_ids = {user.employee_id for user in ENGINE.store.users.values()}
        imported = sorted(after_ids - before_ids)
        data.setdefault("imported_users", imported)
        data.setdefault("added_ids", imported)
        data.setdefault("merged_users", imported)
        data.setdefault("skipped_users_count", 0)
        data.setdefault("import_mode", "add_on")
        return data

    def _list_server_zips(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        root = Path(str(payload.get("pc_save_path") or "").strip())
        if not root.exists():
            raise RuntimeError(f"Server path does not exist: {root}")
        files = []
        for path in sorted(root.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
            files.append({
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
            })
        return {"ok": True, "files": files}

    def stop_recognition(self):
        return self.request("POST", "/stop-recognition")

    def set_camera_rotation(self, camera_rotation: int):
        return self.request("POST", "/settings", {"camera_rotation": int(camera_rotation)}, timeout=15)

    def sas_connect(self, client_name: str = "Windows SAS", client_user: str = "", client_host: str = "", force=False):
        session = {
            "client_name": client_name or "Windows SAS",
            "client_user": client_user,
            "client_host": client_host,
            "connected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return {"ok": True, "message": "Local camera connection reserved.", "session": session}

    def sas_disconnect(self, force=False, stop_engine: bool = False):
        if not stop_engine:
            status = ENGINE.status(message="Local camera session released.")
            return {"ok": True, **status}

        status = ENGINE.stop(wait=True, timeout=6.0)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            thread = ENGINE.capture_thread
            if thread is None or not thread.is_alive():
                break
            time.sleep(0.1)

        self._stream_unhealthy_since = 0.0
        status = ENGINE.status(message="Local camera connection released.")
        if bool(status.get("capture_running", False)):
            status["message"] = "Local camera disconnect requested; RTSP worker is still stopping."
        return {"ok": True, **status}

    def sas_heartbeat(self):
        start_error = ""
        if ENGINE.running:
            ENGINE.ensure_capture_worker()
        elif self.host:
            try:
                ENGINE.start()
            except Exception as exc:
                start_error = str(exc)

        status = ENGINE.status()
        if bool(status.get("stream_healthy", False)):
            self._stream_unhealthy_since = 0.0
            return {"ok": True, "message": "Local heartbeat ok.", **status}

        now = time.monotonic()
        if self._stream_unhealthy_since <= 0.0:
            self._stream_unhealthy_since = now
        unhealthy_for = now - self._stream_unhealthy_since

        state = str(status.get("connection_state") or "unknown").strip()
        error = str(start_error or status.get("last_error") or "no fresh RTSP frame").strip()
        host = str(status.get("host") or ENGINE.host or "").strip()
        resolved_ip = str(status.get("resolved_ip") or "").strip()
        address = f" ({resolved_ip})" if resolved_ip else ""

        # Avoid UI flapping for brief RTSP/OpenCV stalls. Keep reconnecting in
        # the background and declare offline only after a sustained outage.
        if unhealthy_for < 60.0:
            return {
                "ok": True,
                "message": f"Local heartbeat waiting for RTSP recovery ({unhealthy_for:.1f}s).",
                "stream_recovering": True,
                **status,
            }

        raise RuntimeError(f"RTSP stream offline for {host}{address}. State={state}; Error={error}")

