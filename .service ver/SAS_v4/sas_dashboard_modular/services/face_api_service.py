import requests


class FaceApiService:
    """Raspberry Pi Face Recognition API logic migrated from lockapp.py."""

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
        self.port = port
        if host.startswith("http"):
            self.base_url = host.rstrip("/")
        else:
            self.base_url = f"http://{host}:{port}"

    def request(self, method: str, endpoint: str, payload=None, timeout=10):
        url = self.base_url + endpoint
        self.debug(f"{method.upper()} {url}")

        if method.upper() == "GET":
            response = requests.get(url, timeout=timeout)
        else:
            response = requests.post(url, json=payload, timeout=timeout)

        response.raise_for_status()
        return response.json()

    def test_connection(self):
        return self.request("GET", "/status")

    def stop_recognition(self):
        return self.request("POST", "/recognition/stop")

    def get_result(self):
        return self.request("GET", "/recognition/result")

    def train(self):
        return self.request("POST", "/train")

    def capture_user(self, ntid: str):
        return self.request("POST", "/capture", {"ntid": ntid})

    def delete_user(self, ntid: str):
        return self.request("POST", "/users/delete", {"ntid": ntid})

    def refresh_users(self):
        return self.request("GET", "/users")
