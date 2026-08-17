from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.face_data_backup import FaceDataBackupManager


class FaceDataBackupManagerTests(unittest.TestCase):
    def make_manager(self, root: Path) -> FaceDataBackupManager:
        face_data = root / "face_data"
        return FaceDataBackupManager(
            face_data,
            face_data / "users.json",
            face_data / "embeddings.npz",
            face_data / "photos",
            face_data / "backups",
        )

    def test_create_restore_and_delete_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.make_manager(Path(tmp))
            manager.face_data_dir.mkdir(parents=True, exist_ok=True)
            manager.photos_dir.mkdir(parents=True, exist_ok=True)
            (manager.photos_dir / "user-a").mkdir(parents=True, exist_ok=True)
            manager.users_path.write_text(json.dumps([{"employee_id": "A1", "display_name": "User A"}]), encoding="utf-8")
            manager.embeddings_path.write_bytes(b"embedding-bytes")
            (manager.photos_dir / "user-a" / "sample_001.png").write_bytes(b"png-bytes")

            backup = manager.create_backup("before_import")
            self.assertTrue(backup.exists())
            self.assertEqual(len(manager.list_backups()), 1)

            manager.users_path.write_text(json.dumps([{"employee_id": "B2", "display_name": "User B"}]), encoding="utf-8")
            manager.embeddings_path.write_bytes(b"changed")
            (manager.photos_dir / "user-a" / "sample_001.png").write_bytes(b"changed-photo")

            result = manager.restore_backup(str(backup))
            restored_users = json.loads(manager.users_path.read_text(encoding="utf-8"))
            self.assertEqual(restored_users[0]["employee_id"], "A1")
            self.assertEqual(manager.embeddings_path.read_bytes(), b"embedding-bytes")
            self.assertEqual((manager.photos_dir / "user-a" / "sample_001.png").read_bytes(), b"png-bytes")
            self.assertEqual(result["restored_photos"], 1)

            deleted = manager.delete_backup(str(backup))
            self.assertEqual(deleted["deleted_filename"], backup.name)
            self.assertFalse(backup.exists())

    def test_rejects_backup_outside_local_backup_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = self.make_manager(root)
            outside = root / "outside.zip"
            outside.write_bytes(b"not allowed")
            with self.assertRaises(RuntimeError):
                manager.delete_backup(str(outside))


if __name__ == "__main__":
    unittest.main()
