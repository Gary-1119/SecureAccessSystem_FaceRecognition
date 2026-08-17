# SAS Modular v131 — WebSocket Face Unlock Transport

Windows SAS no longer polls `recognition_result.json` from the SMB server path to unlock the workstation.

The new unlock path is:

```text
Pi /ws/sas WebSocket
→ Windows SAS receives recognition_result
→ SAS validates lock_session_id, event_id, timestamp, and NTID
→ SAS unlocks
```

SMB still remains configured in Settings because it is still required for logs, backups, import/export, and face-data transfer.

## New SAS service

```text
services/websocket_client_service.py
```

Purpose:

- Connects to `ws://<pi-host>:5000/ws/sas`.
- Reconnects automatically if the Pi restarts or the network drops.
- Sends `lock_session_started` when SAS locks.
- Sends `lock_session_ended` after SAS unlocks.
- Emits received JSON events to `dashboard.py`.

## Removed SAS service

```text
services/recognition_state_service.py
```

This old service read `<server path>/recognition_result.json`. It is no longer needed.

## Important safety validation

SAS unlocks only when the event belongs to the current lock session. This prevents an old recognition event from unlocking a later lock state.
