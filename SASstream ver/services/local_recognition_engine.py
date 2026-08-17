from __future__ import annotations

import json
import os
import queue
import shutil
import socket
import threading
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast

import cv2
import numpy as np

from services.app_logging import get_logger, log_exception
from services.atomic_file import atomic_replace, atomic_write_bytes_from_writer, atomic_write_text
from services.face_data_backup import FaceDataBackupManager

try:
    from app_config import RUNTIME_DATA_DIR
except Exception:
    RUNTIME_DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


RTSP_USERNAME = "admin"
RTSP_PASSWORD = "penAteam"
RTSP_PORT = 8554
RTSP_PATH = "jabileye-stream"

FACE_MODEL_NAME = "buffalo_l"
FACE_DETECTION_SIZE = (320, 320)
FACE_DISTANCE_THRESHOLD = 0.35
FACE_UNLOCK_MIN_CONFIDENCE = 0.65
RECOGNITION_EVERY_N_FRAMES = 5
CAPTURE_DRAIN_GRABS = 3
FRAME_QUEUE_SIZE = 1
RTSP_STALE_SECONDS = 15.0
RTSP_FRAME_TIMEOUT_SECONDS = 10.0
UNLOCK_FRAME_MAX_AGE_SECONDS = 1.5
UNLOCK_CONFIRMATION_MATCHES = 3
UNLOCK_CONFIRMATION_WINDOW_SECONDS = 10.0
RTSP_RECONNECT_BASE_SECONDS = 0.5
RTSP_RECONNECT_MAX_SECONDS = 5.0

STABLE_CAPTURE_OPTIONS = (
    "rtsp_transport;tcp|"
    "buffer_size;1048576|"
    "probesize;1000000|"
    "analyzeduration;1000000|"
    "max_delay;500000|"
    "reorder_queue_size;16|"
    "timeout;10000000|"
    "rw_timeout;10000000|"
    "stimeout;10000000"
)

FACE_DATA_DIR = Path(RUNTIME_DATA_DIR) / "face_data"
USERS_PATH = FACE_DATA_DIR / "users.json"
EMBEDDINGS_PATH = FACE_DATA_DIR / "embeddings.npz"
PHOTOS_DIR = FACE_DATA_DIR / "photos"
BACKUPS_DIR = FACE_DATA_DIR / "backups"
MODELS_DIR = FACE_DATA_DIR / "models"
LOGGER = get_logger("recognition")


@dataclass
class UserRecord:
    user_id: str
    display_name: str
    employee_id: str
    created_at: str
    sample_count: int = 0


@dataclass
class FaceMatch:
    name: str
    employee_id: str
    confidence: float
    distance: float
    bbox: Tuple[int, int, int, int]


class UserStore:
    """Local persistent storage for registered users, embeddings and photos."""

    def __init__(self) -> None:
        FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.backups = FaceDataBackupManager(
            FACE_DATA_DIR,
            USERS_PATH,
            EMBEDDINGS_PATH,
            PHOTOS_DIR,
            BACKUPS_DIR,
            LOGGER,
        )
        self.users: Dict[str, UserRecord] = self._load_users()
        self.embeddings: Dict[str, List[np.ndarray]] = self._load_embeddings()

    def list_users(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": user.employee_id,
                "user_id": user.user_id,
                "ntid": user.employee_id,
                "name": user.display_name,
                "display_name": user.display_name,
                "employee_id": user.employee_id,
                "sample_count": user.sample_count,
                "images": user.sample_count,
                "photos": user.sample_count,
                "created_at": user.created_at,
            }
            for user in sorted(self.users.values(), key=lambda item: item.employee_id.upper())
        ]

    def find_by_employee_id(self, employee_id: str) -> Optional[UserRecord]:
        key = str(employee_id or "").strip().upper()
        for user in self.users.values():
            if user.employee_id.upper() == key:
                return user
        return None

    def create_or_get_user(self, display_name: str, employee_id: str) -> UserRecord:
        existing = self.find_by_employee_id(employee_id)
        if existing:
            if display_name and existing.display_name != display_name:
                existing.display_name = display_name.strip()
                self.save_users()
            return existing

        user = UserRecord(
            user_id=str(uuid.uuid4()),
            display_name=display_name.strip(),
            employee_id=employee_id.strip().upper(),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.users[user.user_id] = user
        self.embeddings.setdefault(user.user_id, [])
        (PHOTOS_DIR / user.user_id).mkdir(parents=True, exist_ok=True)
        self.save_users()
        self.save_embeddings()
        return user

    def delete_user(self, employee_or_user_id: str) -> bool:
        target = str(employee_or_user_id or "").strip()
        user = self.users.get(target) or self.find_by_employee_id(target)
        if not user:
            return False

        self.users.pop(user.user_id, None)
        self.embeddings.pop(user.user_id, None)
        shutil.rmtree(PHOTOS_DIR / user.user_id, ignore_errors=True)
        self.save_users()
        self.save_embeddings()
        return True

    def add_embedding(self, user: UserRecord, embedding: np.ndarray) -> bool:
        vector = self._normalize(embedding)
        rows = self.embeddings.setdefault(user.user_id, [])
        for existing in rows:
            if float(np.dot(existing, vector)) >= 0.9995:
                return False
        rows.append(vector.astype(np.float32))
        user.sample_count = len(rows)
        self.save_users()
        self.save_embeddings()
        return True

    def save_face_photo(self, user: UserRecord, frame_rgb: np.ndarray, bbox: Iterable[float]) -> Optional[Path]:
        user_dir = PHOTOS_DIR / user.user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        sample_number = max(1, user.sample_count)
        crop = self._crop_face(frame_rgb, bbox)
        if crop.size == 0:
            return None
        output = user_dir / f"sample_{sample_number:03d}.png"
        temp_output = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp.png")
        ok = cv2.imwrite(str(temp_output), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        if not ok:
            try:
                temp_output.unlink(missing_ok=True)
            except Exception:
                LOGGER.warning("Failed to clean temporary face photo %s", temp_output)
            raise RuntimeError(f"Failed to write face photo: {output}")
        atomic_replace(temp_output, output, keep_backup=False)
        return output

    def all_embedding_rows(self) -> List[Tuple[UserRecord, np.ndarray]]:
        rows: List[Tuple[UserRecord, np.ndarray]] = []
        for user_id, embeddings in self.embeddings.items():
            user = self.users.get(user_id)
            if not user:
                continue
            for embedding in embeddings:
                rows.append((user, embedding))
        return rows

    def reload(self) -> None:
        self.users = self._load_users()
        self.embeddings = self._load_embeddings()

    def create_backup(self, reason: str = "manual") -> Path:
        return self.backups.create_backup(reason)

    def list_backups(self) -> List[Dict[str, Any]]:
        return self.backups.list_backups()

    def restore_backup(self, zip_path: str) -> Dict[str, Any]:
        result = self.backups.restore_backup(zip_path)
        self.reload()
        return result

    def delete_backup(self, zip_path: str) -> Dict[str, Any]:
        return self.backups.delete_backup(zip_path)

    def save_users(self) -> None:
        payload = json.dumps([asdict(user) for user in self.users.values()], indent=2)
        atomic_write_text(USERS_PATH, payload, encoding="utf-8", keep_backup=True)

    def save_embeddings(self) -> None:
        payload: Dict[str, np.ndarray] = {
            user_id: np.stack(rows).astype(np.float32)
            for user_id, rows in self.embeddings.items()
            if rows
        }

        def writer(handle) -> None:
            np.savez_compressed(handle, **cast(Dict[str, Any], payload))

        atomic_write_bytes_from_writer(EMBEDDINGS_PATH, writer, keep_backup=True)

    def export_dataset(self, target_folder: Optional[str] = None) -> Path:
        if not str(target_folder or "").strip():
            raise RuntimeError("Export folder is required.")
        target = Path(str(target_folder).strip())
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = target / f"SAS_face_dataset_{stamp}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if USERS_PATH.exists():
                archive.write(USERS_PATH, "users.json")
            if EMBEDDINGS_PATH.exists():
                archive.write(EMBEDDINGS_PATH, "embeddings.npz")
            if PHOTOS_DIR.exists():
                for path in PHOTOS_DIR.rglob("*"):
                    if path.is_file():
                        archive.write(path, str(Path("photos") / path.relative_to(PHOTOS_DIR)))
        return zip_path

    def import_dataset(self, zip_path: str) -> Dict[str, int]:
        imported_users, imported_embeddings = self._read_dataset_zip(zip_path)
        added_users = 0
        added_embeddings = 0

        for incoming in imported_users.values():
            user = self.find_by_employee_id(incoming.employee_id)
            if not user:
                user = self.create_or_get_user(incoming.display_name, incoming.employee_id)
                added_users += 1
            rows = imported_embeddings.get(incoming.user_id, [])
            for row in rows:
                if self.add_embedding(user, row):
                    added_embeddings += 1

        self._import_photos(zip_path, imported_users)
        self.save_users()
        self.save_embeddings()
        return {"added_users": added_users, "added_embeddings": added_embeddings}

    def _load_users(self) -> Dict[str, UserRecord]:
        if not USERS_PATH.exists():
            return {}
        data = json.loads(self._read_text_with_backup(USERS_PATH))
        users: Dict[str, UserRecord] = {}
        for item in data:
            item.setdefault("employee_id", item.get("ntid", ""))
            item.setdefault("display_name", item.get("name", item.get("employee_id", "")))
            item.setdefault("sample_count", 0)
            item.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
            user = UserRecord(**{key: item[key] for key in UserRecord.__dataclass_fields__ if key in item})
            users[user.user_id] = user
        return users

    def _load_embeddings(self) -> Dict[str, List[np.ndarray]]:
        if not EMBEDDINGS_PATH.exists():
            return {}
        loaded = self._load_npz_with_backup(EMBEDDINGS_PATH)
        try:
            return {
                user_id: [self._normalize(row) for row in loaded[user_id]]
                for user_id in loaded.files
            }
        finally:
            loaded.close()

    def _read_dataset_zip(self, zip_path: str) -> Tuple[Dict[str, UserRecord], Dict[str, List[np.ndarray]]]:
        with zipfile.ZipFile(zip_path, "r") as archive:
            users: Dict[str, UserRecord] = {}
            embeddings: Dict[str, List[np.ndarray]] = {}
            if "users.json" in archive.namelist():
                data = json.loads(archive.read("users.json").decode("utf-8"))
                for item in data:
                    item.setdefault("employee_id", item.get("ntid", ""))
                    item.setdefault("display_name", item.get("name", item.get("employee_id", "")))
                    item.setdefault("sample_count", 0)
                    item.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
                    user = UserRecord(**{key: item[key] for key in UserRecord.__dataclass_fields__ if key in item})
                    users[user.user_id] = user
            if "embeddings.npz" in archive.namelist():
                with archive.open("embeddings.npz") as source:
                    loaded = np.load(source, allow_pickle=False)
                    for user_id in loaded.files:
                        embeddings[user_id] = [self._normalize(row) for row in loaded[user_id]]
            return users, embeddings

    def _import_photos(self, zip_path: str, imported_users: Dict[str, UserRecord]) -> None:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.namelist():
                if not member.startswith("photos/") or member.endswith("/"):
                    continue
                parts = Path(member).parts
                if len(parts) < 3:
                    continue
                incoming_user_id = parts[1]
                incoming = imported_users.get(incoming_user_id)
                if not incoming:
                    continue
                user = self.find_by_employee_id(incoming.employee_id)
                if not user:
                    continue
                user_dir = PHOTOS_DIR / user.user_id
                user_dir.mkdir(parents=True, exist_ok=True)
                filename = Path(member).name
                output = user_dir / filename
                if output.exists():
                    stem = output.stem
                    suffix = output.suffix
                    output = user_dir / f"{stem}_{int(time.time())}{suffix}"
                with archive.open(member) as source, open(output, "wb") as dest:
                    shutil.copyfileobj(source, dest)

    @staticmethod
    def _read_text_with_backup(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            backup = path.with_suffix(path.suffix + ".bak")
            if backup.exists():
                LOGGER.warning("Primary file %s failed to load (%s). Using backup %s", path, exc, backup)
                return backup.read_text(encoding="utf-8")
            raise

    @staticmethod
    def _load_npz_with_backup(path: Path):
        try:
            return np.load(path, allow_pickle=False)
        except Exception as exc:
            backup = path.with_suffix(path.suffix + ".bak")
            if backup.exists():
                LOGGER.warning("Primary embeddings %s failed to load (%s). Using backup %s", path, exc, backup)
                return np.load(backup, allow_pickle=False)
            raise

    @staticmethod
    def _normalize(embedding: np.ndarray) -> np.ndarray:
        vector = np.asarray(embedding, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    @staticmethod
    def _crop_face(frame_rgb: np.ndarray, bbox: Iterable[float], padding_ratio: float = 0.35) -> np.ndarray:
        height, width = frame_rgb.shape[:2]
        left, top, right, bottom = [int(value) for value in bbox]
        face_width = max(right - left, 1)
        face_height = max(bottom - top, 1)
        padding_x = int(face_width * padding_ratio)
        padding_y = int(face_height * padding_ratio)
        return frame_rgb[
            max(top - padding_y, 0):min(bottom + padding_y, height),
            max(left - padding_x, 0):min(right + padding_x, width),
        ]


class EmbeddingIndex:
    def __init__(self) -> None:
        self.users: List[UserRecord] = []
        self.matrix = np.empty((0, 512), dtype=np.float32)

    @property
    def size(self) -> int:
        return len(self.users)

    def rebuild(self, rows: List[Tuple[UserRecord, np.ndarray]]) -> None:
        self.users = [user for user, _ in rows]
        vectors = [embedding.astype(np.float32) for _, embedding in rows]
        self.matrix = np.vstack(vectors).astype(np.float32) if vectors else np.empty((0, 512), dtype=np.float32)

    def search(self, embedding: np.ndarray) -> Tuple[Optional[UserRecord], float, float]:
        if self.size == 0:
            return None, 0.0, 1.0
        query = UserStore._normalize(embedding)
        scores = self.matrix @ query
        best_index = int(np.argmax(scores))
        score = float(scores[best_index])
        return self.users[best_index], score, float(1.0 - score)


class LocalRecognitionEngine:
    """Singleton local RTSP + InsightFace engine replacing the old dlib backend."""

    def __init__(self) -> None:
        self.store = UserStore()
        self.index = EmbeddingIndex()
        self.index.rebuild(self.store.all_embedding_rows())
        self.model = None
        self.model_error = ""
        self.model_loaded = False
        self.host = ""
        self.transport = "tcp"
        self.camera_rotation = 0
        self.capture = None
        self.running = False
        self.capture_thread: Optional[threading.Thread] = None
        self.frame_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=FRAME_QUEUE_SIZE)
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_match: Optional[FaceMatch] = None
        self.last_error = ""
        self.connection_state = "stopped"
        self.reconnect_count = 0
        self.consecutive_read_failures = 0
        self.last_frame_at = 0.0
        self.last_reconnect_at = 0.0
        self.last_recognized_employee_id = ""
        self.last_unlock_event_key = ""
        self.frame_index = 0
        self.lock_session_id = ""
        self._unlock_candidate_employee_id = ""
        self._unlock_candidate_count = 0
        self._unlock_candidate_first_seen = 0.0
        self.unlock_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._worker_lock = threading.RLock()
        self._load_model()

    def configure(self, host: str, transport: str = "tcp") -> None:
        clean_host = self._clean_host(host)
        clean_transport = "udp" if str(transport).lower() == "udp" else "tcp"
        changed = clean_host != self.host or clean_transport != self.transport

        if changed:
            previous_thread = self.capture_thread
            if self.running:
                self.stop(wait=True, timeout=4.0)
            elif previous_thread is not None and previous_thread.is_alive():
                previous_thread.join(timeout=2.0)

            if previous_thread is not None and previous_thread.is_alive():
                previous_thread.join(timeout=6.0)

            if previous_thread is not None and previous_thread.is_alive():
                raise RuntimeError("Previous RTSP stream is still stopping. Please try Connect again in a few seconds.")

            if self.capture_thread is previous_thread:
                self.capture_thread = None
                self.capture = None

            self.latest_frame = None
            self.latest_match = None
            self.last_frame_at = 0.0
            self.last_error = ""
            self.connection_state = "stopped"
            self.consecutive_read_failures = 0
            self._reset_unlock_candidate()

        self.host = clean_host
        self.transport = clean_transport
    def rtsp_url(self, host: Optional[str] = None) -> str:
        clean_host = self._clean_host(host if host is not None else self.host)
        return f"rtsp://{RTSP_USERNAME}:{RTSP_PASSWORD}@{clean_host}:{RTSP_PORT}/{RTSP_PATH}"

    def set_camera_rotation(self, rotation: int) -> None:
        try:
            value = int(rotation)
        except Exception:
            value = 0
        value %= 360
        self.camera_rotation = value if value in (0, 90, 180, 270) else 0

    def _start_capture_worker_locked(self) -> None:
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True, name="SASLocalRTSP")
        self.capture_thread.start()

    def ensure_capture_worker(self) -> None:
        """Restart the RTSP worker if OpenCV/FFmpeg exited unexpectedly."""
        with self._worker_lock:
            if not self.running:
                return
            thread = self.capture_thread
            if thread is not None and thread.is_alive():
                return
            LOGGER.warning("RTSP worker was not alive while recognition was running; restarting")
            self.connection_state = "restarting"
            self.last_error = "RTSP worker restarted by watchdog."
            self._start_capture_worker_locked()

    def start(self) -> Dict[str, Any]:
        if not self.host:
            raise RuntimeError("RTSP hostname is not configured.")
        if not self.model_loaded:
            raise RuntimeError(self.model_error or "Face model is not available.")
        with self._worker_lock:
            if self.running:
                self.ensure_capture_worker()
                return self.status(message="Recognition already running.")
            self.running = True
            self.last_error = ""
            self.connection_state = "starting"
            self.consecutive_read_failures = 0
            self._start_capture_worker_locked()
        return self.status(message="Local RTSP recognition started.")

    def stop(self, wait: bool = False, timeout: float = 3.0) -> Dict[str, Any]:
        """Ask the RTSP worker to stop without releasing FFmpeg cross-thread.

        OpenCV/FFmpeg can abort the whole Python process if VideoCapture is
        released from a different thread while grab/retrieve is active. The
        capture loop owns the object and releases it in its own finally block.
        """
        self.running = False
        self.connection_state = "stopping"
        thread = self.capture_thread
        if wait and thread is not None and thread.is_alive() and thread is not threading.current_thread():
            try:
                thread.join(timeout=max(0.1, float(timeout)))
            except Exception:
                LOGGER.exception("Failed while waiting for RTSP worker to stop")

        if thread is None or not thread.is_alive():
            self.capture_thread = None
            self.capture = None
            self.connection_state = "stopped"
        return self.status(message="Local RTSP recognition stopped.")

    def status(self, message: str = "") -> Dict[str, Any]:
        if self.running:
            self.ensure_capture_worker()
        resolved_ip, resolve_error = self.resolve_host()
        capture_alive = bool(self.capture_thread is not None and self.capture_thread.is_alive())
        frame_age = self.last_frame_age_seconds()
        healthy = self.stream_healthy()
        stream_recovering = bool(
            self.running
            and capture_alive
            and not healthy
            and self.latest_frame is not None
            and frame_age is not None
            and frame_age <= 30.0
        )
        return {
            "ok": True,
            "message": message,
            "recognition_running": bool(self.running),
            "capture_running": capture_alive,
            "model_loaded": bool(self.model_loaded),
            "model_error": self.model_error,
            "host": self.host,
            "camera_host": self.host,
            "resolved_ip": resolved_ip,
            "resolve_error": resolve_error,
            "rtsp_url": self.rtsp_url() if self.host else "",
            "camera_rotation": self.camera_rotation,
            "users": self.store.list_users(),
            "user_count": len(self.store.users),
            "embedding_count": self.index.size,
            "last_error": self.last_error,
            "connection_state": self.connection_state,
            "reconnect_count": self.reconnect_count,
            "consecutive_read_failures": self.consecutive_read_failures,
            "last_frame_age_seconds": frame_age,
            "stream_healthy": healthy,
            "stream_recovering": stream_recovering,
            "last_match": asdict(self.latest_match) if self.latest_match else None,
            "system_user": os.environ.get("USERNAME", ""),
            "hostname": os.environ.get("COMPUTERNAME", ""),
        }

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "message": "Local SAS recognition service ready.", **self.status()}

    def register_current_face(self, display_name: str, employee_id: str) -> Dict[str, Any]:
        if self.latest_frame is None:
            raise RuntimeError("No camera frame is available. Start recognition first.")
        user = self.register_face(display_name, employee_id, self.latest_frame)
        return {"ok": True, "message": f"Registered {user.display_name} {user.employee_id}.", "user": asdict(user)}

    def register_face(self, display_name: str, employee_id: str, frame_rgb: np.ndarray) -> UserRecord:
        faces = self._detect_faces(frame_rgb)
        if not faces:
            raise RuntimeError("Registration needs one visible face.")
        face = faces[0]
        user = self.store.create_or_get_user(display_name or employee_id, employee_id)
        added = self.store.add_embedding(user, face.embedding)
        if added:
            self.store.save_face_photo(user, frame_rgb, face.bbox)
        self.index.rebuild(self.store.all_embedding_rows())
        return user

    def delete_user(self, employee_or_user_id: str) -> Dict[str, Any]:
        deleted = self.store.delete_user(employee_or_user_id)
        self.index.rebuild(self.store.all_embedding_rows())
        return {"ok": deleted, "message": "User deleted." if deleted else "User not found.", "users": self.store.list_users()}

    def set_unlock_callback(self, callback: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        self.unlock_callback = callback

    def set_lock_session(self, lock_session_id: str) -> None:
        self.lock_session_id = str(lock_session_id or "")
        self.last_unlock_event_key = ""
        self.last_recognized_employee_id = ""
        self._reset_unlock_candidate()

    def clear_lock_session(self) -> None:
        self.lock_session_id = ""
        self.last_unlock_event_key = ""
        self.last_recognized_employee_id = ""
        self._reset_unlock_candidate()

    def export_face_data(self, target_folder: Optional[str] = None) -> Dict[str, Any]:
        zip_path = self.store.export_dataset(target_folder)
        return {"ok": True, "message": "Face dataset exported.", "zip_path": str(zip_path), "local_zip": str(zip_path)}

    def import_face_data(self, zip_path: str) -> Dict[str, Any]:
        backup_path = self.store.create_backup("before_import")
        result = self.store.import_dataset(zip_path)
        self.index.rebuild(self.store.all_embedding_rows())
        return {
            "ok": True,
            "message": "Face dataset imported.",
            **result,
            "backup_path": str(backup_path),
            "backup_filename": backup_path.name,
            "users": self.store.list_users(),
        }

    def list_face_backups(self) -> Dict[str, Any]:
        return {"ok": True, "backups": self.store.list_backups()}

    def restore_face_backup(self, zip_path: str) -> Dict[str, Any]:
        safety_backup = self.store.create_backup("before_restore")
        was_running = bool(self.running)
        previous_thread = self.capture_thread
        if was_running:
            self.stop()
            if previous_thread is not None and previous_thread.is_alive():
                previous_thread.join(timeout=3.0)

        try:
            result = self.store.restore_backup(zip_path)
            self.index.rebuild(self.store.all_embedding_rows())
            self.latest_match = None
            self.last_recognized_employee_id = ""
            self.last_unlock_event_key = ""
            response = {
                "ok": True,
                "message": "Face data backup restored.",
                **result,
                "safety_backup_path": str(safety_backup),
                "safety_backup_filename": safety_backup.name,
                "users": self.store.list_users(),
            }
        except Exception:
            LOGGER.exception("Face data backup restore failed")
            raise
        finally:
            if was_running and self.host and self.model_loaded:
                try:
                    self.start()
                except Exception as exc:
                    self.last_error = str(exc)
                    LOGGER.exception("Failed to restart recognition after backup restore")
        return response

    def delete_face_backup(self, zip_path: str) -> Dict[str, Any]:
        result = self.store.delete_backup(zip_path)
        return {"ok": True, "message": "Face data backup deleted.", **result, "backups": self.store.list_backups()}

    def _capture_loop(self) -> None:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = STABLE_CAPTURE_OPTIONS.replace(
            "rtsp_transport;tcp", f"rtsp_transport;{self.transport}"
        )
        reconnect_delay = RTSP_RECONNECT_BASE_SECONDS
        while self.running:
            self.connection_state = "connecting"
            self.last_reconnect_at = time.time()
            capture = cv2.VideoCapture(self.rtsp_url(), cv2.CAP_FFMPEG)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 4)
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
            self.capture = capture
            if not capture.isOpened():
                self.connection_state = "disconnected"
                self.last_error = "Could not open RTSP stream."
                self.latest_match = None
                self._reset_unlock_candidate()
                self.reconnect_count += 1
                LOGGER.warning("RTSP open failed for %s", self.rtsp_url())
                capture.release()
                self._sleep_before_reconnect(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, RTSP_RECONNECT_MAX_SECONDS)
                continue
            try:
                self.connection_state = "live"
                self.last_error = ""
                self.consecutive_read_failures = 0
                reconnect_delay = RTSP_RECONNECT_BASE_SECONDS
                last_valid = time.monotonic()
                while self.running:
                    grabbed = False
                    for _ in range(CAPTURE_DRAIN_GRABS):
                        grabbed = capture.grab()
                        if not grabbed:
                            break
                    if not grabbed:
                        self.consecutive_read_failures += 1
                        if time.monotonic() - last_valid > RTSP_FRAME_TIMEOUT_SECONDS:
                            self.last_error = "RTSP frame grab timed out."
                            self.connection_state = "stale"
                            self.latest_match = None
                            self._reset_unlock_candidate()
                            break
                        time.sleep(0.02)
                        continue
                    ok, frame = capture.retrieve()
                    if not ok or frame is None:
                        self.consecutive_read_failures += 1
                        if time.monotonic() - last_valid > RTSP_FRAME_TIMEOUT_SECONDS:
                            self.last_error = "RTSP frame retrieve timed out."
                            self.connection_state = "stale"
                            self.latest_match = None
                            self._reset_unlock_candidate()
                            break
                        time.sleep(0.02)
                        continue
                    last_valid = time.monotonic()
                    self.last_frame_at = time.time()
                    self.consecutive_read_failures = 0
                    frame = self._apply_rotation_bgr(frame)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    self.latest_frame = frame_rgb
                    self.frame_index += 1
                    if self.frame_index % RECOGNITION_EVERY_N_FRAMES == 0:
                        self._recognize_frame(frame_rgb)
            except Exception as exc:
                self.last_error = str(exc)
                self.connection_state = "error"
                LOGGER.exception("RTSP capture loop error")
            finally:
                try:
                    capture.release()
                except Exception:
                    LOGGER.exception("Failed to release RTSP capture")
                self.capture = None
            if self.running:
                self.reconnect_count += 1
                self._sleep_before_reconnect(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, RTSP_RECONNECT_MAX_SECONDS)
        self.connection_state = "stopped"

    def _sleep_before_reconnect(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.1, float(seconds))
        while self.running and time.monotonic() < deadline:
            time.sleep(0.1)

    def last_frame_age_seconds(self) -> Optional[float]:
        if not self.last_frame_at:
            return None
        return max(0.0, time.time() - self.last_frame_at)

    def stream_healthy(self) -> bool:
        age = self.last_frame_age_seconds()
        return bool(self.running and self.connection_state == "live" and age is not None and age <= RTSP_STALE_SECONDS)

    def _recognize_frame(self, frame_rgb: np.ndarray) -> None:
        faces = self._detect_faces(frame_rgb)
        if not faces:
            self.latest_match = None
            self.last_recognized_employee_id = ""
            self._reset_unlock_candidate()
            return
        face = faces[0]
        bbox = self._bbox_tuple(face.bbox)
        if self.index.size == 0:
            self.latest_match = FaceMatch("Unknown", "", 0.0, 1.0, bbox)
            return
        user, score, distance = self.index.search(face.embedding)
        if user and distance <= FACE_DISTANCE_THRESHOLD:
            match = FaceMatch(user.display_name, user.employee_id, max(0.0, min(1.0, score)), distance, bbox)
            self.latest_match = match
            self._publish_unlock(match)
        else:
            self.latest_match = FaceMatch("Unknown", "", max(0.0, min(1.0, score)), distance, bbox)
            self._reset_unlock_candidate()

    def _publish_unlock(self, match: FaceMatch) -> None:
        if not self.lock_session_id or not self.unlock_callback:
            return
        if float(match.confidence or 0.0) < FACE_UNLOCK_MIN_CONFIDENCE:
            self._reset_unlock_candidate()
            return
        frame_age = self.last_frame_age_seconds()
        if frame_age is None or frame_age > UNLOCK_FRAME_MAX_AGE_SECONDS or not self.stream_healthy():
            self._reset_unlock_candidate()
            return
        if not self._confirm_unlock_candidate(match.employee_id):
            return
        event_key = f"{self.lock_session_id}:{match.employee_id}"
        if event_key == self.last_unlock_event_key:
            return
        self.last_unlock_event_key = event_key
        self.last_recognized_employee_id = match.employee_id
        payload = {
            "type": "recognition_result",
            "detected": True,
            "ntid": match.employee_id,
            "user_id": match.employee_id,
            "name": match.name,
            "confidence": round(match.confidence * 100.0, 2),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "occurred_at": datetime.now().isoformat(timespec="seconds"),
            "event_id": str(uuid.uuid4()),
            "lock_session_id": self.lock_session_id,
            "pi_id": self.host or "LOCAL_RTSP",
        }
        self.unlock_callback(payload)

    def _reset_unlock_candidate(self) -> None:
        self._unlock_candidate_employee_id = ""
        self._unlock_candidate_count = 0
        self._unlock_candidate_first_seen = 0.0

    def _confirm_unlock_candidate(self, employee_id: str) -> bool:
        employee = str(employee_id or "").strip().upper()
        if not employee:
            self._reset_unlock_candidate()
            return False

        now = time.monotonic()
        expired = (
            self._unlock_candidate_first_seen > 0.0
            and now - self._unlock_candidate_first_seen > UNLOCK_CONFIRMATION_WINDOW_SECONDS
        )
        if employee != self._unlock_candidate_employee_id or expired:
            self._unlock_candidate_employee_id = employee
            self._unlock_candidate_count = 1
            self._unlock_candidate_first_seen = now
        else:
            self._unlock_candidate_count += 1

        return self._unlock_candidate_count >= UNLOCK_CONFIRMATION_MATCHES

    def _detect_faces(self, frame_rgb: np.ndarray) -> List[Any]:
        if not self.model_loaded or self.model is None:
            return []
        faces = self.model.get(frame_rgb)
        if not faces:
            return []
        return [max(faces, key=lambda face: self._bbox_area(face.bbox))]

    def _load_model(self) -> None:
        try:
            import pip_system_certs.wrapt_requests  # noqa: F401
        except Exception:
            pass
        try:
            from insightface.app import FaceAnalysis

            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            self.model = FaceAnalysis(name=FACE_MODEL_NAME, root=str(FACE_DATA_DIR), providers=["CPUExecutionProvider"])
            self.model.prepare(ctx_id=-1, det_size=FACE_DETECTION_SIZE)
            self.model_loaded = True
            self.model_error = ""
        except Exception as exc:
            self.model_loaded = False
            self.model_error = str(exc)

    def resolve_host(self, host: Optional[str] = None) -> Tuple[str, str]:
        clean_host = self._clean_host(host if host is not None else self.host)
        if not clean_host:
            return "", ""
        try:
            return socket.gethostbyname(clean_host), ""
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"
    @staticmethod
    def _clean_host(host: Optional[str]) -> str:
        value = str(host or "").strip()
        for prefix in ("http://", "https://", "ws://", "wss://", "rtsp://"):
            if value.startswith(prefix):
                value = value.replace(prefix, "", 1)
        value = value.split("/")[0]
        if ":" in value:
            value = value.split(":")[0]
        return value.strip()

    def _apply_rotation_bgr(self, frame_bgr: np.ndarray) -> np.ndarray:
        rotation = int(getattr(self, "camera_rotation", 0) or 0)
        if rotation == 90:
            return cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
        if rotation == 180:
            return cv2.rotate(frame_bgr, cv2.ROTATE_180)
        if rotation == 270:
            return cv2.rotate(frame_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame_bgr

    @staticmethod
    def _bbox_tuple(bbox: Iterable[float]) -> Tuple[int, int, int, int]:
        left, top, right, bottom = [int(value) for value in bbox]
        return left, top, right, bottom

    @staticmethod
    def _bbox_area(bbox: Iterable[float]) -> float:
        left, top, right, bottom = bbox
        return max(float(right - left), 0.0) * max(float(bottom - top), 0.0)


ENGINE = LocalRecognitionEngine()
