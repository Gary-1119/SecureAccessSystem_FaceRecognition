from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def cleanup_expired_daily_logs(
    log_dir: str | Path,
    retention_days: int = 14,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Delete dated SAS audit logs older than the retention window."""
    return _cleanup_expired_date_named_logs(
        log_dir,
        retention_days=retention_days,
        today=today,
        suffix=".txt",
        description="daily audit log",
    )


def cleanup_expired_daily_app_logs(
    log_dir: str | Path,
    retention_days: int = 14,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Delete dated technical app logs older than the retention window."""
    return _cleanup_expired_date_named_logs(
        log_dir,
        retention_days=retention_days,
        today=today,
        suffix="_app.log",
        description="daily app log",
    )


def _cleanup_expired_date_named_logs(
    log_dir: str | Path,
    retention_days: int,
    today: Optional[date],
    suffix: str,
    description: str,
) -> Dict[str, Any]:
    """Delete files named YYYY-MM-DD<suffix> older than the retention window.

    Non-matching files are deliberately ignored. For example, audit cleanup
    ignores technical app logs, and app cleanup ignores the legacy sas_app.log.
    """
    root = Path(log_dir)
    current_day = today or date.today()
    cutoff = current_day - timedelta(days=max(0, int(retention_days)))
    deleted: List[str] = []
    errors: List[str] = []

    if not root.exists():
        return {"deleted_count": 0, "deleted_files": deleted, "errors": errors}
    if not root.is_dir():
        return {"deleted_count": 0, "deleted_files": deleted, "errors": [f"Not a directory: {root}"]}

    pattern = f"*{suffix}"
    try:
        candidates = list(root.glob(pattern))
    except Exception as exc:
        return {"deleted_count": 0, "deleted_files": deleted, "errors": [str(exc)]}

    for path in candidates:
        stem = path.name[: -len(suffix)]
        try:
            log_date = datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue

        if log_date >= cutoff:
            continue

        try:
            path.unlink()
            deleted.append(str(path))
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    return {
        "deleted_count": len(deleted),
        "deleted_files": deleted,
        "errors": errors,
        "description": description,
    }
