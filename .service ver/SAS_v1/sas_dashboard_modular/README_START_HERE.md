# Start Here - SAS Dashboard Modular Version

## 1. Folder structure

```text
sas_dashboard_modular/
│
├── main.py
├── dashboard.py
├── dialogs.py
├── ui_components.py
├── app_config.py
└── services/
    ├── admin_service.py
    ├── credential_service.py
    ├── ad_service.py
    ├── face_api_service.py
    ├── recognition_state_service.py
    └── runtime_lock_service.py
```

## 2. How to run

Open PowerShell inside this folder:

```powershell
cd "sas_dashboard_modular"
python main.py
```

If `python` is not recognised, use your full Python path:

```powershell
C:\Users\4372447\AppData\Local\Programs\Python\Python314\python.exe main.py
```

## 3. Where to edit now

### UI / Layout
Edit:

```text
dashboard.py
dialogs.py
ui_components.py
```

### Logic copied from lockapp.py
Edit:

```text
services/
```

## 4. What has already been moved from lockapp.py

### Admin logic
`services/admin_service.py`

- ensure admins.txt exists
- load admins
- save admin
- first login becomes admin
- check admin login

### Credential logic
`services/credential_service.py`

- read credential.txt
- save credential.txt

### Active Directory / SOAP logic
`services/ad_service.py`

- validate NTID exists
- encrypt password
- validate NTID + password
- validation with debug steps

### Raspberry Pi API logic
`services/face_api_service.py`

- test connection
- capture user
- train
- get result
- stop recognition
- delete user
- refresh users

### Recognition result JSON logic
`services/recognition_state_service.py`

- read recognition_result.json
- check detected/user_id/confidence/timestamp
- validate scan freshness

### Runtime lock logic
`services/runtime_lock_service.py`

- grant access
- lock system
- update face detected state from recognition result

## 5. Next function to migrate from lockapp.py

The next major logic to move is:

```text
_start_auto_scan()
_auto_scan_loop()
_get_idle_secs()
_poll_system_idle()
_apply_lock_controls()
_register_emergency_hotkey()
_disable_keyboard()
_enable_keyboard()
_disable_mouse()
_enable_mouse()
```

These should be added to:

```text
services/runtime_lock_service.py
```

Do not put new backend logic directly inside `dashboard.py` anymore.


## Basic runtime functions added in this version

- Settings Server Credentials now validates NTID + password before saving.
- Browse button now opens a folder picker for the server path.
- Security Options are loaded/saved to `credential.txt`.
- Inactivity lock time is loaded/saved and applied to the countdown timer.
- Server path is used for `recognition_result.json`.
- Server path is used to write logs under `SAS_LOG/YYYY-MM-DD.txt`.
- If `recognition_result.json` is valid/detected, the dashboard unlocks green and the countdown circle flips to Face Detected.
- If the face is no longer detected, the UI stays unlocked while countdown runs.
- If countdown reaches `00:00`, the dashboard locks red and stays at `00:00` until a valid face is detected again.
