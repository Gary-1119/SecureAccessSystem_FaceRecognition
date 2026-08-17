"""Limited privileged device-control bridge for the Pi GUI.

The GUI runs as the non-root ``jbl_facerec`` user.  Hostname and reboot actions
must therefore be delegated to one fixed, root-owned helper script installed by
``deployment/install_system_control.sh``.  This module never runs arbitrary
shell commands and does not ask the GUI to handle a sudo password.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Sequence

SYSTEM_CONTROL_HELPER = "/usr/local/sbin/face-recognition-system-control"

# Standard single-label Linux hostname: letters/numbers/hyphen, 1-63 chars,
# and not starting or ending with a hyphen.  The app does not impose a product
# naming convention such as FaceRecognition-02.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


@dataclass(frozen=True)
class SystemControlResult:
    ok: bool
    message: str


class SystemControlError(RuntimeError):
    """Raised when the limited root helper cannot complete a request."""


def validate_hostname(value: str) -> str:
    """Validate and normalize a Linux hostname entered in the Pi GUI."""
    hostname = str(value or "").strip()
    if not hostname:
        raise ValueError("Hostname cannot be empty.")
    if len(hostname) > 63:
        raise ValueError("Hostname must be 63 characters or fewer.")
    if not _HOSTNAME_RE.fullmatch(hostname):
        raise ValueError(
            "Hostname may contain only letters, numbers, and hyphens. "
            "It cannot start or end with a hyphen."
        )
    return hostname


def _run_helper(args: Sequence[str], timeout: float = 20.0) -> str:
    """Run only the fixed root-owned helper through passwordless sudo."""
    command = ["sudo", "-n", SYSTEM_CONTROL_HELPER, *[str(arg) for arg in args]]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SystemControlError(
            "System-control helper is not installed. Run deployment/install_system_control.sh first."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemControlError("The system-control request timed out.") from exc

    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        detail = error or output or "Unknown system-control error."
        if "a password is required" in detail.lower() or "not allowed" in detail.lower():
            detail = (
                "Permission is not configured. Run "
                "deployment/install_system_control.sh with sudo first."
            )
        raise SystemControlError(detail)
    return output


def verify_system_control_ready() -> SystemControlResult:
    """Confirm that the fixed helper and sudo rule are ready without changing anything."""
    output = _run_helper(["status"], timeout=8.0)
    return SystemControlResult(True, output or "READY")


def change_hostname(hostname: str) -> SystemControlResult:
    """Change the OS hostname through the fixed helper; caller should reboot after success."""
    safe_hostname = validate_hostname(hostname)
    output = _run_helper(["set-hostname", safe_hostname], timeout=20.0)
    return SystemControlResult(True, output or f"HOSTNAME_CHANGED={safe_hostname}")


def request_reboot() -> None:
    """Ask the fixed helper to reboot without waiting for the Pi to shut down.

    Call :func:`verify_system_control_ready` first to surface permission errors
    while the GUI is still available.  The reboot helper is then launched in a
    detached process because a successful reboot intentionally ends the app.
    """
    command = ["sudo", "-n", SYSTEM_CONTROL_HELPER, "reboot"]
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise SystemControlError(
            "System-control helper is not installed. Run deployment/install_system_control.sh first."
        ) from exc
    except OSError as exc:
        raise SystemControlError(f"Could not request Pi reboot: {exc}") from exc
