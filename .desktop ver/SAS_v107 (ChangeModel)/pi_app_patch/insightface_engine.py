from __future__ import annotations

import json
import os
import hashlib
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Optional

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
FACE_DATA_DIR = BASE_DIR / "face_data"
PHOTOS_DIR = FACE_DATA_DIR / "photos"
MODELS_DIR = FACE_DATA_DIR / "models"
USERS_PATH = FACE_DATA_DIR / "users.json"
EMBEDDINGS_PATH = FACE_DATA_DIR / "embeddings.npz"

MODEL_NAME = "buffalo_s"
DET_SIZE = (320, 320)
MATCH_THRESHOLD = 0.38
DUPLICATE_THRESHOLD = 0.995


@dataclass
class UserRecord:
    employee_id: str
    display_name: str
    user_id: str
    sample_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.employee_id,
            "user_id": self.employee_id,
            "ntid": self.employee_id,
            "employee_id": self.employee_id,
            "name": self.display_name,
            "display_name": self.display_name,
            "photos": int(self.sample_count),
            "samples": int(self.sample_count),
            "trained": True,
            "status": "registered",
            "path": str(PHOTOS_DIR / self.employee_id),
        }


@dataclass
class RecognitionMatch:
    detected: bool
    matched: bool
    name: str
    employee_id: str
    confidence: float
    distance: float
    bbox: tuple[int, int, int, int] | None = None


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _normalise_employee_id(value: str) -> str:
    return str(value or "").strip().upper()


def _atomic_write_text(path: Path, text: str, keep_backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_atomic_temp_files()
    if keep_backup and path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            backup.write_bytes(path.read_bytes())
        except Exception:
            pass

    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
    _cleanup_stale_atomic_temp_files()


def _atomic_write_npz(path: Path, arrays: dict[str, np.ndarray], keep_backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_atomic_temp_files()
    if keep_backup and path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            backup.write_bytes(path.read_bytes())
        except Exception:
            pass

    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.savez_compressed(handle, **arrays)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
    _cleanup_stale_atomic_temp_files()


def _cleanup_stale_atomic_temp_files(max_age_seconds: float = 60.0) -> None:
    """Remove abandoned atomic-save temp files left by a killed process."""
    FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for target in (USERS_PATH, EMBEDDINGS_PATH):
        backup_name = target.with_suffix(target.suffix + ".bak").name
        for temp_path in FACE_DATA_DIR.glob(f"{target.name}.*"):
            try:
                if temp_path.name == backup_name:
                    continue
                if temp_path.is_file() and (now - temp_path.stat().st_mtime) > max_age_seconds:
                    temp_path.unlink()
            except Exception:
                pass


class InsightFaceEngine:
    """InsightFace buffalo_s recognition core for the Raspberry Pi app.

    The model is loaded once, registered users are stored as normalised 512D
    embeddings, and recognition compares one query vector against the whole
    matrix in a single NumPy operation.
    """

    def __init__(self) -> None:
        self.lock = RLock()
        self.model: Any = None
        self.model_loaded = False
        self.last_error = ""
        self.users: dict[str, UserRecord] = {}
        self.embeddings: dict[str, list[np.ndarray]] = {}
        self.matrix = np.empty((0, 512), dtype=np.float32)
        self.matrix_user_ids: list[str] = []
        self._users_mtime = 0.0
        self._embeddings_mtime = 0.0
        _cleanup_stale_atomic_temp_files()
        self.reload()

    def ensure_model(self) -> None:
        if self.model_loaded and self.model is not None:
            return

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            from insightface.app import FaceAnalysis

            app = FaceAnalysis(
                name=MODEL_NAME,
                root=str(FACE_DATA_DIR),
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=-1, det_size=DET_SIZE)
            self.model = app
            self.model_loaded = True
            self.last_error = ""
        except Exception as exc:
            self.model = None
            self.model_loaded = False
            self.last_error = str(exc)
            raise RuntimeError(
                "InsightFace buffalo_s is unavailable. Install insightface and "
                "onnxruntime on the Pi, then place/download the buffalo_s model "
                f"under {MODELS_DIR}. Detail: {exc}"
            ) from exc

    def reload(self) -> None:
        with self.lock:
            self.users = self._load_users()
            self.embeddings = self._load_embeddings()
            self._rebuild_matrix()

    def reload_if_changed(self) -> None:
        try:
            users_mtime = USERS_PATH.stat().st_mtime if USERS_PATH.exists() else 0.0
            emb_mtime = EMBEDDINGS_PATH.stat().st_mtime if EMBEDDINGS_PATH.exists() else 0.0
        except Exception:
            return
        if users_mtime != self._users_mtime or emb_mtime != self._embeddings_mtime:
            self.reload()

    def list_users(self) -> list[dict[str, Any]]:
        with self.lock:
            return [self.users[key].to_api() for key in sorted(self.users)]

    def has_face_data(self) -> bool:
        with self.lock:
            return bool(self.users and self.matrix.shape[0] > 0)

    def export_to_zip(self, output_zip: str | Path) -> str:
        """Export only portable registered-user data.

        The InsightFace model files under ``face_data/models`` are runtime
        dependencies downloaded/installed on each Pi. Including them makes a
        two-user export hundreds of MB and is not needed for import, SFTP, or
        SAS backup/restore. Registered face photos are included for audit and
        client review requirements.
        """
        output_path = Path(output_zip)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in (USERS_PATH, EMBEDDINGS_PATH):
                if path.exists() and path.is_file():
                    archive.write(path, path.relative_to(BASE_DIR).as_posix())
            if PHOTOS_DIR.exists():
                for path in sorted(PHOTOS_DIR.rglob("*")):
                    if not path.is_file():
                        continue
                    if path.suffix.lower() in {".tmp", ".part"}:
                        continue
                    archive.write(path, path.relative_to(BASE_DIR).as_posix())
        return str(output_path)

    def is_valid_zip(self, zip_path: str | Path) -> bool:
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                names = {name.replace("\\", "/") for name in archive.namelist()}
            return "face_data/users.json" in names and "face_data/embeddings.npz" in names
        except Exception:
            return False

    def import_from_zip(self, zip_path: str | Path) -> dict[str, Any]:
        source = Path(zip_path)
        if not source.exists():
            raise FileNotFoundError("Import file not found.")
        if not self.is_valid_zip(source):
            raise RuntimeError("ZIP is not an InsightFace face_data package.")

        temp_dir = Path(tempfile.mkdtemp(prefix="face_data_import_"))
        added_users: set[str] = set()
        updated_users: set[str] = set()
        name_conflicts: list[dict[str, str]] = []
        imported_embeddings = 0
        duplicate_embeddings = 0
        copied_photos = 0
        duplicate_photos = 0

        try:
            with zipfile.ZipFile(source, "r") as archive:
                temp_root = temp_dir.resolve()
                for member in archive.infolist():
                    member_name = member.filename.replace("\\", "/")
                    if member_name.startswith("/") or ".." in Path(member_name).parts:
                        raise RuntimeError(f"Unsafe ZIP member path: {member.filename}")
                    target = (temp_dir / member_name).resolve()
                    if not str(target).startswith(str(temp_root)):
                        raise RuntimeError(f"Unsafe ZIP member path: {member.filename}")
                    archive.extract(member, temp_dir)

            incoming_root = temp_dir / "face_data"
            incoming_users = self._read_users_file(incoming_root / "users.json")
            incoming_embeddings = self._read_embeddings_file(incoming_root / "embeddings.npz")

            with self.lock:
                for employee_id, incoming_user in incoming_users.items():
                    current = self.users.get(employee_id)
                    if current is None:
                        self.users[employee_id] = incoming_user
                        added_users.add(employee_id)
                    else:
                        incoming_name = str(incoming_user.display_name or "").strip()
                        current_name = str(current.display_name or "").strip()
                        if incoming_name and current_name and incoming_name != current_name:
                            name_conflicts.append({
                                "employee_id": employee_id,
                                "kept_name": current_name,
                                "incoming_name": incoming_name,
                            })
                        elif incoming_name and not current_name:
                            current.display_name = incoming_name
                            updated_users.add(employee_id)
                        if not current.created_at and incoming_user.created_at:
                            current.created_at = incoming_user.created_at
                        current.updated_at = _now()

                    for embedding in incoming_embeddings.get(employee_id, []):
                        if self._add_embedding_locked(employee_id, embedding):
                            imported_embeddings += 1
                            if employee_id not in added_users:
                                updated_users.add(employee_id)
                        else:
                            duplicate_embeddings += 1

                photos_root = incoming_root / "photos"
                if photos_root.exists():
                    for src in sorted(photos_root.rglob("*")):
                        if not src.is_file():
                            continue
                        rel = src.relative_to(photos_root)
                        parts = rel.parts
                        if not parts:
                            continue
                        employee_id = _normalise_employee_id(parts[0])
                        if employee_id not in self.users:
                            continue
                        dst_dir = PHOTOS_DIR / employee_id
                        dst_dir.mkdir(parents=True, exist_ok=True)
                        src_hash = self._file_sha256(src)
                        if src_hash and self._photo_hash_exists(dst_dir, src_hash):
                            duplicate_photos += 1
                            continue
                        dst = self._unique_path(dst_dir / src.name)
                        shutil.copy2(src, dst)
                        copied_photos += 1
                        if employee_id not in added_users:
                            updated_users.add(employee_id)

                for employee_id, user in self.users.items():
                    user.sample_count = len(self.embeddings.get(employee_id, []))
                    if not user.updated_at:
                        user.updated_at = _now()

                self._save_users_locked()
                self._save_embeddings_locked()
                self._rebuild_matrix()

            return {
                "added_ids": sorted(added_users),
                "updated_ids": sorted(updated_users - added_users),
                "imported_users": sorted(added_users | updated_users),
                "imported_ids": len(added_users | updated_users),
                "new_users": sorted(added_users),
                "updated_users": sorted(updated_users - added_users),
                "new_users_count": len(added_users),
                "updated_users_count": len(updated_users - added_users),
                "embeddings_added": imported_embeddings,
                "duplicate_embeddings": duplicate_embeddings,
                "photos_added": copied_photos,
                "duplicate_photos": duplicate_photos,
                "name_conflicts": name_conflicts,
                "name_conflicts_count": len(name_conflicts),
                "skipped_ids": [],
                "skipped_users_count": 0,
                "skipped_users_preview": [],
                "import_mode": "insightface_merge_by_employee_id",
                "zip_path": str(source),
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _read_users_file(self, path: Path) -> dict[str, UserRecord]:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
        if isinstance(raw, dict):
            raw = list(raw.values())
        users: dict[str, UserRecord] = {}
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            employee_id = _normalise_employee_id(item.get("employee_id") or item.get("ntid") or item.get("id"))
            if not employee_id:
                continue
            users[employee_id] = UserRecord(
                employee_id=employee_id,
                display_name=str(item.get("display_name") or item.get("name") or employee_id).strip(),
                user_id=str(item.get("user_id") or employee_id).strip() or employee_id,
                sample_count=int(item.get("sample_count") or item.get("photos") or 0),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
        return users

    def _read_embeddings_file(self, path: Path) -> dict[str, list[np.ndarray]]:
        if not path.exists():
            return {}
        result: dict[str, list[np.ndarray]] = {}
        with np.load(path, allow_pickle=False) as data:
            for key in data.files:
                employee_id = _normalise_employee_id(key)
                rows = np.asarray(data[key], dtype=np.float32)
                if rows.ndim == 1:
                    rows = rows.reshape(1, -1)
                result[employee_id] = [self._normalise(row) for row in rows if row.size]
        return result

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except Exception:
            return ""

    def _photo_hash_exists(self, folder: Path, source_hash: str) -> bool:
        if not source_hash or not folder.exists():
            return False
        for existing in folder.rglob("*"):
            if existing.is_file() and self._file_sha256(existing) == source_hash:
                return True
        return False

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix or ".png"
        folder = path.parent
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for index in range(1, 10000):
            candidate = folder / f"{stem}_import_{stamp}_{index}{suffix}"
            if not candidate.exists():
                return candidate
        return folder / f"{uuid.uuid4().hex}{suffix}"

    def register_frame(self, display_name: str, employee_id: str, frame: np.ndarray) -> UserRecord:
        self.ensure_model()
        employee_id = _normalise_employee_id(employee_id)
        display_name = str(display_name or employee_id).strip() or employee_id
        if not employee_id:
            raise RuntimeError("Employee ID / NTID is required.")

        frame_bgr = self._ensure_bgr(frame)
        faces = self._detect_faces(frame_bgr)
        if len(faces) != 1:
            raise RuntimeError(f"Registration needs exactly one visible face. Found {len(faces)}.")

        face = faces[0]
        quality_error = self._registration_face_quality_error(frame_bgr, face)
        if quality_error:
            raise RuntimeError(quality_error)
        embedding = self._normalise(getattr(face, "embedding"))

        with self.lock:
            user = self.users.get(employee_id)
            now = _now()
            if user is None:
                user = UserRecord(
                    employee_id=employee_id,
                    display_name=display_name,
                    user_id=employee_id,
                    sample_count=0,
                    created_at=now,
                    updated_at=now,
                )
                self.users[employee_id] = user
            else:
                user.display_name = display_name or user.display_name
                user.updated_at = now

            added = self._add_embedding_locked(employee_id, embedding)
            photo_path = self._save_face_photo(user, frame_bgr, getattr(face, "bbox", None))
            if added or photo_path is not None:
                user.sample_count = len(self.embeddings.get(employee_id, []))
                user.updated_at = now

            self._save_users_locked()
            self._save_embeddings_locked()
            self._rebuild_matrix()
            return user

    def delete_user(self, employee_id: str) -> dict[str, Any]:
        employee_id = _normalise_employee_id(employee_id)
        if not employee_id:
            raise RuntimeError("Employee ID / NTID is required.")

        with self.lock:
            user = self.users.pop(employee_id, None)
            removed_embeddings = len(self.embeddings.pop(employee_id, []))
            removed_photos = False
            photo_dir = PHOTOS_DIR / employee_id
            if photo_dir.exists():
                import shutil

                shutil.rmtree(photo_dir)
                removed_photos = True

            self._save_users_locked()
            self._save_embeddings_locked()
            self._rebuild_matrix()
            return {
                "user_id": employee_id,
                "employee_id": employee_id,
                "dataset_removed": removed_photos,
                "encodings_removed": removed_embeddings,
                "embedding_removed": removed_embeddings,
                "user_removed": user is not None,
            }

    def recognize_frame(self, frame: np.ndarray) -> RecognitionMatch:
        self.ensure_model()
        self.reload_if_changed()
        frame_bgr = self._ensure_bgr(frame)
        faces = self._detect_faces(frame_bgr)
        if not faces:
            return RecognitionMatch(False, False, "Unknown", "", 0.0, 1.0, None)

        face = max(faces, key=lambda item: self._bbox_area(getattr(item, "bbox", None)))
        bbox = self._bbox_tuple(getattr(face, "bbox", None))
        if self.matrix.shape[0] == 0:
            return RecognitionMatch(True, False, "Unknown", "", 0.0, 1.0, bbox)

        query = self._normalise(getattr(face, "embedding"))
        with self.lock:
            scores = self.matrix @ query
            best_index = int(np.argmax(scores))
            score = float(scores[best_index])
            employee_id = self.matrix_user_ids[best_index]
            user = self.users.get(employee_id)

        distance = float(1.0 - score)
        if user is not None and score >= MATCH_THRESHOLD:
            return RecognitionMatch(
                True,
                True,
                user.display_name,
                user.employee_id,
                max(0.0, min(1.0, score)),
                distance,
                bbox,
            )

        return RecognitionMatch(True, False, "Unknown", "", max(0.0, min(1.0, score)), distance, bbox)

    def _detect_faces(self, frame_bgr: np.ndarray) -> list[Any]:
        self.ensure_model()
        if self.model is None:
            return []
        return list(self.model.get(frame_bgr) or [])

    def _load_users(self) -> dict[str, UserRecord]:
        FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not USERS_PATH.exists():
            self._users_mtime = 0.0
            return {}
        try:
            raw = json.loads(USERS_PATH.read_text(encoding="utf-8") or "[]")
            if isinstance(raw, dict):
                raw = list(raw.values())
            users: dict[str, UserRecord] = {}
            for item in raw if isinstance(raw, list) else []:
                if not isinstance(item, dict):
                    continue
                employee_id = _normalise_employee_id(item.get("employee_id") or item.get("ntid") or item.get("id"))
                if not employee_id:
                    continue
                users[employee_id] = UserRecord(
                    employee_id=employee_id,
                    display_name=str(item.get("display_name") or item.get("name") or employee_id).strip(),
                    user_id=str(item.get("user_id") or employee_id).strip() or employee_id,
                    sample_count=int(item.get("sample_count") or item.get("photos") or 0),
                    created_at=str(item.get("created_at") or ""),
                    updated_at=str(item.get("updated_at") or ""),
                )
            self._users_mtime = USERS_PATH.stat().st_mtime
            return users
        except Exception as exc:
            self.last_error = f"users.json load failed: {exc}"
            backup = USERS_PATH.with_suffix(USERS_PATH.suffix + ".bak")
            if backup.exists():
                try:
                    raw = json.loads(backup.read_text(encoding="utf-8") or "[]")
                    return {
                        _normalise_employee_id(item.get("employee_id") or item.get("id")): UserRecord(**item)
                        for item in raw
                        if isinstance(item, dict) and _normalise_employee_id(item.get("employee_id") or item.get("id"))
                    }
                except Exception:
                    pass
            return {}

    def _load_embeddings(self) -> dict[str, list[np.ndarray]]:
        FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not EMBEDDINGS_PATH.exists():
            self._embeddings_mtime = 0.0
            return {}
        try:
            result: dict[str, list[np.ndarray]] = {}
            with np.load(EMBEDDINGS_PATH, allow_pickle=False) as data:
                for key in data.files:
                    employee_id = _normalise_employee_id(key)
                    rows = np.asarray(data[key], dtype=np.float32)
                    if rows.ndim == 1:
                        rows = rows.reshape(1, -1)
                    result[employee_id] = [self._normalise(row) for row in rows if row.size]
            self._embeddings_mtime = EMBEDDINGS_PATH.stat().st_mtime
            return result
        except Exception as exc:
            self.last_error = f"embeddings.npz load failed: {exc}"
            return {}

    def _save_users_locked(self) -> None:
        rows = [asdict(self.users[key]) for key in sorted(self.users)]
        _atomic_write_text(USERS_PATH, json.dumps(rows, indent=2), keep_backup=True)
        try:
            self._users_mtime = USERS_PATH.stat().st_mtime
        except Exception:
            pass

    def _save_embeddings_locked(self) -> None:
        arrays = {
            employee_id: np.vstack(rows).astype(np.float32)
            for employee_id, rows in self.embeddings.items()
            if rows
        }
        _atomic_write_npz(EMBEDDINGS_PATH, arrays, keep_backup=True)
        try:
            self._embeddings_mtime = EMBEDDINGS_PATH.stat().st_mtime
        except Exception:
            pass

    def _add_embedding_locked(self, employee_id: str, embedding: np.ndarray) -> bool:
        rows = self.embeddings.setdefault(employee_id, [])
        if rows:
            existing = np.vstack(rows).astype(np.float32)
            best = float(np.max(existing @ embedding))
            if best >= DUPLICATE_THRESHOLD:
                return False
        rows.append(embedding.astype(np.float32))
        return True

    def _rebuild_matrix(self) -> None:
        vectors: list[np.ndarray] = []
        user_ids: list[str] = []
        for employee_id in sorted(self.embeddings):
            if employee_id not in self.users:
                continue
            for row in self.embeddings.get(employee_id, []):
                vectors.append(self._normalise(row).astype(np.float32))
                user_ids.append(employee_id)
        self.matrix = np.vstack(vectors).astype(np.float32) if vectors else np.empty((0, 512), dtype=np.float32)
        self.matrix_user_ids = user_ids

    def _save_face_photo(self, user: UserRecord, frame_bgr: np.ndarray, bbox: Iterable[float] | None) -> Path | None:
        photo_dir = PHOTOS_DIR / user.employee_id
        photo_dir.mkdir(parents=True, exist_ok=True)
        crop = self._crop_face(frame_bgr, bbox) if bbox is not None else frame_bgr
        filename = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        path = photo_dir / filename
        if crop.ndim == 3 and crop.shape[2] == 4:
            crop = crop[:, :, :3]
        if not cv2.imwrite(str(path), crop):
            return None
        return path

    @staticmethod
    def _ensure_bgr(frame: np.ndarray) -> np.ndarray:
        arr = np.asarray(frame)
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        return np.ascontiguousarray(arr)

    @staticmethod
    def _normalise(embedding: Any) -> np.ndarray:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-12:
            return vector
        return (vector / norm).astype(np.float32)

    @staticmethod
    def _bbox_tuple(bbox: Iterable[float] | None) -> tuple[int, int, int, int] | None:
        if bbox is None:
            return None
        left, top, right, bottom = [int(round(float(value))) for value in bbox]
        return left, top, right, bottom

    @staticmethod
    def _bbox_area(bbox: Iterable[float] | None) -> float:
        if bbox is None:
            return 0.0
        left, top, right, bottom = [float(value) for value in bbox]
        return max(0.0, right - left) * max(0.0, bottom - top)

    @staticmethod
    def _registration_face_quality_error(frame_bgr: np.ndarray, face: Any) -> str:
        bbox = getattr(face, "bbox", None)
        if bbox is None:
            return "Registration needs one clear face. No face box was returned."

        try:
            det_score = float(getattr(face, "det_score", 0.0) or 0.0)
            if det_score and det_score < 0.55:
                return "Face detection is not clear enough for registration."
        except Exception:
            pass

        height, width = frame_bgr.shape[:2]
        if width <= 0 or height <= 0:
            return "Registration frame is invalid."

        left, top, right, bottom = [float(value) for value in bbox]
        face_w = max(0.0, right - left)
        face_h = max(0.0, bottom - top)
        if face_w <= 0 or face_h <= 0:
            return "Registration needs one clear face. Face box is invalid."

        margin_x = max(24.0, width * 0.06)
        margin_y = max(20.0, height * 0.06)
        if left < margin_x or top < margin_y or right > (width - margin_x) or bottom > (height - margin_y):
            return "Move your full face inside the camera frame before registering."

        area_ratio = (face_w * face_h) / float(width * height)
        if area_ratio < 0.045:
            return "Move closer to the camera. Face is too small for registration."
        if area_ratio > 0.68:
            return "Move slightly back. Face is too close to the camera."

        aspect = face_w / face_h
        if aspect < 0.48 or aspect > 1.65:
            return "Face is not fully visible. Look straight at the camera before registering."

        try:
            kps = np.asarray(getattr(face, "kps", []), dtype=np.float32)
            if kps.shape[0] < 5:
                return "Registration needs a complete face with both eyes, nose and mouth visible."
            for x, y in kps[:5]:
                if x < margin_x or y < margin_y or x > (width - margin_x) or y > (height - margin_y):
                    return "Face landmarks are too close to the camera edge. Move your full face inside the frame."
            left_eye, right_eye, _nose, left_mouth, right_mouth = kps[:5]
            eye_gap = float(abs(right_eye[0] - left_eye[0]))
            mouth_gap = float(abs(right_mouth[0] - left_mouth[0]))
            if eye_gap < face_w * 0.16 or mouth_gap < face_w * 0.12:
                return "Registration needs a complete front-facing face. Both sides of the face must be visible."
        except Exception:
            return "Registration needs clear face landmarks. Look straight at the camera before registering."

        return ""

    @staticmethod
    def _crop_face(frame_rgb: np.ndarray, bbox: Iterable[float] | None, padding_ratio: float = 0.35) -> np.ndarray:
        if bbox is None:
            return frame_rgb
        height, width = frame_rgb.shape[:2]
        left, top, right, bottom = [int(round(float(value))) for value in bbox]
        face_w = max(1, right - left)
        face_h = max(1, bottom - top)
        pad_x = int(face_w * padding_ratio)
        pad_y = int(face_h * padding_ratio)
        x1 = max(0, left - pad_x)
        y1 = max(0, top - pad_y)
        x2 = min(width, right + pad_x)
        y2 = min(height, bottom + pad_y)
        if x2 <= x1 or y2 <= y1:
            return frame_rgb
        return frame_rgb[y1:y2, x1:x2].copy()


ENGINE = InsightFaceEngine()


def get_engine() -> InsightFaceEngine:
    return ENGINE
