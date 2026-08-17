import sys
import ctypes
import platform
import os
import time
import json
import html
import requests
import subprocess
import socket
from urllib.parse import quote
try:
    import paramiko
except Exception:
    paramiko = None
import xml.etree.ElementTree as ET
from threading import Thread, Lock
from datetime import datetime
import uuid
from typing import Any, cast

try:
    import cv2
except Exception:
    cv2 = None

from PySide6.QtCore import (
    Qt, QTimer, QDateTime, QRectF, QRect, QPoint, QEvent,
    QPropertyAnimation, QEasingCurve, Property, QObject, Signal
)
from PySide6.QtGui import (
    QFont, QPainter, QPen, QColor, QIcon, QPixmap, QImage, QPainterPath, QIntValidator
)
from PySide6.QtWidgets import (
    QGraphicsEffect,
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
    QGraphicsDropShadowEffect,
    QLineEdit,
    QCheckBox,
    QDialog,
    QGraphicsBlurEffect,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QSystemTrayIcon,
    QListWidget,
    QProgressBar,
)

from app_config import *
from ui_components import *
from dialogs import *

from services.admin_service import AdminService
from services.credential_service import CredentialService
from services.ad_service import ActiveDirectoryService
from services.face_api_service import FaceApiService
from services.websocket_client_service import WebSocketRecognitionClient
from services.runtime_lock_service import RuntimeLockService

from paths import app_resource_path
from views.widgets import ExportCircleSpinnerWidget, SftpEnterKeyFilter
