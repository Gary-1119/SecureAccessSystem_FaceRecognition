SAS v109 — Pi Storage Monitoring Sync

Purpose
- Adds Pi Storage card in SAS Settings.
- Fetches the Pi's live GET /system/storage API response after connection, whenever Settings opens, on manual Refresh, and every 30 seconds while Settings is visible.
- Uses a background thread so the SAS user interface does not freeze.

Deploy to the SAS source folder:
  sas_dashboard_modular/

Replace:
- dashboard.py
- services/face_api_service.py

The Pi app must first have the v109 Pi storage patch installed, otherwise SAS will show a non-fatal storage-unavailable message.

Not changed:
- Windows lock/unlock logic
- camera/recognition workflows
- credential format and server path
- SFTP/import/export
- Pi hostname management
