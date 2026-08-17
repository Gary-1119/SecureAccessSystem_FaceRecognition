"""Retention cleanup for Pi user-delete safety backups.

Only user/embedding backups created before a deletion are removed here.  Import
backup ZIP files in ``received_face_data/pending`` are intentionally excluded.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import List

# "One month" is implemented as 30 calendar days measured from file/folder
# modification time. The Pi GUI runs this cleanup once at startup, once every
# 24 hours, and again after user deletion.
DELETE_BACKUP_RETENTION_DAYS = 30
DELETE_BACKUP_RETENTION_SECONDS = DELETE_BACKUP_RETENTION_DAYS * 24 * 60 * 60


def _is_delete_backup_name(name: str) -> bool:
    """Return True only for pre-delete user/embedding safety backups."""
    lower = str(name or "").lower()
    return (
        lower.startswith("deleted_user_backup_")
        or lower.startswith("embeddings_backup_before_delete_")
        or lower.startswith("embeddings_backup_before_api_delete_")
        or lower in {"users.json.bak", "embeddings.npz.bak"}
    )


def cleanup_delete_backups(
    base_dir: str = ".",
    retention_days: int = DELETE_BACKUP_RETENTION_DAYS,
) -> List[str]:
    """Delete expired user-delete backups in the project root only.

    This function deliberately does *not* traverse folders. Therefore it never
    touches ``received_face_data/pending`` and never deletes import ZIP backups.
    Returns the removed item names for logging.
    """
    try:
        days = max(1, int(retention_days))
    except Exception:
        days = DELETE_BACKUP_RETENTION_DAYS

    threshold_seconds = days * 24 * 60 * 60
    now = time.time()
    removed: List[str] = []

    try:
        root = Path(base_dir).resolve()
        entries = list(root.iterdir())
    except Exception:
        return removed

    for entry in entries:
        # Do not follow symlinks. Only direct, known backup names at project root
        # are eligible for deletion.
        if entry.is_symlink() or not _is_delete_backup_name(entry.name):
            continue

        try:
            age_seconds = now - entry.stat().st_mtime
        except Exception:
            continue

        if age_seconds < threshold_seconds:
            continue

        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            elif entry.is_file():
                entry.unlink()
            else:
                continue
            removed.append(entry.name)
        except Exception:
            # Retention cleanup must never interrupt recognition, capture, import,
            # or a user-delete operation.
            continue

    return removed
