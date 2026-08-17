#!/usr/bin/env bash
# Install/update the limited root helper required by the Pi Settings hostname/reboot UI.
# v108 installs hostname persistence protection as part of the fixed helper.

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo:" >&2
    echo "sudo bash /home/jbl_facerec/FaceRecognition/deployment/install_system_control.sh" >&2
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HELPER_SOURCE="${SCRIPT_DIR}/face-recognition-system-control.sh"
SUDOERS_SOURCE="${SCRIPT_DIR}/face-recognition-system-control.sudoers"
HELPER_DEST="/usr/local/sbin/face-recognition-system-control"
SUDOERS_DEST="/etc/sudoers.d/face-recognition-system-control"

[[ -f "${HELPER_SOURCE}" ]] || { echo "Missing helper script: ${HELPER_SOURCE}" >&2; exit 1; }
[[ -f "${SUDOERS_SOURCE}" ]] || { echo "Missing sudoers file: ${SUDOERS_SOURCE}" >&2; exit 1; }

install -o root -g root -m 755 "${HELPER_SOURCE}" "${HELPER_DEST}"
install -o root -g root -m 440 "${SUDOERS_SOURCE}" "${SUDOERS_DEST}"

visudo -cf "${SUDOERS_DEST}"
echo "Installed hostname persistence helper: ${HELPER_DEST}"
echo "The Pi Settings Device Control page can now persist hostname changes across reboot."
