# SAS Dashboard Modular Version

This folder splits the previous single heavy Python file into smaller files.

## Files

- `main.py` — application entry point
- `dashboard.py` — main PySide dashboard window and page-building methods
- `dialogs.py` — login popup, login success, and failed login UI classes
- `ui_components.py` — reusable UI widgets such as cards, progress ring, tab buttons, animated stack, and toggle control
- `app_config.py` — theme colours, constants, thread-safe UI bridge, and legacy LockApp configuration values

## How to run

```powershell
python main.py
```

Or use your full Python path:

```powershell
C:\Users\4372447\AppData\Local\Programs\Python\Python314\python.exe main.py
```

## Maintenance guide

When you want to edit:
- Login UI → `dialogs.py`
- Main dashboard layout/pages → `dashboard.py`
- Colours/constants → `app_config.py`
- Shared custom widgets → `ui_components.py`
- App start-up only → `main.py`


See `README_START_HERE.md` for the modular logic plan.
