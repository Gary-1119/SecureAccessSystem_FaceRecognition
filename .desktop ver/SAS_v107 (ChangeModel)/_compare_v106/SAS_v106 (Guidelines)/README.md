# SAS v104 — Pi Desktop First-Start Patch

This is a Pi-only desktop startup patch for a freshly imaged Raspberry Pi.

## Main behavior

- The Raspberry Pi app runs as a normal Desktop `.desktop` autostart app.
- It no longer forces the TTY5 fullscreen/kiosk layout when launched from Raspberry Pi Desktop.
- Fresh-start folders/files are created automatically when the app starts.
- The hard-coded developer account stays code-only:

```text
Username: admin
Password: penAteam
```

- The hard-coded developer account is not written into `admins.txt`.
- The first real AD-authenticated user login becomes the first admin and is saved into `admins.txt`.

## Notes

The admin file used by this project is `admins.txt`.
If an old copied file contains `admin`, the app removes it so `admin / penAteam` remains hard-coded only.

## Desktop autostart

Use the included file or installer:

```bash
cd /home/jbl_facerec/FaceRecognition
bash deployment/install_desktop_autostart.sh
```

Then set Raspberry Pi OS to Desktop Autologin using `sudo raspi-config`.

## Not changed

- SAS Windows modular code
- WebSocket protocol
- Recognition algorithm
- Capture/training logic
- SFTP/import/export logic
