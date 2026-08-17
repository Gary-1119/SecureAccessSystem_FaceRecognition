# Pi Fresh Start And SD Image Guide

This guide is based on the `pi_app_patch` folder in `SAS_v107 (ChangeModel).zip`.

## Keep On The Master Image

- Pi application code in `/home/jbl_facerec/FaceRecognition`
- Python virtual environment and installed dependencies
- `face_api.py`, `face_service.py`, `websocket_service.py`, `recog.py`, `capture.py`, `insightface_engine.py`
- `deployment` scripts and installed autostart/system-control setup
- TTY5/systemd service files if the Pi is intended to run kiosk/lock mode
- InsightFace runtime model files under `face_data/models`
- Camera and OS configuration needed for the Pi camera

## Clean Before Creating The Image

Run cleanup only after the Pi app is stopped.

A ready-to-use cleanup script is saved beside this guide:

```bash
pi_prepare_fresh_image.sh
```

Two common modes:

```bash
# Clean fresh start. No registered face users.
bash pi_prepare_fresh_image.sh

# Only if you intentionally want every cloned Pi to share existing registered users.
CLEAR_FACE_USERS=0 bash pi_prepare_fresh_image.sh
```

Recommended runtime data to clear:

- `LOG/*`
- `desktop-gui.log`
- `tty5-gui.log`
- `recognition_result.json`
- `received_face_data/pending/*`
- `received_face_data/accepted/*`
- `received_face_data/rejected/*`
- `temp_export/*`
- `temp_import/*`
- `temp_export/multi_sftp/*`
- `face_data_import_backups/*`
- `sftp_target.txt` saved target Pi hostnames, unless every cloned Pi should start with the same list
- `admins.txt` if the cloned Pi should start with no local Pi admins
- `settings.json` credentials/path values if the cloned Pi should not inherit SMB username, password, or server path

Face recognition data decision:

- Default fresh start clears `face_data/users.json`, `face_data/embeddings.npz`, and `face_data/photos/*`.
- Keep them only if all cloned Pis should share the same registered users.
- Keep `face_data/models/*` because it is runtime model data, not registered user data.

## OS Identity Cleanup Before Imaging

Each cloned Pi should not keep the same network identity forever.

Before making the image, decide:

- Set a generic hostname such as `SAS-PI-TEMPLATE`, then rename after flashing.
- Clear or regenerate `/etc/machine-id` for cloned devices.
- Regenerate SSH host keys after cloning if the Pis will be used on the same network.
- Clear shell history and temporary files.
- Keep Wi-Fi/network config only if all target devices use the same network.

## Create The `.img` On Windows

1. Stop the Pi app/service.
2. Run the fresh-image cleanup script.
3. Shut down the Pi cleanly.
4. Remove the SD card.
5. Insert the SD card into Windows.
6. Use Win32 Disk Imager and choose `Read` to create the master `.img`.
7. Flash the `.img` to another SD card using Raspberry Pi Imager, BalenaEtcher, or Win32 Disk Imager.
8. Boot the cloned Pi.
9. Change the hostname to a unique value.
10. Verify SAS can connect, preview camera, read users, fetch Pi logs, read storage, and lock/unlock.

## Important Notes

- Pi log export API exports only today's local Pi log as a ZIP.
- Multi-Pi SFTP sends to `/home/<pi-user>/FaceRecognition/received_face_data/pending`.
- The Pi storage API is `/system/storage`.
- The Pi app creates missing first-start files automatically: `user.json`, `settings.json`, `admins.txt`, and transfer folders.
