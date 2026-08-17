from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

try:
    from app_config import RUNTIME_DATA_DIR, SAS_LOG_RETENTION_DAYS
except Exception:
    RUNTIME_DATA_DIR = str(Path(__file__).resolve().parent.parent)
    SAS_LOG_RETENTION_DAYS = 14

from services.log_retention import cleanup_expired_daily_app_logs

LOG_DIR = Path(RUNTIME_DATA_DIR) / "SAS_LOG"
APP_LOG_SUFFIX = "_app.log"

_configured = False


def daily_app_log_path(day: Optional[date] = None, log_dir: Optional[Path] = None) -> Path:
    log_day = day or date.today()
    root = Path(log_dir) if log_dir is not None else LOG_DIR
    return root / f"{log_day.isoformat()}{APP_LOG_SUFFIX}"


class DailyAppLogHandler(logging.Handler):
    """Logging handler that writes technical app logs into one file per date."""

    terminator = "\n"

    def __init__(self, log_dir: Path, retention_days: int = 14, encoding: str = "utf-8") -> None:
        super().__init__()
        self.log_dir = Path(log_dir)
        self.retention_days = max(0, int(retention_days))
        self.encoding = encoding
        self.current_day: Optional[date] = None
        self.stream = None
        self.baseFilename = ""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._open_for_today()
            if self.stream is None:
                return
            self.stream.write(self.format(record) + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        if self.stream is not None:
            try:
                self.stream.flush()
            except Exception:
                pass

    def close(self) -> None:
        try:
            if self.stream is not None:
                try:
                    self.stream.flush()
                    self.stream.close()
                finally:
                    self.stream = None
        finally:
            super().close()

    def _open_for_today(self) -> None:
        today = date.today()
        if self.stream is not None and self.current_day == today:
            return

        if self.stream is not None:
            self.stream.flush()
            self.stream.close()
            self.stream = None

        self.log_dir.mkdir(parents=True, exist_ok=True)
        cleanup_expired_daily_app_logs(self.log_dir, retention_days=self.retention_days)
        path = daily_app_log_path(today, self.log_dir)
        self.current_day = today
        self.baseFilename = str(path)
        self.stream = open(path, "a", encoding=self.encoding)


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("sas")
    root.setLevel(logging.INFO)
    if not any(isinstance(handler, DailyAppLogHandler) for handler in root.handlers):
        handler = DailyAppLogHandler(LOG_DIR, retention_days=int(SAS_LOG_RETENTION_DAYS or 14))
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        root.addHandler(handler)
    _configured = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    configure_logging()
    return logging.getLogger("sas" + (f".{name}" if name else ""))


def log_exception(name: str, message: str) -> None:
    get_logger(name).exception(message)
