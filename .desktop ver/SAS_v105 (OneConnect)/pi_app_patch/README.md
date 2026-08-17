# Pi App Patch v106 One-Pi Session

The Pi API now supports one active SAS owner at a time.

New endpoints:

- `GET /sas/session`
- `POST /sas/connect`
- `POST /sas/disconnect`
- `POST /sas/heartbeat`

The WebSocket `/ws/sas` also receives SAS client identity and only sends unlock events to the active owner.
