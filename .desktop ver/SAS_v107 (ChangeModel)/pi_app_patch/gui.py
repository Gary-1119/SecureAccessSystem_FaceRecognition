from email import header
import html
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from threading import Thread, Event
from PIL import Image, ImageTk
import zipfile
import cv2
import os
import time
import pickle
import shutil
from numpy import inner
from numpy import inner
import requests 
import xml.etree.ElementTree as ET
from cryptography.fernet import Fernet
from face_api import start_api_server
from face_service import FaceService
import threading
from threading import Thread, Event


from capture import capture_faces
from recog import start_recognition
from train import train_model
from camera_rotation import (
    camera_rotation_label,
    normalize_camera_rotation,
    read_camera_rotation,
    update_camera_rotation,
)
from backup_retention import (
    DELETE_BACKUP_RETENTION_DAYS,
    cleanup_delete_backups,
)
from system_control import (
    SystemControlError,
    change_hostname,
    request_reboot,
    validate_hostname,
    verify_system_control_ready,
)

import socket
import tempfile
import paramiko
import json
import getpass
import threading
import subprocess
import platform
from typing import Any, cast

# Optional HTTP API support. If Flask is not installed, the local Tkinter app still runs.
# --------------------------------------------------------
# Optional API imports
# --------------------------------------------------------
try:
    from flask import Flask, jsonify, request, Response
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    Flask = None
    jsonify = None
    request = None
    Response = None
    CORS = None
    FLASK_AVAILABLE = False

ENCODINGS_FILE = "encodings.pickle"
DATASET_DIR = "dataset"
USER_JSON_FILE = "user.json"
LOG_DIR = "LOG"
ADMIN_FILE = "admins.txt"
SOAP_URL = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"
SETTINGS_FILE = "settings.json"
FERNET_KEY = b'-_xj1UT6MLokiC2A-cd-LDp1Hj_3I06kdNCky09tr_U='  # replace with output of Fernet.generate_key()

# Developer-team emergency administrator. This account is intentionally local
# and does not call Active Directory. Keep the password out of logs.
DEVELOPER_ADMIN_NTID = "admin"
DEVELOPER_ADMIN_PASSWORD = "penAteam"


#-----------------------------
# SFTP Helper
#--------------------------------
RECEIVED_DIR = "received_face_data"
PENDING_DIR = os.path.join(RECEIVED_DIR, "pending")
ACCEPTED_DIR = os.path.join(RECEIVED_DIR, "accepted")
REJECTED_DIR = os.path.join(RECEIVED_DIR, "rejected")
TEMP_EXPORT_DIR = "temp_export"
TEMP_IMPORT_DIR = "temp_import"

# -----------------------------
# HTTP API helper
# -----------------------------
API_HOST = "0.0.0.0"
API_PORT = 5000
RECOGNITION_RESULT_FILE = "recognition_result.json"


# ----------------------------
# Color palette
# ----------------------------
# Modern white + blue UI palette
BG         = "#F5F7FB"
CARD       = "#FFFFFF"
CARD_SOFT  = "#F8FAFF"
ACCENT     = "#0B72FF"
ACCENT_HOV = "#005BD1"
DANGER     = "#EF4444"
SUCCESS    = "#16A34A"
WARNING    = "#F97316"
PURPLE     = "#7C3AED"
TEXT_PRI   = "#0F172A"
TEXT_SEC   = "#475569"
TEXT_HINT  = "#94A3B8"
BORDER     = "#DDE5F0"
BORDER_DARK= "#CBD5E1"
CAM_BG     = "#111827"
SHADOW     = "#D7E0EF"
Warning    = WARNING




# ----------------------------
# Rounded UI helpers (Tkinter-safe for Raspberry Pi OS)
# ----------------------------
def _draw_round_rect(canvas, x1, y1, x2, y2, radius=18, **kwargs):
    """Draw a smoother rounded rectangle with one canvas polygon to avoid internal seam lines."""
    r = max(1, min(radius, int((x2 - x1) / 2), int((y2 - y1) / 2)))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return [canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)]


class RoundedCard(tk.Frame):
    """A normal Frame with a rounded card background drawn behind its children."""
    def __init__(self, parent, bg_color=CARD, radius=18, shadow=True, border=BORDER):
        super().__init__(parent, bg=BG, bd=0, highlightthickness=0)
        self._bg_color = bg_color
        self._radius = radius
        self._shadow = shadow
        self._border = border
        self._canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event=None):
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        self._canvas.delete("all")
        if self._shadow:
            _draw_round_rect(self._canvas, 5, 7, w - 3, h - 2, self._radius,
                             fill=SHADOW, outline=SHADOW)
        _draw_round_rect(self._canvas, 1, 1, w - 7, h - 8 if self._shadow else h - 2,
                         self._radius, fill=self._bg_color, outline=self._border)
        self._canvas.lower("all")


class CircleBadge(tk.Canvas):
    """Small clean circular icon/avatar without square borders."""
    def __init__(self, parent, text="", size=34, bg_color="#EFF6FF", fg=ACCENT, font=None):
        self.text = text
        self.size = size
        self.bg_color = bg_color
        self.fg = fg
        self.font = font or ("DejaVu Sans", 13, "bold")
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=CARD,
            highlightthickness=0,
            bd=0,
            relief="flat"
        )
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _draw(self):
        self.delete("all")
        s = min(self.winfo_width(), self.winfo_height())
        self.create_oval(
            1, 1, s - 1, s - 1,
            fill=self.bg_color,
            outline=self.bg_color,
            width=0
        )
        self.create_text(
            s / 2,
            s / 2,
            text=self.text,
            fill=self.fg,
            font=self.font,
            anchor="center"
        )


class RoundButton(tk.Canvas):
    """Rounded button that supports the subset of Button.config used by this app."""
    def __init__(self, parent, text, color, command=None, state="normal", fg="white",
                 border=False, padx=12, pady=8, font=None, radius=16, height=None,
                 width=None, activebackground=None, activeforeground=None):
        self.text = text
        self.color = color
        self.fg = fg
        self.command = command
        self.state = state
        self.border = border
        self.padx = padx
        self.pady = pady
        self.font = font or ("DejaVu Sans", 10, "bold")
        self.radius = radius
        self.activebackground = activebackground or (ACCENT_HOV if color == ACCENT else color)
        self.activeforeground = activeforeground or fg
        self.normalbackground = color
        self.normalforeground = fg
        self._hover = False
        h = height or max(40, 24 + pady * 2)
        longest = max(len(line) for line in str(text).split("\n")) if text else 6
        default_w = max(64, longest * 9 + padx * 2 + 18)
        cursor = "hand2" if command else "arrow"
        super().__init__(parent, bg=parent.cget("bg") if hasattr(parent, "cget") else BG,
                         highlightthickness=0, bd=0, height=h, width=width or default_w, cursor=cursor)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def __getitem__(self, key):
        if key == "state":
            return self.state
        if key == "text":
            return self.text
        if key == "bg":
            return self.color
        return super().__getitem__(key)

    def config(self, cnf=None, **kwargs):
        return self.configure(cnf, **kwargs)

    def configure(self, cnf=None, **kwargs):
        self._hover = False
        if cnf:
            kwargs.update(cnf)
        for key, val in kwargs.items():
            if key == "text":
                self.text = val
            elif key in ("bg", "background"):
                self.color = val
                self.normalbackground = val
            elif key in ("fg", "foreground"):
                self.fg = val
                self.normalforeground = val
            elif key == "activebackground":
                self.activebackground = val
            elif key == "activeforeground":
                self.activeforeground = val
            elif key == "command":
                self.command = val
            elif key == "state":
                self.state = val
            elif key == "font":
                self.font = val
            elif key == "cursor":
                super().configure(cursor=val)
            else:
                try:
                    super().configure(**{key: val})
                except Exception:
                    pass
        self._draw()

    def _on_enter(self, event=None):
        self._hover = True
        self._draw()

    def _on_leave(self, event=None):
        self._hover = False
        self._draw()

    def _on_click(self, event=None):
        if self.state != "disabled" and self.command:
            self.command()

    def _draw(self):
        self.delete("all")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        disabled = self.state == "disabled"
        bg = "#EEF2F7" if disabled else (self.activebackground if self._hover else self.color)
        fg = TEXT_HINT if disabled else (self.activeforeground if self._hover else self.fg)
        outline = BORDER if self.border or bg in (CARD, CARD_SOFT, "#FFFFFF") else bg
        _draw_round_rect(self, 2, 2, w - 3, h - 3, self.radius, fill=bg, outline=outline)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font, justify="center", anchor="center")


class FaceRecognitionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Recognition System")
        self.root.configure(bg=BG)

        # Use a normal arrow cursor for all popup cards and layout widgets in TTY5.
        self.root.option_add("*Cursor", "arrow")

        # The normal Pi desktop launch keeps the existing centred application
        # window.  The dedicated X session on TTY5 has no desktop window
        # manager, so a normal Tkinter geometry window can appear tiny on a
        # high-resolution screen. Fullscreen is requested by the service and
        # also detected from the TTY5 / second-X-session context as a fallback.
        self._service_fullscreen = self._is_tty5_fullscreen_session()
        if self._service_fullscreen:
            self.root.resizable(False, False)
            # Avoid an accidental mouse cursor staying over the kiosk screen.
            self.root.configure(cursor="arrow")
        else:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            ww = max(1000, int(sw * 0.85))
            hh = max(650, int(sh * 0.85))
            xx = max(0, (sw - ww) // 2)
            yy = max(0, (sh - hh) // 2)
            self.root.geometry(f"{ww}x{hh}+{xx}+{yy}")
            self.root.minsize(900, 620)
            self.root.resizable(True, True)
            self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))

        self.stop_flag = False
        self.imgtk = None
        self._recognition_running = False
        self._capture_running = False
        self._capture_event = Event()   # legacy manual-capture event; direct registration no longer uses it
        self._stop_capture_event = Event()  # set when Stop is clicked during capture
        # True while a training flow should return the Pi to recognition mode.
        # A local Pi Stop during training clears this, so it remains a real stop.
        self._resume_recognition_after_training = False
        # Capture uses the same camera as recognition.  Every normal capture
        # workflow returns to background recognition after it finishes, including
        # a capture ended with the Capture STOP button.
        self._resume_recognition_after_capture = False
        # API training handshake state for SAS.  These values make it possible
        # for SAS to follow the exact training request rather than guessing from
        # a transient camera status.
        self._api_training_state = "idle"
        self._api_last_training_id = ""
        self._api_last_training_finished_at = 0.0
        self._api_last_training_error = None
        self._api_last_training_new_faces = 0
        # Real train progress exposed through the Pi API.  These are updated
        # from train.py as each untrained dataset image is processed.
        self._api_training_processed = 0
        self._api_training_total = 0
        self._api_training_percent = 0
        self._api_training_phase = "idle"
        self._api_training_message = ""
        # Training summary counters supplied by train.py.  These explain why
        # "captured" image count and "valid trained" image count can differ.
        self._api_training_dataset_total = 0
        self._api_training_already_trained = 0
        self._api_training_valid_images = 0
        self._api_training_skipped_images = 0

        self._build_fonts()
        self._build_ui()

        # Schedule TTY5 fullscreen immediately after the UI is built. Do not
        # wait for SMB/LAN/API startup, because those operations can be slow or
        # unavailable when the Pi boots offline.
        if self._service_fullscreen:
            self._schedule_tty5_fullscreen()

        self.pc_save_path = None
        self.auto_capture_enabled = False
        self.camera_rotation = read_camera_rotation()
        self._settings_rotation_refresh = None
        self._ensure_first_start_files()
        self._load_pc_path()
        self.refresh_dataset()
        self.current_user = None
        self.admin_list = []
        self._load_admin()
        self._set_default_permissions()
        # Mount SMB in the background so an offline LAN never delays the TTY5 UI.
        self._mount_server()




        #---------------------------------------------------
        # For SFTP
        #---------------------------------------------------
        self._ensure_transfer_folders()
        # User/encoding safety backups created before deletion are retained for
        # 30 days. Import ZIP backups in received_face_data/pending are not part
        # of this cleanup and remain unchanged.
        self._schedule_delete_backup_retention_cleanup(initial=True)
        self._received_watcher_started = False
        self._seen_received_files = set()
        self._received_badge_label = None
        self._received_badge_wrap = None
        self._last_pending_received_count = 0
        self._boot_recognition_start_scheduled = False
        self._boot_recognition_start_cancelled = False
        self._start_received_watcher()

        #---------------------------------------------------
        # Shared Face Service + HTTP API server
        #---------------------------------------------------
        self.face_service = FaceService(gui=self)
        start_api_server(self.face_service)

        # Recognition may start automatically once after the Pi GUI has fully
        # loaded. It must never be scheduled by the repeating received-data
        # watcher, otherwise a manual Stop would be undone later.
        self._schedule_boot_recognition_start()

    # --------------------------------------------------------
    # Dedicated TTY5 fullscreen helpers
    # --------------------------------------------------------
    def _is_tty5_fullscreen_session(self):
        """Return True only for the dedicated fullscreen X session."""
        if os.environ.get("FACE_RECOGNITION_FULLSCREEN") == "1":
            return True

        # The systemd service may expose the allocated virtual terminal.
        if os.environ.get("XDG_VTNR") == "5":
            return True

        # xinit normally preserves the service stdin on /dev/tty5.
        for fd in (0, 1, 2):
            try:
                if os.ttyname(fd) == "/dev/tty5":
                    return True
            except (OSError, AttributeError):
                pass

        # The normal Raspberry Pi Desktop uses :0. The dedicated second X
        # server used by this project is :1, so this recovers if an older
        # service unit did not yet export FACE_RECOGNITION_FULLSCREEN.
        return os.environ.get("DISPLAY", "").strip() == ":1"

    def _schedule_tty5_fullscreen(self):
        """Retry fullscreen while TTY5/Xorg and the first Tk window settle."""
        if not self._service_fullscreen:
            return

        # ``after_idle`` can be postponed by busy startup work such as camera,
        # API, or SMB initialization. These timed retries are independent of
        # LAN availability and guarantee a final fullscreen request.
        for delay_ms in (0, 150, 400, 900, 1800, 3500, 6000):
            self.root.after(delay_ms, self._apply_tty5_fullscreen)

    def _apply_tty5_fullscreen(self):
        """Force a borderless full-display Tkinter window without a WM."""
        try:
            self.root.update_idletasks()
            screen_w = max(1, self.root.winfo_screenwidth())
            screen_h = max(1, self.root.winfo_screenheight())

            # -fullscreen is honored by desktop window managers. The explicit
            # geometry is also required when xinit starts a bare TTY5 X server.
            self.root.attributes("-fullscreen", True)
            self.root.overrideredirect(True)
            self.root.geometry(f"{screen_w}x{screen_h}+0+0")
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            print(f"[TTY5 FULLSCREEN] Applied {screen_w}x{screen_h}")

            # Some X servers report their final resolution only after mapping
            # the first top-level window. Apply the geometry once more after
            # that point to prevent a small top-left application window.
            self.root.after(250, self._enforce_tty5_fullscreen)
        except tk.TclError as exc:
            print(f"[TTY5 FULLSCREEN] Could not apply fullscreen: {exc}")

    def _enforce_tty5_fullscreen(self):
        """Reapply the final TTY5 dimensions after the X window is mapped."""
        if not self._service_fullscreen:
            return
        try:
            screen_w = max(1, self.root.winfo_screenwidth())
            screen_h = max(1, self.root.winfo_screenheight())
            self.root.geometry(f"{screen_w}x{screen_h}+0+0")
            self.root.attributes("-fullscreen", True)
            self.root.lift()
            print(f"[TTY5 FULLSCREEN] Enforced {screen_w}x{screen_h}")
        except tk.TclError as exc:
            print(f"[TTY5 FULLSCREEN] Could not enforce fullscreen: {exc}")

    # --------------------------------------------------------
    # User-delete backup retention
    # --------------------------------------------------------
    def _schedule_delete_backup_retention_cleanup(self, initial=False):
        """Remove only expired pre-delete backups without touching import ZIPs."""

        def run_cleanup():
            try:
                removed = cleanup_delete_backups()
                if removed:
                    self.root.after(
                        0,
                        lambda: self.log(
                            f"Deleted {len(removed)} expired pre-delete backup(s) "
                            f"older than {DELETE_BACKUP_RETENTION_DAYS} days.",
                            "info",
                        ),
                    )
            except Exception as exc:
                # Cleanup is maintenance only; it must never affect camera,
                # recognition, SFTP import, or the TTY5 kiosk UI.
                print(f"[BACKUP RETENTION] Cleanup failed: {exc}")

        Thread(target=run_cleanup, daemon=True, name="DeleteBackupRetention").start()
        try:
            self.root.after(24 * 60 * 60 * 1000, self._schedule_delete_backup_retention_cleanup)
        except Exception:
            pass

    def _cleanup_expired_delete_backups_now(self):
        """Run a post-delete retention check and return how many items were removed."""
        try:
            removed = cleanup_delete_backups()
            if removed:
                self.log(
                    f"Deleted {len(removed)} expired pre-delete backup(s) "
                    f"older than {DELETE_BACKUP_RETENTION_DAYS} days.",
                    "info",
                )
            return len(removed)
        except Exception as exc:
            print(f"[BACKUP RETENTION] Post-delete cleanup failed: {exc}")
            return 0

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------
    def _coerce_bool(self, value, default=False):
        """Safely parse boolean values from settings.json/API."""
        if isinstance(value, bool):
            return value
        if value is None:
            return bool(default)
        if isinstance(value, (int, float)):
            return value != 0

        text = str(value).strip().lower()
        if text in ("true", "1", "yes", "y", "enabled", "enable", "on"):
            return True
        if text in ("false", "0", "no", "n", "disabled", "disable", "off"):
            return False
        return bool(default)


    def _build_fonts(self):
        # Use fonts commonly available on Raspberry Pi OS.
        self.font_title  = ("DejaVu Sans", 20, "bold")
        self.font_sub    = ("DejaVu Sans", 10)
        self.font_label  = ("DejaVu Sans", 11, "bold")
        self.font_body   = ("DejaVu Sans", 10)
        self.font_mono   = ("DejaVu Sans Mono", 9)
        self.font_btn    = ("DejaVu Sans", 10, "bold")
        self.font_badge  = ("DejaVu Sans", 9, "bold")
        self.font_small  = ("DejaVu Sans", 8)
        self.font_icon   = ("DejaVu Sans", 16, "bold")

    # --------------------------------------------------------
    # UI build
    # --------------------------------------------------------
    def _build_ui(self):
        # Main shell - fixed 1366x768-friendly layout for Raspberry Pi OS.
        self.root.configure(bg=BG)

        # ---- Clean header, no macOS traffic circles ----
        header_outer = tk.Frame(self.root, bg=BG)
        header_outer.pack(fill="x", side="top", padx=16, pady=(12, 0))

        header = RoundedCard(header_outer, bg_color=CARD, radius=18, shadow=True, border=BORDER)
        header.pack(fill="x")
        header.configure(height=76)
        header.pack_propagate(False)

        logo_wrap = CircleBadge(header, text="◎", size=44, bg_color="#EFF6FF", fg=ACCENT,
                               font=("DejaVu Sans", 20, "bold"))
        logo_wrap.pack(side="left", padx=(22, 14), pady=13)

        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", pady=13)
        tk.Label(title_box, text="Face Recognition System", font=("DejaVu Sans", 20, "bold"),
                 bg=CARD, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(title_box, text="Smart AI identification and model training", font=self.font_sub,
                 bg=CARD, fg=TEXT_HINT).pack(anchor="w", pady=(2, 0))

        self.settings_btn = self._btn(header, "⚙  Settings", CARD_SOFT, self._open_settings,
                                      fg=TEXT_PRI, border=True, padx=12, pady=7)
        self.settings_btn.pack(side="right", padx=(8, 20), pady=18)

        # Google-style account button: compact pill. Before login it starts login; after login it opens account menu.
        self.account_btn = self._btn(header, "  Login", CARD_SOFT, self._login,
                                     fg=TEXT_PRI, border=True, padx=12, pady=7)
        self.account_btn.pack(side="right", padx=(8, 0), pady=18)

        # Keep these names for compatibility with existing logic, but do not display a separate logout button.
        self.login_btn = self.account_btn
        self.logout_btn = self.account_btn

        self.user_label = tk.Label(header, text="", bg=CARD, fg=CARD)

        # ---- Body layout with scrolling for smaller Raspberry Pi displays ----
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, side="top")

        self._scroll_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        v_scroll = ttk.Scrollbar(outer, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand="")
        #v_scroll.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._scroll_canvas, bg=BG)
        self._inner_id = self._scroll_canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)

        shell = tk.Frame(self._inner, bg=BG)
        shell.pack(fill="both", expand=True, padx=16, pady=14)
        shell.columnconfigure(0, weight=5, uniform="main")
        shell.columnconfigure(1, weight=2, uniform="main")
        shell.rowconfigure(0, weight=1)

        left = tk.Frame(shell, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = tk.Frame(shell, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_camera_panel(left)
        self._build_controls(left)
        self._build_log_panel(left)
        self._build_right_panel(right)

    def _on_inner_configure(self, event):
        if hasattr(self, "_scroll_canvas"):
            self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        if hasattr(self, "_scroll_canvas") and hasattr(self, "_inner_id"):
            self._scroll_canvas.itemconfig(self._inner_id, width=event.width)

    def _on_mousewheel(self, event):
        # Do not scroll main window when a popup has grab/focus
        try:
            grabbed = self.root.grab_current()
            if grabbed is not None and grabbed != self.root:
                return "break"
        except:
            pass

        if hasattr(self, "_scroll_canvas"):
            try:
                if event.num == 4:
                    self._scroll_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self._scroll_canvas.yview_scroll(1, "units")
                else:
                    self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return "break"
            except:
                return "break"



    def sync_face_runtime_ui(self, state, message=None):
        """
        Sync Pi GUI when camera state is changed by API or local GUI.

        state:
        - "recognition"
        - "capture"
        - "stopping"
        - "stopped"
        """

        def apply():
            try:
                if state == "recognition":
                    self._recognition_running = True
                    self._capture_running = False
                    self.stop_flag = False

                    self._set_camera_status(True)

                    self.recog_btn.config(state="disabled")
                    self.stop_btn.config(
                        state="normal",
                        bg=WARNING,
                        fg="white",
                        activebackground=WARNING,
                        activeforeground="white"
                    )

                    # Admin buttons stay usable.
                    # Capture can stop recognition first, same as local Pi logic.
                    if self.current_user:
                        self.capture_btn.config(state="normal")
                        self.train_btn.config(state="normal")
                        self.delete_btn.config(state="normal")

                    self.log(message or "Recognition started from API.", "success")

                elif state == "capture":
                    self._recognition_running = False
                    self._capture_running = True
                    self.stop_flag = False

                    self._set_camera_status(True)

                    self.recog_btn.config(state="disabled")
                    self.capture_btn.config(state="disabled")
                    self.train_btn.config(state="disabled")
                    self.delete_btn.config(state="disabled")
                    self.stop_btn.config(
                        state="normal",
                        bg=WARNING,
                        fg="white",
                        activebackground=WARNING,
                        activeforeground="white"
                    )

                    self.log(message or "Capture started from API.", "success")

                elif state == "training":
                    self._recognition_running = False
                    self._capture_running = False
                    self._set_camera_status(False)
                    self.recog_btn.config(state="disabled")
                    self.capture_btn.config(state="disabled")
                    self.train_btn.config(state="disabled")
                    self.delete_btn.config(state="disabled")
                    self.stop_btn.config(state="disabled")
                    self.log(message or "Training face data...", "info")

                elif state == "stopping":
                    self.stop_btn.config(
                        state="normal",
                        bg=WARNING,
                        fg="white",
                        activebackground=WARNING,
                        activeforeground="white"
                    )

                    self.log(message or "Stopping camera...", "warn")

                elif state == "stopped":
                    self._recognition_running = False
                    self._capture_running = False
                    self.stop_flag = True

                    self._set_camera_status(False)
                    self._show_camera_stopped_prompt(message or "Camera stopped.")

                    if self.current_user:
                        self._enable_admin_permissions()
                    else:
                        self._set_default_permissions()

                    self.stop_btn.config(state="disabled")
                    self.recog_btn.config(state="normal")

                    self.log(message or "Camera stopped.", "warn")

            except Exception as e:
                try:
                    self.log(f"UI sync error: {e}", "error")
                except:
                    print("[UI SYNC ERROR]", e)

        # Always update Tkinter widgets on main thread
        try:
            self.root.after(0, apply)
        except:
            apply()


    def _show_camera_stopped_prompt(self, text="Camera stopped."):
        try:
            self.canvas.delete("all")

            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()

            if w <= 1:
                w = 560

            if h <= 1:
                h = 420

            self.placeholder_title = self.canvas.create_text(
                w // 2,
                h // 2,
                text=text,
                fill="#CBD5E1",
                font=("DejaVu Sans", 13),
                tags="placeholder"
            )

            self.imgtk = None

        except Exception as e:
            print("[CAMERA PROMPT ERROR]", e)



    # --------------------------------------------------------
    # Camera panel
    # --------------------------------------------------------
    def _build_camera_panel(self, parent):

        card = self._card(parent)
        card.pack(fill="x", expand=False, pady=(0, 12))

        header = tk.Frame(card, bg=CARD)
        header.pack(fill="x", padx=20, pady=(16, 10))

        CircleBadge(
            header,
            text="▣",
            size=30,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 12, "bold")
        ).pack(side="left", padx=(0, 10))

        tk.Label(
            header,
            text="Camera Preview",
            font=("DejaVu Sans", 14, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(side="left")

        self.live_badge = RoundButton(
            header,
            "●  End",
            "#F1F5F9",
            command=None,
            fg=TEXT_SEC,
            border=False,
            padx=8,
            pady=2,
            font=self.font_badge,
            radius=14,
            height=28,
            width=68
        )
        self.live_badge.pack(side="right")

        # Fixed camera preview size
        CAM_VIEW_W = 560
        CAM_VIEW_H = 420

        cam_outer = tk.Frame(
            card,
            bg=BORDER,
            width=CAM_VIEW_W + 2,
            height=CAM_VIEW_H + 2,
            highlightthickness=0
        )

        # Important: do not use fill="both" / expand=True here
        cam_outer.pack(padx=20, pady=(0, 16), anchor="center")
        cam_outer.pack_propagate(False)

        self.canvas = tk.Canvas(
            cam_outer,
            bg=CAM_BG,
            highlightthickness=0,
            width=CAM_VIEW_W,
            height=CAM_VIEW_H
        )

        # Canvas fills only the fixed cam_outer, not the whole window
        self.canvas.pack(padx=1, pady=1)

        self.placeholder_title = self.canvas.create_text(
            CAM_VIEW_W // 2,
            CAM_VIEW_H // 2,
            text="Camera feed will appear here",
            fill="#CBD5E1",
            font=("DejaVu Sans", 13),
            tags="placeholder"
        )

        self.canvas.bind("<Configure>", self._on_canvas_resize)

    def _set_camera_status(self, is_live: bool):
        if not hasattr(self, "live_badge"):
            return

        if is_live:
            self.live_badge.config(
                text="●  Live",
                bg="#ECFDF5",
                fg=SUCCESS,
                activebackground="#ECFDF5",
                activeforeground=SUCCESS
            )
        else:
            self.live_badge.config(
                text="●  End",
                bg="#F1F5F9",
                fg=TEXT_SEC,
                activebackground="#F1F5F9",
                activeforeground=TEXT_SEC
            )

    def _build_controls(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))

        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=14)

        top_row = tk.Frame(inner, bg=CARD)
        top_row.pack(fill="x", pady=(0, 10))

        tk.Label(top_row, text="Register User", font=self.font_label, bg=CARD, fg=TEXT_PRI).pack(side="left")
        tk.Label(top_row, text="Capture uses name and NTID", font=self.font_small, bg=CARD, fg=TEXT_HINT).pack(side="left", padx=(8, 0))

        tk.Label(inner, text="Name", font=self.font_badge, bg=CARD, fg=TEXT_SEC).pack(anchor="w", padx=2, pady=(0, 4))
        name_wrap = RoundedCard(
            inner,
            bg_color=CARD_SOFT,
            radius=16,
            shadow=False,
            border="#D9E2EC"
        )
        name_wrap.pack(fill="x", pady=(0, 10))

        self.display_name_entry = tk.Entry(
            name_wrap,
            font=("DejaVu Sans", 11),
            bg=CARD_SOFT,
            fg=TEXT_PRI,
            relief="flat",
            bd=0,
            highlightthickness=0,
            insertbackground=ACCENT
        )
        self.display_name_entry.pack(fill="x", padx=14, pady=10)

        tk.Label(inner, text="NTID", font=self.font_badge, bg=CARD, fg=TEXT_SEC).pack(anchor="w", padx=2, pady=(0, 4))

        entry_wrap = RoundedCard(
            inner,
            bg_color=CARD_SOFT,
            radius=16,
            shadow=False,
            border="#D9E2EC"
        )
        entry_wrap.pack(fill="x", pady=(0, 12))

        self.name_entry = tk.Entry(
            entry_wrap,
            font=("DejaVu Sans", 11),
            bg=CARD_SOFT,
            fg=TEXT_PRI,
            relief="flat",
            bd=0,
            highlightthickness=0,
            insertbackground=ACCENT
        )
        self.name_entry.pack(fill="x", padx=14, pady=10)

        btn_grid = tk.Frame(inner, bg=CARD)
        btn_grid.pack(fill="x")
        for i in range(4):
            btn_grid.columnconfigure(i, weight=1, uniform="actions")

        self.capture_btn = self._action_btn(btn_grid, "▣", "Capture", ACCENT, self.start_capture)
        self.capture_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.train_btn = self._action_btn(btn_grid, "⚙", "Train", SUCCESS, self.start_train)
        # InsightFace registers during capture, so Train is kept only as a
        # hidden compatibility object for older state-management code.

        self.recog_btn = self._action_btn(btn_grid, "◎", "Recognise", PURPLE, self.start_recognition_thread)
        self.recog_btn.grid(row=0, column=1, padx=6, sticky="ew")

        self.stop_btn = self._action_btn(btn_grid, "□", "Stop", WARNING, self.stop_all, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=6, sticky="ew")

        self.delete_btn = self._action_btn(btn_grid, "⌫", "Delete", DANGER, self.delete_user)
        self.delete_btn.grid(row=0, column=3, padx=(6, 0), sticky="ew")

        path_row = tk.Frame(inner, bg=CARD)
        path_row.pack(fill="x", pady=(12, 0))

        tk.Label(
            path_row,
            text="Server Path",
            font=self.font_badge,
            bg=CARD,
            fg=TEXT_SEC
        ).pack(side="left", padx=(2, 8))

        self.pc_path_entry = tk.Entry(
            path_row,
            font=self.font_small,
            bg=CARD,
            fg=TEXT_SEC,
            relief="flat",
            bd=0,
            highlightthickness=0,
            state="readonly",
            readonlybackground=CARD
        )
        self.pc_path_entry.pack(side="left", fill="x", expand=True)

    def _build_log_panel(self, parent):
        log_card = self._card(parent)
        log_card.pack(fill="both", expand=False)

        header = tk.Frame(log_card, bg=CARD)
        header.pack(fill="x", padx=20, pady=(12, 6))
        tk.Label(header, text="☷", font=("DejaVu Sans", 14, "bold"), bg=CARD, fg=ACCENT).pack(side="left", padx=(0, 10))
        tk.Label(header, text="System Log", font=("DejaVu Sans", 13, "bold"), bg=CARD, fg=TEXT_PRI).pack(side="left")

        log_inner = RoundedCard(log_card, bg_color=CARD_SOFT, radius=16, shadow=False, border=BORDER)
        log_inner.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        self.log_text = tk.Text(
            log_inner, font=self.font_mono,
            bg=CARD_SOFT, fg=TEXT_PRI,
            relief="flat", state="disabled",
            wrap="word", height=7,
            bd=0, highlightthickness=0,
            padx=10, pady=8
        )
        scroll = ttk.Scrollbar(log_inner, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

        self.log_text.tag_config("info",    foreground=ACCENT)
        self.log_text.tag_config("success", foreground=SUCCESS)
        self.log_text.tag_config("error",   foreground=DANGER)
        self.log_text.tag_config("warn",    foreground=WARNING)

    def _build_right_panel(self, parent):
        ds_card = self._card(parent)
        ds_card.pack(fill="both", expand=True)

        header = tk.Frame(ds_card, bg=CARD)
        header.pack(fill="x", padx=18, pady=(16, 10))
        CircleBadge(
            header,
            text="",
            size=30,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 12, "bold")
        ).pack(side="left", padx=(0, 10))
        tk.Label(header, text="Registered Users", font=("DejaVu Sans", 14, "bold"), bg=CARD, fg=TEXT_PRI).pack(side="left")
        self.user_count_badge = tk.Label(header, text="0", font=self.font_badge, bg=CARD, fg=ACCENT, padx=8, pady=2)
        self.user_count_badge.pack(side="right")

        search_wrap = RoundedCard(ds_card, bg_color=CARD_SOFT, radius=16, shadow=False, border=BORDER)
        search_wrap.pack(fill="x", padx=18, pady=(0, 12))
        self.user_search_entry = tk.Entry(search_wrap, font=self.font_body, bg=CARD_SOFT, fg=TEXT_SEC,
                                          relief="flat", insertbackground=ACCENT)
        self.user_search_entry.pack(fill="x", padx=14, pady=9)
        self.user_search_entry.insert(0, "")
        self.user_search_entry.bind("<KeyRelease>", lambda _event=None: self.refresh_dataset())

        self.dataset_canvas = tk.Canvas(ds_card, bg=CARD, highlightthickness=0)
        self.dataset_canvas.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.dataset_scroll = ttk.Scrollbar(ds_card, orient="vertical", command=self.dataset_canvas.yview)
        self.dataset_canvas.configure(yscrollcommand=self.dataset_scroll.set)
        self.dataset_scroll.pack_forget()

        # Keep dataset_frame name because refresh_dataset() writes into it.
        self.dataset_frame = tk.Frame(self.dataset_canvas, bg=CARD)
        self.dataset_canvas_window = self.dataset_canvas.create_window((0, 0), window=self.dataset_frame, anchor="nw")

        def _cfg_dataset(event=None):
            self.dataset_canvas.configure(scrollregion=self.dataset_canvas.bbox("all"))
            try:
                self.dataset_canvas.itemconfigure(self.dataset_canvas_window, width=self.dataset_canvas.winfo_width())
            except Exception:
                pass
        self.dataset_frame.bind("<Configure>", _cfg_dataset)
        self.dataset_canvas.bind("<Configure>", _cfg_dataset)

        view_btn = self._btn(ds_card, "View All Users", CARD_SOFT, lambda: None,
                             fg=ACCENT, border=True, padx=14, pady=10)
        view_btn.pack(fill="x", padx=18, pady=(0, 16))

    def _ensure_first_start_files(self):
        """Create the local files/folders needed by a freshly imaged Desktop Pi.

        The local developer account (admin / penAteam) is intentionally not
        written into admins.txt.  The first real AD-authenticated login is the
        bootstrap admin and will be stored in admins.txt by _login().
        """
        for folder in (
            LOG_DIR,
            RECEIVED_DIR,
            PENDING_DIR,
            ACCEPTED_DIR,
            REJECTED_DIR,
            TEMP_EXPORT_DIR,
            TEMP_IMPORT_DIR,
        ):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as exc:
                print(f"[WARN] Could not create {folder}: {exc}")

        try:
            if os.path.isdir(DATASET_DIR) and not os.listdir(DATASET_DIR):
                os.rmdir(DATASET_DIR)
        except Exception as exc:
            print(f"[WARN] Could not remove empty legacy {DATASET_DIR} folder: {exc}")

        default_json_files = {
            USER_JSON_FILE: {},
            SETTINGS_FILE: {
                "username": "",
                "password": "",
                "pc_save_path": "",
                "auto_capture": False,
                "camera_rotation": 0,
                "unlock_transport": "websocket",
            },
        }
        for file_name, default_value in default_json_files.items():
            if not os.path.exists(file_name):
                try:
                    with open(file_name, "w", encoding="utf-8") as f:
                        json.dump(default_value, f, indent=4)
                except Exception as exc:
                    print(f"[WARN] Could not create {file_name}: {exc}")

        try:
            if not os.path.exists(ADMIN_FILE):
                open(ADMIN_FILE, "a", encoding="utf-8").close()
        except Exception as exc:
            print(f"[WARN] Could not create {ADMIN_FILE}: {exc}")

        # Remove the hard-coded emergency account if somebody copied it into the
        # admin file. It must remain code-only and not count as the first admin.
        self._remove_developer_admin_from_admin_file()

    def _remove_developer_admin_from_admin_file(self):
        try:
            if not os.path.exists(ADMIN_FILE):
                return
            with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.read().splitlines()]
            cleaned = []
            seen = set()
            changed = False
            for line in lines:
                if not line:
                    continue
                key = line.lower()
                if key == DEVELOPER_ADMIN_NTID.lower():
                    changed = True
                    continue
                if key in seen:
                    changed = True
                    continue
                seen.add(key)
                cleaned.append(line)
            if changed:
                with open(ADMIN_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(cleaned))
                    if cleaned:
                        f.write("\n")
        except Exception as exc:
            print(f"[WARN] Could not clean {ADMIN_FILE}: {exc}")

    def refresh_dataset(self):
        for widget in self.dataset_frame.winfo_children():
            widget.destroy()

        trained_users = set()
        if os.path.exists(ENCODINGS_FILE):
            try:
                with open(ENCODINGS_FILE, "rb") as f:
                    data = pickle.load(f)
                trained_users = set(data.get("names", []))
            except:
                pass

        if not os.path.exists(DATASET_DIR):
            tk.Label(self.dataset_frame, text="No dataset folder found.",
                     font=self.font_body, bg=CARD, fg=TEXT_SEC).pack(anchor="w", pady=10)
            if hasattr(self, "user_count_badge"):
                self.user_count_badge.config(text="0")
            return

        users = [d for d in os.listdir(DATASET_DIR)
                 if os.path.isdir(os.path.join(DATASET_DIR, d))]

        if hasattr(self, "user_count_badge"):
            self.user_count_badge.config(text=str(len(users)))

        if not users:
            tk.Label(self.dataset_frame, text="No users in dataset yet.",
                     font=self.font_body, bg=CARD, fg=TEXT_SEC).pack(anchor="w", pady=10)
            return

        for user in sorted(users):
            user_path = os.path.join(DATASET_DIR, user)
            images = [f for f in os.listdir(user_path)
                      if f.lower().endswith((".jpg", ".png", ".jpeg"))]
            count = len(images)
            is_trained = user in trained_users

            row = RoundedCard(self.dataset_frame, bg_color=CARD_SOFT, radius=16, shadow=False, border="#EAF0F8")
            row.pack(fill="x", pady=(0, 8))
            row.bind("<Button-1>", lambda e, n=user: self._select_user(n))


            info = tk.Frame(row, bg=CARD_SOFT)
            info.pack(side="left", fill="x", expand=True, pady=10,padx=(12,10))
            info.bind("<Button-1>", lambda e, n=user: self._select_user(n))

            name_lbl = tk.Label(info, text=user.upper(), font=("DejaVu Sans", 10, "bold"),
                                bg=CARD_SOFT, fg=TEXT_PRI)
            name_lbl.pack(anchor="w")
            name_lbl.bind("<Button-1>", lambda e, n=user: self._select_user(n))

            sub_lbl = tk.Label(info, text=f"{count} photos", font=self.font_small,
                               bg=CARD_SOFT, fg=TEXT_SEC)
            sub_lbl.pack(anchor="w", pady=(2, 0))
            sub_lbl.bind("<Button-1>", lambda e, n=user: self._select_user(n))

            badge_text = "Trained" if is_trained else "Not trained"
            badge_bg = "#DCFCE7" if is_trained else "#FEE2E2"
            badge_fg = "#15803D" if is_trained else "#B91C1C"
            RoundButton(row, badge_text, badge_bg, command=None, fg=badge_fg, border=False,
                        padx=8, pady=2, font=self.font_badge, radius=12, height=26, width=86).pack(side="right", padx=(8, 12), pady=12)

    def _select_user(self, name):
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, name)

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------
    def log(self, message, level="info"):
        import threading
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda m=message, lv=level: self.log(m, lv))
            return
        self.log_text.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"{ts}  {message}\n", level)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    # --------------------------------------------------------
    # AD SOAP validation
    # --------------------------------------------------------
    def _validate_ntid_in_ad(self, ntid: str) -> bool:
        """Check whether an NTID exists in AD.

        This is still used by Admin Management when adding an NTID. The login
        flow below additionally validates the password before granting access.
        """
        safe_ntid = html.escape((ntid or "").strip())
        if not safe_ntid:
            return False

        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <IsUserExistsInAD xmlns="http://jpetewebapp/jtesw_ws/">
              <userName>{safe_ntid}</userName>
            </IsUserExistsInAD>
          </soap12:Body>
        </soap12:Envelope>"""

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": "http://jpetewebapp/jtesw_ws/IsUserExistsInAD",
        }

        try:
            response = requests.post(
                SOAP_URL,
                data=soap.encode("utf-8"),
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            return self._parse_ad_response(response.text)
        except requests.exceptions.Timeout:
            self.log("AD request timeout.", "error")
            return False
        except requests.exceptions.RequestException as error:
            self.log(f"AD request failed: {error}", "error")
            return False
        except Exception as error:
            self.log(f"Unexpected AD error: {error}", "error")
            return False

    def _parse_ad_response(self, response: str) -> bool:
        if not response or not response.strip():
            return False
        try:
            root = ET.fromstring(response)
            for elem in root.iter():
                if "ReturnedValue" in elem.tag:
                    return (elem.text or "").strip().lower() == "true"
            return False
        except ET.ParseError:
            self.log("Failed to parse AD response.", "error")
            return False
        except Exception as error:
            self.log(f"AD parsing error: {error}", "error")
            return False

    def _encrypt_password_for_ad(self, password: str) -> str | None:
        """Use the same DESEncrypt SOAP operation as the SAS application."""
        safe_password = html.escape(password or "")
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <DESEncrypt xmlns="http://jpetewebapp/jtesw_ws/">
              <sender>{safe_password}</sender>
            </DESEncrypt>
          </soap12:Body>
        </soap12:Envelope>"""

        try:
            response = requests.post(
                SOAP_URL,
                data=soap.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                timeout=15,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
            for elem in root.iter():
                if elem.tag.endswith("DESEncryptResult"):
                    encrypted = (elem.text or "").strip()
                    if encrypted:
                        return encrypted
            self.log("AD password encryption result was empty.", "error")
            return None
        except requests.exceptions.Timeout:
            self.log("AD password encryption timeout.", "error")
            return None
        except Exception as error:
            self.log(f"AD password encryption failed: {error}", "error")
            return None

    def _validate_ntid_password_in_ad(self, ntid: str, password: str) -> tuple[bool, str]:
        """Validate NTID and password through the same three-step SAS SOAP flow."""
        clean_ntid = (ntid or "").strip().lower()
        if not clean_ntid:
            return False, "NTID is empty."
        if not password:
            return False, "Password is empty."

        if not self._validate_ntid_in_ad(clean_ntid):
            return False, "NTID does not exist or the Active Directory service is unreachable."

        encrypted_password = self._encrypt_password_for_ad(password)
        if not encrypted_password:
            return False, "Password encryption failed or the Active Directory service is unreachable."

        safe_ntid = html.escape(clean_ntid)
        safe_encrypted_password = html.escape(encrypted_password)
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <ValidateUserCredentialsInAD xmlns="http://jpetewebapp/jtesw_ws/">
              <userName>{safe_ntid}</userName>
              <password>{safe_encrypted_password}</password>
            </ValidateUserCredentialsInAD>
          </soap12:Body>
        </soap12:Envelope>"""

        try:
            response = requests.post(
                SOAP_URL,
                data=soap.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                timeout=15,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
            for elem in root.iter():
                if elem.tag.endswith("ReturnedValue"):
                    if (elem.text or "").strip().lower() == "true":
                        return True, "Login validated successfully."
                    return False, "Invalid NTID or password."
            return False, "Active Directory response did not contain a validation result."
        except requests.exceptions.Timeout:
            self.log("AD credential validation timeout.", "error")
            return False, "Active Directory validation timed out."
        except Exception as error:
            self.log(f"AD credential validation failed: {error}", "error")
            return False, f"Active Directory validation error: {error}"

    # --------------------------------------------------------
    # Admin setup
    # --------------------------------------------------------
    def _load_admin(self):
        self.admin_list = []
        self._remove_developer_admin_from_admin_file()
        if os.path.exists(ADMIN_FILE):
            try:
                with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                seen = set()
                admins = []
                for line in lines:
                    ntid = line.strip()
                    key = ntid.lower()
                    if not ntid or key == DEVELOPER_ADMIN_NTID.lower() or key in seen:
                        continue
                    seen.add(key)
                    admins.append(ntid)
                self.admin_list = admins
            except Exception:
                self.admin_list = []

    def _save_admin(self, ntid):
        try:
            ntid = str(ntid or "").strip().lower()
            if not ntid:
                return
            if ntid == DEVELOPER_ADMIN_NTID.lower():
                self.log("Developer administrator is hard-coded and was not written to admins.txt.", "info")
                return
            admin_ids = {str(item).strip().lower() for item in self.admin_list}
            if ntid not in admin_ids:
                self.admin_list.append(ntid)
            with open(ADMIN_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(self.admin_list))
                if self.admin_list:
                    f.write("\n")
            self.log(f"Admin registered: {ntid}", "success")
        except Exception as e:
            self.log(f"Failed to save admin: {e}", "error")

    def _remove_admin(self, ntid):
        if ntid == self.current_user:
            messagebox.showerror("Error", "You cannot remove yourself as admin.")
            return False
        if len(self.admin_list) <= 1:
            messagebox.showerror("Error", "Cannot remove the last admin.")
            return False
        try:
            self.admin_list = [item for item in self.admin_list if item.strip().lower() != ntid.strip().lower()]
            with open(ADMIN_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(self.admin_list))
                if self.admin_list:
                    f.write("\n")
            self.log(f"Admin removed: {ntid}", "warn")
            return True
        except Exception as e:
            self.log(f"Failed to remove admin: {e}", "error")
            return False

    # --------------------------------------------------------
    # Settings popup
    # --------------------------------------------------------

    def _get_pi_network_identity(self):
        """Return hostname, Linux username, IP addresses and API base URL for Windows SAS connection."""
        hostname = "unknown"
        system_user = "unknown"
        ip_list = []

        try:
            hostname = socket.gethostname()
        except Exception:
            pass

        try:
            system_user = getpass.getuser() or os.getenv("USER") or "unknown"
        except Exception:
            try:
                system_user = os.getenv("USER") or "unknown"
            except Exception:
                system_user = "unknown"

        try:
            result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                ip_list.extend([ip.strip() for ip in result.stdout.split() if ip.strip()])
        except Exception:
            pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and ip not in ip_list:
                ip_list.append(ip)
        except Exception:
            pass

        cleaned = []
        for ip in ip_list:
            if ip and ip not in cleaned:
                cleaned.append(ip)

        non_loopback = [ip for ip in cleaned if not ip.startswith("127.")]
        if non_loopback:
            cleaned = non_loopback

        primary_ip = cleaned[0] if cleaned else "Not detected"
        api_url = f"http://{hostname}:5000"

        return {
            "hostname": hostname,
            "system_user": system_user,
            "ssh_username": system_user,
            "primary_ip": primary_ip,
            "ip_list": cleaned,
            "api_url": api_url,
            "port": "5000",
        }

    def _copy_to_clipboard(self, text, parent=None):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(text))
            self.root.update()
            self._styled_alert("Copied", f"Copied to clipboard:\\n{text}", "success", parent=parent)
        except Exception as e:
            self._styled_alert("Copy Failed", f"Could not copy text:\\n{e}", "error", parent=parent)


    # --------------------------------------------------------
    # Camera orientation
    # --------------------------------------------------------
    def apply_camera_rotation_setting(self, rotation, source="Pi Settings", persist=False, log_change=True):
        """Apply the camera rotation without interrupting an active camera loop.

        Recognition and capture read the saved setting between frames, so their
        next frame is rotated automatically.  This method only updates the local
        UI state and, when requested, persists the value for SAS/API sync.
        """
        degrees = normalize_camera_rotation(rotation, default=getattr(self, "camera_rotation", 0))
        if persist:
            degrees = update_camera_rotation(degrees)

        changed = degrees != getattr(self, "camera_rotation", 0)
        self.camera_rotation = degrees

        callback = getattr(self, "_settings_rotation_refresh", None)
        if callable(callback):
            try:
                callback(degrees)
            except Exception:
                pass

        if changed and log_change:
            self.log(
                f"Camera rotation set to {camera_rotation_label(degrees)} ({source}).",
                "success",
            )
        return degrees


    def _is_admin_session(self) -> bool:
        """Return True only when the Pi UI currently has a signed-in Admin."""
        current = str(getattr(self, "current_user", "") or "").strip().lower()
        if not current:
            return False
        if current == DEVELOPER_ADMIN_NTID:
            return True
        admins = {str(item).strip().lower() for item in getattr(self, "admin_list", [])}
        return current in admins


    def _open_settings(self):
        import json
        import subprocess

        # Reload settings.json every time the Settings popup is opened.
        # This makes Pi UI reflect changes pushed by Windows SAS /settings.
        self._load_pc_path()

        win = tk.Toplevel(self.root)
        win.title("Face Recognition System")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)

        popup_w = 600
        popup_h = 700 if self.current_user else 560
        self._center_popup(win, popup_w, popup_h)

        self._safe_grab(win)

        def _on_close():
            # Avoid calling a refresh callback belonging to a destroyed popup.
            self._settings_rotation_refresh = None
            self._safe_popup_close(win)
            self.root.focus_force()

        win.protocol("WM_DELETE_WINDOW", _on_close)


        shell = RoundedCard(win, bg_color=CARD, radius=24, shadow=True, border=BORDER)
        shell.pack(fill="both", expand=True, padx=14, pady=14)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=24, pady=(18, 10))
        CircleBadge(
            header,
            text="⚙",
            size=40,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 14, "bold")
        ).pack(side="left", padx=(0, 12))
        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(title_box, text="Settings", font=("DejaVu Sans", 16, "bold"),
                 bg=CARD, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(title_box, text="Server connection, capture preference and admin management",
                 font=self.font_small, bg=CARD, fg=TEXT_HINT).pack(anchor="w", pady=(2, 0))

        # Scrollable body for Settings popup
        body_canvas = tk.Canvas(shell, bg=CARD, highlightthickness=0, bd=0)
        body_canvas.pack(fill="both", expand=True, padx=24, pady=(0, 10))

        body_canvas.configure(yscrollcommand="")

        body = tk.Frame(body_canvas, bg=CARD)
        body_window = body_canvas.create_window((0, 0), window=body, anchor="nw")

        def _settings_body_config(event=None):
            body_canvas.configure(scrollregion=body_canvas.bbox("all"))
            try:
                body_canvas.itemconfigure(body_window, width=body_canvas.winfo_width())
            except:
                pass
            
        body.bind("<Configure>", _settings_body_config)
        body_canvas.bind("<Configure>", _settings_body_config)

        def _settings_mousewheel(event):
            try:
                if event.num == 4:
                    body_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    body_canvas.yview_scroll(1, "units")
                else:
                    body_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return "break"
            except:
                return "break"
            
        def _bind_mousewheel_recursive(widget):
            try:
                widget.bind("<MouseWheel>", _settings_mousewheel, add="+")
                widget.bind("<Button-4>", _settings_mousewheel, add="+")
                widget.bind("<Button-5>", _settings_mousewheel, add="+")
            except:
                pass
            
            try:
                for child in widget.winfo_children():
                    _bind_mousewheel_recursive(child)
            except:
                pass

        # --- Pi Network Identity card ---
        # This helps Windows SAS users know which hostname/IP/API URL to enter.
        net_info = self._get_pi_network_identity()

        net_card = RoundedCard(body, bg_color=CARD_SOFT, radius=18, shadow=False, border=BORDER)
        net_card.pack(fill="x", pady=(0, 12), padx=6)

        net_inner = tk.Frame(net_card, bg=CARD_SOFT)
        net_inner.pack(fill="x", padx=18, pady=14)

        net_top = tk.Frame(net_inner, bg=CARD_SOFT)
        net_top.pack(fill="x", pady=(0, 8))

        tk.Label(
            net_top,
            text="Pi Network Identity",
            font=("DejaVu Sans", 12, "bold"),
            bg=CARD_SOFT,
            fg=TEXT_PRI
        ).pack(side="left")

        tk.Label(
            net_top,
            text="Use this in Windows SAS connection",
            font=("DejaVu Sans", 8),
            bg=CARD_SOFT,
            fg=TEXT_SEC
        ).pack(side="right")

        def network_row(label, value, copy_value=None):
            row = tk.Frame(net_inner, bg=CARD_SOFT)
            row.pack(fill="x", pady=4)

            tk.Label(
                row,
                text=label,
                font=self.font_badge,
                bg=CARD_SOFT,
                fg=TEXT_SEC,
                width=15,
                anchor="w"
            ).pack(side="left")

            value_box = RoundedCard(row, bg_color=CARD, radius=12, shadow=False, border="#D9E2EC")
            value_box.pack(side="left", fill="x", expand=True, padx=(4, 8))

            value_lbl = tk.Label(
                value_box,
                text=value,
                font=("DejaVu Sans", 9),
                bg=CARD,
                fg=TEXT_PRI,
                anchor="w",
                justify="left"
            )
            value_lbl.pack(fill="x", padx=12, pady=7)

            if copy_value:
                self._btn(
                    row,
                    "Copy",
                    "#EFF6FF",
                    lambda v=copy_value: self._copy_to_clipboard(v, parent=win),
                    fg=ACCENT,
                    border=True,
                    padx=8,
                    pady=4,
                    width=58
                ).pack(side="right")

        hostname_value = net_info.get("hostname", "unknown")
        ip_value = ", ".join(net_info.get("ip_list", [])) if net_info.get("ip_list") else net_info.get("primary_ip", "Not detected")
        api_value = net_info.get("api_url", f"http://{hostname_value}:5000")

        username_value = net_info.get("ssh_username") or net_info.get("system_user") or "unknown"

        network_row("Hostname", hostname_value, hostname_value)
        network_row("Username", username_value, username_value)
        network_row("IP Address", ip_value, net_info.get("primary_ip", ""))
        network_row("API URL", api_value, api_value)
        network_row("API Port", "5000", "5000")

        hint = tk.Label(
            net_inner,
            text="In Windows SAS, enter either the hostname or IP address. Username is used by SAS for SFTP pull. API port is fixed at 5000.",
            font=("DejaVu Sans", 8),
            bg=CARD_SOFT,
            fg=TEXT_SEC,
            wraplength=430,
            justify="left"
        )
        hint.pack(anchor="w", pady=(8, 0))

        # --- Pi Storage (compact, view-only) ---
        # Kept inside the existing Pi Network Identity card so the original
        # Settings popup structure, controls, and scrolling remain unchanged.
        storage_wrap = tk.Frame(net_inner, bg=CARD_SOFT)
        storage_wrap.pack(fill="x", pady=(12, 0))

        storage_title_row = tk.Frame(storage_wrap, bg=CARD_SOFT)
        storage_title_row.pack(fill="x")

        tk.Label(
            storage_title_row,
            text="Pi Storage",
            font=("DejaVu Sans", 10, "bold"),
            bg=CARD_SOFT,
            fg=TEXT_PRI,
        ).pack(side="left")

        def _storage_human_size(size_bytes):
            value = float(size_bytes)
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if value < 1024.0 or unit == "TB":
                    return f"{value:.1f} {unit}"
                value /= 1024.0
            return f"{value:.1f} TB"

        try:
            _storage_total, _storage_used, _storage_free = shutil.disk_usage("/")
            _storage_percent = (
                (_storage_used / _storage_total) * 100.0
                if _storage_total else 0.0
            )
            _storage_text = (
                f"{_storage_human_size(_storage_used)} used of "
                f"{_storage_human_size(_storage_total)}  •  "
                f"{_storage_human_size(_storage_free)} available"
            )
            if _storage_percent >= 90.0:
                _storage_color = DANGER
            elif _storage_percent >= 80.0:
                _storage_color = WARNING
            else:
                _storage_color = ACCENT
        except Exception:
            _storage_percent = 0.0
            _storage_text = "Storage information unavailable"
            _storage_color = DANGER

        tk.Label(
            storage_wrap,
            text=_storage_text,
            font=("DejaVu Sans", 8),
            bg=CARD_SOFT,
            fg=TEXT_SEC,
            anchor="w",
        ).pack(fill="x", pady=(3, 3))

        storage_bar = tk.Canvas(
            storage_wrap,
            height=10,
            bg=CARD_SOFT,
            highlightthickness=0,
            bd=0,
        )
        storage_bar.pack(fill="x")

        def _draw_compact_storage_bar(event=None):
            try:
                width = max(2, storage_bar.winfo_width())
                height = max(8, storage_bar.winfo_height())
                fill_width = int(width * max(0.0, min(100.0, _storage_percent)) / 100.0)

                storage_bar.delete("all")
                _draw_round_rect(
                    storage_bar, 0, 1, width, height - 1, 6,
                    fill="#E3EAF4", outline="#D9E2EC"
                )
                if fill_width > 0:
                    _draw_round_rect(
                        storage_bar, 0, 1, max(6, fill_width), height - 1, 6,
                        fill=_storage_color, outline=_storage_color
                    )
            except tk.TclError:
                pass

        storage_bar.bind("<Configure>", _draw_compact_storage_bar)
        tk.Label(
            storage_wrap,
            text=f"{_storage_percent:.1f}% used  •  Root filesystem: /",
            font=("DejaVu Sans", 8),
            bg=CARD_SOFT,
            fg=TEXT_HINT,
            anchor="w",
        ).pack(fill="x", pady=(3, 0))


        # --- Device control card (Admin only) ---
        # Hostname/reboot are operating-system actions.  They are intentionally
        # hidden until an Admin has logged into the Pi UI, then delegated to a
        # single root-owned helper installed outside the application folder.
        if self._is_admin_session():
            device_card = RoundedCard(body, bg_color=CARD_SOFT, radius=18, shadow=False, border=BORDER)
            device_card.pack(fill="x", pady=(0, 12), padx=6)
            device_inner = tk.Frame(device_card, bg=CARD_SOFT)
            device_inner.pack(fill="x", padx=18, pady=14)

            tk.Label(
                device_inner,
                text="Device Control",
                font=("DejaVu Sans", 12, "bold"),
                bg=CARD_SOFT,
                fg=TEXT_PRI,
            ).pack(anchor="w")
            tk.Label(
                device_inner,
                text="Change the Linux hostname or restart this Raspberry Pi. These actions are for Pi administrators only.",
                font=("DejaVu Sans", 8),
                bg=CARD_SOFT,
                fg=TEXT_SEC,
                wraplength=430,
                justify="left",
            ).pack(anchor="w", pady=(3, 10))

            tk.Label(
                device_inner,
                text="New Pi Hostname",
                font=self.font_badge,
                bg=CARD_SOFT,
                fg=TEXT_SEC,
            ).pack(anchor="w", pady=(0, 4))

            hostname_box = RoundedCard(device_inner, bg_color=CARD, radius=14, shadow=False, border="#D9E2EC")
            hostname_box.pack(fill="x")
            hostname_entry = tk.Entry(
                hostname_box,
                font=("DejaVu Sans", 10),
                relief="flat",
                bd=0,
                highlightthickness=0,
                bg=CARD,
                fg=TEXT_PRI,
                insertbackground=ACCENT,
            )
            hostname_entry.pack(fill="x", padx=14, pady=10)
            hostname_entry.insert(0, hostname_value)

            tk.Label(
                device_inner,
                text="Allowed: letters, numbers and hyphens. A hostname change disconnects SSH and SAS connections that use the old hostname. The Pi will reboot after the change.",
                font=("DejaVu Sans", 8),
                bg=CARD_SOFT,
                fg=WARNING,
                wraplength=430,
                justify="left",
            ).pack(anchor="w", pady=(7, 10))

            device_status_lbl = tk.Label(
                device_inner,
                text="",
                font=("DejaVu Sans", 8),
                bg=CARD_SOFT,
                fg=TEXT_SEC,
                wraplength=430,
                justify="left",
            )
            device_status_lbl.pack(anchor="w", pady=(0, 8))

            device_btn_row = tk.Frame(device_inner, bg=CARD_SOFT)
            device_btn_row.pack(fill="x")

            device_actor = str(self.current_user or "unknown").strip() or "unknown"

            def show_device_error(message):
                device_status_lbl.config(text=str(message), fg=DANGER)
                self._styled_alert("Device Control Error", str(message), "error", parent=win)

            def start_reboot_request(reason):
                # Verify sudo/helper setup while the GUI is still available. The
                # actual reboot is launched only after the confirmation message.
                def worker():
                    try:
                        verify_system_control_ready()
                    except SystemControlError as exc:
                        self.root.after(0, lambda e=exc: show_device_error(str(e)))
                        return

                    def complete():
                        device_status_lbl.config(text="Reboot requested. The display will go black while the Pi starts again.", fg=WARNING)
                        self.log(f"Pi reboot requested by {device_actor}. Reason: {reason}", "warn")
                        self._styled_alert(
                            "Rebooting Pi",
                            "The Raspberry Pi will restart now. The TTY5 display and SSH connection will temporarily disconnect.",
                            "warning",
                            parent=win,
                        )
                        try:
                            request_reboot()
                        except SystemControlError as exc:
                            show_device_error(str(exc))

                    self.root.after(0, complete)

                Thread(target=worker, daemon=True, name="PiRebootRequest").start()

            def change_hostname_and_reboot():
                requested = hostname_entry.get().strip()
                try:
                    new_hostname = validate_hostname(requested)
                except ValueError as exc:
                    show_device_error(str(exc))
                    return

                old_hostname = hostname_value
                if new_hostname == old_hostname:
                    self._styled_alert(
                        "No Hostname Change",
                        "The requested hostname is already active. Use Reboot Pi only if you need to restart the device.",
                        "info",
                        parent=win,
                    )
                    return

                if not self._styled_confirm(
                    "Change Pi Hostname",
                    f"Change hostname from '{old_hostname}' to '{new_hostname}'?\n\nThe Pi will reboot. Update Windows SAS if it connects using the old hostname.",
                    parent=win,
                ):
                    return

                hostname_entry.config(state="disabled")
                hostname_change_btn.config(state="disabled")
                reboot_btn.config(state="disabled")
                device_status_lbl.config(text="Applying hostname change...", fg=WARNING)

                def worker():
                    try:
                        verify_system_control_ready()
                        change_hostname(new_hostname)
                    except (SystemControlError, ValueError) as exc:
                        def failed(e=exc):
                            hostname_entry.config(state="normal")
                            hostname_change_btn.config(state="normal")
                            reboot_btn.config(state="normal")
                            show_device_error(str(e))
                        self.root.after(0, failed)
                        return

                    def complete():
                        self.log(
                            f"Pi hostname changed by {device_actor}: {old_hostname} -> {new_hostname}. Reboot requested.",
                            "success",
                        )
                        device_status_lbl.config(text=f"Hostname changed to {new_hostname}. Rebooting Pi...", fg=SUCCESS)
                        self._styled_alert(
                            "Hostname Updated",
                            f"Hostname changed to '{new_hostname}'.\n\nThe Pi will reboot after you close this message. SSH and SAS connections using '{old_hostname}' must use the new hostname after restart.",
                            "success",
                            parent=win,
                        )
                        try:
                            request_reboot()
                        except SystemControlError as exc:
                            show_device_error(str(exc))

                    self.root.after(0, complete)

                Thread(target=worker, daemon=True, name="PiHostnameChange").start()

            def confirm_reboot():
                if not self._styled_confirm(
                    "Reboot Raspberry Pi",
                    "Restart this Raspberry Pi now? The camera, TTY5 interface, API and SSH connection will temporarily stop.",
                    parent=win,
                ):
                    return
                start_reboot_request("Pi Settings reboot button")

            hostname_change_btn = self._btn(
                device_btn_row,
                "Apply Hostname & Reboot",
                ACCENT,
                change_hostname_and_reboot,
                fg="white",
                padx=12,
                pady=8,
                width=195,
            )
            hostname_change_btn.pack(side="left")

            reboot_btn = self._btn(
                device_btn_row,
                "Reboot Pi",
                DANGER,
                confirm_reboot,
                fg="white",
                padx=12,
                pady=8,
                width=105,
            )
            reboot_btn.pack(side="right")

        # --- Server connection card ---
        conn_card = RoundedCard(body, bg_color=CARD_SOFT, radius=18, shadow=False, border=BORDER)
        conn_card.pack(fill="x", pady=(8, 12))
        conn_inner = tk.Frame(conn_card, bg=CARD_SOFT)
        conn_inner.pack(fill="x", padx=18, pady=14)

        tk.Label(conn_inner, text="Server Credentials", font=("DejaVu Sans", 12, "bold"),
                 bg=CARD_SOFT, fg=TEXT_PRI).pack(anchor="w", pady=(0, 4))

        # --- NTID field ---
        tk.Label(conn_inner, text="NTID / Username", font=self.font_badge,
                 bg=CARD_SOFT, fg=TEXT_SEC).pack(anchor="w", pady=(8, 4))

        username_box = RoundedCard(conn_inner, bg_color=CARD, radius=14, shadow=False, border="#D9E2EC")
        username_box.pack(fill="x")

        username_entry = tk.Entry(
            username_box,
            font=("DejaVu Sans", 10),
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=CARD,
            fg=TEXT_PRI,
            insertbackground=ACCENT
        )
        username_entry.pack(fill="x", padx=14, pady=10)

        # --- Password field ---
        tk.Label(conn_inner, text="Password", font=self.font_badge,
                 bg=CARD_SOFT, fg=TEXT_SEC).pack(anchor="w", pady=(10, 4))

        pwd_box = RoundedCard(conn_inner, bg_color=CARD, radius=14, shadow=False, border="#D9E2EC")
        pwd_box.pack(fill="x")

        pwd_row = tk.Frame(pwd_box, bg=CARD)
        pwd_row.pack(fill="x", padx=10, pady=6)

        password_entry = tk.Entry(
            pwd_row,
            font=("DejaVu Sans", 10),
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=CARD,
            fg=TEXT_PRI,
            show="*",
            insertbackground=ACCENT
        )
        password_entry.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=4)

        password_visible = {"value": False}

        def toggle_password():
            password_visible["value"] = not password_visible["value"]

            if password_visible["value"]:
                password_entry.config(show="")
                show_btn.config(text="Hide")
            else:
                password_entry.config(show="*")
                show_btn.config(text="Show")

        show_btn = self._btn(
            pwd_row,
            "Show",
            "#EFF6FF",
            toggle_password,
            fg=ACCENT,
            border=True,
            padx=8,
            pady=4,
            width=64
        )
        show_btn.pack(side="right", padx=4, pady=4)

        # --- PC Server Path field ---
        tk.Label(conn_inner, text="Server Path",
                 font=self.font_badge, bg=CARD_SOFT, fg=TEXT_SEC).pack(anchor="w", pady=(10, 4))

        path_box = RoundedCard(conn_inner, bg_color=CARD, radius=14, shadow=False, border="#D9E2EC")
        path_box.pack(fill="x")

        path_entry = tk.Entry(
            path_box,
            font=("DejaVu Sans", 10),
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=CARD,
            fg=TEXT_PRI,
            insertbackground=ACCENT
        )
        path_entry.pack(fill="x", padx=14, pady=10)

        # --- Camera orientation card ---
        # Rotation is persisted immediately on the Pi.  Recognition, capture,
        # local preview and the SAS /video-feed viewer pick it up between frames.
        rotation_card = RoundedCard(body, bg_color=CARD_SOFT, radius=18, shadow=False, border=BORDER)
        rotation_card.pack(fill="x", pady=(0, 12), padx=6)
        rotation_inner = tk.Frame(rotation_card, bg=CARD_SOFT)
        rotation_inner.pack(fill="x", padx=18, pady=14)

        tk.Label(
            rotation_inner,
            text="Camera Orientation",
            font=("DejaVu Sans", 12, "bold"),
            bg=CARD_SOFT,
            fg=TEXT_PRI,
        ).pack(anchor="w")
        tk.Label(
            rotation_inner,
            text="Use this when the camera is installed in a rotated position. The Pi preview and Windows SAS live panel stay synchronized.",
            font=("DejaVu Sans", 8),
            bg=CARD_SOFT,
            fg=TEXT_SEC,
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(3, 10))

        rotation_button_row = tk.Frame(rotation_inner, bg=CARD_SOFT)
        rotation_button_row.pack(fill="x")
        rotation_buttons = {}

        def refresh_rotation_buttons(rotation):
            selected = normalize_camera_rotation(rotation)
            for degrees, button in rotation_buttons.items():
                if degrees == selected:
                    button.config(
                        bg=ACCENT,
                        fg="white",
                        activebackground=ACCENT_HOV,
                        activeforeground="white",
                    )
                else:
                    button.config(
                        bg=CARD,
                        fg=TEXT_SEC,
                        activebackground="#EEF5FF",
                        activeforeground=ACCENT,
                    )

        def set_rotation_from_pi_settings(degrees):
            applied = self.apply_camera_rotation_setting(
                degrees,
                source="Pi Settings",
                persist=True,
                log_change=True,
            )
            refresh_rotation_buttons(applied)
            try:
                status_lbl.config(
                    text=f"Camera orientation applied: {camera_rotation_label(applied)}",
                    fg=SUCCESS,
                )
            except Exception:
                pass

        for degrees, label in ((0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")):
            button = self._btn(
                rotation_button_row,
                label,
                CARD,
                lambda d=degrees: set_rotation_from_pi_settings(d),
                fg=TEXT_SEC,
                border=True,
                padx=10,
                pady=6,
                width=68,
            )
            button.pack(side="left", padx=(0, 8 if degrees != 270 else 0))
            rotation_buttons[degrees] = button

        # API-driven updates from SAS refresh these buttons while the popup is open.
        self._settings_rotation_refresh = refresh_rotation_buttons
        refresh_rotation_buttons(self.camera_rotation)

        # --- Load existing saved values into fields ---
        settings = self._load_settings()

        self.auto_capture_enabled = False
        self.apply_camera_rotation_setting(
            settings.get("camera_rotation", self.camera_rotation),
            source="settings.json",
            persist=False,
            log_change=False,
        )
        if settings.get("username"):
            username_entry.insert(0, settings["username"])
        if settings.get("password"):
            try:
                f = Fernet(FERNET_KEY)
                decrypted_pwd = f.decrypt(settings["password"].encode()).decode()
                password_entry.insert(0, decrypted_pwd)
            except Exception:
                password_entry.insert(0, settings["password"])
        if settings.get("pc_save_path"):
            path_entry.insert(0, settings["pc_save_path"])

        status_lbl = tk.Label(body, text="", font=self.font_body, bg=CARD, fg=TEXT_SEC)
        status_lbl.pack(anchor="w", pady=(0, 8))

        btn_row = tk.Frame(body, bg=CARD)
        btn_row.pack(fill="x", pady=(0, 12))

        def save():
            ntid    = username_entry.get().strip()
            pwd     = password_entry.get().strip()
            unc     = path_entry.get().strip()

            if not ntid or not pwd or not unc:
                self._styled_alert("Missing Information", "Please fill in NTID, password and server path.", "warning", parent=win)
                return

            status_lbl.config(text="Connecting to server...", fg=Warning)
            win.update()

            linux_path = unc.replace("\\", "/")
            mount_point = "/mnt/pcshare"
            os.makedirs(mount_point, exist_ok=True)

            try:
                subprocess.run(["sudo", "umount", "-l", mount_point], capture_output=True, text=True, timeout=10)
            except Exception:
                pass

            cmd = [
                "sudo", "mount", "-t", "cifs",
                linux_path, mount_point,
                "-o", f"username={ntid},password={pwd},domain=JABIL,vers=3.0,uid=1000,gid=1000"
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except Exception as e:
                status_lbl.config(text="Mount error.", fg=DANGER)
                self._styled_alert("Mount Error", f"Failed to run mount command:\n{e}", "error", parent=win)
                return

            if result.returncode != 0:
                err_msg = result.stderr.strip() if result.stderr.strip() else "Unknown error."
                status_lbl.config(text="Connection failed.", fg=DANGER)
                self._styled_alert(
                    "Connection Failed",
                    f"Could not connect to server.\n\nError:\n{err_msg}\n\nPlease check your NTID, password and server path.",
                    "error",
                    parent=win
                )
                return

            try:
                ls_result = subprocess.run(["ls", mount_point], capture_output=True, text=True, timeout=10)
                if ls_result.returncode != 0:
                    status_lbl.config(text="Access denied.", fg=DANGER)
                    self._styled_alert("Access Denied", f"Mounted but cannot read folder.\n\nError:\n{ls_result.stderr.strip()}", "error", parent=win)
                    return
            except Exception as e:
                status_lbl.config(text="Verification error.", fg=DANGER)
                self._styled_alert("Verification Error", f"Could not verify access:\n{e}", "error", parent=win)
                return

            try:
                f = Fernet(FERNET_KEY)
                encrypted = f.encrypt(pwd.encode()).decode()

                # Preserve camera_rotation and any future non-server settings.
                settings = self._load_settings().copy()
                settings.update({
                    "username": ntid,
                    "password": encrypted,
                    "pc_save_path": unc,
                    "auto_capture": False,
                    "camera_rotation": normalize_camera_rotation(self.camera_rotation),
                    "unlock_transport": "websocket",
                    "recognition_result_file": "local diagnostic only",
                    "server_mount_point": "/mnt/pcshare",
                    "last_synced_from": "Pi GUI",
                    "last_synced_at": time.strftime("%Y-%m-%d %H:%M:%S")
                })

                with open(SETTINGS_FILE, "w") as file:
                    json.dump(settings, file, indent=4)

                self.pc_save_path = mount_point
                self.auto_capture_enabled = False

                # Keep FaceService runtime state aligned without restarting Pi app.
                try:
                    if hasattr(self, "face_service"):
                        self.face_service.auto_capture_enabled = self.auto_capture_enabled
                except Exception:
                    pass

                self.pc_path_entry.config(state="normal")
                self.pc_path_entry.delete(0, tk.END)
                self.pc_path_entry.insert(0, unc)
                self.pc_path_entry.config(state="readonly")

                self.log(f"Settings saved. Connected to: {unc}", "success")
                status_lbl.config(text="Connected successfully!", fg=SUCCESS)
                self._styled_alert("Success", f"Connected to server successfully!\n\nPath: {unc}", "success", parent=win)
                _on_close()

            except Exception as e:
                self.log(f"Failed to save settings: {e}", "error")
                self._styled_alert("Error", f"Failed to save settings:\n{e}", "error", parent=win)

        self._btn(btn_row, "Save & Connect", ACCENT, save, fg="white", padx=18, pady=9, width=160).pack(side="right")
        self._btn(btn_row, "Cancel", CARD_SOFT, _on_close, fg=TEXT_SEC, border=True, padx=18, pady=9, width=100).pack(side="right", padx=(0, 10))
        # ── Admin Management (only visible when admin is logged in) ──
        if self.current_user:
            # ── Face Data Transfer ──
            transfer_card = RoundedCard(
                body,
                bg_color=CARD_SOFT,
                radius=18,
                shadow=False,
                border=BORDER
            )
            transfer_card.pack(fill="x", pady=(2, 12))

            transfer_inner = tk.Frame(transfer_card, bg=CARD_SOFT)
            transfer_inner.pack(fill="x", padx=18, pady=14)

            tk.Label(
                transfer_inner,
                text="Face Data Transfer",
                font=("DejaVu Sans", 12, "bold"),
                bg=CARD_SOFT,
                fg=TEXT_PRI
            ).pack(anchor="w")

            tk.Label(
                transfer_inner,
                text="Export or import InsightFace face data through the SMB server path. Employee names and IDs are preserved; existing IDs are checked and only new data is added.",
                font=self.font_small,
                bg=CARD_SOFT,
                fg=TEXT_HINT,
                wraplength=430,
                justify="left"
            ).pack(anchor="w", pady=(3, 10))

            # Keep SMB Export / Import here. Do not place SFTP buttons in the same row,
            # because the Settings popup width is limited.
            smb_btn_row = tk.Frame(transfer_inner, bg=CARD_SOFT)
            smb_btn_row.pack(fill="x")

            self._btn(
                smb_btn_row,
                "Export Face Data",
                ACCENT,
                self.export_face_data,
                fg="white",
                padx=12,
                pady=8,
                width=150
            ).pack(side="left", padx=(0, 8))

            self._btn(
                smb_btn_row,
                "Import Face Data",
                SUCCESS,
                self.import_face_data,
                fg="white",
                padx=12,
                pady=8,
                width=150
            ).pack(side="left")

            # ── SFTP transfer section ──
            sftp_card = RoundedCard(
                transfer_inner,
                bg_color=CARD,
                radius=16,
                shadow=False,
                border="#D9E2EC"
            )
            sftp_card.pack(fill="x", pady=(14, 0))

            sftp_inner = tk.Frame(sftp_card, bg=CARD)
            sftp_inner.pack(fill="x", padx=14, pady=12)

            tk.Label(
                sftp_inner,
                text="Transfer Face Data via SFTP",
                font=("DejaVu Sans", 11, "bold"),
                bg=CARD,
                fg=TEXT_PRI
            ).pack(anchor="w")

            tk.Label(
                sftp_inner,
                text="Send this Pi's face dataset directly to another Pi's pending receive folder. The receiver can accept or reject it later.",
                font=self.font_small,
                bg=CARD,
                fg=TEXT_HINT,
                wraplength=400,
                justify="left"
            ).pack(anchor="w", pady=(3, 10))

            sftp_btn_row = tk.Frame(sftp_inner, bg=CARD)
            sftp_btn_row.pack(fill="x")

            self._btn(
                sftp_btn_row,
                "Send to Another Pi",
                PURPLE,
                self.send_face_data_to_pi,
                fg="white",
                padx=12,
                pady=8,
                width=170
            ).pack(side="left", padx=(0, 8))

            self._received_badge_wrap = tk.Frame(sftp_btn_row, bg=CARD)
            self._received_badge_wrap.pack(side="left")

            self.check_received_btn = self._btn(
                self._received_badge_wrap,
                "Check Received",
                CARD_SOFT,
                lambda: self.scan_received_face_data(silent=False),
                fg=ACCENT,
                border=True,
                padx=12,
                pady=8,
                width=140
            )
            self.check_received_btn.pack(side="left")

            self._received_badge_label = tk.Label(
                self._received_badge_wrap,
                text="",
                bg=DANGER,
                fg="white",
                font=("DejaVu Sans", 8, "bold"),
                width=2,
                height=1,
                relief="flat",
                bd=0
            )
            self._received_badge_label.place(relx=1.0, rely=0.0, x=-6, y=-6, anchor="ne")
            self._received_badge_label.place_forget()
            self._update_received_badge()

            admin_card = RoundedCard(body, bg_color=CARD_SOFT, radius=18, shadow=False, border=BORDER)
            admin_card.pack(fill="both", expand=True, pady=(2, 0))
            admin_inner = tk.Frame(admin_card, bg=CARD_SOFT)
            admin_inner.pack(fill="both", expand=True, padx=18, pady=14)

            tk.Label(admin_inner, text="Admin Management", font=("DejaVu Sans", 12, "bold"),
                     bg=CARD_SOFT, fg=TEXT_PRI).pack(anchor="w")

            add_row = tk.Frame(admin_inner, bg=CARD_SOFT)
            add_row.pack(fill="x", pady=(10, 6))
            tk.Label(add_row, text="Add Admin NTID", font=self.font_badge,
                     bg=CARD_SOFT, fg=TEXT_SEC).pack(side="left")
            add_entry = tk.Entry(add_row, font=self.font_body, relief="flat", bg=CARD, fg=TEXT_PRI, width=18)
            add_entry.pack(side="left", padx=(10, 8), ipady=6, ipadx=8, fill="x", expand=True)

            list_frame = tk.Frame(admin_inner, bg=CARD_SOFT)
            list_frame.pack(fill="x", pady=(6, 0))

            def refresh_admin_list():
                for w in list_frame.winfo_children():
                    w.destroy()
                for a in self.admin_list:
                    row = tk.Frame(list_frame, bg=CARD_SOFT)
                    row.pack(fill="x", pady=3)
                    tag = " (you)" if a == self.current_user else ""
                    tk.Label(row, text=f"{a}{tag}", font=self.font_body,
                             bg=CARD_SOFT, fg=TEXT_PRI).pack(side="left", padx=(0, 8))
                    can_remove = (a != self.current_user and len(self.admin_list) > 1)
                    if can_remove:
                        def make_remove(ntid=a):
                            def do_remove():
                                if self._styled_confirm("Confirm Remove", f"Remove '{ntid}' from admins?", parent=win):
                                    if self._remove_admin(ntid):
                                        refresh_admin_list()
                            return do_remove
                        self._btn(row, "Remove", "#FEE2E2", make_remove(), fg=DANGER,
                                  padx=10, pady=4, width=90).pack(side="right")

            def _on_close():
                self._safe_popup_close(win)
                self.root.focus_force()

            def add_admin():
                new_ntid = add_entry.get().strip()
                if not new_ntid:
                    self._styled_alert("Missing NTID", "Please enter an NTID.", "warning", parent=win)
                    return
                if new_ntid in self.admin_list:
                    self._styled_alert("Already Admin", f"'{new_ntid}' is already an admin.", "info", parent=win)
                    return
                if not self._validate_ntid_in_ad(new_ntid):
                    self._styled_alert("Invalid NTID", f"'{new_ntid}' is not a valid NTID.", "error", parent=win)
                    return
                self._save_admin(new_ntid)
                add_entry.delete(0, tk.END)
                refresh_admin_list()
                self._styled_alert("Success", f"'{new_ntid}' added as admin.", "success", parent=win)

            self._btn(add_row, "Add", SUCCESS, add_admin, fg="white", padx=12, pady=6, width=80).pack(side="right")
            refresh_admin_list()

        # Bind scrolling after all Settings widgets are created.
        # This must run for both non-login setup mode and admin mode; otherwise the
        # Settings popup cannot scroll when the user opens Settings before login.
        _bind_mousewheel_recursive(win)
        _bind_mousewheel_recursive(shell)
        _bind_mousewheel_recursive(body)


    def _stop_recognition_before_capture(self):
        service_running = False
    
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                service_running = getattr(self.face_service, "_recognition_running", False)
        except Exception:
            service_running = False
    
        if not self._recognition_running and not service_running:
            return False
    
        self.log("Recognition is running. Stopping recognition before capture...", "warn")
    
        # Stop Pi-GUI-started recognition
        self.stop_flag = True
    
        # Stop FaceService/API-started recognition
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                self.face_service._stop_recognition_event.set()
                self.face_service._stop_capture_event.set()
        except Exception as e:
            print("[STOP SERVICE RECOGNITION ERROR]", e)
    
        self._set_camera_status(False)
    
        # Prevent repeated capture clicks while waiting camera release
        self.capture_btn.config(state="disabled")
    
        self.stop_btn.config(
            state="normal",
            bg=WARNING,
            fg="white",
            activebackground=WARNING,
            activeforeground="white"
        )
    
        wait_start = time.time()
    
        def check():
            gui_running = getattr(self, "_recognition_running", False)
    
            service_still_running = False
            try:
                if hasattr(self, "face_service") and self.face_service is not None:
                    service_still_running = getattr(self.face_service, "_recognition_running", False)
            except Exception:
                service_still_running = False
    
            if not gui_running and not service_still_running:
                # Give camera device a short time to release
                self.root.after(800, self.start_capture)
                return
    
            if time.time() - wait_start > 10:
                self.log("Camera is still busy. Please try capture again.", "error")
    
                # Re-enable capture if stopping failed
                self.capture_btn.config(state="normal" if self.current_user else "disabled")
                return
    
            self.root.after(200, check)
    
        check()
        return True

    def _modern_input(self, parent, label, default="", show=""):
        wrapper = tk.Frame(parent, bg=CARD)
        wrapper.pack(fill="x", pady=(0, 14))
    
        tk.Label(
            wrapper,
            text=label,
            font=("Helvetica Neue", 9, "bold"),
            bg=CARD,
            fg=TEXT_SEC
        ).pack(anchor="w", pady=(0, 5))
    
        box = tk.Frame(
            wrapper,
            bg="#F8FAFC",
            highlightthickness=1,
            highlightbackground="#D9E2EC"
        )
        box.pack(fill="x")
    
        entry = tk.Entry(
            box,
            font=("Helvetica Neue", 11),
            bg="#F8FAFC",
            fg=TEXT_PRI,
            relief="flat",
            bd=0,
            insertbackground=ACCENT,
            show=show
        )
        entry.pack(fill="x", padx=14, pady=10)
    
        if default:
            entry.insert(0, default)
    
        return entry

    # --------------------------------------------------------
    # Mount server on startup
    # --------------------------------------------------------
    def _mount_server(self):
        """Start SMB mounting in a background thread.

        The Pi GUI and TTY5 fullscreen must not wait for a Windows SMB server.
        When Ethernet is unavailable, the app continues in local mode and the
        server mount can be retried later through Settings / Windows SAS sync.
        """
        def worker():
            import subprocess

            settings = self._load_settings()
            unc_path = settings.get("pc_save_path")
            username = settings.get("username")
            enc_password = settings.get("password")

            if not unc_path or not username or not enc_password:
                self.log("Server mount skipped: credentials or path not set.", "warn")
                return

            try:
                f = Fernet(FERNET_KEY)
                password = f.decrypt(enc_password.encode()).decode()
            except Exception as exc:
                self.log(f"Server mount skipped: password could not be decrypted ({exc}).", "warn")
                return

            linux_path = unc_path.replace("\\", "/")
            mount_point = "/mnt/pcshare"

            try:
                os.makedirs(mount_point, exist_ok=True)

                # Clear an old lazy/stale mount before making a fresh attempt.
                try:
                    subprocess.run(
                        ["sudo", "umount", "-l", mount_point],
                        capture_output=True,
                        text=True,
                        timeout=8,
                    )
                except Exception:
                    pass

                cmd = [
                    "sudo", "mount", "-t", "cifs",
                    linux_path, mount_point,
                    "-o", (
                        f"username={username},password={password},"
                        "domain=JABIL,vers=3.0,uid=1000,gid=1000"
                    ),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)

                if result.returncode != 0:
                    detail = result.stderr.strip() or "network/server unavailable"
                    self.log(
                        f"Server mount unavailable; continuing in local mode. ({detail})",
                        "warn",
                    )
                    return

                # Verify access in the worker. A failed verification does not
                # block or close the Pi GUI.
                verify = subprocess.run(
                    ["ls", mount_point],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if verify.returncode != 0:
                    detail = verify.stderr.strip() or "mounted path cannot be read"
                    self.log(
                        f"Server mount verification failed; continuing in local mode. ({detail})",
                        "warn",
                    )
                    return

                self.pc_save_path = mount_point
                try:
                    if hasattr(self, "face_service"):
                        self.face_service.pc_save_path = mount_point
                except Exception:
                    pass

                self.log("Server mounted successfully.", "success")

            except Exception as exc:
                self.log(
                    f"Server mount unavailable; continuing in local mode. ({exc})",
                    "warn",
                )

        Thread(target=worker, daemon=True, name="SmbStartupMount").start()

    # --------------------------------------------------------
    # Load settings from settings.json
    # --------------------------------------------------------
    def _load_settings(self):
        import json
        if not os.path.exists(SETTINGS_FILE):
            return {}
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}

    # --------------------------------------------------------
    # Load PC path and other settings on startup
    # --------------------------------------------------------
    def _load_pc_path(self):
        import json

        if not os.path.exists(SETTINGS_FILE):
            return

        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)

            # settings.json may be updated by Windows SAS while Pi app is running.
            # Reload every time Settings is opened or when the app refreshes path state.
            self.pc_save_path = data.get("pc_save_path")
            self.auto_capture_enabled = False
            self.camera_rotation = normalize_camera_rotation(data.get("camera_rotation", self.camera_rotation))

            if self.pc_save_path and hasattr(self, "pc_path_entry"):
                self.pc_path_entry.config(state="normal")
                self.pc_path_entry.delete(0, tk.END)
                self.pc_path_entry.insert(0, self.pc_save_path)
                self.pc_path_entry.config(state="readonly")
                self.log(f"Loaded PC save path: {self.pc_save_path}", "info")

            try:
                if hasattr(self, "face_service"):
                    self.face_service.auto_capture_enabled = False
                    self.face_service.pc_save_path = self.pc_save_path
            except Exception:
                pass

        except Exception as e:
            self.log(f"Failed to load settings: {e}", "error")

    # --------------------------------------------------------
    # Permissions
    # --------------------------------------------------------
    def _set_default_permissions(self):
        # Non-admin: capture, train, delete all disabled
        # Recognition always available; stop only enabled when a process runs
        self.capture_btn.config(state="disabled")
        self.train_btn.config(state="disabled")
        self.delete_btn.config(state="disabled")
        self.recog_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def _enable_admin_permissions(self):
        self.capture_btn.config(state="normal")
        self.train_btn.config(state="normal")
        self.delete_btn.config(state="normal")

        if self._recognition_running or self._capture_running:
            self.recog_btn.config(state="disabled")
            self.stop_btn.config(
                state="normal",
                bg=WARNING,
                fg="white",
                activebackground=WARNING,
                activeforeground="white"
            )
        else:
            self.recog_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

        self.log("Admin access granted.", "success")

    # --------------------------------------------------------
    # Modern popup helpers
    # --------------------------------------------------------

    def _modern_popup_shell(self, title, width=440, height=260):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)

        win.geometry(f"{width}x{height}")
        win.update_idletasks()

        x = self.root.winfo_x() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")

        shell = tk.Frame(win, bg=CARD)
        shell.pack(fill="both", expand=True, padx=12, pady=12)

        self._safe_grab(win)

        return win, shell

    
    def _safe_popup_close(self, win):
        # Release any active Tkinter grab first
        try:
            grabbed = self.root.grab_current()
            if grabbed is not None:
                grabbed.grab_release()
        except:
            pass

        try:
            win.grab_release()
        except:
            pass

        try:
            win.destroy()
        except:
            pass

        try:
            if getattr(self, "_account_menu_win", None) == win:
                self._account_menu_win = None
        except:
            pass

        try:
            self.root.lift()
            self.root.focus_force()
        except:
            pass

    def _safe_grab(self, win):
        try:
            win.update_idletasks()
            win.deiconify()
            win.lift()
            win.focus_force()
            win.grab_set()
        except tk.TclError:
            try:
                win.after(100, lambda: self._safe_grab(win))
            except:
                pass

    def _field_box(self, parent, label, default="", show="", readonly=False):
        tk.Label(
            parent,
            text=label,
            font=self.font_badge,
            bg=CARD,
            fg=TEXT_SEC
        ).pack(anchor="w", pady=(10, 4))

        wrap = RoundedCard(
            parent,
            bg_color=CARD,
            radius=14,
            shadow=False,
            border="#D9E2EC"
        )
        wrap.pack(fill="x")

        entry = tk.Entry(
            wrap,
            font=("DejaVu Sans", 10),
            bg=CARD,
            fg=TEXT_PRI,
            relief="flat",
            bd=0,
            highlightthickness=0,
            show=show,
            insertbackground=ACCENT,
            readonlybackground=CARD
        )
        entry.pack(fill="x", padx=14, pady=10)

        if default:
            entry.insert(0, default)

        if readonly:
            entry.config(state="readonly")

        return entry

    def _styled_alert(self, title, message, kind="info", parent=None):
        colors = {
            "info": (ACCENT, "ⓘ"),
            "success": (SUCCESS, "✓"),
            "warning": (WARNING, "⚠"),
            "error": (DANGER, "✕"),
        }
    
        color, icon = colors.get(kind, colors["info"])
        msg_text = str(message)
    
        # Only use scroll for long messages
        use_scroll = len(msg_text) > 260 or ("\n" in msg_text and len(msg_text) > 180)
    
        popup_w = 540
        popup_h = 390 if use_scroll else 270
    
        win, shell = self._modern_popup_shell(title, popup_w, popup_h)
    
        if parent:
            win.transient(parent)
    
        # Header
        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))
    
        CircleBadge(
            header,
            text=icon,
            size=38,
            bg_color="#EFF6FF" if kind != "error" else "#FEF2F2",
            fg=color,
            font=("DejaVu Sans", 15, "bold")
        ).pack(side="left", padx=(0, 12))
    
        tk.Label(
            header,
            text=title,
            font=("DejaVu Sans", 14, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(side="left")
    
        # Message area
        msg_area = tk.Frame(shell, bg=CARD)
        msg_area.pack(fill="both", expand=True, padx=24, pady=(4, 8))
    
        if use_scroll:
            msg_textbox = tk.Text(
                msg_area,
                font=self.font_body,
                bg=CARD,
                fg=TEXT_SEC,
                relief="flat",
                bd=0,
                highlightthickness=0,
                wrap="word",
                height=7
            )
            msg_textbox.insert("1.0", msg_text)
            msg_textbox.config(state="disabled")
            msg_textbox.pack(side="left", fill="both", expand=True)
    
            # Hidden scrollbar, but scroll function still works
            msg_textbox.configure(yscrollcommand="")
    
            def _alert_mousewheel(event):
                try:
                    if event.num == 4:
                        msg_textbox.yview_scroll(-1, "units")
                    elif event.num == 5:
                        msg_textbox.yview_scroll(1, "units")
                    else:
                        msg_textbox.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return "break"
                except:
                    return "break"
    
            msg_textbox.bind("<MouseWheel>", _alert_mousewheel)
            msg_textbox.bind("<Button-4>", _alert_mousewheel)
            msg_textbox.bind("<Button-5>", _alert_mousewheel)
    
        else:
            tk.Label(
                msg_area,
                text=msg_text,
                font=self.font_body,
                bg=CARD,
                fg=TEXT_SEC,
                wraplength=460,
                justify="center"
            ).pack(expand=True)
    
        # Fixed bottom button row
        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(0, 18))
    
        def close_popup():
            self._safe_popup_close(win)
    
        self._btn(
            row,
            "OK",
            ACCENT if kind != "error" else DANGER,
            close_popup,
            fg="white",
            padx=18,
            pady=9,
            width=120
        ).pack(side="right")
    
        win.wait_window()

    def _styled_confirm(self, title, message, parent=None):
        result = {"value": False}
    
        # Bigger popup height so buttons are visible
        win, shell = self._modern_popup_shell(title, 500, 340)
    
        if parent:
            win.transient(parent)
    
        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))
    
        CircleBadge(
            header,
            text="?",
            size=38,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 15, "bold")
        ).pack(side="left", padx=(0, 12))
    
        tk.Label(
            header,
            text=title,
            font=("DejaVu Sans", 14, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(side="left")
    
        # Message area
        msg_lbl = tk.Label(
            shell,
            text=message,
            font=self.font_body,
            bg=CARD,
            fg=TEXT_SEC,
            wraplength=430,
            justify="left"
        )
        msg_lbl.pack(fill="both", expand=True, padx=24, pady=(8, 12))
    
        # Button row always visible at bottom
        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(0, 18))
    
        def close_popup():
            self._safe_popup_close(win)
    
        def yes():
            result["value"] = True
            close_popup()
    
        self._btn(
            row,
            "Cancel",
            CARD_SOFT,
            close_popup,
            fg=TEXT_SEC,
            border=True,
            padx=18,
            pady=8,
            width=110
        ).pack(side="right", padx=(8, 0))
    
        self._btn(
            row,
            "Confirm",
            DANGER,
            yes,
            fg="white",
            padx=18,
            pady=8,
            width=120
        ).pack(side="right")
    
        win.wait_window()
        return result["value"]

    def _ask_ntid_popup(self, title="Login", prompt="Enter NTID:"):
        result: dict[str, str | None] = {"value": None}

        win, shell = self._modern_popup_shell(title, 440, 260)

        def close_popup():
            self._safe_popup_close(win)
            self.root.focus_force()

        win.protocol("WM_DELETE_WINDOW", close_popup)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 12))

        CircleBadge(
            header,
            text="",
            size=40,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 14, "bold")
        ).pack(side="left", padx=(0, 12))

        tk.Label(
            header,
            text=title,
            font=("DejaVu Sans", 15, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(side="left")

        form = tk.Frame(shell, bg=CARD)
        form.pack(fill="x", padx=24)

        entry = self._field_box(form, prompt, default="")
        entry.focus_set()

        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(20, 18))

        def ok():
            value = entry.get().strip()

            if not value:
                self._styled_alert(
                    "Missing NTID",
                    "Please enter your NTID.",
                    "warning",
                    parent=win
                )
                return

            result["value"] = value
            close_popup()

        self._btn(
            row,
            "Cancel",
            CARD_SOFT,
            close_popup,
            fg=TEXT_SEC,
            border=True,
            padx=18,
            pady=8,
            width=100
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Login",
            ACCENT,
            ok,
            fg="white",
            padx=18,
            pady=8,
            width=100
        ).pack(side="right")

        win.bind("<Return>", lambda e: ok())

        win.wait_window()
        return result["value"]
    def _ask_login_credentials_popup(self, title="Login"):
        """Collect NTID and password locally; password is never written to logs or files."""
        result: dict[str, str | None] = {"ntid": None, "password": None}

        win, shell = self._modern_popup_shell(title, 460, 360)

        def close_popup():
            self._safe_popup_close(win)
            self.root.focus_force()

        win.protocol("WM_DELETE_WINDOW", close_popup)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))

        CircleBadge(
            header,
            text="",
            size=40,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 14, "bold"),
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text=title,
            font=("DejaVu Sans", 15, "bold"),
            bg=CARD,
            fg=TEXT_PRI,
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Enter your NTID and Active Directory password.",
            font=self.font_small,
            bg=CARD,
            fg=TEXT_HINT,
        ).pack(anchor="w", pady=(2, 0))

        form = tk.Frame(shell, bg=CARD)
        form.pack(fill="x", padx=24)

        ntid_entry = self._field_box(form, "NTID", default="")
        password_entry = self._field_box(form, "Password", default="", show="*")
        ntid_entry.focus_set()

        show_password = tk.BooleanVar(value=False)

        def toggle_password():
            password_entry.config(show="" if show_password.get() else "*")

        tk.Checkbutton(
            form,
            text="Show password",
            variable=show_password,
            command=toggle_password,
            bg=CARD,
            fg=TEXT_SEC,
            activebackground=CARD,
            activeforeground=TEXT_PRI,
            selectcolor=CARD,
            font=self.font_small,
            relief="flat",
            bd=0,
            highlightthickness=0,
            anchor="w",
        ).pack(anchor="w", pady=(8, 0))

        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(18, 18))

        def ok():
            ntid = ntid_entry.get().strip()
            password = password_entry.get()
            if not ntid:
                self._styled_alert("Missing NTID", "Please enter your NTID.", "warning", parent=win)
                return
            if not password:
                self._styled_alert("Missing Password", "Please enter your password.", "warning", parent=win)
                return
            result["ntid"] = ntid
            result["password"] = password
            close_popup()

        self._btn(
            row,
            "Cancel",
            CARD_SOFT,
            close_popup,
            fg=TEXT_SEC,
            border=True,
            padx=18,
            pady=8,
            width=100,
        ).pack(side="right", padx=(8, 0))
        self._btn(
            row,
            "Login",
            ACCENT,
            ok,
            fg="white",
            padx=18,
            pady=8,
            width=100,
        ).pack(side="right")

        win.bind("<Return>", lambda event: ok())
        password_entry.bind("<Return>", lambda event: ok())

        win.wait_window()
        if not result["ntid"]:
            return None
        return result["ntid"], result["password"]

    def _finish_admin_login(self, ntid: str, title: str, message: str):
        """Apply the existing admin UI state after an authenticated login."""
        self.current_user = ntid
        self._enable_admin_permissions()
        self._update_account_button()
        self._styled_alert(title, message, "success")

        try:
            grabbed = self.root.grab_current()
            if grabbed is not None:
                grabbed.grab_release()
        except Exception:
            pass

        self.root.after(100, lambda: (
            self.root.lift(),
            self.root.focus_force(),
            self._enable_admin_permissions(),
        ))

    # --------------------------------------------------------
    # Login
    # --------------------------------------------------------
    def _show_account_menu(self):
        # Close existing account menu first if already open
        existing_menu = getattr(self, "_account_menu_win", None)

        if existing_menu is not None:
            try:
                if existing_menu.winfo_exists():
                    self._safe_popup_close(existing_menu)
                    return
            except:
                pass

        win = tk.Toplevel(self.root)
        self._account_menu_win = win

        win.overrideredirect(True)
        win.configure(bg="#FFFFFF")
        win.attributes("-topmost", True)

        self.root.update_idletasks()
        self.account_btn.update_idletasks()

        x = self.account_btn.winfo_rootx()
        y = self.account_btn.winfo_rooty() + self.account_btn.winfo_height() + 6

        width = 210
        height = 120
        win.geometry(f"{width}x{height}+{x}+{y}")

        card = tk.Frame(
            win,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#E5E7EB"
        )
        card.pack(fill="both", expand=True)

        tk.Label(
            card,
            text=f"Signed in as {self.current_user}",
            bg="#FFFFFF",
            fg="#64748B",
            font=("DejaVu Sans", 9)
        ).pack(anchor="w", padx=14, pady=(12, 6))

        switch_btn = tk.Button(
            card,
            text="Switch account",
            bg="#FFFFFF",
            fg="#111827",
            activebackground="#F1F5F9",
            activeforeground="#111827",
            relief="flat",
            bd=0,
            anchor="w",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("DejaVu Sans", 10),
            command=lambda: self._switch_account_from_menu(win)
        )
        switch_btn.pack(fill="x")

        logout_btn = tk.Button(
            card,
            text="Logout",
            bg="#FFFFFF",
            fg="#EF4444",
            activebackground="#FEF2F2",
            activeforeground="#DC2626",
            relief="flat",
            bd=0,
            anchor="w",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("DejaVu Sans", 10, "bold"),
            command=lambda: self._logout_from_menu(win)
        )
        logout_btn.pack(fill="x")

        def close_if_focus_lost(event=None):
            try:
                if win.focus_displayof() is None:
                    self._safe_popup_close(win)
            except:
                pass

        win.bind("<FocusOut>", close_if_focus_lost)
        win.bind("<Escape>", lambda e: self._safe_popup_close(win))

        win.lift()
        win.focus_force()


    def _switch_account_from_menu(self, menu_win):
        self._safe_popup_close(menu_win)

        def do_switch():
            self._logout(silent=True)
            self.root.after(150, self._login)

        self.root.after(150, do_switch)


    def _logout_from_menu(self, menu_win):
        self._safe_popup_close(menu_win)
        self.root.after(100, self._logout)


    def _update_account_button(self):
        if hasattr(self, "account_btn"):
            if self.current_user:
                self.account_btn.config(
                    text=f"  {self.current_user} ▾",
                    command=self._show_account_menu,
                    bg=CARD_SOFT,
                    fg=TEXT_PRI,
                    activebackground="#EFF6FF"
                )
            else:
                self.account_btn.config(
                    text="  Login",
                    command=self._login,
                    bg=CARD_SOFT,
                    fg=TEXT_PRI,
                    activebackground="#EFF6FF"
                )
        if hasattr(self, "user_label"):
            self.user_label.config(text="")

    

    def _center_popup(self, win, width, height):
        win.update_idletasks()

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()

        x = (screen_w - width) // 2
        y = (screen_h - height) // 2

        win.geometry(f"{width}x{height}+{x}+{y}")

    def _login(self):
        credentials = self._ask_login_credentials_popup("Login")
        if not credentials:
            return

        entered_ntid, password = credentials
        ntid = entered_ntid.strip().lower()
        self.log(f"Login attempt: {ntid}", "info")

        # Requested developer-team local administrator. This is intentionally
        # checked before AD so it remains available during an AD outage.
        if ntid == DEVELOPER_ADMIN_NTID and password == DEVELOPER_ADMIN_PASSWORD:
            self.log("Developer administrator login granted.", "success")
            self._finish_admin_login(
                DEVELOPER_ADMIN_NTID,
                "Developer Admin",
                "Developer administrator access granted.",
            )
            return

        validated, message = self._validate_ntid_password_in_ad(ntid, password)
        if not validated:
            self._styled_alert("Login Failed", message, "error")
            self.log(f"Login failed for '{ntid}': {message}", "error")
            return

        # Preserve the original first-AD-login-becomes-admin behavior.
        if not self.admin_list:
            self._save_admin(ntid)
            self._finish_admin_login(
                ntid,
                "Admin Registered",
                f"{ntid} is now the first admin.",
            )
            return

        admin_ids = {str(item).strip().lower() for item in self.admin_list}
        if ntid in admin_ids:
            self._finish_admin_login(ntid, "Login Success", "Admin access granted.")
            return

        self._styled_alert("Access Denied", "You are not an admin.", "error")
        self.log(f"Login denied: '{ntid}' is not in the admin list.", "error")

    # --------------------------------------------------------
    # Logout
    # --------------------------------------------------------
    # Logout
    # --------------------------------------------------------
    def _logout(self, silent=False):
        if not self.current_user:
            if not silent:
                self._styled_alert("Logout", "No user is currently logged in.", "info")
            return

        user = self.current_user
        self.current_user = None
        self._set_default_permissions()
        self.log(f"User '{user}' logged out.", "info")
        self._update_account_button()
        if not silent:
            self._styled_alert("Logout", "Logged out successfully.", "success")


    # --------------------------------------------------------
    # HTTP API server for Windows integration
    # --------------------------------------------------------
    def _api_ok(self, message="", **kwargs):
        if jsonify is None:
            return None
    
        jsonify_fn = cast(Any, jsonify)
    
        data = {
            "ok": True,
            "message": message
        }
        data.update(kwargs)
    
        return jsonify_fn(data)
    
    
    def _api_fail(self, message="", status=400, **kwargs):
        if jsonify is None:
            return None
    
        jsonify_fn = cast(Any, jsonify)
    
        data = {
            "ok": False,
            "message": message
        }
        data.update(kwargs)
    
        return jsonify_fn(data), status

    def _api_update_latest_frame(self, frame, preview_frame=None):
        """Store raw frame for registration and preview frame for /video-feed."""
        try:
            if hasattr(self, "face_service"):
                with self.face_service._api_frame_lock:
                    self.face_service._api_latest_frame = frame.copy()
                    self.face_service._api_preview_frame = (preview_frame if preview_frame is not None else frame).copy()
        except Exception as e:
            try:
                self.log(f"API latest frame update failed: {e}", "error")
            except:
                pass

    def _api_get_users_list(self):
        trained_users = set()
        if os.path.exists(ENCODINGS_FILE):
            try:
                with open(ENCODINGS_FILE, "rb") as f:
                    data = pickle.load(f)
                trained_users = {str(n).strip().lower() for n in data.get("names", [])}
            except Exception:
                trained_users = set()

        users = []
        if not os.path.exists(DATASET_DIR):
            return users

        for user_id in sorted(os.listdir(DATASET_DIR)):
            user_path = os.path.join(DATASET_DIR, user_id)
            if not os.path.isdir(user_path):
                continue

            photos = [
                f for f in os.listdir(user_path)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ]

            users.append({
                "id": user_id,
                "photos": len(photos),
                "trained": user_id.strip().lower() in trained_users
            })

        return users

    def _api_read_recognition_result(self):
        if not os.path.exists(RECOGNITION_RESULT_FILE):
            return {
                "detected": False,
                "user_id": None,
                "confidence": 0,
                "timestamp": None
            }

        try:
            with open(RECOGNITION_RESULT_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            return {
                "detected": False,
                "user_id": None,
                "confidence": 0,
                "timestamp": None,
                "error": str(e)
            }

    def _api_remove_user_from_encodings(self, user_id):
        if not os.path.exists(ENCODINGS_FILE):
            return 0

        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)

        old_encodings = data.get("encodings", [])
        old_names = data.get("names", [])
        old_trained_files = data.get("trained_files", [])

        target = str(user_id).strip().lower()
        new_encodings = []
        new_names = []
        removed = 0

        for enc, name in zip(old_encodings, old_names):
            if str(name).strip().lower() == target:
                removed += 1
            else:
                new_encodings.append(enc)
                new_names.append(name)

        new_trained_files = [
            tf for tf in old_trained_files
            if not str(tf).replace("\\", "/").lower().startswith(target + "/")
        ]

        data["encodings"] = new_encodings
        data["names"] = new_names
        data["trained_files"] = new_trained_files

        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump(data, f)

        return removed

    def _api_start_recognition_request(self):
        """Called by API thread. Schedule the actual GUI recognition starter on Tk main thread."""
        if self._recognition_running:
            return True, "Recognition already running."
        if self._capture_running or getattr(self, "_api_training_running", False):
            return False, "Another process is running. Please stop it first."

        self.root.after(0, self.start_recognition_thread)
        return True, "Recognition start requested."

    def _api_stop_recognition_request(self):
        """Stop only recognition without cancelling post-training recovery."""
        try:
            self.stop_flag = True
            try:
                if hasattr(self, "face_service") and self.face_service is not None:
                    self.face_service._stop_recognition_event.set()
            except Exception:
                pass

            self.root.after(0, lambda: self.log("Recognition stop requested from API.", "warn"))
            return True, "Recognition stop requested.", {}
        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Recognition stop failed: {e}", {}

    def _api_stop_capture_request(self):
        """Stop only capture without changing the training recovery decision."""
        try:
            self._stop_capture_event.set()
            try:
                if hasattr(self, "face_service") and self.face_service is not None:
                    self.face_service._stop_capture_event.set()
            except Exception:
                pass

            self.root.after(0, lambda: self.log("Capture stop requested from API.", "warn"))
            return True, "Capture stop requested.", {}
        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Capture stop failed: {e}", {}

    def _api_stop_request(self):
        try:
            # Stop recognition loop immediately
            self.stop_flag = True

            # Stop capture loop if capture is running
            try:
                self._stop_capture_event.set()
            except Exception:
                pass

            # If face_service has its own stop events, stop them too
            try:
                if hasattr(self, "face_service"):
                    self.face_service._stop_recognition_event.set()
                    self.face_service._stop_capture_event.set()
            except Exception:
                pass

            # Run the normal Pi GUI stop logic on Tkinter main thread
            try:
                self.root.after(0, self.stop_all)
            except Exception:
                pass

            self.root.after(0, lambda: self.log("Stop requested from API.", "warn"))

            return True, "Stop requested.", {}

        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Stop failed: {e}", {}

    def _api_capture_user_request(self, user_id, mode="add"):
        user_id = str(user_id).strip().lower()
        mode = str(mode).strip().lower()

        if not user_id:
            return False, "Missing user_id.", {}

        if mode not in ("add", "replace"):
            mode = "add"

        if getattr(self, "_api_training_running", False):
            return False, "Training is running. Please wait until training is completed.", {}

        if self._capture_running:
            return False, "Capture is already running.", {}

        # --------------------------------------------------------
        # Stop recognition first if it is running
        # --------------------------------------------------------
        if self._recognition_running:
            self.root.after(0, lambda: self.log(
                "Recognition is running. Stopping recognition before API capture...",
                "warn"
            ))

            self.stop_flag = True

            try:
                if hasattr(self, "face_service"):
                    self.face_service._stop_recognition_event.set()
            except Exception:
                pass

            try:
                self.root.after(0, self.stop_all)
            except Exception:
                pass

            # Wait until recognition thread really exits
            wait_start = time.time()

            while self._recognition_running and time.time() - wait_start < 10:
                time.sleep(0.1)

            if self._recognition_running:
                return False, "Camera is still busy. Recognition did not stop in time.", {}

            # Give PiCamera2 time to release /dev/video0
            time.sleep(1.2)

        # --------------------------------------------------------
        # Start API capture
        # --------------------------------------------------------
        self._capture_running = True
        self._stop_capture_event.clear()
        self._capture_event.clear()
        self.stop_flag = False

        self.root.after(0, lambda: self._set_camera_status(True))
        self.root.after(0, lambda: self.log(
            f"API capture started for {user_id}.",
            "info"
        ))

        def frame_cb(frame):
            self._api_update_latest_frame(frame)

            try:
                self.root.after(0, lambda f=frame: self._show_frame(f))
            except Exception:
                pass

            if self._stop_capture_event.is_set():
                return "stop"
            if self._capture_event.is_set():
                self._capture_event.clear()
                return "capture"
            return None

        def run_capture():
            try:
                captured, total = capture_faces(
                    user_id,
                    mode=mode,
                    save_base=DATASET_DIR,
                    frame_callback=frame_cb,
                    stop_flag=lambda: self._stop_capture_event.is_set(),
                    auto_capture=False
                )

                self.root.after(0, lambda: self.log(
                    f"API capture complete for {user_id}. Captured {captured}, total {total}.",
                    "success"
                ))

            except Exception as e:
                self._api_last_error = str(e)
                self.root.after(0, lambda e=e: self.log(
                    f"API capture error: {e}",
                    "error"
                ))

            finally:
                self._capture_running = False
                self._stop_capture_event.clear()

                self.root.after(0, lambda: self._set_camera_status(False))

                try:
                    self.root.after(0, self._show_camera_stopped_prompt)
                except Exception:
                    pass

                self.root.after(0, self.refresh_dataset)

                try:
                    if self.current_user:
                        self.root.after(0, self._enable_admin_permissions)
                    else:
                        self.root.after(0, self._set_default_permissions)
                except Exception:
                    pass

        Thread(target=run_capture, daemon=True).start()

        return True, "Registration started. One valid face sample will be captured automatically.", {
            "user_id": user_id,
            "mode": mode
        }

    def _set_api_training_progress(self, state):
        """Store structured train.py progress for /status and local Pi logs."""
        if not isinstance(state, dict):
            return

        try:
            self._api_training_processed = max(0, int(state.get("processed", 0) or 0))
            self._api_training_total = max(0, int(state.get("total", 0) or 0))
            self._api_training_percent = max(0, min(100, int(state.get("percent", 0) or 0)))
            self._api_training_phase = str(state.get("phase", "training") or "training")
            self._api_training_message = str(state.get("message", "") or "")
            self._api_training_dataset_total = max(0, int(state.get("dataset_total", 0) or 0))
            self._api_training_already_trained = max(0, int(state.get("already_trained", 0) or 0))
            self._api_training_valid_images = max(0, int(state.get("valid_images", 0) or 0))
            self._api_training_skipped_images = max(0, int(state.get("skipped_images", 0) or 0))
        except Exception:
            return

    def _api_train_request(self):
        """Start model training without closing an active recognition camera.

        Training reads stored dataset images; it does not access Picamera2.  The
        camera can therefore keep recognizing existing users while the trained
        encoding file is rebuilt.  recog.py hot-reloads the completed file once
        train.py replaces it atomically.
        """
        if self._capture_running or getattr(self, "_api_training_running", False):
            return False, "Capture or training is already running. Please wait for it to finish.", {}

        training_id = f"train-{int(time.time() * 1000)}"
        self._resume_recognition_after_training = False
        self._api_last_training_error = None
        self._api_last_training_new_faces = 0
        self._api_training_dataset_total = 0
        self._api_training_already_trained = 0
        self._api_training_valid_images = 0
        self._api_training_skipped_images = 0
        self._api_last_training_id = training_id
        self._api_training_state = "running"
        self._api_training_running = True
        self._set_api_training_progress({
            "processed": 0,
            "total": 0,
            "percent": 0,
            "phase": "preparing",
            "message": "Preparing dataset for training...",
        })
        result = {"done": False, "new_faces": 0, "error": None, "training_id": training_id}
        self.root.after(0, lambda: self.log(
            "API training started. Recognition remains active while the model is rebuilt.",
            "info",
        ))

        def update_progress(state):
            safe_state = dict(state) if isinstance(state, dict) else {}

            def apply():
                self._set_api_training_progress(safe_state)
                message = str(safe_state.get("message", "") or "")
                if message:
                    self.log(message, "info")

            self.root.after(0, apply)

        def run_train():
            failed = False
            try:
                count = train_model(
                    progress_callback=lambda m: self.root.after(0, lambda m=m: self.log(m, "info")),
                    progress_state_callback=update_progress,
                )
                result["new_faces"] = count
                self._api_last_training_new_faces = int(count or 0)
                self.root.after(0, lambda: self.log(
                    f"API training complete. {count} new face(s) added. Recognition stayed active.",
                    "success",
                ))
            except Exception as e:
                failed = True
                result["error"] = str(e)
                self._api_last_training_error = str(e)
                self._api_last_error = str(e)
                update_progress({
                    "processed": self._api_training_processed,
                    "total": self._api_training_total,
                    "percent": self._api_training_percent,
                    "phase": "failed",
                    "message": f"Training failed: {e}",
                })
                self.root.after(0, lambda e=e: self.log(f"API training error: {e}", "error"))
            finally:
                result["done"] = True
                self._api_training_running = False
                self._api_training_state = "failed" if failed else "completed"
                self._api_last_training_finished_at = time.time()
                self.root.after(0, self.refresh_dataset)

        Thread(target=run_train, daemon=True).start()
        return True, "Training started. Recognition remains active.", {
            "training_id": training_id,
            "training_state": "running",
        }

    def _api_delete_user_request(self, user_id):
        user_id = str(user_id).strip().lower()
        if not user_id:
            return False, "Missing user_id.", {}
        if self._recognition_running or self._capture_running or getattr(self, "_api_training_running", False):
            return False, "Another process is running. Please stop it first.", {}

        dataset_path = os.path.join(DATASET_DIR, user_id)
        removed_dataset = False
        removed_encodings = 0

        try:
            if os.path.exists(dataset_path):
                shutil.rmtree(dataset_path)
                removed_dataset = True

            removed_encodings = self._api_remove_user_from_encodings(user_id)
            expired_backups_deleted = self._cleanup_expired_delete_backups_now()
            self.root.after(0, self.refresh_dataset)
            self.root.after(0, lambda: self.log(f"API deleted user {user_id}.", "warn"))
            return True, "User deleted.", {
                "user_id": user_id,
                "dataset_removed": removed_dataset,
                "encodings_removed": removed_encodings,
                "expired_backups_deleted": expired_backups_deleted,
            }
        except Exception as e:
            self._api_last_error = str(e)
            return False, f"Delete failed: {e}", {}



    # --------------------------------------------------------
    # Capture
    # --------------------------------------------------------
    def start_capture(self):
        """Start local Pi capture using the same safe workflow as SAS capture.

        Recognition is stopped first because PiCamera2 cannot be shared.  After
        capture finishes (or is stopped from the Capture workflow), recognition
        is automatically restored for workstation unlock.
        """
        if self._capture_running or getattr(self, "_api_training_running", False):
            self.log("Another process is already running.", "warn")
            return

        ntid = self.name_entry.get().strip()
        display_name = ""
        try:
            display_name = self.display_name_entry.get().strip()
        except Exception:
            display_name = ""
        if not ntid:
            messagebox.showerror("Error", "Please enter NTID.")
            return
        if not display_name:
            messagebox.showerror("Error", "Please enter name.")
            return

        self.log(f"Validating NTID '{ntid}' with AD...", "info")
        if not self._validate_ntid_in_ad(ntid):
            messagebox.showerror("Invalid NTID", f"'{ntid}' is not a valid NTID.")
            self.log(f"NTID '{ntid}' validation failed.", "error")
            return

        self.log(f"NTID '{ntid}' validated successfully.", "success")

        service_recognition_running = False
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                service_recognition_running = bool(getattr(self.face_service, "_recognition_running", False))
        except Exception:
            pass

        # Record the intended final state before stopping recognition.  The
        # delayed retry below keeps this flag through the camera-release gap.
        self._resume_recognition_after_capture = True

        if self._recognition_running or service_recognition_running:
            self._stop_recognition_before_capture()
            return

        name = ntid
        save_base = self.pc_save_path if self.pc_save_path else DATASET_DIR

        self._capture_running = True
        self._set_camera_status(True)
        self._capture_event.clear()
        self._stop_capture_event.clear()
        # Keep the Flask FaceService status accurate when capture is started
        # from the Pi screen rather than from SAS.
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                self.face_service._capture_running = True
                self.face_service._stop_capture_event.clear()
        except Exception:
            pass

        self.capture_btn.config(state="disabled")
        self.delete_btn.config(state="disabled")
        self.train_btn.config(state="disabled")
        self.recog_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.auto_capture_enabled = False
        self.log(f"Registering '{display_name}' ({name})...", "info")

        def frame_cb(frame):
            self._api_update_latest_frame(frame)
            self._show_frame(frame)
            if self._stop_capture_event.is_set():
                return "stop"
            return None

        def thread():
            try:
                captured, total = capture_faces(
                    name, mode="add",
                    save_base=save_base,
                    frame_callback=frame_cb,
                    stop_flag=lambda: self._stop_capture_event.is_set(),
                    auto_capture=True,
                    display_name=display_name,
                    max_captures=1
                )
                if captured:
                    self.log(f"Registered {display_name} ({name}). Total sample(s): {total}", "success")
                else:
                    self.log("No valid face sample was registered.", "warn")
                self.root.after(0, self.refresh_dataset)
            except Exception as e:
                self.log(f"Capture error: {e}", "error")
            finally:
                def restore_after_capture():
                    self._capture_running = False
                    self._capture_event.clear()
                    self._stop_capture_event.clear()
                    try:
                        if hasattr(self, "face_service") and self.face_service is not None:
                            self.face_service._capture_running = False
                            self.face_service._stop_capture_event.clear()
                    except Exception:
                        pass
                    self.capture_btn.config(
                        text="▣\nCapture",
                        bg=ACCENT,
                        fg="white",
                        activebackground=ACCENT_HOV,
                        activeforeground="white",
                        command=self.start_capture
                    )
                    self._set_camera_status(False)
                    if self.current_user:
                        self.delete_btn.config(state="normal")
                        self.capture_btn.config(state="normal")
                    else:
                        self.delete_btn.config(state="disabled")
                        self.capture_btn.config(state="disabled")
                    self.recog_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    self._queue_recognition_resume_after_capture()

                self.root.after(0, restore_after_capture)

        Thread(target=thread, daemon=True).start()

    def trigger_capture(self):
        self._capture_event.set()

    def _mount_smb_path(self, ntid, pwd, unc, parent=None, status_lbl=None):
        import subprocess

        if not ntid or not pwd or not unc:
            self._styled_alert(
                "Missing Information",
                "Please fill in NTID, password and server path.",
                "warning",
                parent=parent
            )
            return None

        if status_lbl:
            status_lbl.config(text="Connecting to server...", fg=WARNING)
        
            try:
                status_lbl.update_idletasks()
            except:
                pass
            
        if parent is not None:
            try:
                parent.update()
            except:
                pass

        linux_path = unc.replace("\\", "/")
        mount_point = "/mnt/pcshare"
        os.makedirs(mount_point, exist_ok=True)

        try:
            subprocess.run(
                ["sudo", "umount", "-l", mount_point],
                capture_output=True,
                text=True,
                timeout=10
            )
        except Exception:
            pass

        cmd = [
            "sudo", "mount", "-t", "cifs",
            linux_path, mount_point,
            "-o", f"username={ntid},password={pwd},domain=JABIL,vers=3.0,uid=1000,gid=1000"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
        except Exception as e:
            if status_lbl:
                status_lbl.config(text="Mount error.", fg=DANGER)
            self._styled_alert(
                "Mount Error",
                f"Failed to run mount command:\n{e}",
                "error",
                parent=parent
            )
            return None

        if result.returncode != 0:
            err_msg = result.stderr.strip() if result.stderr.strip() else "Unknown error."

            if status_lbl:
                status_lbl.config(text="Connection failed.", fg=DANGER)

            self._styled_alert(
                "Connection Failed",
                f"Could not connect to server.\n\nError:\n{err_msg}\n\nPlease check your NTID, password and server path.",
                "error",
                parent=parent
            )
            return None

        try:
            ls_result = subprocess.run(
                ["ls", mount_point],
                capture_output=True,
                text=True,
                timeout=10
            )

            if ls_result.returncode != 0:
                if status_lbl:
                    status_lbl.config(text="Access denied.", fg=DANGER)

                self._styled_alert(
                    "Access Denied",
                    f"Mounted but cannot read folder.\n\nError:\n{ls_result.stderr.strip()}",
                    "error",
                    parent=parent
                )
                return None

        except Exception as e:
            if status_lbl:
                status_lbl.config(text="Verification error.", fg=DANGER)

            self._styled_alert(
                "Verification Error",
                f"Could not verify access:\n{e}",
                "error",
                parent=parent
            )
            return None

        if status_lbl:
            status_lbl.config(text="Connected successfully.", fg=SUCCESS)

        return mount_point



    # --------------------------------------------------------
    # Bluetooth-like SFTP Send / Receive Helpers
    # --------------------------------------------------------
    def _ensure_transfer_folders(self):
        os.makedirs(PENDING_DIR, exist_ok=True)
        os.makedirs(ACCEPTED_DIR, exist_ok=True)
        os.makedirs(TEMP_EXPORT_DIR, exist_ok=True)
        os.makedirs(TEMP_IMPORT_DIR, exist_ok=True)
        self._clear_temp_export_packages()


    def _clear_temp_export_packages(self):
        """Remove old temporary export ZIPs so Pi storage is not wasted."""
        try:
            if not os.path.exists(TEMP_EXPORT_DIR):
                return
            for name in os.listdir(TEMP_EXPORT_DIR):
                if name.lower().endswith(".zip"):
                    try:
                        os.remove(os.path.join(TEMP_EXPORT_DIR, name))
                    except Exception:
                        pass
        except Exception:
            pass



    def _device_name(self):
        try:
            return socket.gethostname()
        except:
            return "UnknownPi"


    def _create_face_data_zip(self, zip_path):
        if not os.path.exists(ENCODINGS_FILE):
            raise FileNotFoundError("encodings.pickle was not found.")

        if not os.path.exists(DATASET_DIR):
            raise FileNotFoundError("dataset folder was not found.")

        manifest = {
            "type": "face_data_export",
            "source_device": self._device_name(),
            "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "contains": [
                ENCODINGS_FILE,
                DATASET_DIR
            ]
        }

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(ENCODINGS_FILE, ENCODINGS_FILE)

            for root, dirs, files in os.walk(DATASET_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, ".")
                    z.write(full_path, arcname)

            z.writestr("manifest.json", json.dumps(manifest, indent=4))

        return zip_path


    def _read_zip_manifest(self, zip_path):
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                if "manifest.json" not in z.namelist():
                    return {
                        "type": "face_data_export",
                        "source_device": "Unknown Device",
                        "export_time": "Unknown Time"
                    }

                with z.open("manifest.json") as f:
                    return json.loads(f.read().decode("utf-8"))

        except:
            return {
                "type": "unknown",
                "source_device": "Unknown Device",
                "export_time": "Unknown Time"
            }


    def _sftp_connect(self, host, port, username, password, parent=None, status_lbl=None):
        if not host or not port or not username or not password:
            self._styled_alert(
                "Missing Information",
                "Please fill in Host/IP, Port, Username and Password.",
                "warning",
                parent=parent
            )
            return None, None

        try:
            port = int(port)
        except:
            self._styled_alert(
                "Invalid Port",
                "Port must be a number. Default SFTP port is 22.",
                "warning",
                parent=parent
            )
            return None, None

        if status_lbl:
            status_lbl.config(text="Connecting to SFTP server...", fg=WARNING)
            status_lbl.update_idletasks()

        try:
            transport = paramiko.Transport((host, port))
            transport.connect(username=username, password=password)

            sftp = paramiko.SFTPClient.from_transport(transport)

            if status_lbl:
                status_lbl.config(text="SFTP connected successfully.", fg=SUCCESS)

            return transport, sftp

        except Exception as e:
            if status_lbl:
                status_lbl.config(text="SFTP connection failed.", fg=DANGER)

            self._styled_alert(
                "SFTP Connection Failed",
                f"Could not connect to SFTP server.\n\nError:\n{e}",
                "error",
                parent=parent
            )
            return None, None


    def _sftp_ensure_remote_dir(self, sftp, remote_dir):
        remote_dir = remote_dir.replace("\\", "/").rstrip("/")

        if not remote_dir:
            raise ValueError("Remote folder is empty.")

        parts = remote_dir.split("/")
        current = ""

        # Absolute path starts with /
        if remote_dir.startswith("/"):
            current = "/"

        for part in parts:
            if not part:
                continue

            if current == "/":
                current = "/" + part
            elif current:
                current = current + "/" + part
            else:
                current = part

            try:
                sftp.stat(current)
            except IOError:
                sftp.mkdir(current)

    def export_face_data(self):
        if not os.path.exists(ENCODINGS_FILE):
            self._styled_alert(
                "Export Failed",
                "encodings.pickle was not found. Please train users first.",
                "error"
            )
            return

        if not os.path.exists(DATASET_DIR):
            self._styled_alert(
                "Export Failed",
                "dataset folder was not found.",
                "error"
            )
            return

        win, shell = self._modern_popup_shell("Export Face Data", 520, 430)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))

        CircleBadge(
            header,
            text="⇧",
            size=40,
            bg_color="#EFF6FF",
            fg=ACCENT,
            font=("DejaVu Sans", 15, "bold")
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box,
            text="Export Face Data",
            font=("DejaVu Sans", 15, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Export registered users, InsightFace embeddings and photos to server path.",
            font=self.font_small,
            bg=CARD,
            fg=TEXT_HINT
        ).pack(anchor="w", pady=(2, 0))

        form = tk.Frame(shell, bg=CARD)
        form.pack(fill="x", padx=24, pady=(6, 0))

        ntid_entry = self._field_box(form, "NTID / Username")
        pwd_entry = self._field_box(form, "Password", show="*")
        path_entry = self._field_box(form, "Server Path")

        settings = self._load_settings()
        if settings.get("username"):
            ntid_entry.insert(0, settings["username"])

        if settings.get("password"):
            try:
                f = Fernet(FERNET_KEY)
                pwd_entry.insert(0, f.decrypt(settings["password"].encode()).decode())
            except:
                pwd_entry.insert(0, settings["password"])

        if settings.get("pc_save_path"):
            path_entry.insert(0, settings["pc_save_path"])

        status_lbl = tk.Label(
            shell,
            text="",
            font=self.font_body,
            bg=CARD,
            fg=TEXT_SEC
        )
        status_lbl.pack(anchor="w", padx=24, pady=(8, 0))

        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(16, 18))

        def close_popup():
            self._safe_popup_close(win)

        def do_export():
            ntid = ntid_entry.get().strip()
            pwd = pwd_entry.get().strip()
            unc = path_entry.get().strip()

            mount_point = self._mount_smb_path(
                ntid,
                pwd,
                unc,
                parent=win,
                status_lbl=status_lbl
            )

            if not mount_point:
                return

            try:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                zip_name = f"face_data_{timestamp}.zip"
                zip_path = os.path.join(mount_point, zip_name)

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                    z.write(ENCODINGS_FILE, ENCODINGS_FILE)

                    for root, dirs, files in os.walk(DATASET_DIR):
                        for file in files:
                            full_path = os.path.join(root, file)
                            arcname = os.path.relpath(full_path, ".")
                            z.write(full_path, arcname)

                self.log(f"Face data exported to server: {zip_path}", "success")

                self._styled_alert(
                    "Export Complete",
                    f"Face data exported successfully.\n\nFile:\n{zip_name}",
                    "success",
                    parent=win
                )

                close_popup()

            except Exception as e:
                self.log(f"Export failed: {e}", "error")
                self._styled_alert(
                    "Export Failed",
                    f"Failed to export face data:\n{e}",
                    "error",
                    parent=win
                )

        self._btn(
            row,
            "Cancel",
            CARD_SOFT,
            close_popup,
            fg=TEXT_SEC,
            border=True,
            padx=18,
            pady=8,
            width=110
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Export",
            ACCENT,
            do_export,
            fg="white",
            padx=18,
            pady=8,
            width=120
        ).pack(side="right")


    def _resolve_server_credentials(self, username=None, password=None, pc_save_path=None):
        """Use API-provided credentials first, otherwise fall back to settings.json."""
        settings = self._load_settings()

        ntid = (username or settings.get("username", "") or "").strip()
        unc = (pc_save_path or settings.get("pc_save_path", "") or "").strip()

        if password is not None:
            pwd = str(password)
        else:
            pwd = ""
            if settings.get("password"):
                try:
                    f = Fernet(FERNET_KEY)
                    pwd = f.decrypt(settings["password"].encode()).decode()
                except Exception:
                    pwd = settings.get("password", "")

        return ntid, pwd, unc

    def export_face_data_to_folder(self, target_folder=None, username=None, password=None, pc_save_path=None):
        """API helper: export encodings.pickle + dataset to configured server path."""
        try:
            ntid, pwd, unc = self._resolve_server_credentials(username, password, pc_save_path)

            mount_point = target_folder or self._mount_smb_path(ntid, pwd, unc, parent=None, status_lbl=None)
            if not mount_point:
                return False, "Unable to connect to server path. Please check NTID, password, and server path.", {}

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_name = f"face_data_{timestamp}.zip"
            zip_path = os.path.join(mount_point, zip_name)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                if os.path.exists(ENCODINGS_FILE):
                    z.write(ENCODINGS_FILE, ENCODINGS_FILE)

                for root, dirs, files in os.walk(DATASET_DIR):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, ".")
                        z.write(full_path, arcname)

            self.log(f"Face data exported to server: {zip_path}", "success")
            return True, "Face data exported successfully.", {
                "filename": zip_name,
                "zip_path": zip_path
            }

        except Exception as e:
            self.log(f"API export failed: {e}", "error")
            return False, f"Export failed: {e}", {}



    def list_server_face_data_zips(self, username=None, password=None, pc_save_path=None):
        """API helper: connect to configured server path and return valid SAS export ZIP files."""
        try:
            ntid, pwd, unc = self._resolve_server_credentials(username, password, pc_save_path)

            mount_point = self._mount_smb_path(ntid, pwd, unc, parent=None, status_lbl=None)
            if not mount_point:
                return False, "Unable to connect to server path. Please check NTID, password, and server path.", {}

            files = []
            for name in os.listdir(mount_point):
                lower = name.lower()

                # Only load the export format created by this system.
                if not (
                    lower.endswith(".zip")
                    and (
                        lower.startswith("face_data_")
                        or lower.startswith("face_data_backup_")
                    )
                    and not lower.startswith("backup_before_import_")
                ):
                    continue

                path = os.path.join(mount_point, name)

                # Validate InsightFace export format quickly.
                try:
                    with zipfile.ZipFile(path, "r") as z:
                        names = {item.replace("\\", "/") for item in z.namelist()}
                        if "face_data/users.json" not in names or "face_data/embeddings.npz" not in names:
                            continue
                except Exception:
                    continue

                try:
                    stat = os.stat(path)
                    size = stat.st_size
                    modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                except Exception:
                    size = 0
                    modified = ""

                files.append({
                    "name": name,
                    "path": path,
                    "size": size,
                    "modified": modified
                })

            files.sort(key=lambda x: x.get("modified", ""), reverse=True)
            return True, f"Found {len(files)} valid face data ZIP file(s).", {
                "files": files,
                "mount_point": mount_point
            }

        except Exception as e:
            self.log(f"API ZIP list failed: {e}", "error")
            return False, f"Failed to list ZIP files: {e}", {}



    def import_face_data_from_zip(self, zip_path):
        """API helper: import selected ZIP backup in add-new-only mode.

        Existing users are updated only with new images/encodings.
        Duplicate images/encodings are ignored.
        """
        try:
            if not zip_path or not os.path.exists(zip_path):
                return False, "Selected ZIP file does not exist.", {}

            before_ids = self._get_dataset_ids()

            backup_ids = set()
            try:
                with zipfile.ZipFile(zip_path, "r") as z:
                    if ENCODINGS_FILE in z.namelist():
                        with z.open(ENCODINGS_FILE) as f:
                            backup_data = pickle.load(f)
                        backup_ids = {
                            str(n).strip().lower()
                            for n in backup_data.get("names", [])
                        }
            except Exception:
                backup_ids = set()

            self._import_face_data_zip(zip_path, parent=None)

            after_ids = self._get_dataset_ids()
            new_ids = sorted(after_ids - before_ids)
            updated_ids = sorted(backup_ids & before_ids)
            affected_ids = sorted((backup_ids & after_ids) | set(new_ids))

            message = (
                f"Face data import completed. New users: {len(new_ids)}, "
                f"updated users checked: {len(updated_ids)}. Duplicate data ignored."
            )

            return True, message, {
                "imported_ids": len(affected_ids),
                "imported_users": affected_ids,
                "added_ids": affected_ids,
                "new_users": new_ids,
                "updated_users": updated_ids,
                "new_users_count": len(new_ids),
                "updated_users_count": len(updated_ids),
                "skipped_users_count": 0,
                "skipped_users_preview": [],
                "import_mode": "add_new_only",
                "zip_path": zip_path
            }

        except Exception as e:
            self.log(f"API import failed: {e}", "error")
            return False, f"Import failed: {e}", {}


    def send_face_data_to_pi(self):
        """Open the multi-Pi SFTP transfer popup.

        The transfer feature is imported only when this button is used.  A missing
        or faulty optional transfer module therefore cannot prevent the main Pi
        GUI, Settings popup, camera, or workstation kiosk from starting.
        """
        try:
            from multi_sftp_transfer import open_multi_sftp_transfer
        except Exception as exc:
            self._styled_alert(
                "SFTP Transfer Unavailable",
                "The multi-Pi transfer module could not be loaded.\n\n"
                f"Details: {exc}",
                "error",
            )
            return

        try:
            open_multi_sftp_transfer(self)
        except Exception as exc:
            try:
                self.log(f"Multi-Pi SFTP popup failed to open: {exc}", "error")
            except Exception:
                pass
            self._styled_alert(
                "SFTP Transfer Error",
                f"Could not open the multi-Pi SFTP transfer popup.\n\nDetails: {exc}",
                "error",
            )

    def list_received_face_data(self):
        """Return pending received ZIP metadata for the API/SAS."""
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                return self.face_service.list_received_face_data()
        except Exception as e:
            self.log(f"List received face data failed: {e}", "error")
        return []


    def _cleanup_accepted_folder(self, keep_latest=3):
        """Keep only the latest accepted ZIP files to avoid wasting Pi storage."""
        try:
            if keep_latest <= 0 or not os.path.exists(ACCEPTED_DIR):
                return

            files = []
            for name in os.listdir(ACCEPTED_DIR):
                if not name.lower().endswith(".zip"):
                    continue
                path = os.path.join(ACCEPTED_DIR, name)
                if os.path.isfile(path):
                    files.append((os.path.getmtime(path), path))

            files.sort(reverse=True)
            for _mtime, path in files[keep_latest:]:
                try:
                    os.remove(path)
                    self.log(f"Old accepted face data ZIP deleted: {os.path.basename(path)}", "info")
                except Exception:
                    pass
        except Exception:
            pass


    def accept_received_face_data(self, filename: str):
        """Merge a pending received ZIP, then move it to accepted backup."""
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                ok_state, message, extra = self.face_service.accept_received_face_data(filename)
                self._update_received_badge()
                return ok_state, message, extra
            return False, "Face service is not available.", {}
        except Exception as e:
            self._update_received_badge()
            return False, f"Accept received face data failed: {e}", {}


    def reject_received_face_data(self, filename: str):
        """Delete a pending received ZIP without keeping a rejected copy."""
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                ok_state, message, extra = self.face_service.reject_received_face_data(filename)
                self._update_received_badge()
                return ok_state, message, extra
            return False, "Face service is not available.", {}
        except Exception as e:
            self._update_received_badge()
            return False, f"Reject received face data failed: {e}", {}


    def _get_pending_received_files(self):
        self._ensure_transfer_folders()
        try:
            pending_files = [
                f for f in os.listdir(PENDING_DIR)
                if f.lower().endswith(".zip")
            ]
            pending_files.sort()
            return pending_files
        except Exception:
            return []


    def _update_received_badge(self, count=None):
        if count is None:
            count = len(self._get_pending_received_files())

        self._last_pending_received_count = count

        badge = getattr(self, "_received_badge_label", None)
        if not badge:
            return

        try:
            if count <= 0:
                badge.place_forget()
                return

            badge_text = "99+" if count > 99 else str(count)
            badge.configure(text=badge_text, width=max(2, len(badge_text) + 1))
            badge.place(relx=1.0, rely=0.0, x=-6, y=-6, anchor="ne")
            badge.lift()
        except Exception:
            pass


    def _notify_received_face_data(self, count, filenames=None):
        """Pi app keeps the Check Received badge only.

        The Pi GUI already surfaces received data through the Check Received
        popup. Do not trigger sound or OS desktop notifications here.
        SAS is responsible for Windows desktop notifications.
        """
        return


    def scan_received_face_data(self, silent=False):
        pending_files = self._get_pending_received_files()
        self._update_received_badge(len(pending_files))

        if not pending_files:
            if not silent:
                self._styled_alert(
                    "No Received Data",
                    "No pending received face data ZIP file was found in received_face_data/pending.",
                    "info"
                )
            return

        # Manual Check Received should always show every pending ZIP file.
        if not silent:
            self._show_received_face_data_list(pending_files)
            return

        # Background watcher: update badge and notify only for newly detected files.
        new_files = [f for f in pending_files if f not in self._seen_received_files]
        if not new_files:
            return

        for filename in new_files:
            self._seen_received_files.add(filename)

        self.log(
            f"Received pending face data detected: {len(new_files)} new ZIP file(s).",
            "info"
        )
        self._notify_received_face_data(len(new_files), new_files)


    def _show_received_face_data_list(self, pending_files):
        win, shell = self._modern_popup_shell("Pending Received Data", 560, 430)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))

        CircleBadge(
            header,
            text="⇩",
            size=40,
            bg_color="#ECFDF5",
            fg=SUCCESS,
            font=("DejaVu Sans", 15, "bold")
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box,
            text="Pending Received Face Data",
            font=("DejaVu Sans", 15, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text=f"{len(pending_files)} ZIP file(s) found in received_face_data/pending.",
            font=self.font_small,
            bg=CARD,
            fg=TEXT_HINT
        ).pack(anchor="w", pady=(2, 0))

        list_wrap = RoundedCard(
            shell,
            bg_color=CARD_SOFT,
            radius=14,
            shadow=False,
            border=BORDER
        )
        list_wrap.pack(fill="both", expand=True, padx=24, pady=(8, 10))

        zip_list = tk.Listbox(
            list_wrap,
            font=self.font_body,
            bg=CARD_SOFT,
            fg=TEXT_PRI,
            relief="flat",
            bd=0,
            highlightthickness=0,
            selectbackground="#DBEAFE",
            selectforeground=TEXT_PRI
        )
        zip_list.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        list_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=zip_list.yview)
        list_scroll.pack(side="right", fill="y")
        zip_list.configure(yscrollcommand=list_scroll.set)

        for filename in pending_files:
            zip_list.insert(tk.END, filename)

        status_lbl = tk.Label(
            shell,
            text="Select a ZIP file to review, accept, or reject.",
            font=self.font_small,
            bg=CARD,
            fg=TEXT_HINT
        )
        status_lbl.pack(anchor="w", padx=24, pady=(0, 8))

        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(0, 18))

        def selected_filename():
            selection = zip_list.curselection()
            if not selection:
                self._styled_alert("No File Selected", "Please select a pending ZIP file first.", "warning", parent=win)
                return None
            return zip_list.get(selection[0]).strip()

        def refresh_after_action():
            latest = self._get_pending_received_files()
            self._update_received_badge(len(latest))
            zip_list.delete(0, tk.END)
            for filename in latest:
                zip_list.insert(tk.END, filename)
            status_lbl.configure(text=f"{len(latest)} ZIP file(s) pending. Select a ZIP file to accept or reject.")
            if not latest:
                self._safe_popup_close(win)

        def accept_selected():
            filename = selected_filename()
            if not filename:
                return
            if not self._styled_confirm(
                "Accept Received Data",
                "Accept will merge this received dataset.\n\n"
                "Existing IDs receive only new images/encodings.\n"
                "Duplicate images/encodings are ignored.\n\n"
                "Continue?",
                parent=win
            ):
                return
            ok_state, message, _extra = self.accept_received_face_data(filename)
            if ok_state:
                self.log(f"Accepted received face data: {filename}", "success")
                self._styled_alert("Accepted", message, "success", parent=win)
                refresh_after_action()
            else:
                self._styled_alert("Accept Failed", message, "error", parent=win)

        def reject_selected():
            filename = selected_filename()
            if not filename:
                return
            if not self._styled_confirm(
                "Reject Received Data",
                "Reject will move this received backup file to the rejected folder.\n\n"
                "No face data will be imported.\n\n"
                "Continue?",
                parent=win
            ):
                return
            ok_state, message, _extra = self.reject_received_face_data(filename)
            if ok_state:
                self.log(f"Rejected received file: {filename}", "warn")
                refresh_after_action()
            else:
                self._styled_alert("Reject Failed", message, "error", parent=win)

        self._btn(
            row,
            "Close",
            CARD_SOFT,
            lambda: self._safe_popup_close(win),
            fg=TEXT_SEC,
            border=True,
            padx=18,
            pady=8,
            width=90
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Reject",
            DANGER,
            reject_selected,
            fg="white",
            padx=18,
            pady=8,
            width=100
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Accept",
            SUCCESS,
            accept_selected,
            fg="white",
            padx=18,
            pady=8,
            width=100
        ).pack(side="right")


    def _prompt_received_face_data(self, zip_path):
        manifest = self._read_zip_manifest(zip_path)

        source_device = manifest.get("source_device", "Unknown Device")
        export_time = manifest.get("export_time", "Unknown Time")
        filename = os.path.basename(zip_path)

        win, shell = self._modern_popup_shell("Received Face Dataset", 520, 340)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))

        CircleBadge(
            header,
            text="⇩",
            size=40,
            bg_color="#ECFDF5",
            fg=SUCCESS,
            font=("DejaVu Sans", 15, "bold")
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box,
            text="Received Face Dataset",
            font=("DejaVu Sans", 15, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text=f"From: {source_device}",
            font=self.font_small,
            bg=CARD,
            fg=TEXT_HINT
        ).pack(anchor="w", pady=(2, 0))

        msg = (
            f"You have received an exported face dataset.\n\n"
            f"Source device: {source_device}\n"
            f"Export time: {export_time}\n"
            f"File: {filename}\n\n"
            f"Accept will merge this received dataset.\n"
            f"Existing IDs receive only new images/encodings.\n"
            f"Duplicate images/encodings are ignored.\n\n"
            f"Reject will permanently delete this received file."
        )

        tk.Label(
            shell,
            text=msg,
            font=self.font_body,
            bg=CARD,
            fg=TEXT_SEC,
            wraplength=450,
            justify="left"
        ).pack(fill="both", expand=True, padx=24, pady=(8, 12))

        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(0, 18))

        def close_popup():
            self._safe_popup_close(win)

        def reject():
            if not self._styled_confirm(
                "Reject Received Data",
                "Reject will delete this pending ZIP file.\n\n"
                "No face data will be imported and no rejected copy will be kept.\n\n"
                "Continue?",
                parent=win
            ):
                return

            try:
                os.remove(zip_path)
                self._update_received_badge()
                self.log(f"Rejected and deleted received file: {filename}", "warn")
                close_popup()
            except Exception as e:
                self._styled_alert(
                    "Reject Failed",
                    f"Failed to delete received file:\n{e}",
                    "error",
                    parent=win
                )

        def accept():
            try:
                self._import_face_data_zip(zip_path, parent=win)

                accepted_path = os.path.join(ACCEPTED_DIR, filename)

                # If same filename already exists, add timestamp
                if os.path.exists(accepted_path):
                    base, ext = os.path.splitext(filename)
                    accepted_path = os.path.join(
                        ACCEPTED_DIR,
                        f"{base}_accepted_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
                    )

                shutil.move(zip_path, accepted_path)
                self._cleanup_accepted_folder(keep_latest=3)
                self._update_received_badge()

                self.log(f"Accepted received face data: {filename}", "success")
                close_popup()

            except Exception as e:
                self.log(f"Accept failed: {e}", "error")
                self._styled_alert(
                    "Accept Failed",
                    f"Failed to accept received face data:\n{e}",
                    "error",
                    parent=win
                )

        self._btn(
            row,
            "Reject",
            DANGER,
            reject,
            fg="white",
            padx=18,
            pady=8,
            width=110
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Accept",
            SUCCESS,
            accept,
            fg="white",
            padx=18,
            pady=8,
            width=110
        ).pack(side="right")



    def _schedule_boot_recognition_start(self):
        """Schedule recognition auto-start once after the Pi GUI is ready."""
        if getattr(self, "_boot_recognition_start_scheduled", False):
            return

        self._boot_recognition_start_scheduled = True
        self.root.after(2500, self.auto_start_recognition_on_boot)

    def _start_received_watcher(self):
        if getattr(self, "_received_watcher_started", False):
            return

        self._received_watcher_started = True
        self._received_watch_loop()


    def _received_watch_loop(self):
        try:
            if self.current_user:
                self.scan_received_face_data(silent=True)
        except Exception:
            pass

        # This watcher runs every 15 seconds only to check received ZIP files.
        # Do not schedule recognition here; that would restart the camera after
        # a user explicitly pressed Stop.
        self.root.after(15000, self._received_watch_loop)





    def import_face_data(self):
        win, shell = self._modern_popup_shell("Import Face Data", 560, 660)

        header = tk.Frame(shell, bg=CARD)
        header.pack(fill="x", padx=22, pady=(18, 8))

        CircleBadge(
            header,
            text="⇩",
            size=40,
            bg_color="#ECFDF5",
            fg=SUCCESS,
            font=("DejaVu Sans", 15, "bold")
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box,
            text="Import Face Data",
            font=("DejaVu Sans", 15, "bold"),
            bg=CARD,
            fg=TEXT_PRI
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Import merges backup data. Existing IDs receive only new images/encodings.",
            font=self.font_small,
            bg=CARD,
            fg=TEXT_HINT
        ).pack(anchor="w", pady=(2, 0))

        form = tk.Frame(shell, bg=CARD)
        form.pack(fill="x", padx=24, pady=(6, 0))

        ntid_entry = self._field_box(form, "NTID / Username")
        pwd_entry = self._field_box(form, "Password", show="*")
        path_entry = self._field_box(form, "Server Path")

        settings = self._load_settings()
        if settings.get("username"):
            ntid_entry.insert(0, settings["username"])

        if settings.get("password"):
            try:
                f = Fernet(FERNET_KEY)
                pwd_entry.insert(0, f.decrypt(settings["password"].encode()).decode())
            except:
                pwd_entry.insert(0, settings["password"])

        if settings.get("pc_save_path"):
            path_entry.insert(0, settings["pc_save_path"])

        status_lbl = tk.Label(
            shell,
            text="",
            font=self.font_body,
            bg=CARD,
            fg=TEXT_SEC
        )
        status_lbl.pack(anchor="w", padx=24, pady=(8, 4))

        list_box_wrap = RoundedCard(
            shell,
            bg_color=CARD_SOFT,
            radius=14,
            shadow=False,
            border=BORDER
        )
        list_box_wrap.pack(fill="x", padx=24, pady=(4, 8))
        list_box_wrap.configure(height=130)
        list_box_wrap.pack_propagate(False)

        zip_list = tk.Listbox(
            list_box_wrap,
            font=self.font_body,
            height=5,
            bg=CARD_SOFT,
            fg=TEXT_PRI,
            relief="flat",
            bd=0,
            highlightthickness=0,
            selectbackground="#DBEAFE",
            selectforeground=TEXT_PRI
        )
        zip_list.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        list_scroll = ttk.Scrollbar(list_box_wrap, orient="vertical", command=zip_list.yview)
        list_scroll.pack(side="right", fill="y")
        zip_list.configure(yscrollcommand=list_scroll.set)

        state = {
            "mount_point": None,
            "zip_files": []
        }

        def load_zip_files():
            ntid = ntid_entry.get().strip()
            pwd = pwd_entry.get().strip()
            unc = path_entry.get().strip()

            mount_point = self._mount_smb_path(
                ntid,
                pwd,
                unc,
                parent=win,
                status_lbl=status_lbl
            )

            if not mount_point:
                return

            try:
                files = [
                    f for f in os.listdir(mount_point)
                    if f.lower().endswith(".zip")
                ]

                files.sort(reverse=True)

                zip_list.delete(0, tk.END)

                for f in files:
                    zip_list.insert(tk.END, f)

                state["mount_point"] = mount_point
                state["zip_files"] = files

                if files:
                    status_lbl.config(text=f"Found {len(files)} backup ZIP file(s).", fg=SUCCESS)
                else:
                    status_lbl.config(text="No ZIP backup files found in this server path.", fg=WARNING)

            except Exception as e:
                self._styled_alert(
                    "Load Failed",
                    f"Failed to list ZIP files:\n{e}",
                    "error",
                    parent=win
                )

        def import_selected():
            selection = zip_list.curselection()

            if not selection:
                self._styled_alert(
                    "No File Selected",
                    "Please select a backup ZIP file to import.",
                    "warning",
                    parent=win
                )
                return

            zip_name = zip_list.get(selection[0])
            zip_path = os.path.join(state["mount_point"], zip_name)

            if not self._styled_confirm(
                "Confirm Import",
                "Import will merge this backup into the current dataset.\n\n"
                "Existing IDs will receive only new images/encodings.\n"
                "No current user will be deleted or replaced.\n\n"
                "A local backup will be created before importing.",
                parent=win
            ):
                return

            self._import_face_data_zip(zip_path, parent=win)

        row = tk.Frame(shell, bg=CARD)
        row.pack(fill="x", padx=24, pady=(8, 18))

        def close_popup():
            self._safe_popup_close(win)

        self._btn(
            row,
            "Cancel",
            CARD_SOFT,
            close_popup,
            fg=TEXT_SEC,
            border=True,
            padx=18,
            pady=8,
            width=100
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Import Selected",
            SUCCESS,
            import_selected,
            fg="white",
            padx=18,
            pady=8,
            width=150
        ).pack(side="right", padx=(8, 0))

        self._btn(
            row,
            "Connect & List",
            ACCENT,
            load_zip_files,
            fg="white",
            padx=18,
            pady=8,
            width=140
        ).pack(side="right", padx=(8, 0))


    def _create_current_face_backup(self):
        """Create backup-before-import inside pending folder.

        Export does not need another local backup. This backup is created only
        before import and stays in pending so the user can select it again from
        Check Received if needed.
        """
        os.makedirs(PENDING_DIR, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_zip = os.path.join(
            PENDING_DIR,
            f"backup_before_import_{timestamp}.zip"
        )
        if os.path.exists(backup_zip):
            base, ext = os.path.splitext(backup_zip)
            backup_zip = f"{base}_{int(time.time())}{ext}"

        with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.exists(ENCODINGS_FILE):
                z.write(ENCODINGS_FILE, ENCODINGS_FILE)

            if os.path.exists(DATASET_DIR):
                for root, dirs, files in os.walk(DATASET_DIR):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, ".")
                        z.write(full_path, arcname)

        self.log(f"Backup before import created in pending folder: {backup_zip}", "info")
        return backup_zip


    def _load_encoding_data_safe(self):
        if not os.path.exists(ENCODINGS_FILE):
            return {
                "encodings": [],
                "names": [],
                "trained_files": []
            }

        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)

            return {
                "encodings": data.get("encodings", []),
                "names": data.get("names", []),
                "trained_files": data.get("trained_files", [])
            }

        except Exception as e:
            self.log(f"Failed to load encodings.pickle: {e}", "error")
            return {
                "encodings": [],
                "names": [],
                "trained_files": []
            }


    def _get_dataset_ids(self):
        if not os.path.exists(DATASET_DIR):
            return set()

        return {
            d.strip().lower()
            for d in os.listdir(DATASET_DIR)
            if os.path.isdir(os.path.join(DATASET_DIR, d))
        }


    def _import_face_data_zip(self, zip_path, parent=None):
        try:
            import hashlib

            self._create_current_face_backup()
            current_data = self._load_encoding_data_safe()

            dataset_ids = self._get_dataset_ids()
            current_ids = set(dataset_ids)

            def file_sha256(path):
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                return h.hexdigest()

            def encoding_signature(enc):
                try:
                    import numpy as np
                    arr = np.asarray(enc, dtype="float32")
                    return hashlib.sha256(arr.tobytes()).hexdigest()
                except Exception:
                    return hashlib.sha256(repr(enc).encode("utf-8", errors="ignore")).hexdigest()

            def unique_destination(path):
                if not os.path.exists(path):
                    return path
                folder = os.path.dirname(path)
                base = os.path.basename(path)
                stem, ext = os.path.splitext(base)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                counter = 1
                while True:
                    candidate = os.path.join(folder, f"{stem}_import_{stamp}_{counter}{ext}")
                    if not os.path.exists(candidate):
                        return candidate
                    counter += 1

            existing_hashes_by_user = {}
            for user_id in current_ids:
                user_dir = os.path.join(DATASET_DIR, user_id)
                hashes = set()
                for root, _, files in os.walk(user_dir):
                    for filename in files:
                        try:
                            hashes.add(file_sha256(os.path.join(root, filename)))
                        except Exception:
                            pass
                existing_hashes_by_user[user_id] = hashes

            with zipfile.ZipFile(zip_path, "r") as z:
                file_list = z.namelist()

                if ENCODINGS_FILE not in file_list:
                    self._styled_alert(
                        "Invalid Backup",
                        "This ZIP does not contain encodings.pickle.",
                        "error",
                        parent=parent
                    )
                    return

                with z.open(ENCODINGS_FILE) as f:
                    backup_data = pickle.load(f)

                backup_names = [str(x).strip().lower() for x in backup_data.get("names", [])]
                backup_encodings = list(backup_data.get("encodings", []))
                backup_trained_files = [str(x).replace("\\", "/") for x in backup_data.get("trained_files", [])]
                backup_ids = set(backup_names)

                new_ids = backup_ids - current_ids
                updated_ids = backup_ids & current_ids

                raise RuntimeError("Legacy dlib dataset import is disabled. Use InsightFace face_data import.")

                imported_files = 0
                duplicate_files = 0
                copied_key_map = {}
                copied_original_keys = set()
                affected_ids = set()

                for member in file_list:
                    normalized = member.replace("\\", "/")

                    if not normalized.startswith("dataset/"):
                        continue

                    parts = normalized.split("/")

                    if len(parts) < 3:
                        continue

                    user_id = parts[1].strip().lower()

                    if not user_id or normalized.endswith("/"):
                        continue

                    rel_after_user = "/".join(parts[2:])
                    src_temp = None

                    # Read member into temp path so we can hash before deciding to copy.
                    temp_extract = os.path.join(TEMP_IMPORT_DIR, f"_hash_{time.time_ns()}_{os.path.basename(rel_after_user)}")
                    os.makedirs(os.path.dirname(temp_extract), exist_ok=True)
                    with z.open(member) as source, open(temp_extract, "wb") as tmp:
                        shutil.copyfileobj(source, tmp)
                    src_temp = temp_extract

                    try:
                        src_hash = file_sha256(src_temp)
                    except Exception:
                        src_hash = ""

                    if user_id not in existing_hashes_by_user:
                        existing_hashes_by_user[user_id] = set()

                    if src_hash and src_hash in existing_hashes_by_user[user_id]:
                        duplicate_files += 1
                        try:
                            os.remove(src_temp)
                        except Exception:
                            pass
                        continue

                    output_path = os.path.normpath(os.path.join(DATASET_DIR, user_id, rel_after_user))
                    dataset_abs = os.path.abspath(DATASET_DIR)
                    output_abs = os.path.abspath(output_path)

                    if not output_abs.startswith(dataset_abs):
                        try:
                            os.remove(src_temp)
                        except Exception:
                            pass
                        continue

                    os.makedirs(os.path.dirname(output_abs), exist_ok=True)
                    final_output = unique_destination(output_abs)
                    shutil.move(src_temp, final_output)

                    imported_files += 1
                    affected_ids.add(user_id)

                    if src_hash:
                        existing_hashes_by_user[user_id].add(src_hash)

                    original_key = f"{user_id}/{rel_after_user}".replace("\\", "/")
                    final_key = f"{user_id}/{os.path.relpath(final_output, os.path.join(DATASET_DIR, user_id))}".replace("\\", "/")
                    copied_key_map[original_key] = final_key
                    copied_original_keys.add(original_key)

                current_data["encodings"] = list(current_data.get("encodings", []))
                current_data["names"] = [str(x).strip().lower() for x in current_data.get("names", [])]
                current_trained_files = [str(x).replace("\\", "/") for x in current_data.get("trained_files", [])]

                existing_encoding_sigs = set()
                for enc, name in zip(current_data["encodings"], current_data["names"]):
                    existing_encoding_sigs.add((str(name).strip().lower(), encoding_signature(enc)))

                trained_files = set(current_trained_files)
                imported_encodings = 0
                duplicate_encodings = 0
                has_aligned_trained_files = len(backup_trained_files) == len(backup_encodings)

                for idx, (enc, saved_id) in enumerate(zip(backup_encodings, backup_names)):
                    mapped_key = ""

                    if has_aligned_trained_files:
                        original_key = backup_trained_files[idx]
                        mapped_key = copied_key_map.get(original_key, "")
                        if not mapped_key:
                            duplicate_encodings += 1
                            continue
                    else:
                        if saved_id not in affected_ids:
                            duplicate_encodings += 1
                            continue

                    sig = (saved_id, encoding_signature(enc))
                    if sig in existing_encoding_sigs:
                        duplicate_encodings += 1
                        continue

                    current_data["encodings"].append(enc)
                    current_data["names"].append(saved_id)
                    existing_encoding_sigs.add(sig)
                    imported_encodings += 1

                    if mapped_key:
                        trained_files.add(mapped_key)

                current_data["trained_files"] = list(trained_files)

                with open(ENCODINGS_FILE, "wb") as f:
                    pickle.dump(current_data, f)

            self.refresh_dataset()

            self.log(
                f"Import complete. New data only. New IDs: {len(new_ids)}, updated IDs: {len(updated_ids)}, "
                f"new images: {imported_files}, duplicate images ignored: {duplicate_files}, "
                f"encodings added: {imported_encodings}, duplicate encodings ignored: {duplicate_encodings}",
                "success"
            )

            self._styled_alert(
                "Import Complete",
                f"Import mode: Add new data only\n"
                f"New IDs: {len(new_ids)}\n"
                f"Existing IDs checked: {len(updated_ids)}\n"
                f"New images added: {imported_files}\n"
                f"Duplicate images ignored: {duplicate_files}\n"
                f"Encodings added: {imported_encodings}\n"
                f"Duplicate encodings ignored: {duplicate_encodings}",
                "success",
                parent=parent
            )

        except Exception as e:
            self.log(f"Import failed: {e}", "error")
            self._styled_alert(
                "Import Failed",
                f"Failed to import face data:\n{e}",
                "error",
                parent=parent
            )    



    def _queue_recognition_resume_after_capture(self, delay_ms: int = 1100):
        """Return the Pi to background recognition after a capture workflow.

        Capture and recognition cannot own PiCamera2 at the same time.  Once
        capture releases the camera, this retries recognition without reopening
        the Windows SAS preview.  A normal Pi capture therefore has the same
        end state as an SAS-initiated capture: recognition runs again for
        workstation unlock.
        """
        max_attempts = 6

        def start_when_safe(attempt: int = 0):
            if not getattr(self, "_resume_recognition_after_capture", False):
                return

            if getattr(self, "_capture_running", False) or getattr(self, "_api_training_running", False):
                self.root.after(400, lambda: start_when_safe(attempt))
                return

            if getattr(self, "_recognition_running", False):
                self._resume_recognition_after_capture = False
                self.log("Recognition is already running after capture.", "success")
                return

            self.stop_flag = False
            try:
                if hasattr(self, "face_service") and self.face_service is not None:
                    self.face_service._stop_recognition_event.clear()
                    self.face_service._stop_capture_event.clear()
            except Exception:
                pass

            self.log(
                f"Capture finished. Restarting face recognition (attempt {attempt + 1}/{max_attempts})...",
                "info"
            )
            self.start_recognition_thread()

            def verify_start():
                if not getattr(self, "_resume_recognition_after_capture", False):
                    return
                if getattr(self, "_recognition_running", False):
                    self._resume_recognition_after_capture = False
                    self.log("Face recognition restarted after capture.", "success")
                    return
                if attempt + 1 < max_attempts:
                    self.root.after(900, lambda: start_when_safe(attempt + 1))
                else:
                    self._resume_recognition_after_capture = False
                    self.log("Capture completed, but face recognition could not restart. Press Recognize to retry.", "error")

            self.root.after(1800, verify_start)

        self.root.after(delay_ms, start_when_safe)


    def _queue_recognition_resume_after_training(self, delay_ms: int = 1100):
        """Restart Pi recognition safely after training, with camera-release retries.

        A manual Pi ``Stop`` clears ``_resume_recognition_after_training`` and
        therefore cancels this recovery.  SAS-targeted camera transitions do
        not clear it, so the Pi returns to recognition automatically.
        """
        max_attempts = 6

        def start_when_safe(attempt: int = 0):
            if not getattr(self, "_resume_recognition_after_training", False):
                return

            if getattr(self, "_capture_running", False) or getattr(self, "_api_training_running", False):
                self.root.after(400, lambda: start_when_safe(attempt))
                return

            if getattr(self, "_recognition_running", False):
                self._resume_recognition_after_training = False
                self.log("Recognition is already running after training.", "success")
                return

            # Clear only the temporary camera-stop flags before opening a new
            # PiCamera2 session.  A real local Stop has already cancelled the
            # resume flag above and will not reach this point.
            self.stop_flag = False
            try:
                if hasattr(self, "face_service") and self.face_service is not None:
                    self.face_service._stop_recognition_event.clear()
                    self.face_service._stop_capture_event.clear()
            except Exception:
                pass

            self.log(
                f"Training finished. Restarting face recognition (attempt {attempt + 1}/{max_attempts})...",
                "info"
            )
            self.start_recognition_thread()

            def verify_start():
                if not getattr(self, "_resume_recognition_after_training", False):
                    return
                if getattr(self, "_recognition_running", False):
                    self._resume_recognition_after_training = False
                    self.log("Face recognition restarted after training.", "success")
                    return
                if attempt + 1 < max_attempts:
                    self.root.after(900, lambda: start_when_safe(attempt + 1))
                else:
                    self._resume_recognition_after_training = False
                    self.log("Training completed, but face recognition could not restart. Press Recognize to retry.", "error")

            self.root.after(1800, verify_start)

        self.root.after(delay_ms, start_when_safe)

    def start_train(self):
        """Train stored images without interrupting active face recognition.

        Capture is still blocked because it needs Picamera2. Training itself
        only reads the dataset and writes a new model file, so recognition can
        continue protecting the workstation. recog.py reloads the final model
        automatically after the atomic file replacement.
        """
        if self._capture_running or getattr(self, "_api_training_running", False):
            self.log("Capture or training is already running.", "warn")
            return

        self._resume_recognition_after_training = False
        self._api_training_running = True
        self._api_training_state = "running"
        self._api_last_training_id = f"local-train-{int(time.time() * 1000)}"
        self._api_last_training_error = None
        self._api_last_training_new_faces = 0
        self._api_training_dataset_total = 0
        self._api_training_already_trained = 0
        self._api_training_valid_images = 0
        self._api_training_skipped_images = 0
        self._set_api_training_progress({
            "processed": 0,
            "total": 0,
            "percent": 0,
            "phase": "preparing",
            "message": "Preparing dataset for training...",
        })

        self.train_btn.config(state="disabled")
        self.capture_btn.config(state="disabled")
        self.delete_btn.config(state="disabled")
        # Keep the camera mode as it already is. When recognition is active its
        # buttons remain disabled/locked to avoid a user stopping it mid-train.
        if self._recognition_running:
            self.recog_btn.config(state="disabled")
            self.stop_btn.config(state="disabled")
        else:
            self.recog_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

        self.log("Training model (new images only). Recognition remains active.", "info")

        def update_progress(state):
            safe_state = dict(state) if isinstance(state, dict) else {}

            def apply():
                self._set_api_training_progress(safe_state)
                message = str(safe_state.get("message", "") or "")
                if message:
                    self.log(message, "info")

            self.root.after(0, apply)

        def thread():
            failed = False
            try:
                count = train_model(
                    progress_callback=lambda m: self.root.after(0, lambda m=m: self.log(m, "info")),
                    progress_state_callback=update_progress,
                )
                self._api_last_training_new_faces = int(count or 0)
                if count == 0:
                    self.log("No new images found to train.", "warn")
                else:
                    self.log(
                        f"Training complete. {count} new face(s) added. Recognition remained active.",
                        "success",
                    )
                self.root.after(0, self.refresh_dataset)
            except Exception as e:
                failed = True
                self.log(f"Training error: {e}", "error")
                self._api_last_training_error = str(e)
                self._api_last_error = str(e)
            finally:
                def restore_after_training():
                    self._api_training_running = False
                    self._api_training_state = "failed" if failed else "completed"
                    self._api_last_training_finished_at = time.time()

                    if self.current_user:
                        self.capture_btn.config(state="normal")
                        self.train_btn.config(state="normal")
                        self.delete_btn.config(state="normal")
                    else:
                        self.capture_btn.config(state="disabled")
                        self.train_btn.config(state="disabled")
                        self.delete_btn.config(state="disabled")

                    if self._recognition_running:
                        self.recog_btn.config(state="disabled")
                        self.stop_btn.config(
                            state="normal",
                            bg=WARNING,
                            fg="white",
                            activebackground=WARNING,
                            activeforeground="white",
                        )
                    else:
                        self.recog_btn.config(state="normal")
                        self.stop_btn.config(state="disabled")

                self.root.after(0, restore_after_training)

        Thread(target=thread, daemon=True).start()

    def auto_start_recognition_on_boot(self):
        """Automatically start recognition once shortly after the Pi GUI opens."""
        try:
            if getattr(self, "_boot_recognition_start_cancelled", False):
                self.log("Boot auto-start cancelled after a Stop request.", "info")
                return

            if self._recognition_running or self._capture_running:
                return

            self.log("Auto-start recognition on boot...", "info")
            self.start_recognition_thread()

        except Exception as e:
            self.log(f"Auto-start recognition failed: {e}", "error")


    # --------------------------------------------------------
    # Recognition
    # --------------------------------------------------------
    def start_recognition_thread(self):
        if self._recognition_running or self._capture_running:
            self.log("Another process is already running.", "warn")
            return

        self._recognition_running = True
        self._set_camera_status(True)
        self.stop_flag = False
        self.recog_btn.config(state="disabled")

        try:
            if hasattr(self, "face_service"):
                self.face_service._recognition_running = True
                self.face_service._stop_recognition_event.clear()
        except Exception:
            pass

        # If admin is logged in, allow Capture button to interrupt recognition.
        # If not logged in, keep Capture disabled.
        if self.current_user:
            self.capture_btn.config(state="normal")
        else:
            self.capture_btn.config(state="disabled")

        self.stop_btn.config(
            state="normal",
            bg=WARNING,
            fg="white",
            activebackground=WARNING,
            activeforeground="white"
        )
        self.log("Starting face recognition...", "info")

        def frame_cb(frame, names=None, raw_frame=None):
            self._api_update_latest_frame(raw_frame if raw_frame is not None else frame, frame)
            self._show_frame(frame)
            if names:
                try:
                    name, conf = names[0]
                    self.log(f"Recognized: {name} ({conf*100:.1f}%)", "success")
                except Exception:
                    pass

        def thread():
            try:
                start_recognition(
                    frame_callback=frame_cb,
                    stop_flag=lambda: self.stop_flag,
                )
            except Exception as e:
                self.log(f"Recognition error: {e}", "error")
            finally:
                def _restore():
                    self._recognition_running = False
                    self._set_camera_status(False)
                    
                    self.stop_flag = False
        
                    try:
                        if hasattr(self, "face_service"):
                            self.face_service._recognition_running = False
                    except Exception:
                        pass

                    self.recog_btn.config(state="normal")
                    if self.current_user:
                        self.capture_btn.config(state="normal")
                    else:
                        self.capture_btn.config(state="disabled")
                    self.stop_btn.config(state="disabled")
                    self.log("Recognition stopped.", "info")
                self.root.after(0, _restore)

        Thread(target=thread, daemon=True).start()

    # --------------------------------------------------------
    # Stop
    # --------------------------------------------------------
    def stop_all(self):
        # A user/API Stop must cancel any not-yet-fired boot auto-start.
        self._boot_recognition_start_cancelled = True

        # Training itself cannot safely be interrupted here, but a Pi-side Stop
        # must still prevent the automatic recognition restart after training.
        if getattr(self, "_api_training_running", False):
            self._resume_recognition_after_training = False
            self.log("Training is still running. Recognition will remain stopped when it finishes.", "warn")
            return

        service_running = False

        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                service_running = (
                    getattr(self.face_service, "_recognition_running", False)
                    or getattr(self.face_service, "_capture_running", False)
                )
        except Exception:
            service_running = False

        if not self._capture_running and not self._recognition_running and not service_running:
            self.log("No running process to stop.", "info")
            return

        # Stop Pi-GUI-started recognition
        self.stop_flag = True

        # Stop Pi-GUI-started capture
        try:
            self._stop_capture_event.set()
        except Exception:
            pass

        # Stop API / FaceService-started recognition and capture
        try:
            if hasattr(self, "face_service") and self.face_service is not None:
                self.face_service._stop_recognition_event.set()
                self.face_service._stop_capture_event.set()
        except Exception as e:
            print("[STOP SERVICE EVENT ERROR]", e)

        self._set_camera_status(False)
        self.log("Stopping...", "warn")

        self.capture_btn.config(
            text="▣\nCapture",
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOV,
            activeforeground="white",
            command=self.start_capture,
            state="normal" if self.current_user else "disabled"
        )

        self.recog_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

        if self.current_user:
            self.train_btn.config(state="normal")
            self.delete_btn.config(state="normal")

        self.root.after(500, self._clear_canvas)

    def delete_user_from_encodings(self, username):
        username = username.strip().lower()
    
        if not username:
            self.log("No username provided for encodings delete.", "warn")
            return False
    
        if not os.path.exists(ENCODINGS_FILE):
            self.log("encodings.pickle not found. Skipped encoding delete.", "warn")
            return False
    
        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
    
            old_encodings = data.get("encodings", [])
            old_names = data.get("names", [])
            old_trained_files = data.get("trained_files", [])
    
            new_encodings = []
            new_names = []
            removed_count = 0
    
            for enc, saved_name in zip(old_encodings, old_names):
                if str(saved_name).strip().lower() == username:
                    removed_count += 1
                else:
                    new_encodings.append(enc)
                    new_names.append(saved_name)
    
            new_trained_files = [
                tf for tf in old_trained_files
                if not str(tf).strip().lower().startswith(username + "/")
            ]
    
            updated_data = {
                "encodings": new_encodings,
                "names": new_names,
                "trained_files": new_trained_files
            }
    
            with open(ENCODINGS_FILE, "wb") as f:
                pickle.dump(updated_data, f)
    
            self.log(
                f"Removed '{username}' from encodings.pickle "
                f"({removed_count} encoding(s) removed).",
                "warn"
            )
            return True
    
        except Exception as e:
            self.log(f"Failed to update encodings.pickle: {e}", "error")
            return False

    # --------------------------------------------------------
    # Delete user
    # --------------------------------------------------------
    def delete_user(self):
        name = self.name_entry.get().strip()

        if not name:
            self._styled_alert(
                "Missing NTID",
                "Please enter or select a user ID to delete.",
                "warning"
            )
            return

        delete_id = name.strip().lower()
        user_path = os.path.join(DATASET_DIR, delete_id)

        if not os.path.exists(user_path):
            self._styled_alert(
                "Dataset Not Found",
                f"No dataset folder found for '{name}'.",
                "error"
            )
            return

        if not self._styled_confirm(
            "Confirm Delete",
            f"Delete all data for '{name}'?\n\n"
            "This will remove:\n"
            "• dataset photos\n"
            "• trained face data in encodings.pickle\n\n"
        ):
            return

        # 1. Delete dataset folder
        try:
            shutil.rmtree(user_path)
            self.log(f"Deleted dataset folder for '{delete_id}'.", "warn")
        except Exception as e:
            self.log(f"Failed to delete dataset folder: {e}", "error")
            self._styled_alert(
                "Delete Failed",
                f"Failed to delete dataset folder:\n{e}",
                "error"
            )
            return

        # 2. Delete user from encodings.pickle
        self.delete_user_from_encodings(delete_id)
        self._cleanup_expired_delete_backups_now()

        # 3. Clear selected ID and refresh UI
        self.name_entry.delete(0, tk.END)
        self.refresh_dataset()

        self._styled_alert(
            "User Deleted",
            f"'{delete_id}' has been removed from dataset and encodings.pickle.",
            "success"
        )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    def _on_canvas_resize(self, event):
        try:
            if hasattr(self, "placeholder_title"):
                self.canvas.coords(
                    self.placeholder_title,
                    event.width // 2,
                    event.height // 2
                )
        except:
            pass

    def _show_frame(self, frame):
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
             
            if w < 10 or h < 10:
                w, h = 620, 480
            # Use simple display method for Raspberry Pi stability
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img = img.resize((w, h), Image.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.canvas.delete("placeholder")
            self.canvas.create_image(
                0,
                0,
                anchor="nw",
                image=imgtk
            )
            self.imgtk = imgtk

        except :
            pass

    def _clear_canvas(self):
        self._set_camera_status(False)
        
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        if w < 10 or h < 10:
            w, h = 620, 480
    
        self.canvas.delete("all")
    
        self.canvas.create_rectangle(
            0,
            0,
            w,
            h,
            fill=CAM_BG,
            outline=""
        )
    
        self.canvas.create_text(
            w//2,
            h//2,
            text="Camera stopped",
            fill="#CBD5E1",
            font=("DejaVu Sans", 13, "bold")
        )
    

    
        self.imgtk = None

    def _card(self, parent):
        # Rounded card background while preserving normal Tkinter pack/grid behaviour.
        return RoundedCard(parent, bg_color=CARD, radius=20, shadow=True, border=BORDER)

    def _section_label(self, parent, text):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(row, text=text, font=self.font_label,
                 bg=CARD, fg=TEXT_PRI).pack(side="left")
        # No hard divider line; card spacing provides separation.

    def _btn(self, parent, text, color, command, state="normal", fg="white",
             border=False, padx=12, pady=8, width=None):
        return RoundButton(
            parent,
            text=text,
            color=color,
            command=command,
            state=state,
            fg=fg,
            border=border,
            padx=padx,
            pady=pady,
            font=self.font_btn,
            radius=15,
            height=max(38, 22 + pady * 2),
            width=width,
            activebackground=ACCENT_HOV if color == ACCENT else "#EEF5FF" if color in (CARD, CARD_SOFT) else color,
            activeforeground=fg
        )

    def _action_btn(self, parent, icon, label, color, command, state="normal"):
        # Rounded white action tile like the reference UI.
        return RoundButton(
            parent,
            text=f"{icon}\n{label}",
            color=CARD_SOFT,
            command=command,
            state=state,
            fg=color,
            border=True,
            padx=8,
            pady=10,
            font=("DejaVu Sans", 10, "bold"),
            radius=16,
            height=72,
            activebackground="#EEF5FF",
            activeforeground=color
        )



# --------------------------------------------------------
# InsightFace compatibility overrides for the restored v106 UI
# --------------------------------------------------------
def _insightface_list_users():
    from insightface_engine import get_engine

    return get_engine().list_users()


def _insightface_create_face_data_zip(self, zip_path):
    from insightface_engine import get_engine

    return get_engine().export_to_zip(zip_path)


def _insightface_dlib_removed(*_args, **_kwargs):
    raise RuntimeError("Legacy dlib face-data path is disabled. Use InsightFace registration/import/export.")


def _insightface_refresh_dataset(self):
    for widget in self.dataset_frame.winfo_children():
        widget.destroy()

    try:
        users = _insightface_list_users()
    except Exception as exc:
        tk.Label(
            self.dataset_frame,
            text=f"Could not load InsightFace users: {exc}",
            font=self.font_body,
            bg=CARD,
            fg=DANGER,
        ).pack(anchor="w", pady=10)
        if hasattr(self, "user_count_badge"):
            self.user_count_badge.config(text="0")
        return

    query = ""
    try:
        query = self.user_search_entry.get().strip().lower()
    except Exception:
        query = ""
    if query:
        users = [
            user for user in users
            if query in str(user.get("employee_id") or user.get("id") or "").lower()
            or query in str(user.get("display_name") or user.get("name") or "").lower()
        ]

    if hasattr(self, "user_count_badge"):
        self.user_count_badge.config(text=str(len(users)))

    if not users:
        tk.Label(
            self.dataset_frame,
            text="No users registered yet.",
            font=self.font_body,
            bg=CARD,
            fg=TEXT_SEC,
        ).pack(anchor="w", pady=10)
        return

    for user in sorted(users, key=lambda item: str(item.get("employee_id") or item.get("id") or "")):
        employee_id = str(user.get("employee_id") or user.get("id") or "").strip().upper()
        display_name = str(user.get("display_name") or user.get("name") or employee_id).strip()
        samples = int(user.get("samples") or user.get("photos") or 0)

        row = RoundedCard(self.dataset_frame, bg_color=CARD_SOFT, radius=16, shadow=False, border="#EAF0F8")
        row.pack(fill="x", pady=(0, 8))
        row.bind("<Button-1>", lambda e, n=employee_id: self._select_user(n))

        info = tk.Frame(row, bg=CARD_SOFT)
        info.pack(side="left", fill="x", expand=True, pady=10, padx=(12, 10))
        info.bind("<Button-1>", lambda e, n=employee_id: self._select_user(n))

        name_label = tk.Label(
            info,
            text=f"{display_name} ({employee_id})" if display_name and display_name != employee_id else employee_id,
            font=("DejaVu Sans", 10, "bold"),
            bg=CARD_SOFT,
            fg=TEXT_PRI,
        )
        name_label.pack(anchor="w")
        name_label.bind("<Button-1>", lambda e, n=employee_id: self._select_user(n))

        sample_label = tk.Label(
            info,
            text=f"{samples} InsightFace sample(s)",
            font=self.font_small,
            bg=CARD_SOFT,
            fg=TEXT_SEC,
        )
        sample_label.pack(anchor="w", pady=(2, 0))
        sample_label.bind("<Button-1>", lambda e, n=employee_id: self._select_user(n))

        RoundButton(
            row,
            "Ready",
            "#DCFCE7",
            command=None,
            fg="#15803D",
            border=False,
            padx=8,
            pady=2,
            font=self.font_badge,
            radius=12,
            height=26,
            width=86,
        ).pack(side="right", padx=(8, 12), pady=12)


def _insightface_select_user(self, employee_id):
    employee_id = str(employee_id or "").strip().upper()
    display_name = ""
    try:
        for user in _insightface_list_users():
            if str(user.get("employee_id") or user.get("id") or "").strip().upper() == employee_id:
                display_name = str(user.get("display_name") or user.get("name") or "").strip()
                break
    except Exception:
        pass

    self.name_entry.delete(0, tk.END)
    self.name_entry.insert(0, employee_id)
    try:
        self.display_name_entry.delete(0, tk.END)
        self.display_name_entry.insert(0, display_name)
    except Exception:
        pass


def _insightface_api_capture_user_request(self, user_id, mode="add", auto_capture=None, display_name=None):
    return self.face_service._api_capture_user_request(user_id, mode, auto_capture, display_name)


def _insightface_start_capture(self):
    user_id = self.name_entry.get().strip().upper()
    display_name = ""
    try:
        display_name = self.display_name_entry.get().strip()
    except Exception:
        display_name = ""
    if not display_name:
        self._styled_alert("Missing Name", "Please enter the employee name before registering.", "warning")
        return
    if not user_id:
        self._styled_alert("Missing NTID", "Please enter the employee NTID before registering.", "warning")
        return

    self.log(f"Validating NTID '{user_id}' with AD...", "info")
    if not self._validate_ntid_in_ad(user_id):
        self._styled_alert("Invalid NTID", f"'{user_id}' is not a valid NTID.", "error")
        self.log(f"NTID '{user_id}' validation failed.", "error")
        return
    self.log(f"NTID '{user_id}' validated successfully.", "success")

    self.capture_btn.config(state="disabled")
    self.delete_btn.config(state="disabled")
    self.recog_btn.config(state="disabled")
    self.stop_btn.config(state="normal")
    self.log(f"Registering '{display_name}' ({user_id})...", "info")

    def finish(ok, message, extra):
        self.capture_btn.config(state="normal")
        self.delete_btn.config(state="normal")
        self.recog_btn.config(state="normal")
        self.stop_btn.config(state="disabled" if not getattr(self, "_recognition_running", False) else "normal")
        self.log(message, "success" if ok else "error")
        try:
            self.refresh_dataset()
        except Exception:
            pass
        if ok:
            self._styled_alert(
                "Registration Complete",
                f"{display_name} ({user_id}) registered.\n\nTotal sample(s): {extra.get('photos', extra.get('frames', 1))}",
                "success",
            )
        else:
            self._styled_alert("Registration Failed", message, "error")

    def worker():
        try:
            ok, message, extra = self.face_service._api_capture_user_request(
                user_id,
                mode="add",
                auto_capture=False,
                display_name=display_name,
            )
            if ok and not extra.get("recognition_interrupted", True):
                pass
        except Exception as exc:
            ok, message, extra = False, f"Registration failed: {exc}", {}
        self.root.after(0, lambda ok=ok, message=message, extra=extra: finish(ok, message, extra))

    Thread(target=worker, daemon=True, name="InsightFaceRegister").start()


def _insightface_api_train_request(self):
    return self.face_service._api_train_request()


def _insightface_api_delete_user_request(self, user_id, expected_name=None):
    return self.face_service._api_delete_user_request(user_id, expected_name)


def _insightface_find_user(employee_id):
    employee_id = str(employee_id or "").strip().upper()
    if not employee_id:
        return None
    try:
        for user in _insightface_list_users():
            if str(user.get("employee_id") or user.get("id") or "").strip().upper() == employee_id:
                return user
    except Exception:
        return None
    return None


def _insightface_delete_user(self):
    user_id = self.name_entry.get().strip().upper()
    display_name = ""
    try:
        display_name = self.display_name_entry.get().strip()
    except Exception:
        display_name = ""
    if not user_id:
        self._styled_alert("Missing NTID", "Please enter or select a user ID to delete.", "warning")
        return
    if not display_name:
        self._styled_alert("Missing Name", "Please enter or select the employee name before deleting.", "warning")
        return
    user = _insightface_find_user(user_id)
    if not user:
        self._styled_alert("User Not Found", f"No registered user was found for NTID '{user_id}'.", "error")
        return
    registered_name = str(user.get("display_name") or user.get("name") or "").strip()
    if registered_name and registered_name.casefold() != display_name.casefold():
        self._styled_alert(
            "Name Mismatch",
            f"NTID '{user_id}' is registered as '{registered_name}'.\n\nSelect the user from the list or enter the matching name.",
            "error",
        )
        return
    if not self._styled_confirm(
        "Confirm Delete",
        f"Delete all InsightFace data for '{registered_name or display_name}' ({user_id})?\n\nRecognition will pause and restart automatically.",
    ):
        return

    progress = tk.Toplevel(self.root)
    progress.title("Deleting User")
    progress.configure(bg=CARD)
    progress.geometry("380x155")
    progress.minsize(380, 155)
    progress.resizable(False, False)
    progress.transient(self.root)
    progress.protocol("WM_DELETE_WINDOW", lambda: None)

    wrap = tk.Frame(progress, bg=CARD, padx=24, pady=22)
    wrap.pack(fill="both", expand=True)
    tk.Label(
        wrap,
        text=f"Deleting {user_id}",
        bg=CARD,
        fg=TEXT_PRI,
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w")
    status = tk.Label(
        wrap,
        text="Pausing recognition and deleting user...",
        bg=CARD,
        fg=TEXT_HINT,
        font=("Segoe UI", 10),
        justify="left",
    )
    status.pack(anchor="w", pady=(8, 14))
    bar = ttk.Progressbar(wrap, mode="indeterminate", length=300)
    bar.pack(fill="x")
    bar.start(12)
    progress.update_idletasks()
    x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - progress.winfo_width()) // 2)
    y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - progress.winfo_height()) // 2)
    progress.geometry(f"+{x}+{y}")
    progress.lift()
    progress.update()

    def finish(ok, message, extra):
        try:
            bar.stop()
            progress.destroy()
        except Exception:
            pass
        self.log(message, "success" if ok else "error")
        if ok:
            self.name_entry.delete(0, tk.END)
            try:
                self.display_name_entry.delete(0, tk.END)
            except Exception:
                pass
            self.refresh_dataset()
            if extra.get("recognition_resume_requested"):
                self.log("Recognition restart requested after delete.", "info")
        self._styled_alert("User Deleted" if ok else "Delete Failed", message, "success" if ok else "error")

    def worker():
        try:
            ok, message, extra = self.face_service._api_delete_user_request(user_id, registered_name or display_name)
        except Exception as exc:
            ok, message, extra = False, f"Delete failed: {exc}", {}
        self.root.after(0, lambda ok=ok, message=message, extra=extra: finish(ok, message, extra))

    self.root.after(100, lambda: Thread(target=worker, daemon=True, name="InsightFaceDelete").start())


def _insightface_export_face_data_to_folder(self, target_folder=None, username=None, password=None, pc_save_path=None):
    return self.face_service.export_face_data_to_folder(target_folder, username, password, pc_save_path)


def _insightface_list_server_face_data_zips(self, username=None, password=None, pc_save_path=None):
    return self.face_service.list_server_face_data_zips(username, password, pc_save_path)


def _insightface_import_face_data_from_zip(self, zip_path):
    return self.face_service.import_face_data_from_zip(zip_path)


def _insightface_import_face_data_zip(self, zip_path, parent=None):
    ok, message, extra = self.face_service.import_face_data_from_zip(zip_path)
    self.log(message, "success" if ok else "error")
    if ok:
        imported = int(extra.get("new_users_count", 0) or 0)
        updated = int(extra.get("updated_users_count", 0) or 0)
        embeddings = int(extra.get("embeddings_added", 0) or 0)
        conflicts = int(extra.get("name_conflicts_count", 0) or 0)
        self._styled_alert(
            "Import Complete",
            (
                "Face data imported successfully.\n\n"
                f"New users: {imported}\n"
                f"Updated users: {updated}\n"
                f"Embeddings added: {embeddings}\n"
                f"Name conflicts kept local: {conflicts}"
            ),
            "success",
            parent=parent,
        )
        try:
            self.refresh_dataset()
        except Exception:
            pass
    else:
        self._styled_alert("Import Failed", message, "error", parent=parent)


def _insightface_get_sftp_import_target(self):
    return self.face_service.get_sftp_import_target()


def _insightface_prepare_sftp_download_package(self):
    return self.face_service.prepare_sftp_download_package()


def _insightface_sftp_send_face_data(self, host, username, password, remote_dir, port=22):
    return self.face_service.sftp_send_face_data(host, username, password, remote_dir, port)


def _insightface_export_face_data(self):
    progress = tk.Toplevel(self.root)
    progress.title("Exporting Face Data")
    progress.configure(bg=CARD)
    progress.geometry("360x150")
    progress.minsize(360, 150)
    progress.resizable(False, False)
    progress.transient(self.root)
    progress.protocol("WM_DELETE_WINDOW", lambda: None)

    wrap = tk.Frame(progress, bg=CARD, padx=24, pady=22)
    wrap.pack(fill="both", expand=True)

    tk.Label(
        wrap,
        text="Exporting face data",
        bg=CARD,
        fg=TEXT_PRI,
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w")
    status = tk.Label(
        wrap,
        text="Creating export package...",
        bg=CARD,
        fg=TEXT_HINT,
        font=("Segoe UI", 10),
        justify="left",
    )
    status.pack(anchor="w", pady=(8, 14))

    bar = ttk.Progressbar(wrap, mode="indeterminate", length=280)
    bar.pack(fill="x")
    bar.start(12)

    progress.update_idletasks()
    x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - progress.winfo_width()) // 2)
    y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - progress.winfo_height()) // 2)
    progress.geometry(f"+{x}+{y}")
    progress.lift()
    progress.update()

    def finish(ok, message, extra):
        try:
            bar.stop()
            progress.destroy()
        except Exception:
            pass
        self.log(message, "success" if ok else "error")
        if ok:
            self._styled_alert(
                "Export Complete",
                f"Face data exported successfully.\n\nFile:\n{extra.get('filename', '')}",
                "success",
            )
        else:
            self._styled_alert("Export Failed", message, "error")

    def worker():
        try:
            ok, message, extra = self.face_service.export_face_data_to_folder()
        except Exception as exc:
            ok, message, extra = False, f"Export failed: {exc}", {}
        self.root.after(0, lambda ok=ok, message=message, extra=extra: finish(ok, message, extra))

    self.root.after(100, lambda: Thread(target=worker, daemon=True, name="InsightFaceExport").start())


FaceRecognitionApp._create_face_data_zip = _insightface_create_face_data_zip
FaceRecognitionApp._load_encoding_data_safe = _insightface_dlib_removed
FaceRecognitionApp._api_remove_user_from_encodings = _insightface_dlib_removed
FaceRecognitionApp.delete_user_from_encodings = _insightface_dlib_removed
FaceRecognitionApp.refresh_dataset = _insightface_refresh_dataset
FaceRecognitionApp._select_user = _insightface_select_user
FaceRecognitionApp.start_capture = _insightface_start_capture
FaceRecognitionApp._api_capture_user_request = _insightface_api_capture_user_request
FaceRecognitionApp._api_train_request = _insightface_api_train_request
FaceRecognitionApp._api_delete_user_request = _insightface_api_delete_user_request
FaceRecognitionApp.delete_user = _insightface_delete_user
FaceRecognitionApp.export_face_data_to_folder = _insightface_export_face_data_to_folder
FaceRecognitionApp.list_server_face_data_zips = _insightface_list_server_face_data_zips
FaceRecognitionApp.import_face_data_from_zip = _insightface_import_face_data_from_zip
FaceRecognitionApp._import_face_data_zip = _insightface_import_face_data_zip
FaceRecognitionApp.get_sftp_import_target = _insightface_get_sftp_import_target
FaceRecognitionApp.prepare_sftp_download_package = _insightface_prepare_sftp_download_package
FaceRecognitionApp.sftp_send_face_data = _insightface_sftp_send_face_data
FaceRecognitionApp.export_face_data = _insightface_export_face_data


# --------------------------------------------------------
# Entry point
# --------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = FaceRecognitionApp(root)
    root.mainloop()
