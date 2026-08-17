import sys
import ctypes
import platform
import os
import json
import html
import requests
import xml.etree.ElementTree as ET
from threading import Thread
from datetime import datetime

try:
    import cv2
except Exception:
    cv2 = None

from PySide6.QtCore import (
    Qt, QTimer, QDateTime, QRectF, QRect, QPoint,
    QPropertyAnimation, QEasingCurve, Property, QObject, Signal
)
from PySide6.QtGui import (
    QFont, QPainter, QPen, QColor, QIcon, QPixmap, QImage, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMainWindow,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QWidget,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QLineEdit,
    QCheckBox,
    QDialog,
    QGraphicsBlurEffect,
)


class Theme:
    BG = "#F4F4F4"
    SURFACE = "#F9F9F9"
    SURFACE_LOW = "#F3F3F3"
    CARD = "rgba(255,255,255,0.72)"
    BORDER = "#C4C7C7"
    TEXT = "#1A1C1C"
    SECONDARY = "#5E5E5E"
    MUTED = "#858383"
    PRIMARY = "#000000"
    GREEN = "#16A34A"
    GREEN_CARD = "#3F9468"
    RED = "#DC2626"

class UiBridge(QObject):
    """Thread-safe bridge for running callbacks on the Qt main thread."""
    run_callback = Signal(object)

    def __init__(self):
        super().__init__()
        self.run_callback.connect(lambda callback: callback())




# ============================================================
# Legacy LockApp logic constants copied from lockapp.py
# ============================================================
# v193 runtime data location.
# Source mode: keep runtime files inside sas_dashboard_modular for developer testing.
# PyInstaller EXE mode: keep runtime files beside SAS.exe in SAS_Data so users
# do not need to open PyInstaller's _internal folder.
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RUNTIME_DATA_DIR = os.path.join(APP_DIR, "SAS_Data")
else:
    APP_DIR = SOURCE_DIR
    RUNTIME_DATA_DIR = SOURCE_DIR

os.makedirs(RUNTIME_DATA_DIR, exist_ok=True)

ADMIN_FILE = os.path.join(RUNTIME_DATA_DIR, "admins.txt")
USERS_FILE = os.path.join(RUNTIME_DATA_DIR, "users.txt")
CRED_FILE = os.path.join(RUNTIME_DATA_DIR, "credential.txt")
SAS_CLIENT_ID_FILE = os.path.join(RUNTIME_DATA_DIR, "sas_client_id.txt")
WEBSOCKET_UNLOCK_PATH = "/ws/sas"
UNLOCK_LOG_FILE = os.path.join(RUNTIME_DATA_DIR, "unlock_log.txt")
LOCAL_SAS_LOG_DIR = os.path.join(RUNTIME_DATA_DIR, "SAS_LOG")
SCAN_VALID_SECONDS = 120
DEFAULT_LOCK_TIMEOUT_SECONDS = 300
DOMAIN = "corp.JABIL.ORG"
SERVER_PATH = r"C:\temp"
SOAP_URL = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"

# ============================================================
# Legacy LockApp logic constants copied from lockapp.py
# ============================================================
# Runtime file paths are defined above using APP_DIR.
SCAN_VALID_SECONDS = 120
DEFAULT_LOCK_TIMEOUT_SECONDS = 300
DOMAIN = "corp.JABIL.ORG"
SERVER_PATH = r"C:\temp"
SOAP_URL = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"


# ============================================================
# Built-in emergency/admin login
# ============================================================
# Local fallback admin account for SAS login when AD is unavailable.
# Keep this account restricted and change/remove it before production if required.
HARDCODED_ADMIN_ID = os.environ.get("SAS_HARDCODED_ADMIN_ID", "admin")
HARDCODED_ADMIN_PASSWORD = os.environ.get("SAS_HARDCODED_ADMIN_PASSWORD", "penAteam")

# ============================================================
# Backend SFTP pull configuration for Transfer to Windows
# ============================================================
# Transfer to Windows uses SFTP pull mode. SAS connects to the currently
# connected Pi host/IP, uses this fixed backend username, and derives the
# Pi SSH password from the connected Pi hostname. The user does not type
# Pi SSH credentials in the popup.
PI_SFTP_USERNAME = os.environ.get("SAS_PI_SFTP_USERNAME", "jbl_facerec")
PI_SFTP_PORT = int(os.environ.get("SAS_PI_SFTP_PORT", "22"))
