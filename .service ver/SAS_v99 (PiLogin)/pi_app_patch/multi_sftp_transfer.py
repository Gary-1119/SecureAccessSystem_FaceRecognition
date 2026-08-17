"""Multi-Pi SFTP transfer support for the Face Recognition Pi app.

This module is deliberately imported lazily by gui.py only when the user opens
"Send Face Data to Another Pi".  It never runs during normal GUI startup.
"""
from __future__ import annotations

import os
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk

try:
    import paramiko
except Exception:  # Keep import failure isolated to this optional feature.
    paramiko = None


MODULE_DIR = Path(__file__).resolve().parent
TARGET_FILE = MODULE_DIR / "sftp_target.txt"
TEMP_MULTI_DIR = MODULE_DIR / "temp_export" / "multi_sftp"
MAX_CONCURRENT_TRANSFERS = 4
TARGET_APP_FOLDER = "FaceRecognition"
TARGET_PENDING_SUFFIX = "received_face_data/pending"


class TransferCancelled(Exception):
    """Raised internally when a user cancels an active transfer batch."""


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "SourcePi").strip())
    return cleaned.strip("._-") or "SourcePi"


def _validate_target(hostname: str) -> str:
    value = str(hostname or "").strip()
    if not value:
        raise ValueError("Hostname or IP is required.")
    if len(value) > 253:
        raise ValueError("Hostname or IP is too long.")
    if any(char.isspace() for char in value):
        raise ValueError("Hostname or IP cannot contain spaces.")
    if "/" in value or "\\" in value or ":" in value or "@" in value:
        raise ValueError("Enter only a hostname or IP address, without a port, path, or username.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError("Hostname or IP contains unsupported characters.")
    return value


def _human_size(value: int) -> str:
    number = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024.0 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024.0
    return f"{number:.1f} TB"


@dataclass
class TransferBatch:
    batch_id: str
    targets: List[str]
    created_at: str = field(default_factory=_now_text)
    state: str = "Preparing"
    local_zip: str = ""
    running: bool = True
    cancel_event: threading.Event = field(default_factory=threading.Event)
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class MultiSftpTransferManager:
    """Owns persisted target hosts and independent four-worker SFTP batches."""

    def __init__(self, app: Any):
        self.app = app
        self._lock = threading.RLock()
        self._batches: Dict[str, TransferBatch] = {}
        self._cleanup_stale_temp_packages()

    # ------------------------------------------------------------------
    # Target list persistence
    # ------------------------------------------------------------------
    def list_targets(self) -> List[str]:
        try:
            if not TARGET_FILE.exists():
                return []
            seen = set()
            targets: List[str] = []
            for raw_line in TARGET_FILE.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    target = _validate_target(line)
                except ValueError:
                    continue
                key = target.casefold()
                if key not in seen:
                    seen.add(key)
                    targets.append(target)
            return targets
        except Exception:
            return []

    def _write_targets(self, targets: Iterable[str]) -> None:
        clean: List[str] = []
        seen = set()
        for raw in targets:
            target = _validate_target(raw)
            key = target.casefold()
            if key not in seen:
                clean.append(target)
                seen.add(key)
        TARGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = TARGET_FILE.with_suffix(".txt.tmp")
        temp_file.write_text("\n".join(clean) + ("\n" if clean else ""), encoding="utf-8")
        os.replace(temp_file, TARGET_FILE)

    def add_target(self, hostname: str) -> Tuple[bool, str, List[str]]:
        try:
            target = _validate_target(hostname)
            targets = self.list_targets()
            if any(item.casefold() == target.casefold() for item in targets):
                return False, f"{target} is already in the saved target list.", targets
            targets.append(target)
            self._write_targets(targets)
            self._log(f"Multi-Pi SFTP target added: {target}", "info")
            return True, f"Added {target}.", self.list_targets()
        except Exception as exc:
            return False, str(exc), self.list_targets()

    def remove_target(self, hostname: str) -> Tuple[bool, str, List[str]]:
        try:
            target = _validate_target(hostname)
            targets = self.list_targets()
            remaining = [item for item in targets if item.casefold() != target.casefold()]
            if len(remaining) == len(targets):
                return False, f"{target} was not found in the saved target list.", targets
            self._write_targets(remaining)
            self._log(f"Multi-Pi SFTP target removed: {target}", "info")
            return True, f"Removed {target}.", self.list_targets()
        except Exception as exc:
            return False, str(exc), self.list_targets()

    # ------------------------------------------------------------------
    # Configuration shared later with SAS through API
    # ------------------------------------------------------------------
    def get_transfer_config(self) -> Dict[str, Any]:
        username = self._get_linux_username()
        return {
            "username": username,
            "port": 22,
            "password_mode": "same_as_username",
            "remote_dir": self._remote_pending_dir(username),
            "max_concurrent_transfers": MAX_CONCURRENT_TRANSFERS,
            "target_file": str(TARGET_FILE),
        }

    def _get_linux_username(self) -> str:
        try:
            identity = self.app._get_pi_network_identity()
            username = str(identity.get("ssh_username") or identity.get("system_user") or "").strip()
            if username:
                return username
        except Exception:
            pass
        try:
            import getpass
            username = getpass.getuser().strip()
            if username:
                return username
        except Exception:
            pass
        return "jbl_facerec"

    @staticmethod
    def _remote_pending_dir(username: str) -> str:
        return f"/home/{username}/{TARGET_APP_FOLDER}/{TARGET_PENDING_SUFFIX}"

    # ------------------------------------------------------------------
    # Batch lifecycle
    # ------------------------------------------------------------------
    def start_batch(self, selected_targets: Iterable[str]) -> Tuple[bool, str, Dict[str, Any]]:
        if paramiko is None:
            return False, "Paramiko is not installed. Install python3-paramiko first.", {}

        targets: List[str] = []
        seen = set()
        try:
            for raw in selected_targets:
                target = _validate_target(raw)
                key = target.casefold()
                if key not in seen:
                    targets.append(target)
                    seen.add(key)
        except Exception as exc:
            return False, str(exc), {}

        if not targets:
            return False, "Select at least one target Pi.", {}

        batch_id = uuid.uuid4().hex[:12]
        batch = TransferBatch(batch_id=batch_id, targets=targets)
        for host in targets:
            batch.jobs[host] = {
                "hostname": host,
                "status": "Waiting",
                "progress": 0,
                "message": "Waiting in transfer queue.",
                "started_at": "",
                "finished_at": "",
                "remote_file": "",
            }

        with self._lock:
            self._batches[batch_id] = batch

        thread = threading.Thread(
            target=self._run_batch,
            args=(batch_id, targets, True),
            daemon=True,
            name=f"MultiSftp-{batch_id}",
        )
        thread.start()
        return True, "Multi-Pi transfer started.", self.get_batch_snapshot(batch_id) or {}

    def retry_failed(self, batch_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        with self._lock:
            batch = self._batches.get(str(batch_id))
            if batch is None:
                return False, "Transfer batch was not found.", {}
            if batch.running:
                return False, "This transfer batch is still running.", self._snapshot_unlocked(batch)
            if not batch.local_zip or not os.path.exists(batch.local_zip):
                return False, "The temporary ZIP is no longer available. Start a new transfer.", self._snapshot_unlocked(batch)

            retry_targets = [
                host for host, job in batch.jobs.items()
                if str(job.get("status", "")).startswith("Failed") or job.get("status") == "Cancelled"
            ]
            if not retry_targets:
                return False, "There are no failed or cancelled target Pis to retry.", self._snapshot_unlocked(batch)

            batch.cancel_event = threading.Event()
            batch.state = "Retrying"
            batch.running = True
            for host in retry_targets:
                batch.jobs[host].update({
                    "status": "Waiting",
                    "progress": 0,
                    "message": "Waiting to retry.",
                    "started_at": "",
                    "finished_at": "",
                    "remote_file": "",
                })

        thread = threading.Thread(
            target=self._run_batch,
            args=(batch_id, retry_targets, False),
            daemon=True,
            name=f"MultiSftpRetry-{batch_id}",
        )
        thread.start()
        return True, "Retry started for failed target Pis.", self.get_batch_snapshot(batch_id) or {}

    def cancel_batch(self, batch_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        with self._lock:
            batch = self._batches.get(str(batch_id))
            if batch is None:
                return False, "Transfer batch was not found.", {}
            batch.cancel_event.set()
            for job in batch.jobs.values():
                if job.get("status") == "Waiting":
                    job.update({
                        "status": "Cancelled",
                        "message": "Cancelled before upload started.",
                        "finished_at": _now_text(),
                    })
            batch.state = "Cancelling"
            return True, "Cancellation requested. Active uploads will stop at the next progress update.", self._snapshot_unlocked(batch)

    def cleanup_batch(self, batch_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        with self._lock:
            batch = self._batches.get(str(batch_id))
            if batch is None:
                return False, "Transfer batch was not found.", {}
            if batch.running:
                return False, "Wait for the running transfers to finish before deleting the temporary ZIP.", self._snapshot_unlocked(batch)
            local_zip = batch.local_zip

        if local_zip:
            try:
                path = Path(local_zip).resolve()
                root = TEMP_MULTI_DIR.resolve()
                if root in path.parents and path.exists():
                    path.unlink()
            except Exception as exc:
                return False, f"Could not delete the temporary ZIP: {exc}", self.get_batch_snapshot(batch_id) or {}

        with self._lock:
            batch = self._batches.get(str(batch_id))
            if batch is not None:
                batch.local_zip = ""
                batch.state = "Completed (temp ZIP deleted)"
                return True, "Temporary ZIP deleted.", self._snapshot_unlocked(batch)
        return True, "Temporary ZIP deleted.", {}

    def get_batch_snapshot(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            batch = self._batches.get(str(batch_id))
            return self._snapshot_unlocked(batch) if batch else None

    def _snapshot_unlocked(self, batch: TransferBatch) -> Dict[str, Any]:
        jobs = [dict(batch.jobs[host]) for host in batch.targets if host in batch.jobs]
        active = sum(job["status"] in ("Connecting", "Uploading") for job in jobs)
        waiting = sum(job["status"] == "Waiting" for job in jobs)
        success = sum(job["status"] == "Success" for job in jobs)
        failed = sum(str(job["status"]).startswith("Failed") for job in jobs)
        cancelled = sum(job["status"] == "Cancelled" for job in jobs)
        return {
            "batch_id": batch.batch_id,
            "created_at": batch.created_at,
            "state": batch.state,
            "running": batch.running,
            "local_zip": batch.local_zip,
            "local_zip_size": os.path.getsize(batch.local_zip) if batch.local_zip and os.path.exists(batch.local_zip) else 0,
            "jobs": jobs,
            "summary": {
                "total": len(jobs),
                "active": active,
                "waiting": waiting,
                "success": success,
                "failed": failed,
                "cancelled": cancelled,
            },
            "config": self.get_transfer_config(),
        }

    def _run_batch(self, batch_id: str, target_hosts: List[str], create_zip: bool) -> None:
        batch = self._get_batch(batch_id)
        if batch is None:
            return

        try:
            if create_zip:
                self._set_batch_state(batch_id, "Preparing face-data ZIP")
                TEMP_MULTI_DIR.mkdir(parents=True, exist_ok=True)
                self._cleanup_stale_temp_packages()
                source = _safe_filename_part(self._source_hostname())
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                zip_name = f"face_data_from_{source}_{timestamp}_{batch_id}.zip"
                local_zip = str((TEMP_MULTI_DIR / zip_name).resolve())
                self.app._create_face_data_zip(local_zip)
                with self._lock:
                    live_batch = self._batches.get(batch_id)
                    if live_batch is None:
                        return
                    live_batch.local_zip = local_zip
                self._log(f"Multi-Pi SFTP package created: {local_zip}", "info")

            batch = self._get_batch(batch_id)
            if batch is None or not batch.local_zip or not os.path.exists(batch.local_zip):
                raise FileNotFoundError("Temporary face-data ZIP was not created.")

            if batch.cancel_event.is_set():
                self._mark_remaining_cancelled(batch_id)
                return

            self._set_batch_state(batch_id, f"Uploading to {len(target_hosts)} target Pi(s)")
            workers = min(MAX_CONCURRENT_TRANSFERS, max(1, len(target_hosts)))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="SftpWorker") as pool:
                futures = [pool.submit(self._upload_one, batch_id, host) for host in target_hosts]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        # _upload_one converts transfer exceptions into per-host statuses.
                        pass

            self._finish_batch(batch_id)

        except Exception as exc:
            self._set_batch_state(batch_id, "Failed to prepare transfer")
            with self._lock:
                live_batch = self._batches.get(batch_id)
                if live_batch is not None:
                    live_batch.running = False
                    for job in live_batch.jobs.values():
                        if job.get("status") in ("Waiting", "Preparing"):
                            job.update({
                                "status": "Failed",
                                "message": f"Batch preparation failed: {exc}",
                                "finished_at": _now_text(),
                            })
            self._log(f"Multi-Pi SFTP batch failed: {exc}", "error")

    def _upload_one(self, batch_id: str, host: str) -> None:
        batch = self._get_batch(batch_id)
        if batch is None:
            return

        if batch.cancel_event.is_set():
            self._update_job(batch_id, host, "Cancelled", 0, "Cancelled before upload started.", finished=True)
            return

        transport = None
        sftp = None
        sock = None
        remote_part = ""
        try:
            self._update_job(batch_id, host, "Connecting", 0, "Connecting to target Pi.", started=True)
            username = self._get_linux_username()
            password = username  # Requirement: Linux SFTP password is the same as the Pi username.
            remote_dir = self._remote_pending_dir(username)

            sock = socket.create_connection((host, 22), timeout=12)
            transport = paramiko.Transport(sock)
            transport.banner_timeout = 12
            transport.auth_timeout = 12
            transport.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            if sftp is None:
                raise RuntimeError("SFTP connection was not created.")

            self._ensure_remote_dir(sftp, remote_dir)
            batch = self._get_batch(batch_id)
            if batch is None:
                return

            zip_name = os.path.basename(batch.local_zip)
            remote_final = remote_dir.rstrip("/") + "/" + zip_name
            remote_part = remote_final + ".part"
            try:
                sftp.remove(remote_part)
            except Exception:
                pass

            def progress_callback(transferred: int, total: int) -> None:
                live_batch = self._get_batch(batch_id)
                if live_batch is not None and live_batch.cancel_event.is_set():
                    raise TransferCancelled("Transfer cancelled by user.")
                percent = int((float(transferred) / float(total)) * 100) if total else 0
                self._update_job(
                    batch_id,
                    host,
                    "Uploading",
                    max(0, min(100, percent)),
                    f"Uploading {_human_size(transferred)} of {_human_size(total)}.",
                )

            self._update_job(batch_id, host, "Uploading", 0, "Uploading face-data ZIP.")
            sftp.put(batch.local_zip, remote_part, callback=progress_callback, confirm=True)

            if self._get_batch(batch_id) and self._get_batch(batch_id).cancel_event.is_set():
                raise TransferCancelled("Transfer cancelled by user.")

            try:
                sftp.remove(remote_final)
            except Exception:
                pass
            sftp.rename(remote_part, remote_final)
            self._update_job(
                batch_id,
                host,
                "Success",
                100,
                "Face-data ZIP uploaded successfully.",
                finished=True,
                remote_file=remote_final,
            )
            self._log(f"Multi-Pi SFTP success: {host} -> {remote_final}", "success")

        except TransferCancelled as exc:
            self._update_job(batch_id, host, "Cancelled", 0, str(exc), finished=True)
            self._log(f"Multi-Pi SFTP cancelled: {host}", "warn")

        except Exception as exc:
            self._update_job(batch_id, host, "Failed", 0, str(exc), finished=True)
            self._log(f"Multi-Pi SFTP failed for {host}: {exc}", "error")

        finally:
            try:
                if sftp is not None:
                    sftp.close()
            except Exception:
                pass
            try:
                if transport is not None:
                    transport.close()
            except Exception:
                pass
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass

    @staticmethod
    def _ensure_remote_dir(sftp: Any, remote_dir: str) -> None:
        clean = str(remote_dir).replace("\\", "/").rstrip("/")
        if not clean:
            raise ValueError("Remote pending folder is empty.")
        current = "/" if clean.startswith("/") else ""
        for part in [item for item in clean.split("/") if item]:
            current = current + part if current in ("", "/") else current + "/" + part
            try:
                sftp.stat(current)
            except Exception:
                sftp.mkdir(current)

    def _finish_batch(self, batch_id: str) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return
            if batch.cancel_event.is_set():
                self._mark_remaining_cancelled_unlocked(batch)
            batch.running = False
            snapshot = self._snapshot_unlocked(batch)
            failed_or_cancelled = snapshot["summary"]["failed"] + snapshot["summary"]["cancelled"]
            if failed_or_cancelled:
                batch.state = "Completed with issues — temporary ZIP kept for retry"
            else:
                batch.state = "Completed successfully"

        # A successful batch has no retry use for its temporary ZIP, so remove it.
        if failed_or_cancelled == 0:
            self.cleanup_batch(batch_id)

    def _get_batch(self, batch_id: str) -> Optional[TransferBatch]:
        with self._lock:
            return self._batches.get(batch_id)

    def _set_batch_state(self, batch_id: str, state: str) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is not None:
                batch.state = state

    def _update_job(
        self,
        batch_id: str,
        host: str,
        status: str,
        progress: int,
        message: str,
        started: bool = False,
        finished: bool = False,
        remote_file: str = "",
    ) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None or host not in batch.jobs:
                return
            job = batch.jobs[host]
            job["status"] = status
            job["progress"] = int(max(0, min(100, progress)))
            job["message"] = str(message)
            if started and not job.get("started_at"):
                job["started_at"] = _now_text()
            if finished:
                job["finished_at"] = _now_text()
            if remote_file:
                job["remote_file"] = remote_file

    def _mark_remaining_cancelled(self, batch_id: str) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is not None:
                self._mark_remaining_cancelled_unlocked(batch)

    @staticmethod
    def _mark_remaining_cancelled_unlocked(batch: TransferBatch) -> None:
        for job in batch.jobs.values():
            if job.get("status") == "Waiting":
                job.update({
                    "status": "Cancelled",
                    "message": "Cancelled before upload started.",
                    "finished_at": _now_text(),
                })

    def _source_hostname(self) -> str:
        try:
            identity = self.app._get_pi_network_identity()
            hostname = str(identity.get("hostname") or "").strip()
            if hostname:
                return hostname
        except Exception:
            pass
        try:
            return socket.gethostname()
        except Exception:
            return "SourcePi"

    def _cleanup_stale_temp_packages(self, max_age_seconds: int = 24 * 60 * 60) -> None:
        try:
            TEMP_MULTI_DIR.mkdir(parents=True, exist_ok=True)
            cutoff = time.time() - max_age_seconds
            for item in TEMP_MULTI_DIR.glob("*.zip"):
                try:
                    if item.stat().st_mtime < cutoff:
                        item.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def _log(self, message: str, level: str) -> None:
        try:
            self.app.log(message, level)
        except Exception:
            pass


# ----------------------------------------------------------------------
# Lazy per-app manager accessor used by both Pi UI and future SAS API.
# ----------------------------------------------------------------------
def get_multi_sftp_manager(app: Any) -> MultiSftpTransferManager:
    manager = getattr(app, "_multi_sftp_transfer_manager", None)
    if isinstance(manager, MultiSftpTransferManager):
        return manager
    manager = MultiSftpTransferManager(app)
    setattr(app, "_multi_sftp_transfer_manager", manager)
    return manager


# ----------------------------------------------------------------------
# Pi popup UI — loaded only when user opens Send to Another Pi.
# ----------------------------------------------------------------------
def open_multi_sftp_transfer(app: Any) -> None:
    manager = get_multi_sftp_manager(app)
    win, shell = app._modern_popup_shell("SFTP Transfer", 650, 640)

    shell.configure(bg="#FFFFFF")
    header = tk.Frame(shell, bg="#FFFFFF")
    header.pack(fill="x", padx=22, pady=(16, 8))

    title_area = tk.Frame(header, bg="#FFFFFF")
    title_area.pack(side="left", fill="x", expand=True)
    tk.Label(title_area, text="SFTP Transfer", font=("DejaVu Sans", 16, "bold"), bg="#FFFFFF", fg="#0F172A").pack(anchor="w")
    total_label = tk.Label(title_area, text="Total Nodes: 0", font=("DejaVu Sans", 8, "bold"), bg="#EEF2F7", fg="#475569", padx=8, pady=3)
    total_label.pack(anchor="w", pady=(3, 0))

    def close_popup() -> None:
        app._safe_popup_close(win)

    win.protocol("WM_DELETE_WINDOW", close_popup)
    app._btn(header, "×", "#F8FAFF", close_popup, fg="#475569", border=True, padx=7, pady=3, width=42).pack(side="right", anchor="n")

    tk.Label(
        shell,
        text="Select one or more target Pis. The source Pi creates one ZIP and uploads it with up to 4 independent SFTP workers.",
        font=("DejaVu Sans", 8), bg="#FFFFFF", fg="#64748B", wraplength=570, justify="left"
    ).pack(anchor="w", padx=22, pady=(0, 9))

    controls = tk.Frame(shell, bg="#FFFFFF")
    controls.pack(fill="x", padx=22, pady=(0, 8))
    search_var = tk.StringVar()
    select_all_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="")
    selected_hosts: set[str] = set()

    search_box = tk.Frame(controls, bg="#F8FAFF", highlightthickness=1, highlightbackground="#DDE5F0")
    search_box.pack(side="left", fill="x", expand=True)
    tk.Label(search_box, text="⌕", font=("DejaVu Sans", 14, "bold"), bg="#F8FAFF", fg="#64748B").pack(side="left", padx=(10, 4))
    search_entry = tk.Entry(search_box, textvariable=search_var, font=("DejaVu Sans", 10), relief="flat", bg="#F8FAFF", fg="#0F172A", insertbackground="#0B72FF")
    search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=8)
    search_entry.insert(0, "")

    select_all_box = tk.Frame(controls, bg="#FFFFFF")
    select_all_box.pack(side="right", padx=(12, 0))
    select_all_check = tk.Checkbutton(
        select_all_box, text="Select All", variable=select_all_var,
        font=("DejaVu Sans", 9, "bold"), bg="#FFFFFF", fg="#475569",
        activebackground="#FFFFFF", activeforeground="#0F172A",
        selectcolor="#FFFFFF", highlightthickness=0, bd=0,
    )
    select_all_check.pack()

    # Scrollable hostname list.
    list_outer = tk.Frame(shell, bg="#FFFFFF", highlightthickness=1, highlightbackground="#DDE5F0")
    list_outer.pack(fill="both", expand=True, padx=22, pady=(0, 10))
    list_canvas = tk.Canvas(list_outer, bg="#FFFFFF", highlightthickness=0, bd=0)
    list_scroll = ttk.Scrollbar(list_outer, orient="vertical", command=list_canvas.yview)
    list_canvas.configure(yscrollcommand=list_scroll.set)
    list_scroll.pack(side="right", fill="y")
    list_canvas.pack(side="left", fill="both", expand=True)
    list_frame = tk.Frame(list_canvas, bg="#FFFFFF")
    list_window = list_canvas.create_window((0, 0), window=list_frame, anchor="nw")

    def on_list_configure(event: Any = None) -> None:
        list_canvas.configure(scrollregion=list_canvas.bbox("all"))

    def on_canvas_configure(event: Any = None) -> None:
        try:
            list_canvas.itemconfigure(list_window, width=list_canvas.winfo_width())
        except Exception:
            pass

    list_frame.bind("<Configure>", on_list_configure)
    list_canvas.bind("<Configure>", on_canvas_configure)

    def wheel(event: Any) -> str:
        try:
            if getattr(event, "num", None) == 4:
                list_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                list_canvas.yview_scroll(1, "units")
            else:
                delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
                if delta:
                    list_canvas.yview_scroll(delta, "units")
            return "break"
        except Exception:
            return "break"

    def bind_wheel(widget: Any) -> None:
        try:
            widget.bind("<MouseWheel>", wheel, add="+")
            widget.bind("<Button-4>", wheel, add="+")
            widget.bind("<Button-5>", wheel, add="+")
        except Exception:
            pass

    bind_wheel(list_canvas)
    bind_wheel(list_frame)

    add_row = tk.Frame(shell, bg="#FFFFFF")
    add_row.pack(fill="x", padx=22, pady=(0, 6))
    add_entry = tk.Entry(add_row, font=("DejaVu Sans", 10), bg="#FFFFFF", fg="#0F172A", insertbackground="#0B72FF", relief="flat", highlightthickness=1, highlightbackground="#DDE5F0")
    add_entry.pack(side="left", fill="x", expand=True, ipady=8)
    app._btn(add_row, "+ Add Hostname", "#0F172A", lambda: None, fg="white", padx=12, pady=7, width=142).pack(side="right", padx=(10, 0))
    add_button = add_row.winfo_children()[-1]

    status_label = tk.Label(shell, textvariable=status_var, font=("DejaVu Sans", 8), bg="#FFFFFF", fg="#64748B", anchor="w")
    status_label.pack(fill="x", padx=22, pady=(0, 5))

    footer = tk.Frame(shell, bg="#F8FAFF", highlightthickness=1, highlightbackground="#DDE5F0")
    footer.pack(fill="x", padx=0, pady=(4, 0))

    hosts_cache: List[str] = []

    def visible_hosts() -> List[str]:
        keyword = search_var.get().strip().casefold()
        if not keyword:
            return list(hosts_cache)
        return [host for host in hosts_cache if keyword in host.casefold()]

    def sync_select_all_state() -> None:
        visible = visible_hosts()
        select_all_var.set(bool(visible) and all(host in selected_hosts for host in visible))

    def toggle_host(host: str, var: tk.BooleanVar) -> None:
        if var.get():
            selected_hosts.add(host)
        else:
            selected_hosts.discard(host)
        sync_select_all_state()

    def render_list() -> None:
        nonlocal hosts_cache
        hosts_cache = manager.list_targets()
        total_label.configure(text=f"Total Nodes: {len(hosts_cache)}")
        for child in list_frame.winfo_children():
            child.destroy()

        visible = visible_hosts()
        if not visible:
            message = "No saved hostname matches the search." if hosts_cache else "No target Pi saved yet. Add a hostname or IP below."
            tk.Label(list_frame, text=message, font=("DejaVu Sans", 10), bg="#FFFFFF", fg="#94A3B8", pady=28).pack(fill="x")
        else:
            for host in visible:
                row = tk.Frame(list_frame, bg="#FFFFFF", highlightthickness=0, bd=0)
                row.pack(fill="x", padx=10, pady=5)
                var = tk.BooleanVar(value=host in selected_hosts)
                check = tk.Checkbutton(row, variable=var, bg="#FFFFFF", activebackground="#FFFFFF", selectcolor="#FFFFFF", highlightthickness=0, bd=0, command=lambda h=host, v=var: toggle_host(h, v))
                check.pack(side="left", padx=(0, 8))
                icon_label = tk.Label(row, text="▣", font=("DejaVu Sans", 13), bg="#EEF2F7", fg="#64748B", width=3, pady=4)
                icon_label.pack(side="left")
                host_label = tk.Label(row, text=host, font=("DejaVu Sans", 10, "bold"), bg="#FFFFFF", fg="#0F172A", anchor="w")
                host_label.pack(side="left", fill="x", expand=True, padx=10)
                remove_btn = app._btn(row, "Delete", "#FFFFFF", lambda h=host: remove_target(h), fg="#EF4444", border=True, padx=8, pady=4, width=74)
                remove_btn.pack(side="right")
                for widget in (row, check, icon_label, host_label, remove_btn):
                    bind_wheel(widget)
        sync_select_all_state()
        win.after_idle(on_list_configure)

    def add_target() -> None:
        raw = add_entry.get().strip()
        ok, message, _targets = manager.add_target(raw)
        status_var.set(message)
        status_label.configure(fg="#16A34A" if ok else "#EF4444")
        if ok:
            add_entry.delete(0, tk.END)
            render_list()

    def remove_target(host: str) -> None:
        ok, message, _targets = manager.remove_target(host)
        status_var.set(message)
        status_label.configure(fg="#16A34A" if ok else "#EF4444")
        selected_hosts.discard(host)
        render_list()

    def toggle_visible_hosts() -> None:
        visible = visible_hosts()
        if select_all_var.get():
            selected_hosts.update(visible)
        else:
            for host in visible:
                selected_hosts.discard(host)
        render_list()

    select_all_check.configure(command=toggle_visible_hosts)
    add_button.configure(command=add_target)
    add_entry.bind("<Return>", lambda event: add_target())
    search_var.trace_add("write", lambda *_args: render_list())

    def send_selected() -> None:
        selected = [host for host in hosts_cache if host in selected_hosts]
        ok, message, snapshot = manager.start_batch(selected)
        if not ok:
            status_var.set(message)
            status_label.configure(fg="#EF4444")
            return
        app._safe_popup_close(win)
        show_transfer_progress(app, manager, str(snapshot.get("batch_id", "")))

    app._btn(footer, "Cancel", "#F8FAFF", close_popup, fg="#475569", border=False, padx=18, pady=8, width=110).pack(side="right", padx=(8, 18), pady=12)
    app._btn(footer, "Transfer Selected", "#0B72FF", send_selected, fg="white", padx=18, pady=8, width=180).pack(side="right", pady=12)

    render_list()
    search_entry.focus_set()


def show_transfer_progress(app: Any, manager: MultiSftpTransferManager, batch_id: str) -> None:
    win, shell = app._modern_popup_shell("SFTP Transfer Progress", 670, 560)
    title = tk.Label(shell, text="SFTP Transfer Progress", font=("DejaVu Sans", 16, "bold"), bg="#FFFFFF", fg="#0F172A")
    title.pack(anchor="w", padx=22, pady=(16, 3))
    summary_var = tk.StringVar(value="Preparing transfer...")
    tk.Label(shell, textvariable=summary_var, font=("DejaVu Sans", 9), bg="#FFFFFF", fg="#64748B").pack(anchor="w", padx=22, pady=(0, 10))

    outer = tk.Frame(shell, bg="#FFFFFF", highlightthickness=1, highlightbackground="#DDE5F0")
    outer.pack(fill="both", expand=True, padx=22, pady=(0, 8))
    canvas = tk.Canvas(outer, bg="#FFFFFF", highlightthickness=0, bd=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    list_frame = tk.Frame(canvas, bg="#FFFFFF")
    list_window = canvas.create_window((0, 0), window=list_frame, anchor="nw")

    def on_frame_configure(event: Any = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def on_canvas_configure(event: Any = None) -> None:
        try:
            canvas.itemconfigure(list_window, width=canvas.winfo_width())
        except Exception:
            pass

    list_frame.bind("<Configure>", on_frame_configure)
    canvas.bind("<Configure>", on_canvas_configure)

    def wheel(event: Any) -> str:
        try:
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
                if delta:
                    canvas.yview_scroll(delta, "units")
            return "break"
        except Exception:
            return "break"

    for widget in (canvas, list_frame):
        widget.bind("<MouseWheel>", wheel, add="+")
        widget.bind("<Button-4>", wheel, add="+")
        widget.bind("<Button-5>", wheel, add="+")

    footer = tk.Frame(shell, bg="#F8FAFF", highlightthickness=1, highlightbackground="#DDE5F0")
    footer.pack(fill="x", pady=(5, 0))
    retry_button = app._btn(footer, "Retry Failed", "#FFFFFF", lambda: None, fg="#0B72FF", border=True, padx=14, pady=7, width=140)
    cancel_button = app._btn(footer, "Cancel", "#FFFFFF", lambda: None, fg="#EF4444", border=True, padx=14, pady=7, width=110)
    close_button = app._btn(footer, "Close", "#0B72FF", lambda: None, fg="white", padx=14, pady=7, width=100)
    close_button.pack(side="right", padx=(8, 18), pady=12)
    cancel_button.pack(side="right", padx=4, pady=12)
    retry_button.pack(side="right", padx=4, pady=12)

    polling = {"active": True}

    def safe_close() -> None:
        # The ZIP must stay while workers are reading it.  Once the transfer
        # has stopped, closing this progress popup automatically removes it.
        snapshot = manager.get_batch_snapshot(batch_id)
        if snapshot and snapshot.get("running"):
            app._styled_alert(
                "Transfer Still Running",
                "The temporary ZIP is still being used by active uploads. "
                "Use Cancel first, wait until the transfer stops, then press Close. "
                "Close will delete the temporary ZIP automatically.",
                "warning",
                parent=win,
            )
            return

        ok, message, _snapshot = manager.cleanup_batch(batch_id)
        if not ok:
            app._styled_alert("Temporary ZIP", message, "warning", parent=win)
            return

        polling["active"] = False
        app._safe_popup_close(win)

    win.protocol("WM_DELETE_WINDOW", safe_close)
    close_button.configure(command=safe_close)

    def retry() -> None:
        ok, message, _snapshot = manager.retry_failed(batch_id)
        if not ok:
            app._styled_alert("Retry Failed", message, "warning", parent=win)
        else:
            summary_var.set(message)

    def cancel() -> None:
        ok, message, _snapshot = manager.cancel_batch(batch_id)
        if not ok:
            app._styled_alert("Cancel Transfer", message, "warning", parent=win)
        else:
            summary_var.set(message)

    retry_button.configure(command=retry)
    cancel_button.configure(command=cancel)

    def render(snapshot: Dict[str, Any]) -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        summary = snapshot.get("summary", {})
        state = snapshot.get("state", "")
        summary_var.set(
            f"{state}  •  {summary.get('success', 0)} success  •  "
            f"{summary.get('failed', 0)} failed  •  {summary.get('waiting', 0)} waiting  •  "
            f"{summary.get('active', 0)} active"
        )
        for job in snapshot.get("jobs", []):
            status = str(job.get("status", ""))
            if status == "Success":
                color = "#16A34A"
            elif status.startswith("Failed"):
                color = "#EF4444"
            elif status == "Cancelled":
                color = "#F97316"
            elif status in ("Uploading", "Connecting"):
                color = "#0B72FF"
            else:
                color = "#64748B"

            row = tk.Frame(list_frame, bg="#FFFFFF")
            row.pack(fill="x", padx=10, pady=6)
            host_label = tk.Label(row, text=str(job.get("hostname", "")), font=("DejaVu Sans", 10, "bold"), bg="#FFFFFF", fg="#0F172A", anchor="w", width=18)
            host_label.pack(side="left")
            middle = tk.Frame(row, bg="#FFFFFF")
            middle.pack(side="left", fill="x", expand=True, padx=6)
            state_label = tk.Label(middle, text=status, font=("DejaVu Sans", 9, "bold"), bg="#FFFFFF", fg=color, anchor="w")
            state_label.pack(anchor="w")
            detail_label = tk.Label(middle, text=str(job.get("message", "")), font=("DejaVu Sans", 8), bg="#FFFFFF", fg="#64748B", anchor="w", wraplength=300, justify="left")
            detail_label.pack(anchor="w")
            percent = int(job.get("progress", 0) or 0)
            percent_label = tk.Label(row, text=f"{percent}%", font=("DejaVu Sans", 9, "bold"), bg="#FFFFFF", fg=color, width=5, anchor="e")
            percent_label.pack(side="right")
            for widget in (row, host_label, middle, state_label, detail_label, percent_label):
                widget.bind("<MouseWheel>", wheel, add="+")
                widget.bind("<Button-4>", wheel, add="+")
                widget.bind("<Button-5>", wheel, add="+")

        running = bool(snapshot.get("running"))
        retry_button.configure(state="disabled" if running or not summary.get("failed", 0) and not summary.get("cancelled", 0) else "normal")
        cancel_button.configure(state="normal" if running else "disabled")
        win.after_idle(on_frame_configure)

    def poll() -> None:
        if not polling["active"]:
            return
        try:
            snapshot = manager.get_batch_snapshot(batch_id)
            if snapshot is None:
                summary_var.set("Transfer batch is no longer available.")
            else:
                render(snapshot)
        except Exception as exc:
            summary_var.set(f"Could not refresh transfer status: {exc}")
        try:
            if polling["active"] and win.winfo_exists():
                win.after(350, poll)
        except Exception:
            pass

    poll()
