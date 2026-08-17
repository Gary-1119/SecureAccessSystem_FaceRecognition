from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.atomic_file import atomic_write_bytes_from_writer, atomic_write_text


class FaceDataBackupManager:
    """Versioned local backups for face users, embeddings and PNG photos."""

    def __init__(
        self,
        face_data_dir: Path,
        users_path: Path,
        embeddings_path: Path,
        photos_dir: Path,
        backups_dir: Path,
        logger: Optional[Any] = None,
    ) -> None:
        self.face_data_dir = Path(face_data_dir)
        self.users_path = Path(users_path)
        self.embeddings_path = Path(embeddings_path)
        self.photos_dir = Path(photos_dir)
        self.backups_dir = Path(backups_dir)
        self.logger = logger
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, reason: str = "manual") -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self._unique_backup_path()
        temp_path = zip_path.with_name(f".{zip_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("backup_manifest.json", json.dumps(self._manifest(reason), indent=2))
                if self.users_path.exists():
                    archive.write(self.users_path, "users.json")
                if self.embeddings_path.exists():
                    archive.write(self.embeddings_path, "embeddings.npz")
                if self.photos_dir.exists():
                    for path in self.photos_dir.rglob("*"):
                        if path.is_file():
                            archive.write(path, str(Path("photos") / path.relative_to(self.photos_dir)))
            os.replace(temp_path, zip_path)
            self._fsync_parent(self.backups_dir)
            return zip_path
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                if self.logger:
                    self.logger.warning("Failed to clean temporary backup file %s", temp_path)
            raise

    def list_backups(self) -> List[Dict[str, Any]]:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        rows: List[Dict[str, Any]] = []
        for path in sorted(self.backups_dir.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                stat = path.stat()
                manifest = self._read_manifest(path)
                rows.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "size": stat.st_size,
                        "size_text": self._format_size(stat.st_size),
                        "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                        "created_at": str(manifest.get("created_at") or ""),
                        "reason": str(manifest.get("reason") or ""),
                        "user_count": int(manifest.get("user_count") or 0),
                    }
                )
            except Exception as exc:
                if self.logger:
                    self.logger.warning("Skipping unreadable face data backup %s: %s", path, exc)
        return rows

    def restore_backup(self, zip_path: str) -> Dict[str, Any]:
        backup_path = self._resolve_backup_path(zip_path)
        if not backup_path.exists():
            raise RuntimeError(f"Backup file was not found: {backup_path}")

        restore_id = uuid.uuid4().hex
        temp_photos = self.face_data_dir / f".photos_restore_{restore_id}"
        old_photos = self.face_data_dir / f".photos_old_{restore_id}"
        imported_photo_count = 0

        with zipfile.ZipFile(backup_path, "r") as archive:
            names = set(archive.namelist())
            if not {"users.json", "embeddings.npz", "backup_manifest.json"}.intersection(names):
                raise RuntimeError("Selected ZIP does not look like a SAS face data backup.")

            if "users.json" in names:
                users_text = archive.read("users.json").decode("utf-8")
                json.loads(users_text)
                atomic_write_text(self.users_path, users_text, encoding="utf-8", keep_backup=True)
            else:
                atomic_write_text(self.users_path, "[]", encoding="utf-8", keep_backup=True)

            if "embeddings.npz" in names:
                embedding_bytes = archive.read("embeddings.npz")

                def embedding_writer(handle) -> None:
                    handle.write(embedding_bytes)

                atomic_write_bytes_from_writer(self.embeddings_path, embedding_writer, keep_backup=True)
            else:
                def empty_embeddings_writer(handle) -> None:
                    import numpy as np

                    np.savez_compressed(handle)

                atomic_write_bytes_from_writer(self.embeddings_path, empty_embeddings_writer, keep_backup=True)

            temp_photos.mkdir(parents=True, exist_ok=True)
            for member in archive.namelist():
                relative = self._photo_member_relative_path(member)
                if relative is None:
                    continue
                target = temp_photos / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target, "wb") as destination:
                    shutil.copyfileobj(source, destination)
                imported_photo_count += 1

        if self.photos_dir.exists():
            self.photos_dir.rename(old_photos)
        try:
            temp_photos.rename(self.photos_dir)
        except Exception:
            if old_photos.exists() and not self.photos_dir.exists():
                old_photos.rename(self.photos_dir)
            raise
        finally:
            if old_photos.exists():
                shutil.rmtree(old_photos, ignore_errors=True)
            if temp_photos.exists():
                shutil.rmtree(temp_photos, ignore_errors=True)

        return {
            "backup_path": str(backup_path),
            "backup_filename": backup_path.name,
            "restored_photos": imported_photo_count,
        }

    def delete_backup(self, zip_path: str) -> Dict[str, Any]:
        backup_path = self._resolve_backup_path(zip_path)
        if not backup_path.exists():
            raise RuntimeError(f"Backup file was not found: {backup_path}")
        backup_path.unlink()
        return {"deleted_path": str(backup_path), "deleted_filename": backup_path.name}

    def _unique_backup_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.backups_dir / f"SAS_face_backup_{stamp}.zip"
        if not base.exists():
            return base
        for index in range(1, 100):
            candidate = self.backups_dir / f"SAS_face_backup_{stamp}_{index:02d}.zip"
            if not candidate.exists():
                return candidate
        return self.backups_dir / f"SAS_face_backup_{stamp}_{uuid.uuid4().hex[:8]}.zip"

    def _manifest(self, reason: str) -> Dict[str, Any]:
        return {
            "format": "sas-face-data-backup-v1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reason": str(reason or "manual"),
            "user_count": self._current_user_count(),
        }

    def _current_user_count(self) -> int:
        try:
            if not self.users_path.exists():
                return 0
            data = json.loads(self.users_path.read_text(encoding="utf-8"))
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0

    def _read_manifest(self, path: Path) -> Dict[str, Any]:
        try:
            with zipfile.ZipFile(path, "r") as archive:
                if "backup_manifest.json" in archive.namelist():
                    data = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _resolve_backup_path(self, zip_path: str) -> Path:
        value = str(zip_path or "").strip()
        if not value:
            raise RuntimeError("Backup file is required.")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.backups_dir / value
        resolved = candidate.resolve()
        backups_root = self.backups_dir.resolve()
        if resolved.suffix.lower() != ".zip":
            raise RuntimeError("Backup file must be a ZIP file.")
        if not self._is_relative_to(resolved, backups_root):
            raise RuntimeError("Only local SAS backup files can be restored or deleted.")
        return resolved

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _photo_member_relative_path(member: str) -> Optional[Path]:
        normalized = str(member or "").replace("\\", "/")
        if not normalized.startswith("photos/") or normalized.endswith("/"):
            return None
        parts = [part for part in normalized.split("/")[1:] if part]
        if not parts or any(part in (".", "..") for part in parts):
            return None
        return Path(*parts)

    @staticmethod
    def _format_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024.0 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024.0
        return f"{int(size)} B"

    @staticmethod
    def _fsync_parent(path: Path) -> None:
        try:
            dir_fd = os.open(str(path), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            pass
