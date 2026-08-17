# Pi App Patch v104 — Desktop First-Start Admin Setup

This patch is for the Raspberry Pi Desktop `.desktop` startup version.

## What changed

- Desktop launch uses a normal window instead of forced TTY5 fullscreen.
- Fresh Pi startup automatically creates required local files and folders.
- First real AD-authenticated login becomes the first stored admin.
- The local developer account stays hard-coded only:

```text
admin / penAteam
```

It is intentionally not written into `admins.txt`.

## Fresh-start files/folders created

```text
dataset/
LOG/
received_face_data/pending/
received_face_data/accepted/
received_face_data/rejected/
temp_export/
temp_import/
user.json
settings.json
admins.txt
```

## Desktop autostart install

After copying the Pi app to `/home/jbl_facerec/FaceRecognition`, run:

```bash
cd /home/jbl_facerec/FaceRecognition
bash deployment/install_desktop_autostart.sh
```

Then set boot mode to Desktop Autologin:

```bash
sudo raspi-config
```

Use:

```text
System Options -> Boot / Auto Login -> Desktop Autologin
```

## Important

Before at least one user is captured and trained, recognition may show `recognition_running: false` because `encodings.pickle` does not exist yet. That is expected on a fresh Pi.
