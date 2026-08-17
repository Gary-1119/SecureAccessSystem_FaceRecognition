# SAS Automation Testing

Run this before building or deploying the exe:

```powershell
.\run-automation-tests.ps1
```

Current automated coverage:

- App settings hostname normalization and AJABILEYE URL generation.
- App settings clone isolation so changed UI hostname cannot mutate a running camera session.
- JabilEye JSON parsing for received-file object arrays.
- Face-data import/export validation and SMB temporary credential settings.
- SMB path normalization and mounted ZIP path mapping.
- Camera connection controller reconnect behavior.
- Wrong-hostname connection failure behavior.
- First valid sign-in/admin bootstrap behavior.

Still requiring real camera/manual verification:

- Real RTSP camera preview rendering.
- Real local face-recognition unlock event.
- Locked keyboard/mouse behavior.
- Camera offline/reconnect while locked.
- Real SMB export/import credentials.
