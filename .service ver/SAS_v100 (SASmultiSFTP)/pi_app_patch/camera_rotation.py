"""Shared camera orientation helpers for the Raspberry Pi face-recognition app.

The value is stored in ``settings.json`` under ``camera_rotation``.  It is
applied at the Pi camera source, so the local Pi preview, capture workflow,
recognition pipeline, API ``/video-feed`` stream, and Windows SAS lock viewer
all show the same orientation.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

import cv2


SETTINGS_FILE = "settings.json"
CAMERA_ROTATION_KEY = "camera_rotation"
VALID_CAMERA_ROTATIONS = (0, 90, 180, 270)

_ROTATION_LABELS = {
    0: "0° (Normal)",
    90: "90° Clockwise",
    180: "180°",
    270: "270° Clockwise",
}

_settings_lock = threading.RLock()
_rotation_cache = 0
_rotation_mtime_ns: int | None = None


def normalize_camera_rotation(value: Any, default: int = 0) -> int:
    """Return a supported right-angle rotation (0, 90, 180, or 270)."""
    try:
        rotation = int(str(value).strip())
    except (TypeError, ValueError):
        rotation = int(default)

    rotation %= 360
    return rotation if rotation in VALID_CAMERA_ROTATIONS else int(default)


def camera_rotation_label(value: Any) -> str:
    """Return a user-friendly label for the persisted rotation value."""
    return _ROTATION_LABELS[normalize_camera_rotation(value)]


def _read_settings_unlocked(settings_file: str) -> dict:
    try:
        with open(settings_file, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_settings_atomic_unlocked(settings_file: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(settings_file)) or "."
    basename = os.path.basename(settings_file)
    temporary = os.path.join(
        folder,
        f".{basename}.tmp-{os.getpid()}-{threading.get_ident()}",
    )

    try:
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, settings_file)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except Exception:
            pass


def read_camera_rotation(settings_file: str = SETTINGS_FILE, force: bool = False) -> int:
    """Read a cached rotation value and refresh only when settings.json changes.

    This function is safe to call from every recognition/capture frame.  It
    avoids opening ``settings.json`` again unless its modification time changes.
    """
    global _rotation_cache, _rotation_mtime_ns

    try:
        mtime_ns = os.stat(settings_file).st_mtime_ns
    except OSError:
        return _rotation_cache

    with _settings_lock:
        if not force and _rotation_mtime_ns == mtime_ns:
            return _rotation_cache

        settings = _read_settings_unlocked(settings_file)
        _rotation_cache = normalize_camera_rotation(settings.get(CAMERA_ROTATION_KEY, 0))
        _rotation_mtime_ns = mtime_ns
        return _rotation_cache


def update_camera_rotation(value: Any, settings_file: str = SETTINGS_FILE) -> int:
    """Persist a new camera rotation while retaining every other setting."""
    global _rotation_cache, _rotation_mtime_ns

    rotation = normalize_camera_rotation(value)
    with _settings_lock:
        settings = _read_settings_unlocked(settings_file)
        settings[CAMERA_ROTATION_KEY] = rotation
        _write_settings_atomic_unlocked(settings_file, settings)
        _rotation_cache = rotation
        try:
            _rotation_mtime_ns = os.stat(settings_file).st_mtime_ns
        except OSError:
            _rotation_mtime_ns = None
    return rotation


def rotate_camera_frame(frame, rotation: Any | None = None):
    """Rotate one OpenCV frame clockwise without resizing or stretching it."""
    if frame is None:
        return frame

    degrees = read_camera_rotation() if rotation is None else normalize_camera_rotation(rotation)

    if degrees == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame
