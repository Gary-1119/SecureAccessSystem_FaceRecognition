# Pi App Patch v131 — WebSocket Face Unlock Transport

This patch changes only the workstation unlock transport.

Old unlock transport:

```text
Pi writes recognition_result.json to SMB
SAS polls the server-path JSON file
```

New unlock transport:

```text
Pi sends recognition_result through /ws/sas WebSocket
SAS receives and validates it in real time
```

## Dependency

Install this on the Raspberry Pi environment:

```bash
pip install flask-sock
```

The HTTP API still runs without this package, but WebSocket unlock will not be available.

## WebSocket route

```text
ws://<Pi hostname or IP>:5000/ws/sas
```

SAS connects to this route after Pi API connection succeeds.

## Event flow

1. SAS locks.
2. SAS sends `lock_session_started` with a new `lock_session_id`.
3. Pi stores that session for the SAS WebSocket client.
4. Recognition loop detects a valid trained face.
5. Pi sends `recognition_result` with the same `lock_session_id`.
6. SAS validates and unlocks.

## SMB remains

SMB is still used for:

- `Pi_LOG`
- `user.json` sync
- import/export ZIP files
- SFTP transfer staging
- backup folders

Only SMB `recognition_result.json` delivery was removed.
