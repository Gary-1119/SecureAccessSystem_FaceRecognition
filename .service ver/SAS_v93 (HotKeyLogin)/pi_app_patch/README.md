# Pi App Patch v104 — Offline-Safe SMB Result Delivery and TTY5 Fullscreen

## Purpose

This patch prevents the Raspberry Pi Face Recognition GUI from depending on the
LAN/SMB server during normal camera operation.

It fixes two behaviours:

1. **Boot without LAN** — TTY5 fullscreen is scheduled with repeated timed
   requests instead of depending on Tkinter becoming idle.
2. **LAN unplugged while running** — the recognition loop always writes the
   local `recognition_result.json` immediately and never directly writes to the
   SMB mount. SMB delivery occurs in a background worker.

## Changed Files

- **Modified: `gui.py`**
  - Schedules fullscreen immediately after the UI is built.
  - Retries fullscreen at 0, 150, 400, 900, 1800, 3500 and 6000 ms.
  - Runs the automatic startup SMB mount in a background thread.
  - When the server/LAN is unavailable at boot, the Pi continues in local mode
    without blocking the TTY5 GUI or displaying a startup error dialog.

- **Modified: `recog.py`**
  - Writes the local `recognition_result.json` atomically and immediately.
  - Replaces direct SMB recognition-result writes with one background,
    latest-result-only publisher.
  - Checks the CIFS mount and SMB port before touching `/mnt/pcshare`.
  - Drops offline/stale results instead of replaying an old authorization later.
  - After LAN/SMB reconnects, first resets the SMB result to a safe
    `detected: false` state and requires a new live recognition event.
  - Moves server `user.json` sync and server log writes out of the camera loop.

- **Modified: `face_service.py`**
  - Uses the shared local writer and background SMB result publisher when
    settings are synchronised from Windows SAS.
  - Removes direct SMB result-file writes from the settings reset path.

- **Added: `README.md`**
  - Documents this patch and deployment/testing steps.

## Not Changed

- `capture.py`
- `train.py`
- `face_api.py`
- TTY5 systemd service files
- Face detection/encoding model, confidence threshold, API routes, SFTP,
  dataset import/export and admin workflow

## Deployment

Back up the current files on the Pi first:

```bash
cd /home/jbl_facerec/New2.0
cp gui.py gui.py.before_v104
cp recog.py recog.py.before_v104
cp face_service.py face_service.py.before_v104
```

Copy the three modified `.py` files from this patch into:

```text
/home/jbl_facerec/New2.0/
```

Validate and restart the TTY5 GUI:

```bash
cd /home/jbl_facerec/New2.0
python3 -m py_compile gui.py recog.py face_service.py
sudo systemctl restart face-recognition-tty5.service
```

## Expected Behaviour

| Scenario | Expected Result |
|---|---|
| Boot with LAN connected | TTY5 app opens fullscreen; SMB result delivery works. |
| Boot without LAN | TTY5 app still opens fullscreen; camera and local recognition work. |
| Remove LAN while running | GUI/camera remain responsive; local result keeps updating; SMB delivery stops safely. |
| Reconnect LAN | First remote result is reset to `detected: false`; a new live scan is needed before SAS can unlock. |
