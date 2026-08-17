# Pi App Patch v119 — Auto-delete Temporary ZIP on Close

This patch is for a Pi already running the working v118 Multi-Pi SFTP feature.

## Changed file

### Modified: `multi_sftp_transfer.py`

- Removes the **Delete Temp ZIP** button from the Multi-Pi SFTP progress popup.
- When the user presses **Close** (or the window ×) after the transfer has stopped, the app deletes that batch's temporary ZIP automatically, then closes the popup.
- `Retry Failed` remains available while the popup stays open. Closing after a failed/cancelled batch intentionally discards the temporary ZIP, so retry is no longer available for that batch.
- If active uploads are still running, Close does not delete the ZIP because worker threads are still reading it. The app explains that the user must press Cancel, wait for the transfers to stop, then press Close. This prevents a transfer from breaking midway.

## Not changed

- `gui.py`
- Settings UI and Settings access
- target list / `sftp_target.txt`
- hostname and reboot
- server credentials
- camera rotation and storage
- SFTP worker limit (4)
- source ZIP creation
- target upload `.part` then rename behavior
- retry, cancel, or status logic
- face API/service
- SMB, recognition, and TTY5 service
- SAS Windows app

## Install

Run through SSH:

```bash
cd /home/jbl_facerec/FaceRecognition
cp multi_sftp_transfer.py multi_sftp_transfer.py.before_v119
```

Upload only this patch's `multi_sftp_transfer.py` into:

```text
/home/jbl_facerec/FaceRecognition/
```

Then run:

```bash
cd /home/jbl_facerec/FaceRecognition
python3 -m py_compile multi_sftp_transfer.py
sudo systemctl restart face-recognition-tty5.service
```
