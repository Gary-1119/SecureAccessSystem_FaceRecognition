# SAS v123 — Multi-Pi SFTP Checkbox Fix

## Fix

The Multi-Pi SFTP popup previously used `QCheckBox` indicators styled only with a
background color. On the deployed Windows UI, selected items could look blank, so
users could not confirm whether a Pi had been selected.

This patch replaces only the Multi-Pi SFTP popup checkboxes with the same
checkable `QPushButton("✓")` pattern already used by the working **Disable Keyboard**
and **Disable Mouse** controls in SAS Settings.

## Result

- The Select All checkbox visibly shows a white `✓` on a black square when selected.
- Each target Pi checkbox visibly shows a white `✓` on a black square when selected.
- Clicking **Select All** selects every currently visible hostname.
- Clicking the **Select All** text also toggles the same checkbox.
- Searching, adding/removing targets, transfer progress, retries, and Pi API calls are unchanged.

## Changed Files

### Modified
- `sas_dashboard_modular/dashboard.py`
  - Multi-Pi SFTP popup checkbox rendering only.

### Not Changed
- `sas_dashboard_modular/services/face_api_service.py`
- Any Pi file
- Pi API routes
- `sftp_target.txt`
- Transfer queue / four-worker logic
- SAS lock/unlock, settings, camera, storage, import/export, or Check Received

## Install

1. Close SAS.
2. Back up the existing file:
```bat
cd C:\Your\SAS\Project\sas_dashboard_modular
copy dashboard.py dashboard.py.before_v123
```
3. Replace only `dashboard.py` from this patch.
4. Restart SAS.

For a packaged EXE, rebuild the EXE after replacing the source file.
