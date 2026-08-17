"""Small, dependency-free storage reader for the Raspberry Pi application.

The root filesystem (``/``) is the Raspberry Pi OS filesystem, normally the
installed SD card.  ``shutil.disk_usage`` reads the live filesystem statistics
without walking the dataset or blocking the camera/recognition process.
"""

from __future__ import annotations

from datetime import datetime
import shutil
from typing import Any


def format_storage_size(value: int | float) -> str:
    """Format bytes as a compact decimal-style GB/MB display string."""
    try:
        amount = max(0, int(value))
    except (TypeError, ValueError):
        amount = 0

    units = ("B", "KB", "MB", "GB", "TB")
    number = float(amount)
    unit = units[0]
    for unit in units:
        if number < 1024.0 or unit == units[-1]:
            break
        number /= 1024.0

    if unit == "B":
        return f"{int(number)} {unit}"
    return f"{number:.1f} {unit}"


def get_system_storage(mount_point: str = "/") -> dict[str, Any]:
    """Return one live root-filesystem storage snapshot for the UI/API."""
    path = str(mount_point or "/")
    usage = shutil.disk_usage(path)

    total = int(usage.total)
    used = int(usage.used)
    available = int(usage.free)
    used_percent = round((used / total * 100.0), 1) if total else 0.0
    available_percent = round(max(0.0, 100.0 - used_percent), 1)

    return {
        "mount_point": path,
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "used_percent": used_percent,
        "available_percent": available_percent,
        "total_human": format_storage_size(total),
        "used_human": format_storage_size(used),
        "available_human": format_storage_size(available),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
