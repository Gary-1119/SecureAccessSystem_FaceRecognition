# Pi App Patch v108 — Hostname Persistence Fix

## Why this patch is needed

Version v107 can change the currently running hostname, but on this Pi the old hostname returns after a reboot. This patch updates only the root helper used by **Pi Settings → Device Control**.

The updated helper now:

1. Writes the requested name explicitly to `/etc/hostname`.
2. Updates the `127.0.1.1` entry in `/etc/hosts`.
3. Sets the current live hostname through `hostnamectl`.
4. Adds a cloud-init protection file only when cloud-init is present, preventing a boot-time process from restoring an old image hostname.
5. Verifies that the persistent hostname was written before returning success to the Pi app.

## Installation

Upload the entire `deployment` folder to:

```text
/home/jbl_facerec/FaceRecognition/
```

Allow it to replace the existing `deployment` folder files. Then run through SSH or TTY3:

```bash
cd /home/jbl_facerec/FaceRecognition
sudo cp /usr/local/sbin/face-recognition-system-control \
  /usr/local/sbin/face-recognition-system-control.before_v108
sudo bash deployment/install_system_control.sh
sudo -n /usr/local/sbin/face-recognition-system-control status
```

Expected final result:

```text
READY
```

Then use **Pi Settings → Device Control → Apply Hostname & Reboot** again. Use a name different from the current name.

After reboot, verify from SSH or TTY3:

```bash
hostname
hostnamectl --static
cat /etc/hostname
grep -E '^127\.0\.1\.1' /etc/hosts
```

All four outputs should use the new hostname.

## Rollback

```bash
sudo cp /usr/local/sbin/face-recognition-system-control.before_v108 \
  /usr/local/sbin/face-recognition-system-control
sudo chmod 755 /usr/local/sbin/face-recognition-system-control
```

No Python files, camera logic, API, SMB, recognition data, TTY5 service, or SAS Windows files are changed.
