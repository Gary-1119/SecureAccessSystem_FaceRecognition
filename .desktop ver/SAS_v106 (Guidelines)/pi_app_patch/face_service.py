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
import re
import uuid
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from recog import (
    start_recognition,
    write_local_recognition_result,
)
from train import train_model
from camera_rotation import normalize_camera_rotation
from system_storage import get_system_storage as read_system_storage
from backup_retention import (
    DELETE_BACKUP_RETENTION_DAYS,
    cleanup_delete_backups,
)


ENCODINGS_FILE = "encodings.pickle"
DATASET_DIR = "dataset"
USER_JSON_FILE = "user.json"
LOG_DIR = "LOG"
ADMIN_FILE = "admins.txt"
SETTINGS_FILE = "settings.json"

# Local emergency admin is intentionally hard-coded only. It must never be
# stored in admins.txt, so the first real AD login can still bootstrap admin.
DEVELOPER_ADMIN_NTID = "admin"
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

# Multi-Pi SFTP target list and transfer defaults. The text file is intentionally
# stored beside the Pi application so both the local Pi UI and the future SAS UI
# can operate on the same saved hostname list through the Pi HTTP API.
SFTP_TARGETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sftp_target.txt")
SFTP_MULTI_TEMP_FOLDER = "multi_sftp"
SFTP_MULTI_MAX_WORKERS = 4
SFTP_MULTI_PACKAGE_TTL_SECONDS = 24 * 60 * 60


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
        self._api_latest_frame_at = 0.0
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

        self._multi_sftp_lock = threading.RLock()
        self._multi_sftp_batches: dict[str, dict] = {}
        self._ensure_first_start_files()
        self._ensure_transfer_folders()
        self._ensure_sftp_targets_file()
        self._cleanup_stale_multi_sftp_packages()
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
            self._api_latest_frame_at = time.monotonic()

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

    def _ensure_first_start_files(self) -> None:
        """Create local files/folders required on a freshly imaged Desktop Pi."""
        for folder in (
            DATASET_DIR,
            LOG_DIR,
            RECEIVED_DIR,
            PENDING_DIR,
            ACCEPTED_DIR,
            REJECTED_DIR,
            TEMP_EXPORT_DIR,
            TEMP_IMPORT_DIR,
        ):
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(USER_JSON_FILE):
            with open(USER_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)

        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "username": "",
                    "password": "",
                    "pc_save_path": "",
                    "auto_capture": False,
                    "camera_rotation": 0,
                    "unlock_transport": "websocket",
                }, f, indent=4)

        if not os.path.exists(ADMIN_FILE):
            open(ADMIN_FILE, "a", encoding="utf-8").close()
        self._remove_developer_admin_from_admin_file()

    def _remove_developer_admin_from_admin_file(self) -> None:
        if not os.path.exists(ADMIN_FILE):
            return
        try:
            with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.read().splitlines()]
            cleaned: list[str] = []
            seen: set[str] = set()
            changed = False
            for line in lines:
                if not line:
                    continue
                key = line.lower()
                if key == DEVELOPER_ADMIN_NTID.lower():
                    changed = True
                    continue
                if key in seen:
                    changed = True
                    continue
                seen.add(key)
                cleaned.append(line)
            if changed:
                with open(ADMIN_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(cleaned))
                    if cleaned:
                        f.write("\n")
        except Exception as exc:
            self.log(f"Could not clean {ADMIN_FILE}: {exc}", "warn")

    def _ensure_transfer_folders(self) -> None:
        for folder in (RECEIVED_DIR, PENDING_DIR, ACCEPTED_DIR, REJECTED_DIR, TEMP_EXPORT_DIR, TEMP_IMPORT_DIR):
            os.makedirs(folder, exist_ok=True)
        os.makedirs(self._multi_sftp_temp_dir(), exist_ok=True)

    def get_system_storage(self) -> dict:
        """Return the live Raspberry Pi root-filesystem storage snapshot.

        This deliberately reads only filesystem metadata. It does not scan the
        dataset or other folders, so the SAS/API request stays lightweight.
        """
        return read_system_storage("/")

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
        """Reset Pi-local diagnostic recognition state only.

        Workstation unlock is delivered by the WebSocket API.  This method no
        longer writes recognition_result.json to SMB or queues a server copy.
        """
        data = {
            "detected": False,
            "user_id": None,
            "confidence": 0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "settings_sync_local_only",
        }

        if not write_local_recognition_result(data):
            self.log("Failed to reset local recognition_result.json.", "warn")

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

        camera_rotation = normalize_camera_rotation(settings.get("camera_rotation", 0))
        settings["camera_rotation"] = camera_rotation

        return {
            "settings": settings,
            "pc_save_path": self.pc_save_path,
            "auto_capture": self.auto_capture_enabled,
            "camera_rotation": camera_rotation,
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
            # Preserve non-server settings, including camera_rotation.
            new_settings = self._load_settings().copy()
            new_settings.update({
                "username": username,
                "password": self.encrypt_password(password),
                "pc_save_path": unc_path,
                "auto_capture": self.auto_capture_enabled,
            })
            self._save_settings_file(new_settings)

        self.log(f"Server mounted successfully: {unc_path}", "success")
        return True, "Connected to server successfully.", {"server_path": unc_path, "mount_point": mount_point}

    def _api_save_settings_request(self, payload: dict) -> tuple[bool, str, dict]:
        """Save settings pushed from Windows SAS into Pi ``settings.json``.

        The endpoint supports two safe request types:
        1. Full server-settings sync (NTID/password/server path/auto-capture).
        2. Rotation-only or auto-capture-only updates, which do not remount SMB.

        Camera rotation is stored on the Pi and applied at the camera source, so
        the Pi GUI and all SAS video panels always use the same orientation.
        """
        payload = payload or {}
        current_settings = self._load_settings().copy()

        server_fields = ("username", "password", "pc_save_path")
        has_server_update = any(key in payload for key in server_fields)
        has_auto_capture_update = "auto_capture" in payload
        has_rotation_update = "camera_rotation" in payload

        if not (has_server_update or has_auto_capture_update or has_rotation_update):
            return False, "No supported settings were provided.", {}

        extra = {}
        username = str(current_settings.get("username", "") or "").strip()
        pc_save_path = str(current_settings.get("pc_save_path", "") or "").strip()
        password = None

        if has_server_update:
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", "")).strip()
            pc_save_path = str(payload.get("pc_save_path", "")).strip()

            if not username or not password or not pc_save_path:
                return False, "Please fill in NTID, password and server path.", {}

            # Mount first. Do not persist invalid SMB credentials/path.
            ok_state, message, extra = self.mount_server(
                username=username,
                password=password,
                unc_path=pc_save_path,
                save=False,
            )
            if not ok_state:
                return False, message, extra

            current_settings.update({
                "username": username,
                "password": self.encrypt_password(password),
                "pc_save_path": pc_save_path,
            })

        if has_auto_capture_update:
            self.auto_capture_enabled = self._coerce_bool(
                payload.get("auto_capture"),
                default=self._coerce_bool(current_settings.get("auto_capture", False)),
            )
            current_settings["auto_capture"] = self.auto_capture_enabled
        else:
            self.auto_capture_enabled = self._coerce_bool(
                current_settings.get("auto_capture", self.auto_capture_enabled),
                default=self.auto_capture_enabled,
            )

        camera_rotation = normalize_camera_rotation(current_settings.get("camera_rotation", 0))
        if has_rotation_update:
            camera_rotation = normalize_camera_rotation(
                payload.get("camera_rotation"),
                default=camera_rotation,
            )
        current_settings["camera_rotation"] = camera_rotation

        current_settings.update({
            "unlock_transport": "websocket",
            "recognition_result_file": "local diagnostic only",
            "server_mount_point": SERVER_MOUNT_POINT,
            "last_synced_from": str(payload.get("source", "Windows SAS")),
            "last_synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save_settings_file(current_settings)

        if has_server_update:
            self.pc_save_path = SERVER_MOUNT_POINT

        # Keep the optional local Pi GUI aligned without restarting its camera.
        try:
            if self.gui is not None:
                if has_server_update:
                    self.gui.pc_save_path = pc_save_path
                    if hasattr(self.gui, "pc_path_entry"):
                        try:
                            self.gui.pc_path_entry.config(state="normal")
                            self.gui.pc_path_entry.delete(0, "end")
                            self.gui.pc_path_entry.insert(0, pc_save_path)
                            self.gui.pc_path_entry.config(state="readonly")
                        except Exception:
                            pass

                self.gui.auto_capture_enabled = self.auto_capture_enabled
                if hasattr(self.gui, "apply_camera_rotation_setting"):
                    self._run_in_gui_thread(
                        lambda: self.gui.apply_camera_rotation_setting(
                            camera_rotation,
                            source=str(payload.get("source", "Windows SAS")),
                            persist=False,
                            log_change=False,
                        )
                    )
                else:
                    self.gui.camera_rotation = camera_rotation
        except Exception:
            pass

        # Reset the remote SAS state only after a successful server-settings sync.
        # A rotation-only update never touches the SMB mount.
        if has_server_update:
            self._reset_recognition_result_file()

        changes = []
        if has_server_update:
            changes.append(f"Path={pc_save_path}")
        if has_auto_capture_update:
            changes.append(f"Auto-Capture={'Enabled' if self.auto_capture_enabled else 'Disabled'}")
        if has_rotation_update:
            changes.append(f"Camera Rotation={camera_rotation}°")
        self.log(
            "Settings synced from Windows SAS. " + (", ".join(changes) or "No visible change."),
            "success",
        )

        return True, "Pi settings synced successfully.", {
            **extra,
            "settings": {
                "username": username if has_server_update else str(current_settings.get("username", "") or ""),
                "pc_save_path": pc_save_path if has_server_update else str(current_settings.get("pc_save_path", "") or ""),
                "auto_capture": self.auto_capture_enabled,
                "camera_rotation": camera_rotation,
                "unlock_transport": "websocket",
                "recognition_result_file": "local diagnostic only",
                "server_mount_point": SERVER_MOUNT_POINT,
            },
            "camera_rotation": camera_rotation,
        }


    # --------------------------------------------------------
    # Admin logic
    # --------------------------------------------------------
    def _load_admin(self) -> list[str]:
        self.admin_list = []
        self._remove_developer_admin_from_admin_file()
        if os.path.exists(ADMIN_FILE):
            try:
                with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                seen: set[str] = set()
                admins: list[str] = []
                for line in lines:
                    ntid = line.strip()
                    key = ntid.lower()
                    if not ntid or key == DEVELOPER_ADMIN_NTID.lower() or key in seen:
                        continue
                    seen.add(key)
                    admins.append(ntid)
                self.admin_list = admins
            except Exception:
                self.admin_list = []
        return self.admin_list

    def _save_admin_file(self) -> None:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in self.admin_list:
            ntid = str(item or "").strip().lower()
            if not ntid or ntid == DEVELOPER_ADMIN_NTID.lower() or ntid in seen:
                continue
            seen.add(ntid)
            cleaned.append(ntid)
        self.admin_list = cleaned
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.admin_list))
            if self.admin_list:
                f.write("\n")

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
        ntid = str(ntid or "").strip().lower()
        if not ntid:
            return False, "Please enter an NTID.", {}
        if ntid == DEVELOPER_ADMIN_NTID.lower():
            return True, "Developer administrator is hard-coded and was not written to admins.txt.", {"admins": self.admin_list}
        self._load_admin()
        admin_ids = {str(item).strip().lower() for item in self.admin_list}
        if ntid in admin_ids:
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
        ntid = str(ntid or "").strip().lower()
        self._load_admin()
        current_user = str(getattr(self.gui, "current_user", self.current_user) or "").strip().lower()
        if ntid == current_user:
            return False, "You cannot remove yourself as admin.", {}
        if len(self.admin_list) <= 1:
            return False, "Cannot remove the last admin.", {}
        admin_ids = {str(item).strip().lower() for item in self.admin_list}
        if ntid not in admin_ids:
            return False, "Admin not found.", {"admins": self.admin_list}
        self.admin_list = [item for item in self.admin_list if str(item).strip().lower() != ntid]
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
            expired_backups_deleted = cleanup_delete_backups()
            if expired_backups_deleted:
                self.log(
                    f"Deleted {len(expired_backups_deleted)} expired pre-delete backup(s) "
                    f"older than {DELETE_BACKUP_RETENTION_DAYS} days.",
                    "info",
                )
            self._refresh_dataset_ui()
            self.log(f"User deleted: {user_id}", "warn")
            return True, "User deleted.", {
                "user_id": user_id,
                "dataset_removed": removed_dataset,
                "encodings_removed": removed_encodings,
                "expired_backups_deleted": len(expired_backups_deleted),
            }
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

    # --------------------------------------------------------
    # Multi-Pi SFTP transfer
    # --------------------------------------------------------
    def _multi_sftp_temp_dir(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            TEMP_EXPORT_DIR,
            SFTP_MULTI_TEMP_FOLDER,
        )

    def _ensure_sftp_targets_file(self) -> None:
        """Create the shared hostname list if it does not exist yet."""
        try:
            folder = os.path.dirname(SFTP_TARGETS_FILE)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if not os.path.exists(SFTP_TARGETS_FILE):
                with open(SFTP_TARGETS_FILE, "w", encoding="utf-8") as file:
                    file.write("# Saved SFTP target Pis. One hostname or IPv4 address per line.\n")
        except Exception as exc:
            self.log(f"Could not initialise sftp_target.txt: {exc}", "error")

    def _validate_sftp_target_host(self, value: str) -> str:
        """Validate a normal hostname, FQDN, or IPv4 address without enforcing a naming prefix."""
        host = str(value or "").strip()
        if not host:
            raise ValueError("Hostname is required.")
        if len(host) > 253:
            raise ValueError("Hostname is too long.")
        if any(ch.isspace() for ch in host) or any(ch in host for ch in ("/", "\\", "@", ":", "#")):
            raise ValueError("Hostname cannot contain spaces or special path characters.")

        try:
            ipaddress.IPv4Address(host)
            return host
        except ValueError:
            pass

        labels = host.split(".")
        if any(not label for label in labels):
            raise ValueError("Hostname contains an empty label.")
        for label in labels:
            if len(label) > 63 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label):
                raise ValueError("Use letters, numbers, hyphens, or dots in a normal hostname format.")
        return host

    def _read_sftp_targets(self) -> list[str]:
        self._ensure_sftp_targets_file()
        targets: list[str] = []
        seen: set[str] = set()
        try:
            with open(SFTP_TARGETS_FILE, "r", encoding="utf-8") as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        host = self._validate_sftp_target_host(line)
                    except ValueError:
                        self.log(f"Ignored invalid target hostname in sftp_target.txt: {line}", "warn")
                        continue
                    key = host.casefold()
                    if key not in seen:
                        seen.add(key)
                        targets.append(host)
        except FileNotFoundError:
            return []
        except Exception as exc:
            self.log(f"Could not read sftp_target.txt: {exc}", "error")
        return targets

    def _write_sftp_targets(self, targets: list[str]) -> None:
        self._ensure_sftp_targets_file()
        with open(SFTP_TARGETS_FILE, "w", encoding="utf-8") as file:
            file.write("# Saved SFTP target Pis. One hostname or IPv4 address per line.\n")
            for host in targets:
                file.write(f"{host}\n")

    def get_multi_sftp_transfer_defaults(self) -> tuple[bool, str, dict]:
        """Return the fixed connection policy used by Pi and future SAS screens."""
        username = getpass.getuser().strip()
        remote_dir = f"/home/{username}/FaceRecognition/received_face_data/pending" if username else ""
        return True, "Multi-Pi SFTP defaults loaded.", {
            "username": username,
            "password_rule": "same_as_username",
            "remote_dir": remote_dir,
            "port": 22,
            "max_workers": SFTP_MULTI_MAX_WORKERS,
            "targets_file": os.path.basename(SFTP_TARGETS_FILE),
        }

    def list_sftp_targets(self) -> tuple[bool, str, dict]:
        targets = self._read_sftp_targets()
        _ok, _message, defaults = self.get_multi_sftp_transfer_defaults()
        return True, f"Loaded {len(targets)} SFTP target(s).", {
            "targets": targets,
            "count": len(targets),
            **defaults,
        }

    def add_sftp_target(self, hostname: str) -> tuple[bool, str, dict]:
        try:
            host = self._validate_sftp_target_host(hostname)
            targets = self._read_sftp_targets()
            if any(item.casefold() == host.casefold() for item in targets):
                return False, f"{host} is already in the saved target list.", {"targets": targets}
            targets.append(host)
            self._write_sftp_targets(targets)
            self.log(f"SFTP target added: {host}", "success")
            return True, f"Added {host}.", {"target": host, "targets": targets, "count": len(targets)}
        except Exception as exc:
            return False, f"Could not add target hostname: {exc}", {}

    def remove_sftp_target(self, hostname: str) -> tuple[bool, str, dict]:
        try:
            host = self._validate_sftp_target_host(hostname)
            targets = self._read_sftp_targets()
            kept = [item for item in targets if item.casefold() != host.casefold()]
            if len(kept) == len(targets):
                return False, f"{host} was not found in the saved target list.", {"targets": targets}
            self._write_sftp_targets(kept)
            self.log(f"SFTP target removed: {host}", "info")
            return True, f"Removed {host}.", {"target": host, "targets": kept, "count": len(kept)}
        except Exception as exc:
            return False, f"Could not remove target hostname: {exc}", {}

    def _cleanup_stale_multi_sftp_packages(self) -> None:
        """Remove old retained packages after one day; never remove an active batch package."""
        try:
            folder = self._multi_sftp_temp_dir()
            os.makedirs(folder, exist_ok=True)
            now = time.time()
            active_paths: set[str] = set()
            lock = getattr(self, "_multi_sftp_lock", None)
            batches = getattr(self, "_multi_sftp_batches", {})
            if lock is not None:
                with lock:
                    active_paths = {
                        str(batch.get("zip_path"))
                        for batch in batches.values()
                        if batch.get("zip_path") and batch.get("status") in {"preparing", "running", "retrying"}
                    }
            for name in os.listdir(folder):
                if not name.lower().endswith(".zip"):
                    continue
                path = os.path.join(folder, name)
                if path in active_paths:
                    continue
                try:
                    if now - os.path.getmtime(path) >= SFTP_MULTI_PACKAGE_TTL_SECONDS:
                        os.remove(path)
                        self.log(f"Deleted old multi-Pi SFTP package: {name}", "info")
                except Exception:
                    pass
        except Exception:
            pass

    def _create_multi_sftp_package(self) -> tuple[str, str]:
        if paramiko is None:
            raise RuntimeError("Paramiko is not installed. Install python3-paramiko first.")
        if not os.path.exists(ENCODINGS_FILE):
            raise FileNotFoundError("encodings.pickle was not found. Train face data before sending.")
        if not os.path.exists(DATASET_DIR):
            raise FileNotFoundError("dataset folder was not found.")

        folder = self._multi_sftp_temp_dir()
        os.makedirs(folder, exist_ok=True)
        self._cleanup_stale_multi_sftp_packages()
        source = re.sub(r"[^A-Za-z0-9-]", "_", self._device_name()) or "Pi"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        zip_name = f"face_data_from_{source}_{timestamp}_{uuid.uuid4().hex[:6]}.zip"
        zip_path = os.path.join(folder, zip_name)
        self._create_face_data_zip(zip_path)
        return zip_path, zip_name

    def _multi_sftp_batch_snapshot(self, batch_id: str) -> tuple[bool, str, dict]:
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            if batch is None:
                return False, "Multi-Pi SFTP transfer batch was not found.", {}
            jobs = []
            for host in batch.get("targets", []):
                job = dict(batch.get("jobs", {}).get(host, {}))
                if job:
                    jobs.append(job)
            return True, "Multi-Pi SFTP transfer status loaded.", {
                "batch_id": batch.get("batch_id"),
                "status": batch.get("status"),
                "created_at": batch.get("created_at"),
                "started_at": batch.get("started_at"),
                "finished_at": batch.get("finished_at"),
                "username": batch.get("username"),
                "remote_dir": batch.get("remote_dir"),
                "filename": batch.get("filename"),
                "max_workers": batch.get("max_workers"),
                "package_state": batch.get("package_state"),
                "package_deleted": bool(batch.get("package_deleted")),
                "message": batch.get("message", ""),
                "jobs": jobs,
                "total": len(jobs),
                "success_count": sum(1 for job in jobs if job.get("state") == "success"),
                "failed_count": sum(1 for job in jobs if job.get("state") == "failed"),
                "queued_count": sum(1 for job in jobs if job.get("state") == "queued"),
                "active_count": sum(1 for job in jobs if job.get("state") in {"connecting", "uploading"}),
            }

    def get_multi_sftp_transfer_status(self, batch_id: str) -> tuple[bool, str, dict]:
        return self._multi_sftp_batch_snapshot(str(batch_id or "").strip())

    def _set_multi_sftp_job(self, batch_id: str, host: str, **changes) -> None:
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            if batch is None:
                return
            job = batch.get("jobs", {}).get(host)
            if job is None:
                return
            job.update(changes)
            job["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def _is_multi_sftp_cancelled(self, batch_id: str) -> bool:
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            return bool(batch and batch.get("cancel_requested"))

    def _multi_sftp_upload_one(self, batch_id: str, host: str) -> None:
        transport = None
        sftp = None
        remote_part = ""
        try:
            with self._multi_sftp_lock:
                batch = self._multi_sftp_batches.get(batch_id)
                if batch is None:
                    return
                if batch.get("cancel_requested"):
                    self._set_multi_sftp_job(batch_id, host, state="cancelled", message="Cancelled before upload started.")
                    return
                username = str(batch.get("username", ""))
                password = str(batch.get("password", ""))
                remote_dir = str(batch.get("remote_dir", ""))
                zip_path = str(batch.get("zip_path", ""))
                filename = str(batch.get("filename", ""))

            if not zip_path or not os.path.exists(zip_path):
                raise FileNotFoundError("The temporary multi-Pi SFTP package is no longer available.")

            self._set_multi_sftp_job(batch_id, host, state="connecting", progress=0, message="Connecting…", error="")
            transport = paramiko.Transport((host, 22))
            transport.banner_timeout = 12
            transport.auth_timeout = 12
            transport.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            if sftp is None:
                raise RuntimeError("SFTP connection was not created.")

            self._sftp_ensure_remote_dir(sftp, remote_dir)
            remote_final = remote_dir.rstrip("/") + "/" + filename
            remote_part = remote_final + ".part"

            try:
                sftp.remove(remote_part)
            except Exception:
                pass

            def _progress(sent: int, total: int) -> None:
                if self._is_multi_sftp_cancelled(batch_id):
                    raise RuntimeError("Transfer cancelled by user.")
                percent = int((sent / total) * 100) if total else 0
                self._set_multi_sftp_job(
                    batch_id,
                    host,
                    state="uploading",
                    progress=max(0, min(100, percent)),
                    message=f"Uploading {max(0, min(100, percent))}%",
                    bytes_sent=int(sent),
                    bytes_total=int(total),
                )

            self._set_multi_sftp_job(batch_id, host, state="uploading", progress=0, message="Uploading 0%")
            sftp.put(zip_path, remote_part, callback=_progress)
            if self._is_multi_sftp_cancelled(batch_id):
                raise RuntimeError("Transfer cancelled by user.")
            sftp.rename(remote_part, remote_final)
            remote_part = ""
            self._set_multi_sftp_job(
                batch_id,
                host,
                state="success",
                progress=100,
                message="Completed",
                remote_file=remote_final,
                error="",
            )
            self.log(f"Multi-Pi SFTP send completed: {host} → {remote_final}", "success")

        except Exception as exc:
            if remote_part and sftp is not None:
                try:
                    sftp.remove(remote_part)
                except Exception:
                    pass
            state = "cancelled" if self._is_multi_sftp_cancelled(batch_id) else "failed"
            message = "Cancelled" if state == "cancelled" else f"Failed: {exc}"
            self._set_multi_sftp_job(batch_id, host, state=state, message=message, error=str(exc))
            self.log(f"Multi-Pi SFTP send failed for {host}: {exc}", "error")

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

    def _finalise_multi_sftp_batch(self, batch_id: str) -> None:
        zip_to_delete = ""
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            if batch is None:
                return
            jobs = list(batch.get("jobs", {}).values())
            failures = [job for job in jobs if job.get("state") in {"failed", "cancelled"}]
            successes = [job for job in jobs if job.get("state") == "success"]
            if failures:
                batch["status"] = "completed_with_failures"
                batch["package_state"] = "retained_for_retry"
                batch["message"] = (
                    f"{len(successes)} completed, {len(failures)} need retry. "
                    "Temporary ZIP retained for Retry Failed."
                )
            else:
                batch["status"] = "completed"
                batch["package_state"] = "deleting"
                batch["message"] = f"All {len(successes)} target Pi transfer(s) completed."
                zip_to_delete = str(batch.get("zip_path") or "")
            batch["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        if zip_to_delete:
            try:
                if os.path.exists(zip_to_delete):
                    os.remove(zip_to_delete)
                with self._multi_sftp_lock:
                    batch = self._multi_sftp_batches.get(batch_id)
                    if batch is not None:
                        batch["package_deleted"] = True
                        batch["package_state"] = "deleted"
            except Exception as exc:
                with self._multi_sftp_lock:
                    batch = self._multi_sftp_batches.get(batch_id)
                    if batch is not None:
                        batch["package_state"] = "retained"
                        batch["message"] += f" Temporary ZIP cleanup failed: {exc}"

    def _run_multi_sftp_batch(self, batch_id: str, hosts: Optional[list[str]] = None, create_package: bool = True) -> None:
        try:
            if create_package:
                with self._multi_sftp_lock:
                    batch = self._multi_sftp_batches.get(batch_id)
                    if batch is None:
                        return
                    batch["status"] = "preparing"
                    batch["package_state"] = "creating"
                    batch["message"] = "Creating one shared face-data ZIP package…"
                    batch["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                zip_path, filename = self._create_multi_sftp_package()
                with self._multi_sftp_lock:
                    batch = self._multi_sftp_batches.get(batch_id)
                    if batch is None:
                        return
                    batch["zip_path"] = zip_path
                    batch["filename"] = filename
                    batch["package_state"] = "ready"
            else:
                with self._multi_sftp_lock:
                    batch = self._multi_sftp_batches.get(batch_id)
                    if batch is None:
                        return
                    if not batch.get("zip_path") or not os.path.exists(str(batch.get("zip_path"))):
                        raise FileNotFoundError("The temporary ZIP was not available for retry.")
                    batch["status"] = "retrying"
                    batch["message"] = "Retrying failed target Pi transfer(s)…"
                    batch["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            with self._multi_sftp_lock:
                batch = self._multi_sftp_batches.get(batch_id)
                if batch is None:
                    return
                run_hosts = list(hosts or batch.get("targets", []))
                batch["status"] = "running" if create_package else "retrying"
                batch["message"] = f"Sending to {len(run_hosts)} target Pi(s), up to {batch.get('max_workers')} at once."
                max_workers = int(batch.get("max_workers", SFTP_MULTI_MAX_WORKERS))

            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="multi-sftp") as executor:
                futures = {executor.submit(self._multi_sftp_upload_one, batch_id, host): host for host in run_hosts}
                for future in as_completed(futures):
                    host = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        self._set_multi_sftp_job(batch_id, host, state="failed", message=f"Failed: {exc}", error=str(exc))

            self._finalise_multi_sftp_batch(batch_id)

        except Exception as exc:
            with self._multi_sftp_lock:
                batch = self._multi_sftp_batches.get(batch_id)
                if batch is not None:
                    batch["status"] = "failed"
                    batch["package_state"] = "not_created"
                    batch["message"] = f"Could not prepare multi-Pi SFTP package: {exc}"
                    batch["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    for job in batch.get("jobs", {}).values():
                        if job.get("state") == "queued":
                            job.update({"state": "failed", "message": f"Package preparation failed: {exc}", "error": str(exc)})
            self.log(f"Multi-Pi SFTP batch preparation failed: {exc}", "error")

    def start_multi_sftp_send(self, hostnames: list[str], max_workers: int = SFTP_MULTI_MAX_WORKERS) -> tuple[bool, str, dict]:
        """Start one ZIP package upload to many saved target hosts, max four active SFTP connections."""
        if paramiko is None:
            return False, "Paramiko is not installed. Install python3-paramiko first.", {}
        if not isinstance(hostnames, list):
            return False, "hostnames must be a list.", {}

        targets: list[str] = []
        seen: set[str] = set()
        try:
            for raw_host in hostnames:
                host = self._validate_sftp_target_host(str(raw_host))
                key = host.casefold()
                if key not in seen:
                    seen.add(key)
                    targets.append(host)
        except Exception as exc:
            return False, f"Invalid target hostname: {exc}", {}

        if not targets:
            return False, "Select at least one target Pi.", {}

        username = getpass.getuser().strip()
        if not username:
            return False, "Could not determine the current Pi username.", {}
        # Requirement for this internal deployment: target SSH password is the
        # same text as the current Pi Linux username. It is not written into
        # sftp_target.txt and is never returned by the API.
        password = username
        remote_dir = f"/home/{username}/FaceRecognition/received_face_data/pending"
        try:
            workers = max(1, min(int(max_workers), SFTP_MULTI_MAX_WORKERS))
        except Exception:
            workers = SFTP_MULTI_MAX_WORKERS

        batch_id = uuid.uuid4().hex[:16]
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        jobs = {
            host: {
                "host": host,
                "state": "queued",
                "progress": 0,
                "message": "Waiting",
                "error": "",
                "bytes_sent": 0,
                "bytes_total": 0,
                "updated_at": created_at,
            }
            for host in targets
        }
        batch = {
            "batch_id": batch_id,
            "status": "preparing",
            "created_at": created_at,
            "started_at": "",
            "finished_at": "",
            "targets": targets,
            "jobs": jobs,
            "username": username,
            "password": password,
            "remote_dir": remote_dir,
            "max_workers": workers,
            "zip_path": "",
            "filename": "",
            "package_state": "creating",
            "package_deleted": False,
            "cancel_requested": False,
            "message": "Preparing shared ZIP package…",
        }
        with self._multi_sftp_lock:
            self._multi_sftp_batches[batch_id] = batch

        threading.Thread(
            target=self._run_multi_sftp_batch,
            args=(batch_id,),
            kwargs={"create_package": True},
            daemon=True,
            name=f"multi-sftp-batch-{batch_id[:6]}",
        ).start()
        self.log(f"Multi-Pi SFTP batch started for {len(targets)} target(s): {', '.join(targets)}", "info")
        return True, "Multi-Pi SFTP transfer started.", {
            "batch_id": batch_id,
            "targets": targets,
            "max_workers": workers,
            "username": username,
            "remote_dir": remote_dir,
        }

    def retry_failed_multi_sftp_transfer(self, batch_id: str) -> tuple[bool, str, dict]:
        batch_id = str(batch_id or "").strip()
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            if batch is None:
                return False, "Multi-Pi SFTP transfer batch was not found.", {}
            if batch.get("status") in {"preparing", "running", "retrying"}:
                return False, "This transfer is still running.", {}
            zip_path = str(batch.get("zip_path") or "")
            retry_hosts = [
                host for host in batch.get("targets", [])
                if batch.get("jobs", {}).get(host, {}).get("state") in {"failed", "cancelled"}
            ]
            if not retry_hosts:
                return False, "There are no failed target Pi transfers to retry.", {}
            if not zip_path or not os.path.exists(zip_path):
                return False, "The temporary ZIP is no longer available. Start a new transfer instead.", {}
            batch["cancel_requested"] = False
            batch["package_deleted"] = False
            batch["package_state"] = "retained_for_retry"
            for host in retry_hosts:
                batch["jobs"][host].update({
                    "state": "queued",
                    "progress": 0,
                    "message": "Waiting to retry",
                    "error": "",
                    "bytes_sent": 0,
                    "bytes_total": 0,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

        threading.Thread(
            target=self._run_multi_sftp_batch,
            args=(batch_id, retry_hosts),
            kwargs={"create_package": False},
            daemon=True,
            name=f"multi-sftp-retry-{batch_id[:6]}",
        ).start()
        self.log(f"Retrying multi-Pi SFTP batch for: {', '.join(retry_hosts)}", "info")
        return True, f"Retry started for {len(retry_hosts)} target Pi(s).", {"batch_id": batch_id, "targets": retry_hosts}

    def cancel_multi_sftp_transfer(self, batch_id: str) -> tuple[bool, str, dict]:
        batch_id = str(batch_id or "").strip()
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            if batch is None:
                return False, "Multi-Pi SFTP transfer batch was not found.", {}
            if batch.get("status") not in {"preparing", "running", "retrying"}:
                return False, "This transfer is not running.", {}
            batch["cancel_requested"] = True
            for job in batch.get("jobs", {}).values():
                if job.get("state") == "queued":
                    job.update({"state": "cancelled", "message": "Cancelled before upload started."})
            batch["message"] = "Cancellation requested. Active uploads will stop at the next progress update."
        return True, "Cancellation requested.", {"batch_id": batch_id}

    def cleanup_multi_sftp_transfer(self, batch_id: str) -> tuple[bool, str, dict]:
        batch_id = str(batch_id or "").strip()
        zip_path = ""
        with self._multi_sftp_lock:
            batch = self._multi_sftp_batches.get(batch_id)
            if batch is None:
                return False, "Multi-Pi SFTP transfer batch was not found.", {}
            if batch.get("status") in {"preparing", "running", "retrying"}:
                return False, "Cannot delete the temporary ZIP while the transfer is running.", {}
            zip_path = str(batch.get("zip_path") or "")
        try:
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            with self._multi_sftp_lock:
                batch = self._multi_sftp_batches.get(batch_id)
                if batch is not None:
                    batch["package_deleted"] = True
                    batch["package_state"] = "deleted"
            return True, "Temporary multi-Pi SFTP package deleted.", {"batch_id": batch_id}
        except Exception as exc:
            return False, f"Could not delete temporary ZIP: {exc}", {}


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
