from __future__ import annotations

import shutil
import zipfile

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase
from services.log_retention import cleanup_expired_daily_logs


class AuditLogControllerMixin(DashboardMixinBase):
    def get_audit_actor(self, fallback: str = "UNAUTHENTICATED") -> str:
        """Return the current authenticated SAS user for audit records."""
        actor = str(getattr(self, "current_user", "") or "").strip().upper()
        return actor or fallback

    def _audit_append_system_log(self, message: str) -> None:
        logger = getattr(self, "append_system_log", None)
        if callable(logger):
            logger(message)


    def _audit_read_credentials(self) -> dict:
        reader = getattr(self, "_read_credentials", None)
        if callable(reader):
            result = reader()
            return result if isinstance(result, dict) else {}
        return {}



    def _audit_plain_text(self, value) -> str:
        """Return one clean single-line value for a plain-text SAS audit log."""
        text = str(value if value is not None else "").strip()
        text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
        return text or "—"


    def _audit_text_safe(self, value) -> str:
        """Return a safe value for a pipe-delimited plain-text audit row."""
        return self._audit_plain_text(value).replace("|", "/")


    def _normalise_audit_detail_key(self, key) -> str:
        """Return a stable lowercase key for audit-detail formatting."""
        return " ".join(str(key or "").replace("_", " ").strip().lower().split())


    def _audit_detail_label(self, key) -> str:
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
            "pi host": "Pi host",
            "requested host": "Requested host",
            "pi hostname": "Pi host",
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
            "embeddings removed": "Embeddings removed",
            "workstation user": "Workstation user",
            "access": "Access",
            "confidence": "Confidence",
            "source": "Source",
            "result": "Result",
            "state": "State",
        }
        return labels.get(normalised, normalised.title() if normalised else "")


    def _audit_detail_value(self, key, value) -> str:
        """Make known internal audit values readable without changing paths or IDs."""
        value_text = self._audit_plain_text(value)
        normalised_key = self._normalise_audit_detail_key(key)
        known_values = {
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
            return known_values.get(value_text.upper(), value_text)
        return value_text


    def _audit_detail_pairs(self, details):
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


    def _format_audit_details(self, details) -> str:
        """Format clean audit details without leaking secrets or Pi account names."""
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


    def _parse_legacy_audit_message(self, message: str):
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


    def _append_text_audit_row(self, log_file: str, header: str, row: str):
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


    def cleanup_expired_sas_logs(self):
        """Clean local SAS_LOG immediately and server SAS_LOG in the background."""
        try:
            self._cleanup_expired_daily_audit_logs(LOCAL_SAS_LOG_DIR)
        except Exception:
            pass

        server_path = self._get_server_log_path_for_write()
        if not server_path:
            return

        def cleanup_server():
            try:
                self._cleanup_expired_daily_audit_logs(os.path.join(server_path, "SAS_LOG"))
            except Exception as exc:
                self._audit_append_system_log(f"Server SAS_LOG cleanup failed: {exc}")

        Thread(target=cleanup_server, daemon=True, name="SASServerAuditCleanup").start()


    def _cleanup_expired_daily_audit_logs(self, log_root: str) -> None:
        try:
            retention_days = int(globals().get("SAS_LOG_RETENTION_DAYS", 14) or 14)
            result = cleanup_expired_daily_logs(log_root, retention_days=retention_days)
            errors = result.get("errors", []) if isinstance(result, dict) else []
            if errors:
                self._audit_append_system_log(f"SAS_LOG cleanup warning: {errors[0]}")
        except Exception as exc:
            self._audit_append_system_log(f"SAS_LOG cleanup failed: {exc}")


    def _log_download_stamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")


    def _select_local_log_download_folder(self, title: str) -> str:
        try:
            return QFileDialog.getExistingDirectory(
                self,
                title,
                os.path.expanduser("~"),
                QFileDialog.Option.ShowDirsOnly,
            )
        except Exception:
            return ""


    def _set_log_download_status(self, text: str, ok: bool | None = None):
        label = getattr(self, "log_download_status_label", None)
        if label is None:
            return
        label.setText(text)
        if ok is True:
            label.setObjectName("SettingsConnected")
        elif ok is False:
            label.setObjectName("SettingsDisconnected")
        else:
            label.setObjectName("SettingsHint")
        try:
            label.style().unpolish(label)
            label.style().polish(label)
            label.update()
        except Exception:
            pass


    def _show_log_download_result(self, title: str, message: str, success: bool):
        try:
            self.show_settings_message(title, message, success=success, issues=[] if success else [(title.upper(), message)])
        except Exception:
            self._audit_append_system_log(f"{title}: {message}")


    def download_sas_logs_to_local(self):
        """Copy today's local SAS_LOG file to a user-selected Windows folder."""
        target_root = self._select_local_log_download_folder("Select Local Folder for SAS_LOG Download")
        if not target_root:
            return

        self._set_log_download_status("Copying SAS_LOG to local folder...", None)
        stamp = self._log_download_stamp()
        target_dir = os.path.join(target_root, f"SAS_LOG_{stamp}")

        try:
            source_dir = LOCAL_SAS_LOG_DIR
            if not os.path.isdir(source_dir):
                raise RuntimeError("No local SAS_LOG folder was found yet.")

            today = datetime.now().strftime("%Y-%m-%d")
            source = os.path.join(source_dir, f"{today}.txt")
            if not os.path.isfile(source):
                raise RuntimeError(f"No SAS_LOG file found for today ({today}).")

            os.makedirs(target_dir, exist_ok=False)
            dest = os.path.join(target_dir, f"{today}.txt")
            shutil.copy2(source, dest)

            info_file = os.path.join(target_dir, "download_info.txt")
            with open(info_file, "w", encoding="utf-8") as f:
                f.write(f"Downloaded at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Date: {today}\n")
                f.write("Files copied: 1\n")

            self._set_log_download_status(f"SAS_LOG downloaded: {target_dir}", True)
            self.write_sas_log(
                "SAS LOG DOWNLOADED",
                actor=self.get_audit_actor(),
                details={"local folder": target_dir, "result": f"{today} only"},
            )
            self._show_log_download_result("SAS_LOG Downloaded", f"Saved to:\n{target_dir}", True)
        except Exception as exc:
            error = str(exc)
            self._set_log_download_status(f"SAS_LOG download failed: {error}", False)
            self._show_log_download_result("SAS_LOG Download Failed", error, False)


    def _pi_logs_download_url(self) -> str:
        host = str(getattr(self, "pi_api_host", "") or "").strip()
        port = str(getattr(self, "pi_api_port", "5000") or "5000").strip()
        if not host:
            return ""
        base = host.rstrip("/") if host.startswith("http") else f"http://{host}:{port}"
        return base + "/logs/export"


    def download_pi_logs_to_local(self):
        """Download Pi_LOG archive from the connected Pi to a local Windows folder."""
        if not getattr(self, "pi_connected", False):
            self._set_log_download_status("Pi_LOG download failed: Pi is not connected.", False)
            self._show_log_download_result("Pi_LOG Download Failed", "Please connect the Pi first.", False)
            return

        target_root = self._select_local_log_download_folder("Select Local Folder for Pi_LOG Download")
        if not target_root:
            return

        url = self._pi_logs_download_url()
        if not url:
            self._set_log_download_status("Pi_LOG download failed: Pi hostname/IP is not configured.", False)
            return

        button = getattr(self, "download_pi_logs_btn", None)
        if button is not None:
            button.setEnabled(False)
            button.setText("Downloading...")
        self._set_log_download_status("Downloading Pi_LOG archive from Raspberry Pi...", None)

        def worker():
            target_path = ""
            try:
                response = requests.get(url, timeout=120, stream=True)
                response.raise_for_status()
                stamp = self._log_download_stamp()
                filename = f"Pi_LOG_{self._log_download_stamp()}.zip"
                disposition = response.headers.get("content-disposition", "")
                if "filename=" in disposition:
                    filename = disposition.split("filename=", 1)[1].strip().strip('"')
                filename = os.path.basename(filename) or f"Pi_LOG_{self._log_download_stamp()}.zip"
                target_path = os.path.join(target_root, f"Pi_LOG_{stamp}")
                os.makedirs(target_path, exist_ok=False)
                archive_path = os.path.join(target_path, filename)

                with open(archive_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)

                with zipfile.ZipFile(archive_path, "r") as zipf:
                    target_abs = os.path.abspath(target_path)
                    for member in zipf.infolist():
                        dest_abs = os.path.abspath(os.path.join(target_path, member.filename))
                        if not (dest_abs == target_abs or dest_abs.startswith(target_abs + os.sep)):
                            raise RuntimeError("Pi_LOG archive contains an unsafe file path.")
                    zipf.extractall(target_path)

                try:
                    os.remove(archive_path)
                except Exception:
                    pass

                def done():
                    if button is not None:
                        button.setEnabled(True)
                        button.setText("Download Pi_LOG")
                    self._set_log_download_status(f"Pi_LOG downloaded: {target_path}", True)
                    self.write_sas_log(
                        "PI LOG DOWNLOADED",
                        actor=self.get_audit_actor(),
                        details={"local folder": target_path, "pi host": getattr(self, "pi_api_host", "")},
                    )
                    self._show_log_download_result("Pi_LOG Downloaded", f"Saved to:\n{target_path}", True)

                self.qt_after(0, done)
            except Exception as exc:
                error = str(exc)

                def fail():
                    if button is not None:
                        button.setEnabled(True)
                        button.setText("Download Pi_LOG")
                    self._set_log_download_status(f"Pi_LOG download failed: {error}", False)
                    self._show_log_download_result("Pi_LOG Download Failed", error, False)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True, name="PiLogDownload").start()


    def _get_server_log_path_for_write(self) -> str:
        server_path = str(getattr(self, "server_path", "") or "").strip()
        if server_path:
            return server_path

        try:
            creds = self._audit_read_credentials()
            return str(creds.get("server", "") or "").strip()
        except Exception:
            return ""


    def _append_server_sas_log_worker(self, server_path: str, date_str: str, header: str, row: str) -> None:
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
                    self._audit_append_system_log(f"Server SAS_LOG write failed: {error_text}")

                try:
                    qt_after = getattr(self, "qt_after", None)
                    if callable(qt_after):
                        qt_after(0, notify)
                    else:
                        notify()
                except Exception:
                    notify()
        finally:
            self._sas_server_log_write_running = False


    def _schedule_server_sas_log_write(self, date_str: str, header: str, row: str) -> None:
        server_path = self._get_server_log_path_for_write()
        if not server_path:
            self._audit_append_system_log("Server SAS_LOG write skipped: server path is empty")
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


    def write_sas_log(self, action: str, actor: str | None = None, details=None):
        """Write SAS audit locally and copy to the server path in the background.

        Local ``SAS_LOG/YYYY-MM-DD.txt`` is immediate and authoritative. Server
        logging is best-effort so an offline SMB path cannot freeze lock/unlock.
        Dated logs older than ``SAS_LOG_RETENTION_DAYS`` are cleaned safely.
        """
        raw_action = str(action or "").strip()
        if not raw_action:
            return

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
                self._audit_append_system_log(f"Local SAS_LOG write failed: {exc}")
        finally:
            if lock is not None:
                lock.release()

        self._schedule_server_sas_log_write(date_str, header, row)
