# Raspberry Pi TTY5 Fullscreen Face Recognition Service

This optional setup runs the Face Recognition GUI as a dedicated fullscreen X session on **TTY5**.
The regular Raspberry Pi Desktop remains available on **TTY7**.

Keyboard switching:

```text
Ctrl + Alt + F5  -> Face Recognition fullscreen screen
Ctrl + Alt + F7  -> Normal Raspberry Pi Desktop
```

## Important prerequisites

1. Use **X11**, not Wayland, because this setup starts a second X session with `xinit`.
2. Keep Raspberry Pi **Desktop Autologin** enabled so the normal desktop is still available.
3. Disable the existing GUI `.desktop` autostart file. Otherwise two Face Recognition GUIs can start and compete for the camera.

Switch to X11 if needed:

```bash
sudo raspi-config
# Advanced Options -> Wayland -> X11
```

Install required packages:

```bash
sudo apt update
sudo apt install -y xinit xserver-xorg
```

Disable the current `.desktop` GUI autostart without deleting it:

```bash
mv /home/jbl_facerec/.config/autostart/facerecognition.desktop \
   /home/jbl_facerec/.config/autostart/facerecognition.desktop.disabled
```

## Install the service files

Copy this project to `/home/jbl_facerec/New2.0` first. Then run:

```bash
cd /home/jbl_facerec/New2.0

sudo install -m 755 pi_app_patch/tty5_service_files/run_face_tty5.sh \
  /home/jbl_facerec/New2.0/run_face_tty5.sh

sudo install -m 755 pi_app_patch/tty5_service_files/switch-to-tty5.sh \
  /usr/local/sbin/switch-to-tty5.sh

sudo install -m 644 pi_app_patch/tty5_service_files/face-recognition-tty5.service \
  /etc/systemd/system/face-recognition-tty5.service

sudo install -m 644 pi_app_patch/tty5_service_files/switch-to-tty5.service \
  /etc/systemd/system/switch-to-tty5.service

sudo systemctl daemon-reload
sudo systemctl enable face-recognition-tty5.service
sudo systemctl enable switch-to-tty5.service
sudo reboot
```

After boot, the Pi waits for the Face Recognition X session and switches to TTY5.
The GUI runs fullscreen only in this service session because it receives:

```text
FACE_RECOGNITION_FULLSCREEN=1
```

The normal desktop launch remains non-fullscreen.

## Verify or troubleshoot

```bash
systemctl status face-recognition-tty5.service
systemctl status switch-to-tty5.service
journalctl -u face-recognition-tty5.service -b --no-pager
```

## Restore the previous `.desktop` method

```bash
sudo systemctl disable --now switch-to-tty5.service face-recognition-tty5.service

mv /home/jbl_facerec/.config/autostart/facerecognition.desktop.disabled \
   /home/jbl_facerec/.config/autostart/facerecognition.desktop

sudo reboot
```
