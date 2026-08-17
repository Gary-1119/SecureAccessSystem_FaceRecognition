import os
from pathlib import Path

from services.atomic_file import atomic_write_text
from services.credential_crypto import is_protected_secret, protect_secret, unprotect_secret


class CredentialService:
    """credential.txt read/write logic with Windows DPAPI password protection."""

    def __init__(self, credential_file: str):
        self.credential_file = credential_file

    def read_credentials(self):
        raw = self._read_raw_credentials()
        password = str(raw.get("password", "") or "")
        if password:
            try:
                raw["password"] = unprotect_secret(password)
            except Exception:
                raw["password"] = ""
        return raw

    def migrate_plaintext_password_if_needed(self) -> bool:
        raw = self._read_raw_credentials()
        password = str(raw.get("password", "") or "")
        if not password or is_protected_secret(password):
            self._delete_legacy_backup()
            return False

        self.save_credentials(
            raw.get("ntid", ""),
            password,
            raw.get("server", ""),
            raw.get("timeout", "300"),
            disable_keyboard=self._as_bool(raw.get("disable_keyboard"), False),
            disable_mouse=self._as_bool(raw.get("disable_mouse"), False),
            disable_usb=self._as_bool(raw.get("disable_usb"), False),
            enable_hotkey=self._as_bool(raw.get("enable_hotkey"), True),
            pi_host=raw.get("pi_host", ""),
            pi_port=raw.get("pi_port", "5000"),
            auto_capture=False,
            transfer_host=raw.get("transfer_host", ""),
            transfer_port=raw.get("transfer_port", "22"),
            transfer_username=raw.get("transfer_username", ""),
            transfer_remote_dir=raw.get("transfer_remote_dir", ""),
            video_source=raw.get("video_source", "pi"),
        )
        return True

    def save_credentials(
        self,
        ntid,
        password,
        server,
        timeout,
        disable_keyboard=False,
        disable_mouse=False,
        disable_usb=False,
        enable_hotkey=True,
        pi_host="",
        pi_port="5000",
        auto_capture=False,
        transfer_host="",
        transfer_port="22",
        transfer_username="",
        transfer_remote_dir="",
        video_source="pi",
    ):
        protected_password = protect_secret(str(password or ""))
        lines = [
            f"ntid={ntid}",
            f"password={protected_password}",
            f"server={server}",
            f"timeout={timeout}",
            f"disable_keyboard={disable_keyboard}",
            f"disable_mouse={disable_mouse}",
            f"disable_usb={disable_usb}",
            f"enable_hotkey={enable_hotkey}",
            f"pi_host={pi_host}",
            f"pi_port={pi_port}",
            "auto_capture=False",
            f"transfer_host={transfer_host}",
            f"transfer_port={transfer_port}",
            f"transfer_username={transfer_username}",
            f"transfer_remote_dir={transfer_remote_dir}",
            f"video_source={video_source}",
        ]
        atomic_write_text(self.credential_file, "\n".join(lines) + "\n", encoding="utf-8", keep_backup=False)
        self._delete_legacy_backup()

    def _read_raw_credentials(self):
        if not os.path.exists(self.credential_file):
            return {}

        creds = {}
        try:
            with open(self.credential_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, val = line.split("=", 1)
                        creds[key.strip()] = val.strip()
        except Exception:
            return {}

        return creds

    def _delete_legacy_backup(self) -> None:
        backup = Path(self.credential_file).with_suffix(Path(self.credential_file).suffix + ".bak")
        try:
            backup.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _as_bool(value, default=False) -> bool:
        if value is None or value == "":
            return bool(default)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
