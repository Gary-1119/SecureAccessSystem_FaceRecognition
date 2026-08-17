#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/jbl_facerec/FaceRecognition"
AUTOSTART_DIR="/home/jbl_facerec/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/facerecognition.desktop"

mkdir -p "$AUTOSTART_DIR"
cat > "$DESKTOP_FILE" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Face Recognition GUI
Comment=Start Face Recognition GUI after Raspberry Pi Desktop login
Exec=bash -lc 'sleep 10; cd /home/jbl_facerec/FaceRecognition && /home/jbl_facerec/FaceRecognition/.venv/bin/python gui.py >> /home/jbl_facerec/desktop-gui.log 2>&1'
Terminal=false
X-GNOME-Autostart-enabled=true
DESKTOP

chmod 644 "$DESKTOP_FILE"
echo "Installed desktop autostart: $DESKTOP_FILE"
echo "Make sure Raspberry Pi boot is set to Desktop Autologin."
echo "App folder expected at: $APP_DIR"
