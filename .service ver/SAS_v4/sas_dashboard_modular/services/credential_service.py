import os


class CredentialService:
    """credential.txt read/write logic migrated from lockapp.py."""

    def __init__(self, credential_file: str):
        self.credential_file = credential_file

    def read_credentials(self):
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
    ):
        with open(self.credential_file, "w", encoding="utf-8") as f:
            f.write(f"ntid={ntid}\n")
            f.write(f"password={password}\n")
            f.write(f"server={server}\n")
            f.write(f"timeout={timeout}\n")
            f.write(f"disable_keyboard={disable_keyboard}\n")
            f.write(f"disable_mouse={disable_mouse}\n")
            f.write(f"disable_usb={disable_usb}\n")
            f.write(f"enable_hotkey={enable_hotkey}\n")
