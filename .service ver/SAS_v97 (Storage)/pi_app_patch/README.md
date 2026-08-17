# Pi App Patch v115 — Compact Storage, Preserve Working Settings

## Why this patch exists

The previous storage patch added a large separate card. On the Pi screen, it could occupy
most of the visible Settings area and make the lower existing controls appear missing.

This patch starts directly from the user's working **v107 gui.py** and adds only a compact
read-only Pi Storage section inside the already-existing **Pi Network Identity** card.

## What it shows

- Used storage
- Total storage
- Available storage
- Percentage used
- A compact usage bar
- Root filesystem (`/`), normally the Pi SD-card storage

The displayed value is refreshed each time the Settings popup is opened.

## Changed file

### Modified: `gui.py`
Only one block was inserted below the existing Pi Network Identity help text.

## Not changed

- Settings scroll code
- Settings popup size/layout rules
- Login or admin checks
- Hostname controls
- Reboot controls
- Server Credentials / Save & Connect
- Auto-capture
- Camera rotation
- SFTP, import, export, Check Received
- Admin Management
- SMB, recognition, camera, API, TTY5 service
- SAS Windows application

No Python methods were removed, renamed, or replaced.

## Install

1. Restore/use the working v107 `gui.py` first if it is not already running.
2. Back it up:
```bash
cd /home/jbl_facerec/FaceRecognition
cp gui.py gui.py.before_v115
```
3. Upload this patch's `gui.py` to:
```text
/home/jbl_facerec/FaceRecognition/gui.py
```
4. Validate and restart:
```bash
cd /home/jbl_facerec/FaceRecognition
python3 -m py_compile gui.py
sudo systemctl restart face-recognition-tty5.service
```

No cache clearing is required.
