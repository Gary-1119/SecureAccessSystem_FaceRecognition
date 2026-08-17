# SASstream Reliability Test Checklist

Run this checklist before packaging or deploying to production PCs.

## Environment

- Windows 10/11 machine, standard non-admin user.
- Python 3.11 or 3.12 production environment.
- Dependencies installed from `requirements.txt`.
- Face model folder exists at `face_data/models/buffalo_l`.
- Company RTSP camera hostname is reachable.

## Startup

- Launch `run.ps1`.
- App opens without console traceback.
- Login screen symbols render normally: close button, password bullets, and login arrow are not mojibake.
- Settings can load saved credentials without corrupting `credential.txt`.
- Confirm `credential.txt` does not contain the plain password after Save Connect.

## Camera And Recognition

- Connect camera hostname in Settings.
- Face Recognition preview reaches Live state.
- Stop/restart source camera and confirm preview recovers after reconnect.
- Lock Windows/SAS, unlock Windows, and confirm the app still receives latest frames.
- Register one user and verify `face_data/users.json`, `embeddings.npz`, and PNG photo are created.
- Recognized registered user unlocks SAS.
- Unknown user does not unlock SAS.
- If two faces appear, closest/largest face is selected.

## Data Safety

- Register a user, then confirm `.bak` files exist after later updates.
- Export face data ZIP to a user-entered local or SMB path and confirm the ZIP is created in that selected path.
- Import the same ZIP on another PC and verify users merge by employee ID.
- Confirm import creates a dated ZIP under `face_data/backups` before the merge starts.
- Open Restore from Face Data Transfer, restore a backup version, and verify users/photos match that version.
- Delete an unneeded local backup from the Restore popup and confirm no SMB/server ZIP is removed.
- Simulate bad/corrupt `users.json` only on a test copy and confirm `.bak` recovery behavior.

## Lock Controls

- With non-admin user, lock SAS and confirm configured keyboard/mouse blocking behavior.
- Confirm emergency unlock hotkey `Ctrl + Shift + Alt` releases keyboard/mouse.
- Confirm emergency unlock does not grant Settings/Face Recognition admin access.
- Confirm lock controls are released when the app exits normally.

## Logging

- Confirm `SAS_LOG/YYYY-MM-DD_app.log` is created for technical app logs.
- Confirm RTSP disconnect/reconnect errors are written to the log.
- Confirm audit log still writes daily files in `SAS_LOG`.
- Confirm daily audit and app logs older than 14 days are removed by date.

## Automated Smoke Tests

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m unittest discover -s tests
```
