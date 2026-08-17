#!/usr/bin/env bash
# Starts the Face Recognition GUI inside the dedicated TTY5 X session.
set -euo pipefail

export FACE_RECOGNITION_FULLSCREEN=1
export PYTHONUNBUFFERED=1

cd /home/jbl_facerec/New2.0
exec /usr/bin/python3 /home/jbl_facerec/New2.0/gui.py
