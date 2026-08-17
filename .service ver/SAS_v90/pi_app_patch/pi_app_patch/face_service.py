"""
face_service.py

Shared backend service for the Raspberry Pi Face Recognition System.

Use this file as the common business-logic layer for both:
1. gui.py local Raspberry Pi UI
2. face_api.py HTTP API called by the Windows lockscreen app

The goal is to avoid rewriting validation and operational logic in two places.
"""

from __future__ import annotations

import os
import cv2
import json
import time
import pickle
import shutil
import socket
import zipfile
import tempfile
import threading
import subprocess
import xml.etree.ElementTree as ET
from typing import Any, Callable, Optional
import threading
from threading import Thread, Event

import requests
from cryptography.fernet import Fernet

try:
    import paramiko
except ImportError:
    paramiko = None

from capture import capture_faces
from recog import start_recognition
from train import train_model


ENCODINGS_FILE = "encodings.pickle"
DATASET_DIR = "dataset"
ADMIN_FILE = "admins.txt"
SETTINGS_FILE = "settings.json"
RECOGNITION_RESULT_FILE = "recognition_result.json"

SOAP_URL = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"
FERNET_KEY = b'-_xj1UT6MLokiC2A-cd-LDp1Hj_3I06kdNCky09tr_U='
SERVER_MOUNT_POINT = "/mnt/pcshare"

RECEIVED_DIR = "received_face_data"
PENDING_DIR = os.path.join(RECEIVED_DIR, "pending")
ACCEPTED_DIR = os.path.join(RECEIVED_DIR, "accepted")
REJECTED_DIR = os.path.join(RECEIVED_DIR, "rejected")
TEMP_EXPORT_DIR = "temp_export"
TEMP_IMPORT_DIR = "temp_import"
BACKUP_DIR = "face_data_import_backups"


class FaceService:
    def __init__(self, gui: Any = None):
        self.gui = gui
        self.root = getattr(gui, "root", None)

        self._state_lock = threading.Lock()
        self._service_lock = threading.RLock()

        self._recognition_running = False
        self._capture_running = False
        self._api_training_running = False

        self._stop_recognition_event = Event()
        self._stop_capture_event = Event()

        self._api_latest_frame = None
        self._api_frame_lock = threading.Lock()
        self._api_last_error = None
        self._api_server_started = False

        self._stop_recognition_event = threading.Event()
        self._stop_capture_event = threading.Event()
        self._manual_capture_event = threading.Event()
        self._manual_capture_count = 0
        self._active_capture_user = None
        self._active_capture_auto = False

        # Camera workflow recovery and asynchronous training status.  The Flask
        # /status endpoint exposes these fields to SAS.
        self._resume_recognition_after_capture = False
        self._resume_recognition_after_training = False
        self._recognition_resume_pending = False
        self._api_training_state = "idle"
        self._api_last_training_id = ""
        self._api_last_training_finished_at = 0.0
        self._api_last_training_error = None
        self._api_last_training_new_faces = 0

        self.current_user = getattr(gui, "current_user", None)
        self.auto_capture_enabled = False
        self.pc_save_path = None
        self.admin_list: list[str] = []
        self._logs: list[str] = []

        self._ensure_transfer_folders()
        self._load_admin()
        self._load_pc_path_only()

    # --------------------------------------------------------
    # General helpers
    # --------------------------------------------------------
    def log(self, message: str, level: str = "info") -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"{ts}  {message}"
        self._logs.append(line)
        self._logs = self._logs[-500:]

        if self.gui is not None and hasattr(self.gui, "log"):
            try:
                self.gui.log(message, level)
                return
            except Exception:
                pass

        print(f"[{level.upper()}] {message}")

    def _run_in_gui_thread(self, func: Callable[[], Any]) -> None:
        if self.root is not None:
            try:
                self.root.after(0, func)
                return
            except Exception:
                pass
        try:
            func()
        except Exception:
            pass

    def _refresh_dataset_ui(self) -> None:
        if self.gui is not None and hasattr(self.gui, "refresh_dataset"):
            self._run_in_gui_thread(lambda: self.gui.refresh_dataset())

    def _set_gui_camera_status(self, is_live: bool) -> None:
        if self.gui is not None and hasattr(self.gui, "_set_camera_status"):
            self._run_in_gui_thread(lambda: self.gui._set_camera_status(is_live))

    def _set_gui_frame(self, frame) -> None:
        with self._api_frame_lock:
            self._api_latest_frame = frame.copy()

        if self.gui is None:
            return

        for name in ("_update_camera_frame", "update_camera_frame", "_show_frame"):
            if hasattr(self.gui, name) and callable(getattr(self.gui, name)):
                try:
                    self._run_in_gui_thread(lambda n=name: getattr(self.gui, n)(frame))
                    return
                except Exception:
                    pass

    def _device_name(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return "RaspberryPi"

    def _ensure_transfer_folders(self) -> None:
        for folder in (RECEIVED_DIR, PENDING_DIR, ACCEPTED_DIR, TEMP_EXPORT_DIR, TEMP_IMPORT_DIR):
            os.makedirs(folder, exist_ok=True)

    # --------------------------------------------------------
    # Settings / server path
    # --------------------------------------------------------
    def _load_settings(self) -> dict:
        if not os.path.exists(SETTINGS_FILE):
            return {}
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings_file(self, settings: dict) -> None:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)

    def _reset_recognition_result_file(self) -> None:
        """Ensure recognition_result.json exists locally and in mounted server path.

        Windows SAS reads recognition_result.json from the configured server path.
        After Settings sync, create/reset a safe false state to avoid stale unlock data.
        """
        data = {
            "detected": False,
            "user_id": None,
            "confidence": 0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "settings_sync"
        }

        # Local copy
        try:
            with open(RECOGNITION_RESULT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.log(f"Failed to reset local recognition_result.json: {e}", "warn")

        # Server/mounted copy
        try:
            if os.path.exists(SERVER_MOUNT_POINT) and os.access(SERVER_MOUNT_POINT, os.W_OK):
                server_file = os.path.join(SERVER_MOUNT_POINT, RECOGNITION_RESULT_FILE)
                with open(server_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
        except Exception as e:
            self.log(f"Failed to reset server recognition_result.json: {e}", "warn")

    def _load_pc_path_only(self) -> None:
        settings = self._load_settings()
        self.pc_save_path = settings.get("pc_save_path")
        self.auto_capture_enabled = self._coerce_bool(settings.get("auto_capture", False), default=False)

        # Keep attached Pi GUI state aligned whenever settings.json is reloaded.
        try:
            if self.gui is not None:
                self.gui.pc_save_path = settings.get("pc_save_path")
                self.gui.auto_capture_enabled = self.auto_capture_enabled
        except Exception:
            pass


    def _coerce_bool(self, value, default=False) -> bool:
        """Safely parse booleans from JSON/string payloads.

        bool("False") is True in Python, so do not use bool() directly for
        values that may come from HTTP payloads or settings.json.
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return bool(default)
        if isinstance(value, (int, float)):
            return value != 0

        text = str(value).strip().lower()
        if text in ("true", "1", "yes", "y", "enabled", "enable", "on"):
            return True
        if text in ("false", "0", "no", "n", "disabled", "disable", "off"):
            return False

        return bool(default)


    def get_settings(self, include_password: bool = False) -> dict:
        # Always reload settings.json so Windows SAS receives the latest value.
        self._load_pc_path_only()
        settings = self._load_settings().copy()

        if include_password and settings.get("password"):
            try:
                # Windows SAS needs the actual password only when pulling settings
                # to mirror Pi Settings UI. Keep default GET password-hidden.
                settings["password"] = self.decrypt_password(settings["password"])
            except Exception:
                settings["password_saved"] = True
                settings.pop("password", None)
        elif "password" in settings:
            settings["password_saved"] = True
            settings.pop("password", None)

        return {
            "settings": settings,
            "pc_save_path": self.pc_save_path,
            "auto_capture": self.auto_capture_enabled,
            "mount_point": SERVER_MOUNT_POINT,
        }

    def decrypt_password(self, encrypted: str) -> str:
        f = Fernet(FERNET_KEY)
        return f.decrypt(encrypted.encode()).decode()

    def encrypt_password(self, password: str) -> str:
        f = Fernet(FERNET_KEY)
        return f.encrypt(password.encode()).decode()

    def mount_server(self, username: Optional[str] = None, password: Optional[str] = None,
                     unc_path: Optional[str] = None, save: bool = False) -> tuple[bool, str, dict]:
        settings = self._load_settings()
        username = username or settings.get("username")
        unc_path = unc_path or settings.get("pc_save_path")

        if password is None:
            enc_password = settings.get("password")
            if enc_password:
                try:
                    password = self.decrypt_password(enc_password)
                except Exception as e:
                    return False, f"Failed to decrypt password: {e}", {}

        if not username or not password or not unc_path:
            return False, "Please fill in NTID, password and server path.", {}

        linux_path = unc_path.replace("\\", "/")
        mount_point = SERVER_MOUNT_POINT
        os.makedirs(mount_point, exist_ok=True)

        try:
            subprocess.run(["sudo", "umount", "-l", mount_point], capture_output=True, text=True, timeout=10)
        except Exception:
            pass

        cmd = [
            "sudo", "mount", "-t", "cifs",
            linux_path, mount_point,
            "-o", f"username={username},password={password},domain=JABIL,vers=3.0,uid=1000,gid=1000"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except Exception as e:
            return False, f"Failed to run mount command: {e}", {}

        if result.returncode != 0:
            err_msg = result.stderr.strip() if result.stderr.strip() else "Unknown error."
            return False, f"Could not connect to server. Error: {err_msg}", {"stderr": err_msg}

        try:
            ls_result = subprocess.run(["ls", mount_point], capture_output=True, text=True, timeout=10)
            if ls_result.returncode != 0:
                err_msg = ls_result.stderr.strip()
                return False, f"Mounted but cannot read folder. Error: {err_msg}", {"stderr": err_msg}
        except Exception as e:
            return False, f"Could not verify access: {e}", {}

        self.pc_save_path = mount_point

        if save:
            new_settings = {
                "username": username,
                "password": self.encrypt_password(password),
                "pc_save_path": unc_path,
                "auto_capture": self.auto_capture_enabled,
            }
            self._save_settings_file(new_settings)

        self.log(f"Server mounted successfully: {unc_path}", "success")
        return True, "Connected to server successfully.", {"server_path": unc_path, "mount_point": mount_point}

    def _api_save_settings_request(self, payload: dict) -> tuple[bool, str, dict]:
        """Save settings pushed from Windows SAS into Pi settings.json.

        This is called by:
            Windows SAS → POST /settings

        It updates:
        - username
        - encrypted password
        - pc_save_path
        - auto_capture
        - runtime GUI state
        - recognition_result.json safe state on mounted server path
        """
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        pc_save_path = str(payload.get("pc_save_path", "")).strip()
        auto_capture = self._coerce_bool(payload.get("auto_capture", False), default=False)

        if not username or not password or not pc_save_path:
            return False, "Please fill in NTID, password and server path.", {}

        self.auto_capture_enabled = auto_capture

        # Mount server first. If mount fails, do not save invalid server settings.
        ok_state, message, extra = self.mount_server(
            username=username,
            password=password,
            unc_path=pc_save_path,
            save=False,
        )

        if not ok_state:
            return False, message, extra

        settings = self._load_settings().copy()
        settings.update({
            "username": username,
            "password": self.encrypt_password(password),
            "pc_save_path": pc_save_path,
            "auto_capture": auto_capture,
            "recognition_result_file": RECOGNITION_RESULT_FILE,
            "server_mount_point": SERVER_MOUNT_POINT,
            "last_synced_from": str(payload.get("source", "Windows SAS")),
            "last_synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save_settings_file(settings)

        # Runtime state for service and optional Tk GUI.
        self.pc_save_path = SERVER_MOUNT_POINT
        self.auto_capture_enabled = auto_capture

        try:
            if self.gui is not None:
                self.gui.pc_save_path = pc_save_path
                self.gui.auto_capture_enabled = auto_capture

                # Update main readonly path box if it exists.
                if hasattr(self.gui, "pc_path_entry"):
                    try:
                        self.gui.pc_path_entry.config(state="normal")
                        self.gui.pc_path_entry.delete(0, "end")
                        self.gui.pc_path_entry.insert(0, pc_save_path)
                        self.gui.pc_path_entry.config(state="readonly")
                    except Exception:
                        pass
        except Exception:
            pass

        # Ensure Windows SAS state polling has a valid file at the synced server path.
        self._reset_recognition_result_file()

        self.log(
            f"Settings synced from Windows SAS. Path={pc_save_path}, Auto-Capture={'Enabled' if auto_capture else 'Disabled'}",
            "success"
        )

        return True, "Pi settings synced successfully.", {
            **extra,
            "settings": {
                "username": username,
                "pc_save_path": pc_save_path,
                "auto_capture": auto_capture,
                "recognition_result_file": RECOGNITION_RESULT_FILE,
                "server_mount_point": SERVER_MOUNT_POINT,
            }
        }


    # --------------------------------------------------------
    # Admin logic
    # --------------------------------------------------------
    def _load_admin(self) -> list[str]:
        self.admin_list = []
        if os.path.exists(ADMIN_FILE):
            try:
                with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                self.admin_list = [line.strip() for line in lines if line.strip()]
            except Exception:
                self.admin_list = []
        return self.admin_list

    def _save_admin_file(self) -> None:
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.admin_list))

    def _parse_ad_response(self, response: str) -> bool:
        if not response or not response.strip():
            return False
        try:
            root = ET.fromstring(response)
            for elem in root.iter():
                if "ReturnedValue" in elem.tag:
                    return (elem.text or "").strip().lower() == "true"
            return False
        except Exception as e:
            self.log(f"AD parsing error: {e}", "error")
            return False

    def _validate_ntid_in_ad(self, ntid: str) -> bool:
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                        xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
        <soap12:Body>
            <IsUserExistsInAD xmlns="http://jpetewebapp/jtesw_ws/">
            <userName>{ntid}</userName>
            </IsUserExistsInAD>
        </soap12:Body>
        </soap12:Envelope>"""
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": "http://jpetewebapp/jtesw_ws/IsUserExistsInAD"
        }
        try:
            response = requests.post(SOAP_URL, data=soap.encode("utf-8"), headers=headers, timeout=10)
            response.raise_for_status()
            return self._parse_ad_response(response.text)
        except requests.exceptions.Timeout:
            self.log("AD request timeout.", "error")
            return False
        except requests.exceptions.RequestException as e:
            self.log(f"AD request failed: {e}", "error")
            return False
        except Exception as e:
            self.log(f"Unexpected AD error: {e}", "error")
            return False

    def add_admin(self, ntid: str, validate: bool = True) -> tuple[bool, str, dict]:
        ntid = ntid.strip()
        if not ntid:
            return False, "Please enter an NTID.", {}
        self._load_admin()
        if ntid in self.admin_list:
            return False, f"'{ntid}' is already an admin.", {"admins": self.admin_list}
        if validate and not self._validate_ntid_in_ad(ntid):
            return False, f"'{ntid}' is not a valid NTID.", {}
        self.admin_list.append(ntid)
        self._save_admin_file()
        if self.gui is not None:
            try:
                self.gui.admin_list = self.admin_list
            except Exception:
                pass
        self.log(f"Admin registered: {ntid}", "success")
        return True, "Admin added.", {"admins": self.admin_list}

    def remove_admin(self, ntid: str) -> tuple[bool, str, dict]:
        ntid = ntid.strip()
        self._load_admin()
        current_user = getattr(self.gui, "current_user", self.current_user)
        if ntid == current_user:
            return False, "You cannot remove yourself as admin.", {}
        if len(self.admin_list) <= 1:
            return False, "Cannot remove the last admin.", {}
        if ntid not in self.admin_list:
            return False, "Admin not found.", {"admins": self.admin_list}
        self.admin_list.remove(ntid)
        self._save_admin_file()
        if self.gui is not None:
            try:
                self.gui.admin_list = self.admin_list
            except Exception:
                pass
        self.log(f"Admin removed: {ntid}", "warn")
        return True, "Admin removed.", {"admins": self.admin_list}

    def _save_admin(self, ntid: str) -> None:
        self.add_admin(ntid, validate=False)

    def _remove_admin(self, ntid: str) -> bool:
        ok, _msg, _extra = self.remove_admin(ntid)
        return ok

    # --------------------------------------------------------
    # Dataset / users
    # --------------------------------------------------------
    def _load_encoding_data_safe(self) -> dict:
        if not os.path.exists(ENCODINGS_FILE):
            return {"encodings": [], "names": [], "trained_files": []}
        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
            if not isinstance(data, dict):
                return {"encodings": [], "names": [], "trained_files": []}
            data.setdefault("encodings", [])
            data.setdefault("names", [])
            data.setdefault("trained_files", [])
            return data
        except Exception as e:
            self.log(f"Failed to load encodings: {e}", "error")
            return {"encodings": [], "names": [], "trained_files": []}

    def _api_get_users_list(self) -> list[dict]:
        data = self._load_encoding_data_safe()
        trained_users = set(data.get("names", []))
        users = []
        if not os.path.exists(DATASET_DIR):
            return users
        for user_id in sorted(os.listdir(DATASET_DIR)):
            user_path = os.path.join(DATASET_DIR, user_id)
            if not os.path.isdir(user_path):
                continue
            images = [f for f in os.listdir(user_path) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            users.append({"id": user_id, "photos": len(images), "trained": user_id in trained_users, "path": user_path})
        return users

    def get_user_detail(self, user_id: str) -> Optional[dict]:
        for user in self._api_get_users_list():
            if str(user.get("id", "")).lower() == str(user_id).lower():
                return user
        return None

    def _api_read_recognition_result(self) -> dict:
        if not os.path.exists(RECOGNITION_RESULT_FILE):
            return {"detected": False, "user_id": None, "confidence": 0, "timestamp": None}
        try:
            with open(RECOGNITION_RESULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"detected": False, "user_id": None, "confidence": 0, "timestamp": None, "error": str(e)}

    # --------------------------------------------------------
    # Recognition / capture / train / delete
    # --------------------------------------------------------
    def _recognition_frame_callback(self, frame, boxes=None):
        display = frame.copy()
        if boxes:
            for box in boxes:
                try:
                    top, right, bottom, left = box
                    cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 0), 2)
                except Exception:
                    pass
        self._set_gui_frame(display)

    def _is_gui_recognition_running(self) -> bool:
        try:
            return bool(self.gui is not None and getattr(self.gui, "_recognition_running", False))
        except Exception:
            return False

    def _is_gui_capture_running(self) -> bool:
        try:
            return bool(self.gui is not None and getattr(self.gui, "_capture_running", False))
        except Exception:
            return False

    def _stop_recognition_for_transition(self, label: str, timeout_seconds: float = 12.0) -> tuple[bool, str]:
        """Stop whichever recognition loop owns PiCamera2, then wait for release."""
        service_running = bool(getattr(self, "_recognition_running", False))
        gui_running = self._is_gui_recognition_running()
        if not service_running and not gui_running:
            return True, "Recognition already stopped."

        self.log(f"Stopping recognition before {label}...", "warn")
        self._notify_gui_state("stopping", f"Stopping recognition before {label}...")
        self._stop_recognition_event.set()

        try:
            if self.gui is not None:
                self.gui.stop_flag = True
        except Exception:
            pass

        started = time.time()
        while time.time() - started < timeout_seconds:
            if not bool(getattr(self, "_recognition_running", False)) and not self._is_gui_recognition_running():
                # PiCamera2 needs a short release period before capture/training
                # opens the device again.
                time.sleep(0.8)
                return True, "Recognition stopped."
            time.sleep(0.1)

        return False, "Camera is still busy. Recognition did not stop in time."

    def _queue_recognition_resume(self, workflow: str, delay_seconds: float = 1.0) -> None:
        """Retry background recognition after capture or training completes."""
        with self._service_lock:
            if self._recognition_resume_pending:
                return
            self._recognition_resume_pending = True

        def worker():
            last_error = ""
            try:
                time.sleep(delay_seconds)
                for attempt in range(1, 7):
                    with self._service_lock:
                        capture_running = bool(self._capture_running)
                        training_running = bool(self._api_training_running)
                        recognition_running = bool(self._recognition_running)

                    if capture_running or training_running:
                        time.sleep(0.5)
                        continue

                    if recognition_running or self._is_gui_recognition_running():
                        self.log(f"Recognition is already running after {workflow}.", "success")
                        return

                    self._stop_recognition_event.clear()
                    self._stop_capture_event.clear()
                    try:
                        if self.gui is not None:
                            self.gui.stop_flag = False
                    except Exception:
                        pass

                    ok_state, message, _extra = self._api_start_recognition_request()
                    if ok_state:
                        # State becomes true only when the recognition thread has
                        # been accepted. Give PiCamera2 a moment before verifying.
                        time.sleep(1.0)
                        if bool(getattr(self, "_recognition_running", False)):
                            self.log(f"Recognition restarted after {workflow}.", "success")
                            return
                    else:
                        last_error = message

                    time.sleep(0.9)

                detail = f" Last error: {last_error}" if last_error else ""
                self._api_last_error = f"Recognition did not restart after {workflow}.{detail}"
                self.log(self._api_last_error, "error")
                self._notify_gui_state("stopped", "Camera stopped. Press Recognize to retry.")
            finally:
                with self._service_lock:
                    self._recognition_resume_pending = False
                    if workflow == "capture":
                        self._resume_recognition_after_capture = False
                    elif workflow == "training":
                        self._resume_recognition_after_training = False

        Thread(target=worker, daemon=True).start()

    def _api_stop_recognition_request(self) -> tuple[bool, str, dict]:
        """Targeted stop used for a capture/train camera transition."""
        try:
            self._stop_recognition_event.set()
            if self.gui is not None:
                self.gui.stop_flag = True
            self.log("Recognition stop requested from Windows API.", "warn")
            return True, "Recognition stop requested.", {}
        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Recognition stop failed: {e}", {}

    def _api_stop_capture_request(self) -> tuple[bool, str, dict]:
        """Stop capture but retain normal post-capture recognition recovery."""
        try:
            self._stop_capture_event.set()
            if self.gui is not None and hasattr(self.gui, "_stop_capture_event"):
                self.gui._stop_capture_event.set()
            self.log("Capture stop requested from Windows API.", "warn")
            return True, "Capture stop requested.", {}
        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Capture stop failed: {e}", {}

    def _api_start_recognition_request(self) -> tuple[bool, str, dict]:
        # Also check if recognition was started from Pi GUI
        gui_recognition_running = False
        try:
            if self.gui is not None:
                gui_recognition_running = getattr(self.gui, "_recognition_running", False)
        except Exception:
            pass
        
        with self._service_lock:
            if self._recognition_running or gui_recognition_running:
                return True, "Recognition already running.", {}
    
            if self._capture_running or self._api_training_running:
                return False, "Another process is running. Please stop it first.", {}
    
            self._recognition_running = True
            self._stop_recognition_event.clear()
    
            if self.gui is not None:
                try:
                    self.gui._recognition_running = True
                    self.gui.stop_flag = False
                except Exception:
                    pass
                
        # Update Pi GUI buttons/camera status after state is set
        self._notify_gui_state("recognition", "Recognition started from Windows API.")
    
        def run():
            try:
                self.log("Recognition started.", "success")
                self._set_gui_camera_status(True)
    
                start_recognition(
                    frame_callback=self._recognition_frame_callback,
                    stop_flag=lambda: self._stop_recognition_event.is_set()
                )
    
            except Exception as e:
                self._api_last_error = str(e)
                self.log(f"Recognition failed: {e}", "error")
    
            finally:
                with self._service_lock:
                    self._recognition_running = False
    
                    if self.gui is not None:
                        try:
                            self.gui._recognition_running = False
                            self.gui.stop_flag = False
                        except Exception:
                            pass
                        
                self._set_gui_camera_status(False)
                self._notify_gui_state("stopped", "Recognition stopped.")
                self.log("Recognition stopped.", "warn")
    
        Thread(target=run, daemon=True).start()
    
        return True, "Recognition started.", {}

    def _api_stop_request(self):
        """Full manual Pi stop: end camera work and cancel auto-recovery."""
        try:
            with self._service_lock:
                self._resume_recognition_after_capture = False
                self._resume_recognition_after_training = False
                self._recognition_resume_pending = False

            self._notify_gui_state("stopping", "Stop requested from Windows API.")
            self._stop_recognition_event.set()
            self._stop_capture_event.set()

            if self.gui is not None:
                try:
                    self.gui.stop_flag = True
                    if hasattr(self.gui, "_stop_capture_event"):
                        self.gui._stop_capture_event.set()
                except Exception:
                    pass

            self.log("Full manual stop requested from Windows API.", "warn")
            return True, "Stop requested.", {}
        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Stop failed: {e}", {}

    def _capture_frame_callback(self, frame):
        self._set_gui_frame(frame)

        if self._stop_capture_event.is_set():
            return "stop"

        # Manual mode: Windows SAS app calls /capture-photo.
        # capture_faces() will save one image only when exactly one face is detected.
        if hasattr(self, "_manual_capture_event") and self._manual_capture_event.is_set():
            self._manual_capture_event.clear()
            self._manual_capture_count += 1
            return "capture"

        return None

    def _api_manual_capture_request(self):
        """Request one manual photo during API capture mode."""
        if not getattr(self, "_capture_running", False):
            return False, "Capture is not running. Press Capture first.", {}

        if getattr(self, "_active_capture_auto", False):
            return False, "Manual Take Photo is only available when Auto-Capture is disabled.", {}

        self._manual_capture_event.set()
        self.log("Manual Take Photo requested from Windows API.", "info")

        return True, "Take Photo requested. Image will save if exactly one face is detected.", {
            "user_id": self._active_capture_user,
            "manual_capture_count": self._manual_capture_count + 1
        }

    def _api_capture_user_request(self, user_id, mode="add", auto_capture=None):
        """Capture through the Pi API and restore background recognition after it ends."""
        user_id = str(user_id).strip().lower()
        mode = str(mode or "add").strip().lower()

        self._load_pc_path_only()
        if not user_id:
            return False, "Missing user_id.", {}
        if mode not in ("add", "replace"):
            mode = "add"

        if auto_capture is None:
            auto_capture = self._coerce_bool(getattr(self, "auto_capture_enabled", False), default=False)
        else:
            auto_capture = self._coerce_bool(auto_capture, default=getattr(self, "auto_capture_enabled", False))
        self.auto_capture_enabled = auto_capture

        with self._service_lock:
            if self._api_training_running:
                return False, "Training is running. Please wait until training is completed.", {}
            if self._capture_running or self._is_gui_capture_running():
                return False, "Capture is already running.", {}
            # Capture must always leave recognition running afterward so SAS can
            # still unlock a workstation without another user action.
            self._resume_recognition_after_capture = True
            self._active_capture_auto = auto_capture
            self._manual_capture_count = 0
            self._active_capture_user = user_id

        stopped, message = self._stop_recognition_for_transition("capture")
        if not stopped:
            with self._service_lock:
                self._resume_recognition_after_capture = False
            return False, message, {}

        with self._state_lock:
            self._capture_running = True
            self._stop_capture_event.clear()
            self._manual_capture_event.clear()

        if self.gui is not None:
            try:
                self.gui._capture_running = True
                self.gui.stop_flag = False
                if hasattr(self.gui, "_stop_capture_event"):
                    self.gui._stop_capture_event.clear()
            except Exception:
                pass

        mode_text = "auto-capture" if auto_capture else "manual capture"
        self._notify_gui_state("capture", f"Capture started for {user_id} from Windows API ({mode_text}).")

        def run_capture():
            try:
                captured, total = capture_faces(
                    user_id,
                    mode=mode,
                    save_base=DATASET_DIR,
                    frame_callback=self._capture_frame_callback,
                    stop_flag=lambda: self._stop_capture_event.is_set(),
                    auto_capture=auto_capture
                )
                self.log(f"Capture completed for {user_id}: {captured}/{total}", "success")
                try:
                    if self.gui is not None and hasattr(self.gui, "refresh_dataset"):
                        self.gui.root.after(0, self.gui.refresh_dataset)
                except Exception:
                    pass
            except Exception as e:
                self._api_last_error = str(e)
                self.log(f"Capture failed: {e}", "error")
            finally:
                with self._state_lock:
                    self._capture_running = False
                    self._stop_capture_event.clear()
                    self._manual_capture_event.clear()
                    self._active_capture_user = None
                    self._active_capture_auto = False

                if self.gui is not None:
                    try:
                        self.gui._capture_running = False
                        if hasattr(self.gui, "_stop_capture_event"):
                            self.gui._stop_capture_event.clear()
                    except Exception:
                        pass

                self._notify_gui_state("stopping", "Capture finished. Restoring recognition...")
                if self._resume_recognition_after_capture:
                    self._queue_recognition_resume("capture")
                else:
                    self._notify_gui_state("stopped", "Capture stopped.")

        Thread(target=run_capture, daemon=True).start()

        if auto_capture:
            msg = "Capture started. It will auto-capture face photos, then recognition will resume."
        else:
            msg = "Manual capture started. Click Take Photo to save each image; recognition resumes after STOP."

        return True, msg, {
            "user_id": user_id,
            "mode": mode,
            "auto_capture": auto_capture
        }

    def _api_train_request(self) -> tuple[bool, str, dict]:
        """Train asynchronously, stopping recognition first and restoring it after."""
        with self._service_lock:
            if self._api_training_running:
                return False, "Training is already running. Please wait until it is completed.", {}
            if self._capture_running or self._is_gui_capture_running():
                return False, "Capture is running. Finish or stop capture before training.", {}

            training_id = f"train-{int(time.time() * 1000)}"
            self._api_training_running = True
            self._api_training_state = "preparing"
            self._api_last_training_id = training_id
            self._api_last_training_finished_at = 0.0
            self._api_last_training_error = None
            self._api_last_training_new_faces = 0
            self._resume_recognition_after_training = True

        def run_train():
            failed = False
            messages: list[str] = []
            try:
                stopped, stop_message = self._stop_recognition_for_transition("training")
                if not stopped:
                    raise RuntimeError(stop_message)

                self._api_training_state = "running"
                self._notify_gui_state("training", "Training face data on the Pi...")
                self.log("Training started.", "info")

                def progress(msg):
                    text = str(msg)
                    messages.append(text)
                    self.log(text, "info")

                new_count = train_model(progress_callback=progress)
                self._api_last_training_new_faces = int(new_count or 0)
                self.log(f"Training completed. New faces trained: {new_count}", "success")
                self._refresh_dataset_ui()
            except Exception as e:
                failed = True
                self._api_last_training_error = str(e)
                self._api_last_error = str(e)
                self.log(f"Training failed: {e}", "error")
            finally:
                with self._service_lock:
                    self._api_training_running = False
                    self._api_training_state = "failed" if failed else "completed"
                    self._api_last_training_finished_at = time.time()

                if self._resume_recognition_after_training:
                    self._notify_gui_state("stopping", "Training finished. Restoring recognition...")
                    self._queue_recognition_resume("training")
                else:
                    self._notify_gui_state("stopped", "Training finished. Recognition remains stopped.")

        Thread(target=run_train, daemon=True).start()
        return True, "Training started.", {
            "training_id": training_id,
            "training_state": "preparing"
        }

    def _api_delete_user_request(self, user_id: str) -> tuple[bool, str, dict]:
        user_id = str(user_id).strip().lower()
        if not user_id:
            return False, "Missing user_id.", {}
        with self._service_lock:
            if self._recognition_running or self._capture_running or self._api_training_running:
                return False, "Another process is running. Please stop it first.", {}
        dataset_path = os.path.join(DATASET_DIR, user_id)
        removed_dataset = False
        removed_encodings = 0
        try:
            if os.path.exists(dataset_path):
                backup_folder = f"deleted_user_backup_{user_id}_{time.strftime('%Y%m%d_%H%M%S')}"
                shutil.copytree(dataset_path, backup_folder)
                shutil.rmtree(dataset_path)
                removed_dataset = True
            removed_encodings = self._remove_user_from_encodings(user_id)
            self._refresh_dataset_ui()
            self.log(f"User deleted: {user_id}", "warn")
            return True, "User deleted.", {"user_id": user_id, "dataset_removed": removed_dataset, "encodings_removed": removed_encodings}
        except Exception as e:
            self._api_last_error = str(e)
            self.log(f"Delete failed: {e}", "error")
            return False, f"Delete failed: {e}", {}

    def _remove_user_from_encodings(self, user_id: str) -> int:
        if not os.path.exists(ENCODINGS_FILE):
            return 0
        data = self._load_encoding_data_safe()
        encodings = data.get("encodings", [])
        names = data.get("names", [])
        trained_files = data.get("trained_files", [])
        new_encodings = []
        new_names = []
        removed = 0
        for enc, name in zip(encodings, names):
            if str(name).lower() == str(user_id).lower():
                removed += 1
                continue
            new_encodings.append(enc)
            new_names.append(name)
        new_trained_files = [f for f in trained_files if not str(f).lower().startswith(str(user_id).lower() + "/")]
        backup_name = f"encodings_backup_before_delete_{user_id}_{time.strftime('%Y%m%d_%H%M%S')}.pickle"
        shutil.copy2(ENCODINGS_FILE, backup_name)
        data["encodings"] = new_encodings
        data["names"] = new_names
        data["trained_files"] = new_trained_files
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump(data, f)
        return removed

    # --------------------------------------------------------
    # Logs
    # --------------------------------------------------------
    def get_logs(self, limit: int = 200) -> list[str]:
        if self.gui is not None and hasattr(self.gui, "log_text"):
            try:
                text = self.gui.log_text.get("1.0", "end").strip()
                return text.splitlines()[-limit:]
            except Exception:
                pass
        return self._logs[-limit:]

    def clear_logs(self) -> tuple[bool, str, dict]:
        self._logs.clear()
        if self.gui is not None and hasattr(self.gui, "log_text"):
            def clear():
                self.gui.log_text.config(state="normal")
                self.gui.log_text.delete("1.0", "end")
                self.gui.log_text.config(state="disabled")
            self._run_in_gui_thread(clear)
        return True, "Logs cleared.", {}

    # --------------------------------------------------------
    # Face data import/export
    # --------------------------------------------------------
    def _resolve_server_credentials(self, username=None, password=None, pc_save_path=None):
        """Use API-provided credentials first, otherwise fall back to settings.json."""
        settings = self._load_settings()

        ntid = (username or settings.get("username", "") or "").strip()
        unc = (pc_save_path or settings.get("pc_save_path", "") or "").strip()

        if password is not None:
            pwd = str(password)
        else:
            pwd = ""
            enc_password = settings.get("password")
            if enc_password:
                try:
                    pwd = self.decrypt_password(enc_password)
                except Exception:
                    pwd = str(enc_password)

        return ntid, pwd, unc

    def _create_face_data_zip(self, output_zip: str) -> str:
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.exists(ENCODINGS_FILE):
                z.write(ENCODINGS_FILE, ENCODINGS_FILE)
            if os.path.exists(DATASET_DIR):
                for root, _dirs, files in os.walk(DATASET_DIR):
                    for file in files:
                        if file.lower().endswith((".jpg", ".jpeg", ".png")):
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, ".")
                            z.write(full_path, rel_path)
        return output_zip

    def _clear_temp_export_packages(self) -> None:
        """Remove old temporary export ZIPs so Pi storage is not wasted."""
        try:
            if not os.path.exists(TEMP_EXPORT_DIR):
                return
            for name in os.listdir(TEMP_EXPORT_DIR):
                if name.lower().endswith(".zip"):
                    try:
                        os.remove(os.path.join(TEMP_EXPORT_DIR, name))
                    except Exception:
                        pass
        except Exception:
            pass

    def export_face_data_to_folder(self, target_folder: Optional[str] = None,
                                   username: Optional[str] = None,
                                   password: Optional[str] = None,
                                   pc_save_path: Optional[str] = None) -> tuple[bool, str, dict]:
        """API helper: export encodings.pickle + dataset to configured server path.

        Called by Windows SAS through /face-data/export. It must accept the
        credentials typed in the SAS Export card, not only settings.json.
        """
        try:
            if target_folder:
                mount_point = target_folder
            else:
                ntid, pwd, unc = self._resolve_server_credentials(username, password, pc_save_path)
                ok_state, message, extra = self.mount_server(
                    username=ntid,
                    password=pwd,
                    unc_path=unc,
                    save=False,
                )
                if not ok_state:
                    return False, message, extra
                mount_point = extra.get("mount_point", SERVER_MOUNT_POINT)

            if not mount_point or not os.path.exists(mount_point):
                return False, "Server/export path does not exist. Please connect server path first.", {}

            os.makedirs(mount_point, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_name = f"face_data_{timestamp}.zip"
            output_zip = os.path.join(mount_point, zip_name)

            self._create_face_data_zip(output_zip)
            self.log(f"Face data exported to server: {output_zip}", "success")
            return True, "Face data exported successfully.", {
                "file": output_zip,
                "filename": zip_name,
                "zip_path": output_zip,
            }

        except Exception as e:
            self._api_last_error = str(e)
            self.log(f"API export failed: {e}", "error")
            return False, f"Export failed: {e}", {}

    def _create_current_face_backup(self, reason: str = "backup_before_import") -> str:
        """Create safety backup before import and store it in pending.

        Export does not need another local backup because the export ZIP itself
        is already a copy of the current data. Import is the operation that can
        change current Pi data, so the backup is created only before import.
        The backup is stored in pending so the user can select it again from
        Check Received if needed.
        """
        os.makedirs(PENDING_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_zip = os.path.join(PENDING_DIR, f"{reason}_{timestamp}.zip")
        if os.path.exists(backup_zip):
            base, ext = os.path.splitext(backup_zip)
            backup_zip = f"{base}_{int(time.time())}{ext}"
        self._create_face_data_zip(backup_zip)
        self.log(f"Backup before import created in pending folder: {backup_zip}", "info")
        return backup_zip

    def list_server_face_data_zips(self, username: Optional[str] = None,
                                  password: Optional[str] = None,
                                  pc_save_path: Optional[str] = None) -> tuple[bool, str, dict]:
        """API helper: list valid SAS face-data export ZIP files from server path."""
        try:
            ntid, pwd, unc = self._resolve_server_credentials(username, password, pc_save_path)
            ok_state, message, extra = self.mount_server(
                username=ntid,
                password=pwd,
                unc_path=unc,
                save=False,
            )
            if not ok_state:
                return False, message, extra

            mount_point = extra.get("mount_point", SERVER_MOUNT_POINT)
            files = []

            for name in os.listdir(mount_point):
                lower = name.lower()
                if not (
                    lower.endswith(".zip")
                    and (
                        lower.startswith("face_data_")
                        or lower.startswith("face_data_backup_")
                    )
                    and not lower.startswith("backup_before_import_")
                ):
                    continue

                path = os.path.join(mount_point, name)

                try:
                    with zipfile.ZipFile(path, "r") as z:
                        names = set(z.namelist())
                        if ENCODINGS_FILE not in names:
                            continue
                except Exception:
                    continue

                try:
                    stat = os.stat(path)
                    size = stat.st_size
                    modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                except Exception:
                    size = 0
                    modified = ""

                files.append({
                    "name": name,
                    "path": path,
                    "size": size,
                    "modified": modified,
                })

            files.sort(key=lambda x: x.get("modified", ""), reverse=True)
            return True, f"Found {len(files)} valid face data ZIP file(s).", {
                "files": files,
                "mount_point": mount_point,
            }

        except Exception as e:
            self._api_last_error = str(e)
            self.log(f"API ZIP list failed: {e}", "error")
            return False, f"Failed to list ZIP files: {e}", {}

    def import_face_data_from_zip(self, zip_path: str) -> tuple[bool, str, dict]:
        return self._merge_import_zip_add_new_only(zip_path)

    def _merge_import_zip_add_new_only(self, zip_path: str) -> tuple[bool, str, dict]:
        """Import face backup in add-new-only mode.

        Requirement:
        - Do not skip existing users.
        - Existing users can receive additional new images and encodings.
        - Identical images are not copied again.
        - Encodings for duplicate images are not appended again.
        """
        if not os.path.exists(zip_path):
            return False, "Import file not found.", {}

        import hashlib

        backup_file = self._create_current_face_backup("backup_before_import")
        temp_dir = tempfile.mkdtemp(prefix="face_import_")

        added_ids: list[str] = []
        updated_ids: list[str] = []
        affected_ids: list[str] = []
        copied_files = 0
        duplicate_files = 0
        imported_encodings = 0
        duplicate_encodings = 0

        def file_sha256(path: str) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()

        def encoding_signature(enc) -> str:
            try:
                import numpy as np
                arr = np.asarray(enc, dtype="float32")
                return hashlib.sha256(arr.tobytes()).hexdigest()
            except Exception:
                return hashlib.sha256(repr(enc).encode("utf-8", errors="ignore")).hexdigest()

        def unique_destination(path: str) -> str:
            if not os.path.exists(path):
                return path
            folder = os.path.dirname(path)
            base = os.path.basename(path)
            stem, ext = os.path.splitext(base)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            counter = 1
            while True:
                candidate = os.path.join(folder, f"{stem}_import_{stamp}_{counter}{ext}")
                if not os.path.exists(candidate):
                    return candidate
                counter += 1

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_dir)

            incoming_dataset = os.path.join(temp_dir, DATASET_DIR)
            incoming_encoding = os.path.join(temp_dir, ENCODINGS_FILE)

            os.makedirs(DATASET_DIR, exist_ok=True)

            current_dataset_ids = {
                d.strip().lower()
                for d in os.listdir(DATASET_DIR)
                if os.path.isdir(os.path.join(DATASET_DIR, d))
            } if os.path.exists(DATASET_DIR) else set()

            # Existing image hashes per user. This prevents importing the same picture twice,
            # even when the filename is different.
            existing_hashes_by_user: dict[str, set[str]] = {}
            for user_id in current_dataset_ids:
                user_dir = os.path.join(DATASET_DIR, user_id)
                hashes = set()
                for root, _, files in os.walk(user_dir):
                    for filename in files:
                        path = os.path.join(root, filename)
                        try:
                            hashes.add(file_sha256(path))
                        except Exception:
                            pass
                existing_hashes_by_user[user_id] = hashes

            copied_key_map: dict[str, str] = {}
            copied_original_keys: set[str] = set()
            duplicate_original_keys: set[str] = set()

            # Add-new-only copy:
            # - new user: copy all images
            # - existing user: copy only image files whose SHA256 does not already exist
            if os.path.exists(incoming_dataset):
                for user_id in sorted(os.listdir(incoming_dataset)):
                    src_user_dir = os.path.join(incoming_dataset, user_id)
                    if not os.path.isdir(src_user_dir):
                        continue

                    normalized_id = str(user_id).strip().lower()
                    if not normalized_id:
                        continue

                    dst_user_dir = os.path.join(DATASET_DIR, normalized_id)
                    user_was_existing = normalized_id in current_dataset_ids or os.path.exists(dst_user_dir)

                    os.makedirs(dst_user_dir, exist_ok=True)
                    if normalized_id not in existing_hashes_by_user:
                        existing_hashes_by_user[normalized_id] = set()

                    if user_was_existing:
                        if normalized_id not in updated_ids:
                            updated_ids.append(normalized_id)
                    else:
                        if normalized_id not in added_ids:
                            added_ids.append(normalized_id)
                        current_dataset_ids.add(normalized_id)

                    user_got_new_file = False

                    for root, _, files in os.walk(src_user_dir):
                        rel_root = os.path.relpath(root, src_user_dir)
                        for filename in files:
                            src_file = os.path.join(root, filename)

                            if rel_root == ".":
                                rel_path = filename
                            else:
                                rel_path = os.path.join(rel_root, filename)

                            original_key = f"{normalized_id}/{rel_path}".replace("\\", "/")

                            try:
                                src_hash = file_sha256(src_file)
                            except Exception:
                                src_hash = ""

                            if src_hash and src_hash in existing_hashes_by_user[normalized_id]:
                                duplicate_files += 1
                                duplicate_original_keys.add(original_key)
                                continue

                            dst_file = os.path.join(dst_user_dir, rel_path)
                            os.makedirs(os.path.dirname(dst_file), exist_ok=True)

                            final_dst = unique_destination(dst_file)
                            shutil.copy2(src_file, final_dst)
                            copied_files += 1
                            user_got_new_file = True

                            if src_hash:
                                existing_hashes_by_user[normalized_id].add(src_hash)

                            final_rel = os.path.relpath(final_dst, dst_user_dir)
                            final_key = f"{normalized_id}/{final_rel}".replace("\\", "/")
                            copied_key_map[original_key] = final_key
                            copied_original_keys.add(original_key)

                    if user_got_new_file and normalized_id not in affected_ids:
                        affected_ids.append(normalized_id)

            # Add only encodings that belong to newly copied images.
            # If trained_files aligns with encodings, use trained_files as the accurate mapping.
            # Also protect with encoding hash to avoid duplicated encoding vectors.
            if os.path.exists(incoming_encoding) and (copied_original_keys or affected_ids):
                local_data = self._load_encoding_data_safe()

                try:
                    with open(incoming_encoding, "rb") as f:
                        incoming_data = pickle.load(f)
                except Exception:
                    incoming_data = {"encodings": [], "names": [], "trained_files": []}

                local_encodings = list(local_data.get("encodings", []))
                local_names = [str(x).strip().lower() for x in local_data.get("names", [])]
                local_trained_files = [str(x).replace("\\", "/") for x in local_data.get("trained_files", [])]

                existing_encoding_sigs = set()
                for enc, name in zip(local_encodings, local_names):
                    existing_encoding_sigs.add((str(name).strip().lower(), encoding_signature(enc)))

                incoming_encodings = list(incoming_data.get("encodings", []))
                incoming_names = [str(x).strip().lower() for x in incoming_data.get("names", [])]
                incoming_trained_files = [str(x).replace("\\", "/") for x in incoming_data.get("trained_files", [])]

                trained_files_set = set(local_trained_files)

                has_aligned_trained_files = len(incoming_trained_files) == len(incoming_encodings)

                for idx, (enc, name_id) in enumerate(zip(incoming_encodings, incoming_names)):
                    if not name_id:
                        continue

                    incoming_key = ""
                    mapped_key = ""

                    if has_aligned_trained_files:
                        incoming_key = incoming_trained_files[idx]
                        mapped_key = copied_key_map.get(incoming_key, "")
                        if not mapped_key:
                            # The source image was duplicate or not copied, so do not add its encoding.
                            duplicate_encodings += 1
                            continue
                    else:
                        # Fallback when old encodings.pickle has no aligned trained_files:
                        # only add encodings for users who got at least one new file,
                        # then dedupe by encoding vector.
                        if name_id not in set(affected_ids):
                            duplicate_encodings += 1
                            continue
                        mapped_key = ""

                    sig = (name_id, encoding_signature(enc))
                    if sig in existing_encoding_sigs:
                        duplicate_encodings += 1
                        continue

                    local_encodings.append(enc)
                    local_names.append(name_id)
                    existing_encoding_sigs.add(sig)
                    imported_encodings += 1

                    if mapped_key:
                        trained_files_set.add(mapped_key)

                local_data["encodings"] = local_encodings
                local_data["names"] = local_names
                local_data["trained_files"] = list(trained_files_set)

                with open(ENCODINGS_FILE, "wb") as f:
                    pickle.dump(local_data, f)

            self._refresh_dataset_ui()

            affected_ids = sorted(set(affected_ids))
            added_ids = sorted(set(added_ids))
            updated_ids = sorted(set(updated_ids))

            if copied_files or imported_encodings:
                message = (
                    f"Import completed. New users: {len(added_ids)}, updated users: {len(updated_ids)}, "
                    f"new images added: {copied_files}, duplicate images ignored: {duplicate_files}, "
                    f"encodings added: {imported_encodings}."
                )
            else:
                message = (
                    f"Import completed. No new data added. "
                    f"Duplicate images ignored: {duplicate_files}, duplicate encodings ignored: {duplicate_encodings}."
                )

            self.log(
                f"Import add-new-only completed. New users={added_ids}; updated users={updated_ids}; "
                f"new_images={copied_files}; duplicate_images={duplicate_files}; "
                f"encodings_added={imported_encodings}; duplicate_encodings={duplicate_encodings}",
                "success" if (copied_files or imported_encodings) else "warn"
            )

            return True, message, {
                "backup": backup_file,
                "added_ids": affected_ids,
                "imported_users": affected_ids,
                "imported_ids": len(affected_ids),
                "new_users": added_ids,
                "updated_users": updated_ids,
                "new_users_count": len(added_ids),
                "updated_users_count": len(updated_ids),
                "files_added": copied_files,
                "duplicate_files": duplicate_files,
                "encodings_added": imported_encodings,
                "duplicate_encodings": duplicate_encodings,
                "skipped_ids": [],
                "skipped_users_count": 0,
                "skipped_users_preview": [],
                "import_mode": "add_new_only",
                "zip_path": zip_path,
            }

        except Exception as e:
            self._api_last_error = str(e)
            self.log(f"Import failed: {e}", "error")
            return False, f"Import failed: {e}", {"backup": backup_file}

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)



    def get_sftp_import_target(self) -> tuple[bool, str, dict]:
        """Return an absolute temp_import folder for SAS local-ZIP SFTP upload."""
        try:
            import_dir = os.path.abspath(TEMP_IMPORT_DIR)
            os.makedirs(import_dir, exist_ok=True)
            self.log(f"SFTP import target prepared: {import_dir}", "info")
            return True, "SFTP import target folder prepared.", {
                "remote_dir": import_dir,
                "import_dir": import_dir,
            }
        except Exception as e:
            self._api_last_error = str(e)
            self.log(f"Prepare SFTP import target failed: {e}", "error")
            return False, f"Prepare SFTP import target failed: {e}", {}


    def prepare_sftp_download_package(self) -> tuple[bool, str, dict]:
        """Create a temporary face-data ZIP for Windows SAS to download by SFTP.

        The Windows SAS app uses SFTP pull mode: it first calls this API route
        to create the ZIP, then connects to the Pi SSH/SFTP server and downloads
        the returned absolute remote_path.
        """
        try:
            os.makedirs(TEMP_EXPORT_DIR, exist_ok=True)
            self._clear_temp_export_packages()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            # Keep the Windows SFTP download ZIP naming consistent with
            # Export to Server Path so both transfer methods produce the
            # same filename pattern.
            zip_name = f"face_data_{timestamp}.zip"
            local_zip = os.path.abspath(os.path.join(TEMP_EXPORT_DIR, zip_name))

            self._create_face_data_zip(local_zip)
            self.log(f"Prepared SFTP download package: {local_zip}", "success")

            return True, "Face data package prepared for Windows SFTP download.", {
                "remote_path": local_zip,
                "zip_path": local_zip,
                "filename": zip_name,
            }

        except Exception as e:
            self._api_last_error = str(e)
            self.log(f"Prepare SFTP download package failed: {e}", "error")
            return False, f"Prepare SFTP download package failed: {e}", {}



    def sftp_send_face_data(
        self,
        host: str,
        username: str,
        password: str,
        remote_dir: str,
        port: int = 22
    ) -> tuple[bool, str, dict]:

        if paramiko is None:
            return False, "Paramiko is not installed. Install python3-paramiko first.", {}

        host = host.strip()
        username = username.strip()
        password = password.strip()
        remote_dir = remote_dir.strip().replace("\\", "/").rstrip("/")

        if not host or not username or not password or not remote_dir:
            return False, "Please fill in host, username, password and remote folder.", {}

        local_zip = None
        transport = None
        sftp = None

        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            device = self._device_name().replace(" ", "_")
            zip_name = f"face_data_from_{device}_{timestamp}.zip"

            os.makedirs(TEMP_EXPORT_DIR, exist_ok=True)
            local_zip = os.path.join(TEMP_EXPORT_DIR, zip_name)

            self._create_face_data_zip(local_zip)

            transport = paramiko.Transport((host, int(port)))
            transport.connect(username=username, password=password)

            sftp = paramiko.SFTPClient.from_transport(transport)

            if sftp is None:
                return False, "SFTP connection was not created.", {}

            self._sftp_ensure_remote_dir(sftp, remote_dir)

            remote_file = remote_dir + "/" + zip_name

            sftp.put(local_zip, remote_file)

            self.log(f"Face data sent to {host}: {remote_file}", "success")

            return True, "Face data sent successfully.", {
                "host": host,
                "remote_file": remote_file,
                "filename": zip_name
            }

        except Exception as e:
            self._api_last_error = str(e)
            return False, f"SFTP send failed: {e}", {}

        finally:
            try:
                if sftp is not None:
                    sftp.close()
            except Exception:
                pass

            try:
                if transport is not None:
                    transport.close()
            except Exception:
                pass

            try:
                if local_zip and os.path.exists(local_zip):
                    os.remove(local_zip)
            except Exception:
                pass

    def _sftp_ensure_remote_dir(self, sftp, remote_dir: str) -> None:
        parts = [p for p in remote_dir.replace("\\", "/").split("/") if p]
        current = "/" if remote_dir.startswith("/") else ""
        for part in parts:
            current = current + part if current in ("", "/") else current + "/" + part
            try:
                sftp.stat(current)
            except Exception:
                sftp.mkdir(current)

    def list_received_face_data(self) -> list[dict]:
        files = []
        if os.path.exists(PENDING_DIR):
            for name in os.listdir(PENDING_DIR):
                if name.lower().endswith(".zip"):
                    path = os.path.join(PENDING_DIR, name)
                    files.append({"filename": name, "size": os.path.getsize(path), "modified": os.path.getmtime(path), "path": path})
        return files

    def _cleanup_accepted_folder(self, keep_latest: int = 3) -> None:
        """Keep only the latest accepted ZIP files to avoid wasting Pi storage."""
        try:
            if keep_latest <= 0 or not os.path.exists(ACCEPTED_DIR):
                return

            files = []
            for name in os.listdir(ACCEPTED_DIR):
                if not name.lower().endswith(".zip"):
                    continue
                path = os.path.join(ACCEPTED_DIR, name)
                if os.path.isfile(path):
                    files.append((os.path.getmtime(path), path))

            files.sort(reverse=True)
            for _mtime, path in files[keep_latest:]:
                try:
                    os.remove(path)
                    self.log(f"Old accepted face data ZIP deleted: {os.path.basename(path)}", "info")
                except Exception:
                    pass
        except Exception:
            pass


    def reject_received_face_data(self, filename: str) -> tuple[bool, str, dict]:
        filename = os.path.basename(filename)
        path = os.path.abspath(os.path.join(PENDING_DIR, filename))
        if not path.startswith(os.path.abspath(PENDING_DIR)):
            return False, "Invalid filename.", {}
        if not os.path.exists(path):
            return False, "File not found.", {}

        os.remove(path)
        self.log(f"Rejected received face data deleted: {filename}", "warn")
        return True, "Received file rejected and deleted.", {"filename": filename, "deleted": True}

    

    def _notify_gui_state(self, state, message=None):
        try:
            if self.gui and hasattr(self.gui, "sync_face_runtime_ui"):
                self.gui.sync_face_runtime_ui(state, message)
        except Exception as e:
            print("[SERVICE UI NOTIFY ERROR]", e)


    def accept_received_face_data(self, filename: str) -> tuple[bool, str, dict]:
        filename = os.path.basename(filename)
        path = os.path.abspath(os.path.join(PENDING_DIR, filename))
        if not path.startswith(os.path.abspath(PENDING_DIR)):
            return False, "Invalid filename.", {}
        if not os.path.exists(path):
            return False, "File not found.", {}
        ok, msg, extra = self._merge_import_zip_add_new_only(path)
        if ok:
            os.makedirs(ACCEPTED_DIR, exist_ok=True)
            accepted_path = os.path.join(ACCEPTED_DIR, filename)
            if os.path.exists(accepted_path):
                base, ext = os.path.splitext(filename)
                accepted_path = os.path.join(ACCEPTED_DIR, f"{base}_{int(time.time())}{ext}")
            shutil.move(path, accepted_path)
            extra["accepted_path"] = accepted_path
            self._cleanup_accepted_folder(keep_latest=3)
        return ok, msg, extra
