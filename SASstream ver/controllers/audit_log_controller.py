from __future__ import annotations

from typing import Any

import os
import time
from datetime import datetime
from threading import Thread

from app_config import *
from services.log_retention import cleanup_expired_daily_logs


class AuditLogControllerMixin:
    def get_audit_actor(self: Any, fallback: str = "UNAUTHENTICATED") -> str:
        """Return the current authenticated SAS user for audit records."""
        actor = str(getattr(self, "current_user", "") or "").strip().upper()
        return actor or fallback

    def _audit_plain_text(self: Any, value: object) -> str:
        """Return one clean single-line value for a plain-text SAS audit log."""
        text = str(value if value is not None else "").strip()
        text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
        return text or "—"

    def _audit_text_safe(self: Any, value) -> str:
        """Return a safe value for a pipe-delimited plain-text audit row."""
        return self._audit_plain_text(value).replace("|", "/")

    def _normalise_audit_detail_key(self: Any, key) -> str:
        """Return a stable lowercase key for audit-detail formatting."""
        return " ".join(str(key or "").replace("_", " ").strip().lower().split())

    def _audit_detail_label(self: Any, key) -> str:
        """Use compact, consistent labels in the DETAILS column."""
        normalised = self._normalise_audit_detail_key(key)
        labels = {
            "role": "Role",
            "method": "Method",
            "login method": "Method",
            "sign in method": "Method",
            "page": "Page",
            "target": "Admin",
            "server credentials": "Server credentials",
            "server user": "Server account",
            "server account": "Server account",
            "server path": "Server path",
            "pi host": "Camera host",
            "requested host": "Requested host",
            "pi hostname": "Camera host",
            "api port": "API port",
            "inactivity lock": "Inactivity lock",
            "disabled while locked": "Disabled while locked",
            "auto capture": "Auto capture",
            "camera rotation": "Camera rotation",
            "face id": "Face ID",
            "zip file": "ZIP file",
            "local folder": "Local folder",
            "imported users": "Imported users",
            "captured images": "Captured images",
            "dataset removed": "Dataset removed",
            "encodings removed": "Encodings removed",
            "workstation user": "Workstation user",
            "access": "Access",
            "confidence": "Confidence",
            "source": "Source",
            "result": "Result",
            "state": "State",
        }
        return labels.get(normalised, normalised.title() if normalised else "")

    def _audit_detail_value(self: Any, key: object, value: object) -> str:
        """Make known internal audit values readable without changing paths or IDs."""
        value_text = self._audit_plain_text(value)
        normalised_key = self._normalise_audit_detail_key(key)
        known_values: dict[str, str] = {
            "ADMIN": "Admin",
            "USER": "User",
            "BUILT_IN_LOCAL_ADMIN": "Built-in Local Admin",
            "ACTIVE_DIRECTORY": "Active Directory",
            "EMERGENCY_HOTKEY": "Emergency Hotkey",
            "FACE_RECOGNITION": "Face Recognition",
            "DESKTOP_ONLY": "Desktop only",
            "MANUAL": "Manual",
            "N/A": "—",
            "SETTINGS": "Settings",
        }
        if normalised_key in {"role", "method", "login method", "sign in method", "page", "access", "confidence"}:
            return str(known_values.get(value_text.upper()) or value_text)
        return value_text

    def _audit_detail_pairs(self: Any, details):
        """Yield detail key/value pairs, including legacy lists of two-item tuples."""
        if isinstance(details, dict):
            return list(details.items())

        if isinstance(details, tuple) and len(details) == 2 and not isinstance(details[0], (dict, list, tuple, set)):
            return [(details[0], details[1])]

        if isinstance(details, (list, tuple, set)):
            pairs = []
            for item in details:
                if isinstance(item, dict):
                    pairs.extend(item.items())
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    pairs.append((item[0], item[1]))
                else:
                    pairs.append(("", item))
            return pairs

        return [("", details)]

    def _format_audit_details(self: Any, details) -> str:
        """Format clean audit details without leaking secrets or camera account names."""
        if details is None:
            return "—"

        sensitive_words = ("password", "secret", "token", "credential value")
        hidden_keys = {"pi account", "pi username", "system user", "ssh username"}
        parts = []

        for key, value in self._audit_detail_pairs(details):
            normalised_key = self._normalise_audit_detail_key(key)
            if normalised_key in hidden_keys:
                continue

            label = self._audit_detail_label(key)
            if any(word in normalised_key for word in sensitive_words):
                status = self._audit_plain_text(value).lower()
                if status in {"updated", "changed", "configured", "set"}:
                    value_text = "Updated"
                elif status in {"confirmed", "unchanged", "not changed"}:
                    value_text = "Not changed"
                else:
                    value_text = "Not recorded"
            else:
                value_text = self._audit_detail_value(key, value)

            parts.append(f"{label}: {value_text}" if label else value_text)

        return " · ".join(parts) if parts else "—"

    def _parse_legacy_audit_message(self: Any, message: str):
        """Convert existing pipe-delimited audit calls into clean text-log rows."""
        parts = [part.strip() for part in str(message or "").split("|") if part.strip()]
        if not parts:
            return "SYSTEM EVENT", "SYSTEM", "—"

        action = parts[0].replace("_", " ").strip().upper() or "SYSTEM EVENT"
        actor = ""
        detail_items = []

        for part in parts[1:]:
            if "=" not in part:
                detail_items.append(("", part))
                continue

            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            key_upper = key.upper()

            if key_upper in {"ACTOR", "USER"} and value:
                actor = value
                continue

            # Emergency unlock records can be written while SAS has no active
            # application login. Use the Windows workstation user as the actor
            # instead of producing a vague NOT_AUTHENTICATED value.
            if key_upper == "WORKSTATION_USER" and value and not actor:
                actor = value
                continue

            detail_items.append((key, value))

        return action, actor or self.get_audit_actor("SYSTEM"), self._format_audit_details(detail_items)

    def _append_text_audit_row(self: Any, log_file: str, header: str, row: str):
        """Append one clean plain-text audit row, adding a daily heading when required.

        Existing legacy text logs are preserved.  When a legacy file already
        exists for today, the new structured audit section begins below it
        instead of replacing historical entries.
        """
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        audit_marker = "SAS AUDIT LOG -"
        needs_header = not os.path.exists(log_file) or os.path.getsize(log_file) == 0

        if not needs_header:
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as existing_file:
                    existing_text = existing_file.read()
                needs_header = audit_marker not in existing_text
            except Exception:
                needs_header = False

        with open(log_file, "a", encoding="utf-8") as f:
            if needs_header:
                if os.path.getsize(log_file) > 0:
                    f.write("\n")
                f.write(header)
            f.write(row)

    def _cleanup_expired_daily_audit_logs(self: Any, log_root: str) -> None:
        try:
            retention_days = int(globals().get("SAS_LOG_RETENTION_DAYS", 14) or 14)
            result = cleanup_expired_daily_logs(log_root, retention_days=retention_days)
            errors = result.get("errors", []) if isinstance(result, dict) else []
            if errors:
                self.append_system_log(f"SAS_LOG cleanup warning: {errors[0]}")
        except Exception as exc:
            self.append_system_log(f"SAS_LOG cleanup failed: {exc}")


    def _get_server_log_path_for_write(self: Any) -> str:
        server_path = str(getattr(self, "server_path", "") or "").strip()
        if server_path:
            return server_path

        try:
            creds = self._read_credentials()
            return str(creds.get("server", "") or "").strip()
        except Exception:
            return ""

    def _append_server_sas_log_worker(self: Any, server_path: str, date_str: str, header: str, row: str) -> None:
        try:
            lock = getattr(self, "_sas_server_log_lock", None)
            if lock is not None:
                lock.acquire()

            try:
                server_root = os.path.join(server_path, "SAS_LOG")
                self._cleanup_expired_daily_audit_logs(server_root)
                server_log_file = os.path.join(server_root, f"{date_str}.txt")
                self._append_text_audit_row(server_log_file, header, row)
                self._sas_server_log_skip_until = 0.0
                self._sas_server_log_last_error = ""
            finally:
                if lock is not None:
                    lock.release()
        except Exception as exc:
            now = time.monotonic()
            self._sas_server_log_skip_until = now + 60.0
            error_text = str(exc)
            last_error = str(getattr(self, "_sas_server_log_last_error", "") or "")
            last_warn = float(getattr(self, "_sas_server_log_last_warn_at", 0.0) or 0.0)
            if error_text != last_error or now - last_warn >= 60.0:
                self._sas_server_log_last_error = error_text
                self._sas_server_log_last_warn_at = now

                def notify() -> None:
                    self.append_system_log(f"Server SAS_LOG write failed: {error_text}")

                try:
                    self.qt_after(0, notify)
                except Exception:
                    notify()
        finally:
            self._sas_server_log_write_running = False

    def _schedule_server_sas_log_write(self: Any, date_str: str, header: str, row: str) -> None:
        server_path = self._get_server_log_path_for_write()
        if not server_path:
            self.append_system_log("Server SAS_LOG write skipped: server path is empty")
            return

        now = time.monotonic()
        if now < float(getattr(self, "_sas_server_log_skip_until", 0.0) or 0.0):
            return
        if getattr(self, "_sas_server_log_write_running", False):
            return

        self._sas_server_log_write_running = True
        Thread(
            target=self._append_server_sas_log_worker,
            args=(server_path, date_str, header, row),
            daemon=True,
            name="SASServerAuditLog",
        ).start()

    def write_sas_log(self: Any, action: str, actor: str | None = None, details=None):
        """Write SAS audit locally immediately and copy to SMB in the background.

        The lock/unlock path must never wait for a disconnected network share.
        Local ``SAS_LOG/YYYY-MM-DD.txt`` remains the authoritative immediate log.
        The configured server path is best-effort and is skipped briefly after a
        network failure to avoid freezing the UI with repeated SMB timeouts.
        """
        raw_action = str(action or "").strip()
        if not raw_action:
            return

        # Backward compatibility for existing audit callers such as:
        # "UNLOCKED | USER=NTID | CONFIDENCE=90%".
        if details is None and actor is None and "|" in raw_action:
            event_action, event_actor, event_details = self._parse_legacy_audit_message(raw_action)
        else:
            event_action = raw_action.replace("_", " ").strip().upper()
            event_actor = str(actor or self.get_audit_actor("SYSTEM")).strip().upper() or "SYSTEM"
            event_details = self._format_audit_details(details)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        header = (
            "======================================================================\n"
            f"SAS AUDIT LOG - {date_str}\n"
            "======================================================================\n"
            "One row records one SAS action. Passwords and secret values are never written to this file.\n\n"
            "TIME     | ACTOR                | ACTION                       | DETAILS\n"
            "---------+----------------------+------------------------------+------------------------------------------\n"
        )
        row = (
            f"{self._audit_text_safe(time_str):<8} | "
            f"{self._audit_text_safe(event_actor):<20} | "
            f"{self._audit_text_safe(event_action):<28} | "
            f"{self._audit_text_safe(event_details)}\n"
        )

        lock = getattr(self, "_sas_log_lock", None)
        if lock is not None:
            lock.acquire()

        try:
            try:
                local_root = LOCAL_SAS_LOG_DIR
                self._cleanup_expired_daily_audit_logs(local_root)
                local_log_file = os.path.join(local_root, f"{date_str}.txt")
                self._append_text_audit_row(local_log_file, header, row)
            except Exception as exc:
                self.append_system_log(f"Local SAS_LOG write failed: {exc}")
        finally:
            if lock is not None:
                lock.release()

        self._schedule_server_sas_log_write(date_str, header, row)
