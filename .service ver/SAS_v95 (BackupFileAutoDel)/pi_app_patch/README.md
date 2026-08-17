# Pi App Patch v106 — Recognition Result Cleanup and Delete-Backup Retention

## Purpose

This patch fixes two storage-maintenance behaviours in the Raspberry Pi Face
Recognition application:

1. **Only one active `recognition_result.json` file is kept.**
2. **User/encoding safety backups created before deletion are retained for 30
   days, then removed automatically.**

It is built on top of Pi App Patch v105 (Camera Rotation Sync).

---

## 1. Recognition-result files

The active Pi-local recognition state remains exactly one file:

```text
/home/jbl_facerec/New2.0/recognition_result.json
```

Each new recognition result overwrites this same file atomically. The previous
offline-safe implementation used unique temporary filenames such as:

```text
recognition_result.json.tmp-<process>-<thread>
```

If a write was interrupted, those temporary files could remain visible beside
the real JSON file. They are not separate recognition-history records and are
not required by SAS.

This patch now uses a single short-lived temporary file:

```text
recognition_result.json.tmp
```

and then replaces the real `recognition_result.json` file. It also removes old
temporary files matching this exact temp-file pattern:

```text
recognition_result.json.tmp*
```

The live `recognition_result.json` file itself is never removed by this cleanup.

### Where cleanup happens

- Pi-local temporary result files: when `recog.py` starts after the Pi GUI
  restart.
- SMB temporary result files: on the first successful server delivery after
  SMB/LAN reconnects.

---

## 2. One-month retention for pre-delete backups

Only the following **pre-delete safety backups** in the project root are
eligible for automatic deletion:

```text
deleted_user_backup_<user>_<timestamp>/
encodings_backup_before_delete_<user>_<timestamp>.pickle
encodings_backup_before_api_delete_<user>_<timestamp>.pickle
encodings.pickle.bak
```

Retention period: **30 days** from the file/folder modification time.

Cleanup runs:

- once when the Pi app starts,
- once every 24 hours while the Pi app is running,
- immediately after a user deletion.

If the Pi is off at the exact 30-day point, cleanup occurs the next time the Pi
app runs. This prevents the maintenance task from affecting recognition,
capture, or the TTY5 interface.

### Intentionally not changed

The following import ZIP backup flow is untouched:

```text
received_face_data/pending/backup_before_import_*.zip
```

Import backups continue to be created in the **pending** folder and are not
removed by this patch. Pending, accepted, rejected, export, dataset, and normal
training files are outside the retention cleanup scope.

---

## Changed files

### Added: `backup_retention.py`

- Contains the 30-day retention rule for pre-delete user/encoding backups.
- Scans only the project root; it does not scan or modify the pending import
  folder.

### Modified: `recog.py`

- Uses one fixed temporary file for local and SMB recognition-result writes.
- Cleans stale `recognition_result.json.tmp*` files safely.
- Keeps exactly one live local `recognition_result.json` state file.
- Preserves the offline-safe local/SMB delivery design from v104/v105.

### Modified: `gui.py`

- Schedules delete-backup cleanup at Pi application startup and every 24 hours.
- Runs a retention check after local or API user deletion.
- Does not modify import ZIP backup behaviour.

### Modified: `face_service.py`

- Runs the same retention check after API/SAS user deletion.
- Returns the number of expired delete backups removed in the delete response.

### Added: `CHANGED_FILES.txt`

- Short change summary for deployment tracking.

---

## Not changed

- `capture.py`
- `train.py`
- `face_api.py`
- `camera_rotation.py`
- TTY5 systemd service files
- camera rotation function
- face model, recognition threshold, API routes, SFTP, import/export, pending
  ZIP backup location, admin workflow, and SAS logic

---

## Deployment

Back up the current Pi files through SSH first:

```bash
cd /home/jbl_facerec/New2.0

cp gui.py gui.py.before_v106
cp recog.py recog.py.before_v106
cp face_service.py face_service.py.before_v106
```

Upload these four files from this patch into:

```text
/home/jbl_facerec/New2.0/
```

```text
gui.py
recog.py
face_service.py
backup_retention.py
```

Do not overwrite `dataset`, `received_face_data`, `settings.json`, `user.json`,
`encodings.pickle`, or any existing pending ZIP backup.

Then validate and restart:

```bash
cd /home/jbl_facerec/New2.0
python3 -m py_compile backup_retention.py gui.py recog.py face_service.py
sudo systemctl restart face-recognition-tty5.service
```

---

## Test checklist

1. After the Pi app restarts, open `/home/jbl_facerec/New2.0/` and confirm only
   `recognition_result.json` remains as the active result file. Old
   `recognition_result.json.tmp*` files should disappear.
2. Connect LAN and verify any stale SMB temp result files disappear after the
   first successful recognition-result delivery.
3. Confirm face recognition and SAS unlock still work normally.
4. Confirm `received_face_data/pending/backup_before_import_*.zip` files remain
   unchanged.
5. To test retention without waiting 30 days, create a deliberately old
   pre-delete backup in a test environment and restart the Pi app. Do not age or
   delete production backups solely for testing.
