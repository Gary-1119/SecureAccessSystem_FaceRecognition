# Pi App Patch v120 — Active Directory Password Login

## Base used

This patch was created from the working Pi multi-SFTP GUI in:

```text
pi_app_patch_v118_multi_pi_sftp_safe.zip
```

Base `gui.py` SHA-256:

```text
eb24f2e486e7d7d109829010fc8f52c3cc049b7c3c973ff073da1d63907b2444
```

It changes only `gui.py`.

## New login behavior

The Pi Login popup now asks for:

- NTID
- Active Directory password

For normal users, the Pi uses the same SOAP sequence as SAS:

1. `IsUserExistsInAD`
2. `DESEncrypt`
3. `ValidateUserCredentialsInAD`

A normal AD user still becomes the first Pi admin only when `admins.txt` is empty. Existing Pi admins must use their own AD password to sign in.

## Developer administrator requested

A built-in local developer administrator is enabled:

```text
NTID: admin
Password: penAteam
```

This account does not contact AD and remains an administrator even when `admins.txt` already contains other users. It is not added to `admins.txt`.

> This password is plain text inside `gui.py`, as requested. Anyone who can read the Pi application files can view it.

## Not changed

- Multi-Pi SFTP popup and its helper `multi_sftp_transfer.py`
- Auto cleanup on transfer popup close (`v119`)
- Settings layout, scroll behavior, hostname/reboot
- Server credentials and Save & Connect
- Camera rotation, Pi storage, SMB sync
- Admin Management behavior, except authenticated login now requires password
- Face recognition, capture, training, API, TTY5 service, SAS Windows app

## Install

1. Back up your current GUI:

```bash
cd /home/jbl_facerec/FaceRecognition
cp gui.py gui.py.before_v120
```

2. Upload only this patch's `gui.py` to:

```text
/home/jbl_facerec/FaceRecognition/gui.py
```

3. Validate and restart:

```bash
cd /home/jbl_facerec/FaceRecognition
python3 -m py_compile gui.py
sudo systemctl restart face-recognition-tty5.service
```

No cache clearing is required.

## Test order

1. Confirm the Pi app opens.
2. Log in with `admin` / `penAteam`.
3. Confirm Settings still shows hostname/reboot, transfer, camera rotation, storage, and Admin Management.
4. Test one normal AD admin account using the real AD password.
