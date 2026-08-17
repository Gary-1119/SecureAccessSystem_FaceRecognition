import requests
from urllib.parse import quote


class FaceApiService:
    """Raspberry Pi Face Recognition API client.

    Endpoints are aligned with the uploaded Pi API:
    /health, /status, /start-recognition, /stop-recognition,
    /users, /capture-user, /train, /delete-user, /settings,
    /system/storage, /server/mount, /logs, and /face-data/*.

    Note: workstation unlock no longer uses GET /recognition-result.
    Real-time face unlock is handled by services/websocket_client_service.py
    through the Pi /ws/sas WebSocket endpoint.
    """

    def __init__(self, host: str, port: str, debug_callback=None):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.debug_callback = debug_callback

    def debug(self, message: str):
        if self.debug_callback:
            self.debug_callback(message)
        else:
            print("[FACE API]", message)

    def configure(self, host: str, port: str):
        self.host = host
        self.port = port or "5000"
        if host.startswith("http"):
            self.base_url = host.rstrip("/")
        else:
            self.base_url = f"http://{host}:{self.port}"

    def request(self, method: str, endpoint: str, payload=None, timeout=10):
        """Send one Pi API request and surface Pi error messages to the UI."""
        url = self.base_url + endpoint
        verb = str(method or "GET").upper()
        self.debug(f"{verb} {url}")

        if verb == "GET":
            response = requests.get(url, timeout=timeout)
        elif verb == "POST":
            response = requests.post(url, json=payload, timeout=timeout)
        elif verb == "DELETE":
            response = requests.delete(url, json=payload, timeout=timeout)
        else:
            raise ValueError(f"Unsupported Pi API method: {verb}")

        try:
            data = response.json()
        except Exception:
            data = None

        if not response.ok:
            message = ""
            if isinstance(data, dict):
                message = str(data.get("message") or "").strip()
            if not message:
                message = f"Pi API request failed ({response.status_code})."
            raise RuntimeError(message)

        if not isinstance(data, dict):
            raise RuntimeError("Pi API returned an invalid JSON response.")
        return data

    def health(self):
        return self.request("GET", "/health")

    def status(self):
        return self.request("GET", "/status")

    def start_recognition(self):
        return self.request("POST", "/start-recognition")

    def stop_recognition(self):
        return self.request("POST", "/stop-recognition")

    def get_result(self):
        """Legacy diagnostic endpoint; not used for SAS unlock in v131+."""
        return self.request("GET", "/recognition-result")

    def train(self):
        return self.request("POST", "/train", timeout=120)

    def capture_user(self, user_id: str, mode="add", auto_capture=False):
        return self.request(
            "POST",
            "/capture-user",
            {"user_id": user_id, "mode": mode, "auto_capture": auto_capture},
            timeout=90,
        )

    def stop_capture(self):
        return self.request("POST", "/stop-capture")

    def capture_photo(self):
        return self.request("POST", "/capture-photo")

    def delete_user(self, user_id: str):
        return self.request("POST", "/delete-user", {"user_id": user_id})

    def refresh_users(self):
        return self.request("GET", "/users")

    def get_settings(self):
        return self.request("GET", "/settings")

    def get_system_storage(self):
        """Return the Pi root-filesystem storage snapshot for SAS Settings."""
        return self.request("GET", "/system/storage", timeout=8)

    def save_settings(
        self,
        username: str,
        password: str,
        pc_save_path: str,
        auto_capture=False,
        camera_rotation=None,
    ):
        payload = {
            "username": username,
            "password": password,
            "pc_save_path": pc_save_path,
            "auto_capture": bool(auto_capture),
        }
        if camera_rotation is not None:
            payload["camera_rotation"] = int(camera_rotation)
        return self.request("POST", "/settings", payload, timeout=45)

    def set_camera_rotation(self, camera_rotation: int):
        """Persist Pi camera orientation without remounting SMB/server settings."""
        return self.request(
            "POST",
            "/settings",
            {
                "camera_rotation": int(camera_rotation),
                "source": "Windows SAS",
            },
            timeout=15,
        )

    def mount_server(self, username: str, password: str, pc_save_path: str, save=False):
        return self.request(
            "POST",
            "/server/mount",
            {
                "username": username,
                "password": password,
                "pc_save_path": pc_save_path,
                "save": bool(save),
            },
            timeout=45,
        )

    def get_logs(self):
        return self.request("GET", "/logs")

    def clear_logs(self):
        return self.request("POST", "/logs/clear")

    def export_face_data(self, target_folder=None):
        return self.request("POST", "/face-data/export", {"target_folder": target_folder}, timeout=90)

    def import_face_data(self, zip_path: str):
        return self.request("POST", "/face-data/import", {"zip_path": zip_path}, timeout=90)

    def sftp_send(self, host: str, username: str, password: str, remote_dir: str, port=22):
        return self.request(
            "POST",
            "/face-data/sftp-send",
            {
                "host": host,
                "username": username,
                "password": password,
                "remote_dir": remote_dir,
                "port": int(port or 22),
            },
            timeout=120,
        )


    # ------------------------------------------------------------
    # One-Pi SAS connection ownership
    # ------------------------------------------------------------
    def sas_session(self):
        return self.request("GET", "/sas/session", timeout=8)

    def sas_connect(self, client_id: str, client_name: str = "Windows SAS", client_user: str = "", client_host: str = "", force=False):
        return self.request(
            "POST",
            "/sas/connect",
            {
                "client_id": client_id,
                "client_name": client_name,
                "client_user": client_user,
                "client_host": client_host,
                "force": bool(force),
            },
            timeout=8,
        )

    def sas_disconnect(self, client_id: str, force=False):
        return self.request(
            "POST",
            "/sas/disconnect",
            {"client_id": client_id, "force": bool(force)},
            timeout=8,
        )

    def sas_heartbeat(self, client_id: str):
        return self.request("POST", "/sas/heartbeat", {"client_id": client_id}, timeout=5)

    # ------------------------------------------------------------
    # Multi-Pi SFTP transfer (Pi owns the target list and transfers)
    # ------------------------------------------------------------
    def list_multi_sftp_targets(self):
        return self.request("GET", "/face-data/sftp-targets", timeout=15)

    def add_multi_sftp_target(self, hostname: str):
        return self.request(
            "POST",
            "/face-data/sftp-targets",
            {"hostname": str(hostname or "").strip()},
            timeout=15,
        )

    def remove_multi_sftp_target(self, hostname: str):
        encoded = quote(str(hostname or "").strip(), safe="")
        return self.request("DELETE", f"/face-data/sftp-targets/{encoded}", timeout=15)

    def get_multi_sftp_config(self):
        return self.request("GET", "/face-data/sftp-multi-config", timeout=15)

    def start_multi_sftp_transfer(self, targets):
        return self.request(
            "POST",
            "/face-data/sftp-multi-send",
            {"targets": list(targets or [])},
            timeout=30,
        )

    def get_multi_sftp_transfer(self, batch_id: str):
        return self.request(
            "GET",
            f"/face-data/sftp-multi-send/{quote(str(batch_id or ''), safe='')}",
            timeout=15,
        )

    def retry_multi_sftp_failed(self, batch_id: str):
        return self.request(
            "POST",
            f"/face-data/sftp-multi-send/{quote(str(batch_id or ''), safe='')}/retry-failed",
            timeout=30,
        )

    def cancel_multi_sftp_transfer(self, batch_id: str):
        return self.request(
            "POST",
            f"/face-data/sftp-multi-send/{quote(str(batch_id or ''), safe='')}/cancel",
            timeout=20,
        )

    def cleanup_multi_sftp_transfer(self, batch_id: str):
        return self.request(
            "POST",
            f"/face-data/sftp-multi-send/{quote(str(batch_id or ''), safe='')}/cleanup",
            timeout=30,
        )

    def list_received(self):
        return self.request("GET", "/face-data/received")

    def accept_received(self, filename: str):
        return self.request("POST", "/face-data/received/accept", {"filename": filename}, timeout=90)

    def reject_received(self, filename: str):
        return self.request("POST", "/face-data/received/reject", {"filename": filename}, timeout=45)
