# SAS Automation Testing

Run this before building or deploying the exe:

```powershell
.\run-automation-tests.ps1
```

Current automated coverage:

- App settings hostname normalization and API URL generation.
- App settings clone isolation so changed UI hostname cannot mutate a running Pi session.
- Pi JSON parsing for received-file object arrays.
- Face-data import/export validation and SMB temporary credential settings.
- SMB path normalization and mounted ZIP path mapping.
- Pi connection controller reconnect behavior.
- Wrong-hostname connection failure behavior.
- Pi log download controller behavior.
- First valid sign-in/admin bootstrap behavior.

Still requiring real Pi/manual verification:

- Real camera preview rendering.
- Real websocket unlock event.
- Locked keyboard/mouse behavior.
- Pi offline/reconnect while locked.
- Windows toast notification delivery and sound.
- Real SMB export/import credentials.
- Real SFTP multi-Pi transfer progress.
- Pi storage API endpoint/response shape.
