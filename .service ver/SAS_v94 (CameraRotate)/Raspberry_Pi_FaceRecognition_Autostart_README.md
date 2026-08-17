# Raspberry Pi Auto Start Guide for Face Recognition GUI

This guide records the steps to make the Raspberry Pi automatically run the Face Recognition GUI when the Raspberry Pi is powered on.

Project path:

```bash
/home/jbl_facerec/New2.0/gui.py
```

---

## 1. Confirm the GUI can run manually first

Open Terminal on the Raspberry Pi and run:

```bash
cd /home/jbl_facerec/New2.0
python3 gui.py
```

If the GUI opens correctly, continue to the next step.

If it does not open, fix the Python error first before setting autostart.

---

## 2. Set Raspberry Pi to boot into Desktop Autologin

The GUI needs the Raspberry Pi desktop environment to display properly.

Run:

```bash
sudo raspi-config
```

Then select:

```text
System Options
→ Boot / Auto Login
→ Desktop Autologin
```

After setting it, reboot later after completing all steps.

---

## 3. Create the autostart folder

Run:

```bash
mkdir -p ~/.config/autostart
```

---

## 4. Create the autostart desktop file

Run:

```bash
nano ~/.config/autostart/facerecognition.desktop
```

Paste the following content:

```ini
[Desktop Entry]
Type=Application
Name=Face Recognition GUI
Comment=Start Face Recognition GUI on Raspberry Pi boot
Exec=lxterminal -e bash -c "cd /home/jbl_facerec/New2.0 && python3 gui.py; exec bash"
Terminal=false
X-GNOME-Autostart-enabled=true
```

Save the file:

```text
CTRL + O
Enter
CTRL + X
```

---

## 5. Reboot the Raspberry Pi

Run:

```bash
sudo reboot
```

After the Raspberry Pi boots into the desktop, the Face Recognition GUI should start automatically.

---

## 6. If the GUI does not start

Check whether the desktop file exists:

```bash
ls ~/.config/autostart
```

Check the content:

```bash
cat ~/.config/autostart/facerecognition.desktop
```

Try running the command manually:

```bash
cd /home/jbl_facerec/New2.0
python3 gui.py
```

Common causes:

```text
1. Wrong project path
2. Python package missing
3. GUI error inside gui.py
4. Raspberry Pi is booting into command line instead of desktop
5. Permission or display issue
```

---

## 7. If the project uses a virtual environment

If the project uses a Python virtual environment, replace the `Exec` line with this:

```ini
Exec=lxterminal -e bash -c "cd /home/jbl_facerec/New2.0 && source venv/bin/activate && python gui.py; exec bash"
```

Only use this if there is a `venv` folder inside:

```bash
/home/jbl_facerec/New2.0/venv
```

---

## 8. How to disable autostart

Remove the desktop file:

```bash
rm ~/.config/autostart/facerecognition.desktop
```

Then reboot:

```bash
sudo reboot
```

---

## Recommended setup for this project

Use this method:

```text
Desktop Autologin
+
~/.config/autostart/facerecognition.desktop
```

Reason:

```text
gui.py is a GUI application, so it should start after the Raspberry Pi desktop environment is loaded.
```
