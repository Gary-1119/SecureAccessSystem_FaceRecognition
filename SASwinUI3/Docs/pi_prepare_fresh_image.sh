#!/usr/bin/env bash
# Prepare a Raspberry Pi SAS image for cloning.
#
# Run this on the Pi only after confirming you are preparing the MASTER image.
# This script stops the Pi app, clears runtime files, and leaves app code/model
# files in place.

set -euo pipefail

APP_DIR="${APP_DIR:-/home/jbl_facerec/FaceRecognition}"
APP_USER="${APP_USER:-jbl_facerec}"
CLEAR_FACE_USERS="${CLEAR_FACE_USERS:-1}"
CLEAR_SFTP_TARGETS="${CLEAR_SFTP_TARGETS:-1}"
CLEAR_PI_ADMINS="${CLEAR_PI_ADMINS:-1}"
RESET_SETTINGS="${RESET_SETTINGS:-1}"

echo "SAS Pi fresh-image cleanup"
echo "App directory: ${APP_DIR}"
echo

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory not found: ${APP_DIR}" >&2
  exit 1
fi

echo "Stopping known SAS Pi services/processes..."
sudo systemctl stop face-recognition-tty5.service 2>/dev/null || true
pkill -f "${APP_DIR}/gui.py" 2>/dev/null || true
pkill -f "${APP_DIR}/face_api.py" 2>/dev/null || true
pkill -f "${APP_DIR}/recog.py" 2>/dev/null || true

cd "${APP_DIR}"

echo "Clearing runtime logs and transfer/temp files..."
rm -f recognition_result.json
rm -f recognition_result.json.tmp*
rm -f /home/"${APP_USER}"/desktop-gui.log
rm -f /home/"${APP_USER}"/tty5-gui.log

find LOG -type f -delete 2>/dev/null || true
find received_face_data/pending -type f -delete 2>/dev/null || true
find received_face_data/accepted -type f -delete 2>/dev/null || true
find received_face_data/rejected -type f -delete 2>/dev/null || true
find temp_export -type f -delete 2>/dev/null || true
find temp_import -type f -delete 2>/dev/null || true
find face_data_import_backups -type f -delete 2>/dev/null || true

mkdir -p LOG
mkdir -p received_face_data/pending received_face_data/accepted received_face_data/rejected
mkdir -p temp_export temp_import

if [[ "${CLEAR_SFTP_TARGETS}" == "1" ]]; then
  echo "Resetting saved SFTP target list..."
  cat > sftp_target.txt <<'EOF'
# Saved SFTP target Pis. One hostname or IPv4 address per line.
EOF
fi

if [[ "${CLEAR_PI_ADMINS}" == "1" ]]; then
  echo "Clearing Pi-local admins.txt..."
  : > admins.txt
fi

if [[ "${RESET_SETTINGS}" == "1" ]]; then
  echo "Resetting Pi settings.json credentials/server path..."
  cat > settings.json <<'EOF'
{
  "username": "",
  "password": "",
  "pc_save_path": "",
  "auto_capture": false,
  "camera_rotation": 0,
  "unlock_transport": "websocket"
}
EOF
fi

if [[ ! -f user.json ]]; then
  echo "{}" > user.json
fi

if [[ "${CLEAR_FACE_USERS}" == "1" ]]; then
  echo "Clearing registered face users, embeddings, and photos..."
  rm -f face_data/users.json
  rm -f face_data/users.json.bak
  rm -f face_data/embeddings.npz
  rm -f face_data/embeddings.npz.bak
  rm -rf face_data/photos
  mkdir -p face_data/photos
fi

echo "Preserving face_data/models if present."
mkdir -p face_data/models

echo "Fixing ownership..."
sudo chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo
echo "Optional OS clone cleanup, run manually only if approved for your Pi image:"
echo "  sudo truncate -s 0 /etc/machine-id"
echo "  sudo rm -f /etc/ssh/ssh_host_*"
echo "  history -c"
echo
echo "Cleanup complete. Shut down the Pi cleanly before reading the SD card image:"
echo "  sudo shutdown -h now"
