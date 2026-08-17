#!/usr/bin/env bash
set -u

cd /home/jbl_facerec/FaceRecognition

export HOME=/home/jbl_facerec
export PYTHONUNBUFFERED=1

exec /home/jbl_facerec/FaceRecognition/.venv/bin/python \
  /home/jbl_facerec/FaceRecognition/gui.py \
  >> /home/jbl_facerec/tty5-gui.log 2>&1
