# Pi App Patch v105 — Camera Rotation Sync

## Purpose

This patch adds a persisted camera-orientation setting to the Raspberry Pi Face
Recognition app. Use it when the Pi camera is physically mounted sideways or
upside down and hardware placement cannot be changed.

The setting is stored in the Pi's `settings.json` under:

```json
"camera_rotation": 0
```

Allowed values are `0`, `90`, `180`, and `270` degrees clockwise.

## What is synchronized

The Pi is the source of truth for camera orientation:

```text
Pi Settings or Windows SAS Settings
        ↓
Pi settings.json: camera_rotation
        ↓
Pi recognition / capture pipeline rotates each frame
        ↓
Pi local preview + Pi API /video-feed
        ↓
Windows SAS camera page + locked desktop camera panel
```

This means rotation is applied once at the camera source. SAS does not rotate a
second copy of the image, so the Pi preview and SAS viewer cannot disagree.

## Changed files

- **Added: `camera_rotation.py`**
  - Shared persisted camera-rotation helper.
  - Validates rotations and atomically saves `settings.json`.
  - Rotates frames without stretching them.

- **Modified: `gui.py`**
  - Adds `Camera Orientation` controls to the Pi Settings popup.
  - Allows 0°, 90°, 180°, and 270° orientation changes without remounting SMB.
  - Saves the selected rotation immediately and refreshes the local setting state.
  - Preserves the setting when Pi server credentials are later saved.

- **Modified: `recog.py`**
  - Applies the persisted rotation before live preview, face detection, face encoding,
    recognition boxes, local `recognition_result.json`, and API video streaming.

- **Modified: `capture.py`**
  - Applies the same persisted rotation to capture preview, face detection, and saved
    training photos.

- **Modified: `face_service.py`**
  - Returns `camera_rotation` through `GET /settings`.
  - Supports rotation-only `POST /settings` requests from Windows SAS without
    requiring credentials or remounting SMB.
  - Updates the Pi UI when a Windows SAS rotation request is received.
  - Preserves the setting during normal Windows Settings synchronisation.

## Not changed

- `train.py`
- `face_api.py` routes (the existing `/settings` route already forwards the payload)
- TTY5 systemd service files
- Face model, confidence threshold, SFTP/import/export, and admin workflow

## Deployment

Back up the current Pi files first:

```bash
cd /home/jbl_facerec/New2.0
cp gui.py gui.py.before_v105
cp recog.py recog.py.before_v105
cp face_service.py face_service.py.before_v105
cp capture.py capture.py.before_v105
```

Copy the files from this patch into:

```text
/home/jbl_facerec/New2.0/
```

Then validate and restart the TTY5 GUI:

```bash
cd /home/jbl_facerec/New2.0
python3 -m py_compile camera_rotation.py gui.py recog.py capture.py face_service.py
sudo systemctl restart face-recognition-tty5.service
```

## Test checklist

1. On the Pi, open **Settings** → **Camera Orientation**.
2. Select 90° / 180° / 270° and verify the local Pi preview changes.
3. In Windows SAS, open **Settings** → **Camera Orientation** and reconnect or
   revisit Settings; it should show the Pi's current value.
4. Change the value in SAS; verify the Pi preview and the locked SAS camera panel
   update within the next camera frame.
5. Capture and train one test photo. Saved photos must use the chosen orientation.
