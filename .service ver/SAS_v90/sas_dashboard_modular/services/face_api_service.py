import requests


class FaceApiService:
    """Raspberry Pi Face Recognition API client.

    Endpoints are aligned with the uploaded Pi API:
    /health, /status, /start-recognition, /stop-recognition,
    /recognition-result, /users, /capture-user, /train, /delete-user,
    /settings, /server/mount, /logs, and /face-data/*.
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
        url = self.base_url + endpoint
        self.debug(f"{method.upper()} {url}")

        if method.upper() == "GET":
            response = requests.get(url, timeout=timeout)
        else:
            response = requests.post(url, json=payload, timeout=timeout)

        response.raise_for_status()
        return response.json()

    def health(self):
        return self.request("GET", "/health")

    def status(self):
        return self.request("GET", "/status")

    def start_recognition(self):
        return self.request("POST", "/start-recognition")

    def stop_recognition(self):
        return self.request("POST", "/stop-recognition")

    def get_result(self):
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

    def save_settings(self, username: str, password: str, pc_save_path: str, auto_capture=False):
        return self.request(
            "POST",
            "/settings",
            {
                "username": username,
                "password": password,
                "pc_save_path": pc_save_path,
                "auto_capture": bool(auto_capture),
            },
            timeout=45,
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

    def list_received(self):
        return self.request("GET", "/face-data/received")

    def accept_received(self, filename: str):
        return self.request("POST", "/face-data/received/accept", {"filename": filename}, timeout=90)

    def reject_received(self, filename: str):
        return self.request("POST", "/face-data/received/reject", {"filename": filename}, timeout=45)
