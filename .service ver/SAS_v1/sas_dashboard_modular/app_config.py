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
ADMIN_FILE = "admins.txt"
USERS_FILE = "users.txt"
CRED_FILE = "credential.txt"
RECOGNITION_RESULT_FILE = "recognition_result.json"
UNLOCK_LOG_FILE = "unlock_log.txt"
SCAN_VALID_SECONDS = 120
DEFAULT_LOCK_TIMEOUT_SECONDS = 300
DOMAIN = "corp.JABIL.ORG"
SERVER_PATH = r"C:\temp"
SOAP_URL = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"

# ============================================================
# Legacy LockApp logic constants copied from lockapp.py
# ============================================================
ADMIN_FILE = "admins.txt"
USERS_FILE = "users.txt"
CRED_FILE = "credential.txt"
RECOGNITION_RESULT_FILE = "recognition_result.json"
UNLOCK_LOG_FILE = "unlock_log.txt"
SCAN_VALID_SECONDS = 120
DEFAULT_LOCK_TIMEOUT_SECONDS = 300
DOMAIN = "corp.JABIL.ORG"
SERVER_PATH = r"C:\temp"
SOAP_URL = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"
