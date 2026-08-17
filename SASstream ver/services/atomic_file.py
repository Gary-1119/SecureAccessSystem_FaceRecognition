from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable, Union

PathLike = Union[str, Path]


def _fsync_file(handle) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def atomic_write_text(path: PathLike, text: str, encoding: str = "utf-8", keep_backup: bool = True) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            _fsync_file(handle)
        atomic_replace(tmp_path, target, keep_backup=keep_backup)
        return target
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_write_bytes_from_writer(path: PathLike, writer: Callable[[BinaryIO], None], keep_backup: bool = True) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            writer(handle)
            _fsync_file(handle)
        atomic_replace(tmp_path, target, keep_backup=keep_backup)
        return target
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_replace(source: PathLike, target: PathLike, keep_backup: bool = True) -> None:
    src = Path(source)
    dst = Path(target)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and dst.exists():
        backup = dst.with_suffix(dst.suffix + ".bak")
        shutil.copy2(dst, backup)
    os.replace(src, dst)
    try:
        dir_fd = os.open(str(dst.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        pass
