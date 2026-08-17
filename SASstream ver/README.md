# SASstream Local RTSP Version

This version keeps the original PySide6 SAS desktop UI, keyboard/mouse lock,
emergency unlock, hardcoded admin fallback, SMB logs/backups, and import/export
screens.  The old dlib backend is replaced by a PC-local RTSP face
recognition engine.

## RTSP camera

The Settings camera hostname is converted into this fixed company stream format:

```text
rtsp://view_ZW2:IVCQtz@<hostname>:8554/jabileye-stream
```

Example hostname:

```text
jbleyepoc035
```

## Recognition path

```text
RTSP frame
-> InsightFace detects the closest/largest face
-> InsightFace creates a 512D embedding
-> NumPy compares it against the stored embedding matrix
-> recognized registered user can unlock SAS
```

Unknown users cannot unlock.  If more than one face is visible, recognition uses
the closest/largest face.

## Credentials

`credential.txt` stores the saved password using Windows DPAPI, so the password is not readable as plain text. The protected value can normally be decrypted only by the same Windows user profile that saved it. Old plain-text credential files are migrated on startup.

## Logs

SAS writes daily audit logs as `SAS_LOG/YYYY-MM-DD.txt` and daily technical app logs as `SAS_LOG/YYYY-MM-DD_app.log`. Both dated log types are cleaned automatically after 14 days. Non-date files are ignored by cleanup.

## Data storage

Local face data is stored beside the app:

```text
face_data/
  users.json
  embeddings.npz
  photos/              # PNG face samples
  backups/             # dated backup ZIPs created before import/restore
  models/buffalo_l/
```

`users.json` stores names and employee IDs. `embeddings.npz` stores the NumPy
embedding arrays. Export requires the user to enter/select a target folder.
Import/export ZIP files include users, embeddings and photos, but not the model
files. Before every import, SAS creates a dated local backup ZIP in
`face_data/backups`. Restore can roll back to one of those versions, and restore
creates its own safety backup first. Live import/save data keeps `.bak`
protection files.

## Register user

1. Connect the camera hostname in Settings.
2. Open Face Recognition.
3. Press Recognize if you want live preview.
4. Type employee name and employee ID / NTID.
5. Press Register.

No Train button is needed. The embedding is created and stored immediately on this PC.

## Run from source

```powershell
.\run.ps1
```

Or:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" .\main.py
```

## Build later

For EXE packaging, include `face_data/models/buffalo_l` with the app so the
company network does not need to download the model from GitHub.  Inno Setup can
then place the installed app shortcut in `shell:common startup`.


