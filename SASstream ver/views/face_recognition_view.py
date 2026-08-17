from __future__ import annotations

import html
import os
import time
import uuid
from datetime import datetime
from threading import Thread
from typing import Any, cast

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency guard
    cv2 = None

from PySide6.QtCore import QDateTime, QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app_config import *
from dialogs import *
from ui_components import *


class FaceRecognitionViewMixin:
    def build_face_page(self: Any):
        outer = QWidget()
        outer.setObjectName("Page")

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("MainContent")
        main.setMaximumWidth(self.content_max_width())
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(main)
        mx = 28 if not self.compact_mode else 18
        # Match the provided Face Recognition console composition:
        # compact top gap, left control/directory column and large right camera/log area.
        mt = 8 if not self.compact_mode else 5
        mb = 8 if not self.compact_mode else 5
        main_layout.setContentsMargins(mx, mt, mx, mb)
        main_layout.setSpacing(0)

        console = QHBoxLayout()
        console.setSpacing(24 if not self.compact_mode else 16)
        console.setContentsMargins(0, 0, 0, 0)

        # Left column, similar to the HTML reference:
        # [ Control Panel ]
        # [ Authorized Personnel / Users ]
        left_column = QVBoxLayout()
        left_column.setSpacing(16 if not self.compact_mode else 12)
        left_column.setContentsMargins(0, 0, 0, 0)

        # Right column, similar to the HTML reference:
        # [ Large camera console ]
        # [ Activity terminal / System Log ]
        right_column = QVBoxLayout()
        right_column.setSpacing(16 if not self.compact_mode else 12)
        right_column.setContentsMargins(0, 0, 0, 0)

        controls = self.face_controls_card()
        users = self.face_users_card()
        camera = self.camera_feed_card()
        logs = self.system_log_card()

        self.face_cards = [camera, controls, logs, users]
        self.update_face_card_sizes()

        left_column.addWidget(controls, 0)
        left_column.addWidget(users, 1)
        right_column.addWidget(camera, 1)
        right_column.addWidget(logs, 0)

        console.addLayout(left_column, 3)
        console.addLayout(right_column, 9)
        main_layout.addLayout(console, 1)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    def camera_feed_card(self: Any):
        card = QFrame()
        card.setObjectName("CameraFeedCard")
        card.setMinimumHeight(250 if not self.compact_mode else 215)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addStretch()

        self.camera_state_badge = QLabel("●  End")
        self.camera_state_badge.setObjectName("CameraStateEndBadge")
        self.camera_state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_state_badge.setFixedHeight(24 if not self.compact_mode else 22)
        self.camera_state_badge.setMinimumWidth(72 if not self.compact_mode else 64)

        top.addWidget(self.camera_state_badge)

        self.camera_preview_label = QLabel("Camera preview loading...")
        self.camera_preview_label.setObjectName("CameraPreviewLabel")
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setScaledContents(False)
        self.camera_preview_label.setMinimumHeight(170 if not self.compact_mode else 135)
        self.camera_preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        layout.addLayout(top)
        layout.addWidget(self.camera_preview_label, 1)

        QTimer.singleShot(300, self.check_pi_camera_status_and_update_panel)
        return card

    def check_pi_camera_status_and_update_panel(self: Any):
        host = str(getattr(self, "pi_api_host", "") or "").strip()
        if not host:
            self.append_face_log("CAMERA_SKIPPED: camera hostname/IP is not configured.")
            return

        """Check local status before opening /video-feed.

        This prevents startup from showing a stale MJPEG frame when the RTSP camera
        is already stopped.
        """
        # If camera is connected, always verify /status instead of trusting old
        # _camera_user_stopped state from a previous disconnect.
        if getattr(self, "_camera_user_stopped", False) and not getattr(self, "pi_connected", False):
            self.show_camera_stopped_prompt("Camera stopped")
            return

        def preview_has_recent_frame(max_age: float = 30.0) -> bool:
            try:
                from services.local_recognition_engine import ENGINE

                age = ENGINE.last_frame_age_seconds()
                return bool(
                    getattr(self, "_camera_preview_running", False)
                    and ENGINE.latest_frame is not None
                    and age is not None
                    and age <= max_age
                )
            except Exception:
                return False

        self.set_pi_status_label(checking=True)

        def worker():
            try:
                self._local_face_base_url()
                data = self._local_face_request("GET", "/status", timeout=8, host_override=host)

                rec = bool(data.get("recognition_running", False))
                cap = bool(data.get("capture_running", False))
                stream_healthy = bool(data.get("stream_healthy", False))
                stream_recovering = bool(data.get("stream_recovering", False))
                if not stream_healthy:
                    state = str(data.get("connection_state") or "unknown").strip()
                    error = str(data.get("last_error") or "no fresh RTSP frame").strip()
                    resolved_ip = str(data.get("resolved_ip") or "").strip()
                    address = f" ({resolved_ip})" if resolved_ip else ""
                    reason = f"RTSP stream offline for {host}{address}. State={state}; Error={error}"

                    def disconnected(reason=reason):
                        self.append_face_log(f"CAMERA_STATUS_OFFLINE: {reason}")
                        in_grace = time.monotonic() < float(getattr(self, "_camera_disconnect_grace_until", 0.0) or 0.0)
                        if rec or cap or stream_recovering or in_grace or self.is_local_rtsp_active_for_ui():
                            self.pi_connection_checked = True
                            self.pi_connected = True
                            self._camera_user_stopped = False
                            self.set_face_controls_connection_enabled(True)
                            self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                            self.update_pi_connect_ui_state(connected=True)
                            self._handling_pi_disconnect = False
                            self.set_camera_state_badge(True)
                            if not getattr(self, "_camera_preview_running", False):
                                self.start_camera_preview(force=True)
                            return

                        self.stop_camera_preview(show_prompt=True)
                        quiet_until = float(getattr(self, "_startup_disconnect_warning_suppressed_until", 0.0) or 0.0)
                        if time.monotonic() < quiet_until:
                            self.pi_connection_checked = True
                            self.pi_connected = False
                            self.set_face_controls_connection_enabled(False)
                            self.set_pi_status_label(connected=False, message="Status: Waiting for camera...")
                            self.suspend_locking_for_pi_disconnect(reason)
                            self.start_pi_disconnect_retry_loop(reason)
                        else:
                            self.handle_pi_runtime_disconnect(reason)

                    self.qt_after(0, disconnected)
                    return

                def done():
                    if str(locals().get("origin", locals().get("origin_safe", "")) or "") == "settings":
                        self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self._camera_connected_once_this_run = True
                    self.pi_api_host = host
                    self.pi_api_port = "5000"
                    self._local_face_base_url()
                    self.resume_locking_after_pi_reconnect()
                    self.set_face_capture_in_progress(cap)
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self._handling_pi_disconnect = False

                    # An explicit SAS Stop must remain stopped in the Windows UI.
                    # The camera can need a short cleanup interval before /status changes,
                    # so do not re-open the preview just because one status response
                    # still reports an active camera mode.
                    if getattr(self, "_camera_user_stopped", False):
                        self.stop_camera_preview(show_prompt=True)
                    elif rec or cap:
                        if preview_has_recent_frame():
                            self.set_camera_state_badge(True)
                        elif not getattr(self, "_camera_preview_running", False):
                            self.start_camera_preview(force=True)
                        else:
                            self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                            self.set_camera_state_badge(True)
                    else:
                        self.stop_camera_preview(show_prompt=True)
                        self.append_face_log("CAMERA_STATUS: camera service online, camera is stopped.")

                    # Keep Dashboard and Face Recognition authorised users aligned.
                    self._local_face_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.append_face_log(f"CAMERA_STATUS_FAILED: {err}")
                    in_grace = time.monotonic() < float(getattr(self, "_camera_disconnect_grace_until", 0.0) or 0.0)
                    if preview_has_recent_frame() or in_grace or self.is_local_rtsp_active_for_ui():
                        self.pi_connection_checked = True
                        self.pi_connected = True
                        self._camera_user_stopped = False
                        self.set_face_controls_connection_enabled(True)
                        self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                        self.update_pi_connect_ui_state(connected=True)
                        self.set_camera_state_badge(True)
                        return
                    self.stop_camera_preview(show_prompt=True)
                    quiet_until = float(getattr(self, "_startup_disconnect_warning_suppressed_until", 0.0) or 0.0)
                    reason = "Camera disconnected or unreachable. Please check camera."
                    if time.monotonic() < quiet_until:
                        self.pi_connection_checked = True
                        self.pi_connected = False
                        self.set_face_controls_connection_enabled(False)
                        self.set_pi_status_label(connected=False, message="Status: Waiting for camera...")
                        self.suspend_locking_for_pi_disconnect(reason)
                        self.start_pi_disconnect_retry_loop(reason)
                    else:
                        self.handle_pi_runtime_disconnect(reason)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()

    def set_camera_state_badge(self: Any, live: bool = False, stopped: bool = False):
        if not hasattr(self, "camera_state_badge"):
            return

        if stopped:
            self.camera_state_badge.setText("●  Stop")
            self.camera_state_badge.setObjectName("CameraStateStopBadge")
        elif live:
            self.camera_state_badge.setText("●  Live")
            self.camera_state_badge.setObjectName("CameraStateLiveBadge")
        else:
            try:
                if callable(getattr(self, "is_local_rtsp_active_for_ui", None)) and self.is_local_rtsp_active_for_ui():
                    self.camera_state_badge.setText("●  Live")
                    self.camera_state_badge.setObjectName("CameraStateLiveBadge")
                    self.camera_state_badge.style().unpolish(self.camera_state_badge)
                    self.camera_state_badge.style().polish(self.camera_state_badge)
                    self.camera_state_badge.update()
                    return
                from services.local_recognition_engine import ENGINE

                frame_age = ENGINE.last_frame_age_seconds()
                if (
                    getattr(self, "_camera_preview_running", False)
                    and ENGINE.latest_frame is not None
                    and frame_age is not None
                    and frame_age <= 30.0
                ):
                    self.camera_state_badge.setText("●  Live")
                    self.camera_state_badge.setObjectName("CameraStateLiveBadge")
                    self.camera_state_badge.style().unpolish(self.camera_state_badge)
                    self.camera_state_badge.style().polish(self.camera_state_badge)
                    self.camera_state_badge.update()
                    return
            except Exception:
                pass
            self.camera_state_badge.setText("●  End")
            self.camera_state_badge.setObjectName("CameraStateEndBadge")

        self.camera_state_badge.style().unpolish(self.camera_state_badge)
        self.camera_state_badge.style().polish(self.camera_state_badge)
        self.camera_state_badge.update()

    def is_local_rtsp_active_for_ui(self: Any, max_frame_age: float = 60.0) -> bool:
        """Return True when UI should remain Connected during RTSP recovery."""
        if getattr(self, "_camera_manual_disconnected", False):
            return False
        host = str(getattr(self, "pi_api_host", "") or "").strip().lower()
        if not host:
            return False
        try:
            from services.local_recognition_engine import ENGINE

            engine_host = str(getattr(ENGINE, "host", "") or "").strip().lower()
            if engine_host and engine_host != host:
                return False
            status = ENGINE.status()
            frame_age = status.get("last_frame_age_seconds")
            recent_frame = bool(
                ENGINE.latest_frame is not None
                and frame_age is not None
                and float(frame_age) <= max_frame_age
            )
            state = str(status.get("connection_state") or "").strip().lower()
            in_grace = time.monotonic() < float(getattr(self, "_camera_disconnect_grace_until", 0.0) or 0.0)
            return bool(
                status.get("recognition_running", False)
                or status.get("capture_running", False)
                or status.get("stream_healthy", False)
                or status.get("stream_recovering", False)
                or recent_frame
                or in_grace
                or state in {"starting", "connecting", "live", "stale", "restarting"}
            )
        except Exception:
            return False

    def show_camera_stopped_prompt(self: Any, message: str = "Camera stopped"):
        """Blacken camera panel and prompt user after Stop is pressed.

        Important: clear the QLabel pixmap first. Otherwise the last video frame
        can remain painted until the second Stop click.
        """
        if not hasattr(self, "camera_preview_label"):
            return
        if (
            bool(getattr(self, "pi_connected", False))
            and not bool(getattr(self, "_camera_user_stopped", False))
            and self.is_local_rtsp_active_for_ui()
        ):
            self.set_camera_state_badge(True)
            self.append_face_log(f"CAMERA_STOP_PROMPT_SUPPRESSED: {message}")
            if not getattr(self, "_camera_preview_running", False):
                self.start_camera_preview(force=True)
            return

        self.camera_preview_label.clear()
        self.camera_preview_label.setPixmap(QPixmap())
        self.camera_preview_label.setObjectName("CameraPreviewStoppedLabel")
        self.camera_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview_label.setText(
            f"{message}\n\nPress Recognize to start camera again."
        )

        self.camera_preview_label.style().unpolish(self.camera_preview_label)
        self.camera_preview_label.style().polish(self.camera_preview_label)
        self.camera_preview_label.repaint()
        self.camera_preview_label.update()

        self.set_camera_state_badge(stopped=True)
        QApplication.processEvents()

    def pause_camera_for_modal(self: Any):
        """Temporarily pause camera repainting while a heavy popup animation is shown."""
        self._modal_open_count = getattr(self, "_modal_open_count", 0) + 1

        timer = getattr(self, "camera_timer", None)
        if timer is not None:
            self._camera_resume_after_modal = True
            try:
                timer.stop()
            except Exception:
                pass

    def resume_camera_after_modal(self: Any):
        """Resume camera repainting after popup closes if it was active before."""
        self._modal_open_count = max(0, getattr(self, "_modal_open_count", 0) - 1)

        if self._modal_open_count > 0:
            return

        if getattr(self, "_camera_resume_after_modal", False):
            self._camera_resume_after_modal = False

            timer = getattr(self, "camera_timer", None)
            if (
                getattr(self, "camera_capture", None) is not None
                and timer is not None
                and not getattr(self, "_camera_user_stopped", False)
            ):
                try:
                    timer.start(66)
                except Exception:
                    pass

    def handle_camera_feed_unavailable(self: Any, reason: str = "RTSP camera feed unavailable."):
        """Camera feed failure is not always camera disconnect.

        The local recognition engine can be online while /video-feed is unavailable or stopped.
        In that case, keep camera connected and only show the camera-stopped prompt.
        Only mark Camera disconnected if /status also fails.
        """
        def worker():
            try:
                data = self._local_face_request("GET", "/status", timeout=5)
                rec = bool(data.get("recognition_running", False))
                cap = bool(data.get("capture_running", False))
                users = data.get("users", None)
                stream_healthy = bool(data.get("stream_healthy", False))
                stream_recovering = bool(data.get("stream_recovering", False))
                if (rec or cap or stream_recovering or getattr(self, "pi_connected", False)) and not stream_healthy:
                    state = str(data.get("connection_state") or "unknown").strip()
                    error = str(data.get("last_error") or "no fresh RTSP frame").strip()
                    reason = f"RTSP camera feed lost. State={state}; Error={error}"

                    def disconnected(reason=reason):
                        self.append_face_log(f"CAMERA_FEED_OFFLINE: {reason}")
                        self.pi_connection_checked = True
                        self.pi_connected = True
                        self.set_face_controls_connection_enabled(True)
                        self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                        self.update_pi_connect_ui_state(connected=True)
                        self.set_camera_state_badge(True)

                    self.qt_after(0, disconnected)
                    return

                def api_online():
                    stream_live = bool(stream_healthy or stream_recovering or self.is_local_rtsp_active_for_ui())
                    self.pi_connection_checked = True
                    self.pi_connected = stream_live
                    self.set_face_controls_connection_enabled(stream_live)
                    if stream_live:
                        self._camera_user_stopped = False
                        message = "Status: Connected" if stream_healthy else "Status: Connected | camera feed recovering"
                        self.set_pi_status_label(connected=True, message=message)
                        self.update_pi_connect_ui_state(connected=True)
                    else:
                        self.set_pi_status_label(connected=False)
                    self._handling_pi_disconnect = False

                    self.set_camera_state_badge(stream_live)

                    if hasattr(self, "camera_preview_label"):
                        if stream_live:
                            self.append_face_log(f"CAMERA_FEED_RECOVERING: {reason} | keeping last preview frame")
                            if not getattr(self, "_camera_preview_running", False):
                                self.start_camera_preview(force=True)
                            return
                        self._camera_preview_running = False
                        self.camera_capture = None
                        self.camera_preview_label.setPixmap(QPixmap())
                        if rec or cap:
                            self.camera_preview_label.setText("Camera feed unavailable.\ncamera service is online. Please retry Recognize or check camera.")
                        else:
                            self.show_camera_stopped_prompt("Camera stopped")

                    self.append_face_log(f"CAMERA_FEED_UNAVAILABLE: {reason} | API online")

                    # Keep authorised users/dashboard consistent if /status only returns count.
                    try:
                        self._local_face_refresh_users()
                    except Exception:
                        pass

                self.qt_after(0, api_online)

            except Exception:
                self.qt_after(0, lambda: self.handle_pi_runtime_disconnect("Camera disconnected or unreachable. Please check camera power/network/source."))

        Thread(target=worker, daemon=True).start()

    def handle_pi_runtime_disconnect(self: Any, reason: str = "Camera disconnected. Please check camera power/network/source and reconnect from Settings."):
        """Handle camera shutdown / network loss without freezing the SAS UI."""
        try:
            from services.local_recognition_engine import ENGINE

            status = ENGINE.status()
            frame_age = status.get("last_frame_age_seconds")
            recent_frame = (
                ENGINE.latest_frame is not None
                and frame_age is not None
                and float(frame_age) <= 30.0
            )
            engine_active = bool(status.get("recognition_running", False) or status.get("capture_running", False))
            connection_state = str(status.get("connection_state") or "").strip().lower()
            recovering_state = connection_state in {"starting", "connecting", "live", "stale", "restarting"}
            now = time.monotonic()
            candidate_since = float(getattr(self, "_runtime_disconnect_candidate_since", 0.0) or 0.0)
            in_grace = now < float(getattr(self, "_camera_disconnect_grace_until", 0.0) or 0.0)
            if bool(status.get("stream_recovering", False)) or recent_frame or engine_active or recovering_state or in_grace:
                if not recent_frame and not bool(status.get("stream_recovering", False)):
                    if candidate_since <= 0.0:
                        self._runtime_disconnect_candidate_since = now
                        candidate_since = now
                    if now - candidate_since > 60.0 and not recovering_state and not in_grace:
                        raise RuntimeError("RTSP engine stayed offline beyond recovery grace.")
                else:
                    self._runtime_disconnect_candidate_since = 0.0
                self.pi_connection_checked = True
                self.pi_connected = True
                self._camera_user_stopped = False
                self.set_face_controls_connection_enabled(True)
                self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                self.update_pi_connect_ui_state(connected=True)
                self.set_camera_state_badge(True)
                if not getattr(self, "_camera_preview_running", False):
                    self.start_camera_preview(force=True)
                self.append_face_log(f"CAMERA_RECOVERING: {reason}")
                return
        except Exception:
            pass

        if getattr(self, "_handling_pi_disconnect", False):
            return

        self._handling_pi_disconnect = True

        try:
            self.pi_connection_checked = True
            self.pi_connected = False
            self.set_face_controls_connection_enabled(False)
            self.set_pi_status_label(connected=False)
            self.update_pi_connect_ui_state(connected=False)
            self._camera_user_stopped = True

            # Stop preview state without doing blocking OpenCV work on the UI thread.
            self._camera_preview_running = False
            if hasattr(self, "camera_timer") and self.camera_timer is not None:
                try:
                    self.camera_timer.stop()
                except Exception:
                    pass
                self.camera_timer = None

            self.camera_capture = None

            if hasattr(self, "camera_preview_label"):
                self.camera_preview_label.setPixmap(QPixmap())
                self.camera_preview_label.setText("Camera disconnected.\nPlease check camera power/network/source and reconnect from Settings.")

            self.set_camera_state_badge(False)
            self.clear_all_authorized_users_ui()
            self.append_face_log(f"CAMERA_DISCONNECTED: {reason}")
            self._allow_settings_disconnect_popup_once = True
            self.suspend_locking_for_pi_disconnect(reason)
            self.show_pi_disconnect_alert_if_needed(reason, force=True, origin="runtime-watchdog")
            self.start_pi_disconnect_retry_loop(reason)

        finally:
            # Allow a future disconnect popup after user reconnects/fails again.
            self.qt_after(1200, lambda: setattr(self, "_handling_pi_disconnect", False))

    def _draw_recognition_overlay_rgb(self: Any, frame_rgb, match):
        """Draw the latest recognition state on a preview frame."""
        if frame_rgb is None or match is None or cv2 is None:
            return frame_rgb

        cv2_mod = cast(Any, cv2)

        try:
            bbox = match.get("bbox") if isinstance(match, dict) else getattr(match, "bbox", None)
            if not bbox or len(bbox) != 4:
                return frame_rgb

            frame_h, frame_w = frame_rgb.shape[:2]
            left, top, right, bottom = [int(round(float(value))) for value in bbox]
            left = max(0, min(left, frame_w - 1))
            right = max(0, min(right, frame_w - 1))
            top = max(0, min(top, frame_h - 1))
            bottom = max(0, min(bottom, frame_h - 1))

            if right <= left or bottom <= top:
                return frame_rgb

            name = match.get("name") if isinstance(match, dict) else getattr(match, "name", "")
            employee_id = match.get("employee_id") if isinstance(match, dict) else getattr(match, "employee_id", "")
            confidence = match.get("confidence") if isinstance(match, dict) else getattr(match, "confidence", 0.0)
            name = str(name or "").strip()
            employee_id = str(employee_id or "").strip()
            try:
                confidence_percent = float(str(confidence).replace("%", ""))
                if confidence_percent <= 1.0:
                    confidence_percent *= 100.0
            except Exception:
                confidence_percent = 0.0
            confidence_percent = max(0.0, min(100.0, confidence_percent))
            confidence_text = f"{confidence_percent:.2f}%"

            is_registered = bool(employee_id)
            state = "REGISTERED" if is_registered else "UNKNOWN"
            label = (
                f"{state} | {name or 'Unknown'} | {employee_id} | {confidence_text}"
                if is_registered
                else f"{state} | {confidence_text}"
            )

            color = (22, 163, 74) if is_registered else (220, 38, 38)
            text_color = (255, 255, 255)
            font = cv2_mod.FONT_HERSHEY_SIMPLEX
            font_scale = 0.72 if frame_w >= 900 else 0.56
            thickness = 2

            # Keep long names/IDs inside the image instead of clipping off-screen.
            while font_scale > 0.36:
                (text_w, text_h), baseline = cv2_mod.getTextSize(label, font, font_scale, thickness)
                if text_w <= frame_w - 16:
                    break
                font_scale -= 0.04

            (text_w, text_h), baseline = cv2_mod.getTextSize(label, font, font_scale, thickness)
            pad_x = 10
            pad_y = 7
            label_w = min(text_w + pad_x * 2, frame_w)
            label_h = text_h + baseline + pad_y * 2

            box_thickness = 3 if frame_w >= 900 else 2
            cv2_mod.rectangle(frame_rgb, (left, top), (right, bottom), color, box_thickness)

            label_left = max(0, min(left, frame_w - label_w))
            if top - label_h - 4 >= 0:
                label_top = top - label_h - 4
            else:
                label_top = min(bottom + 4, max(0, frame_h - label_h))
            label_top = max(0, label_top)
            label_bottom = min(frame_h, label_top + label_h)

            cv2_mod.rectangle(
                frame_rgb,
                (label_left, label_top),
                (label_left + label_w, label_bottom),
                color,
                -1,
            )
            cv2_mod.putText(
                frame_rgb,
                label,
                (label_left + pad_x, label_bottom - baseline - pad_y),
                font,
                font_scale,
                text_color,
                thickness,
                cv2_mod.LINE_AA,
            )
        except Exception as e:
            self.append_face_log(f"CAMERA_OVERLAY_FAILED: {e}")

        return frame_rgb

    def render_camera_frame_from_worker(self: Any, frame):
        """Render camera frame sent from background camera worker.

        This keeps OpenCV read() away from the Qt UI thread, preventing
        the whole SAS app from becoming Not Responding when camera power/network/source drops.
        """
        if getattr(self, "_modal_open_count", 0) > 0:
            return

        if frame is None or not hasattr(self, "camera_preview_label"):
            return

        if cv2 is None:
            return

        cv2_mod = cast(Any, cv2)

        try:
            frame = cv2_mod.cvtColor(frame, cv2_mod.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w

            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimg).scaled(
                self.camera_preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            self.camera_preview_label.setPixmap(pixmap)

            self.camera_frame_count += 1
            now = datetime.now()
            if self.camera_last_tick is not None:
                elapsed = (now - self.camera_last_tick).total_seconds()
                if elapsed >= 1.0:
                    self.camera_fps = int(self.camera_frame_count / elapsed)
                    self.camera_frame_count = 0
                    self.camera_last_tick = now

            self.set_camera_state_badge(True)
            self._runtime_disconnect_candidate_since = 0.0

        except Exception as e:
            self.append_face_log(f"CAMERA_RENDER_FAILED: {e}")

    def start_camera_preview(self: Any, force: bool = False):
        """Start preview from the single local recognition capture.

        Do not open a second OpenCV VideoCapture here.  The local recognition
        engine owns the RTSP connection, and the UI only paints its latest
        decoded frame.  This avoids FFmpeg thread assertions when the stream is
        already being decoded for unlock recognition.
        """
        if not hasattr(self, "camera_preview_label"):
            return

        if getattr(self, "_camera_user_stopped", False) and not force:
            self.show_camera_stopped_prompt("Camera stopped")
            return

        if cv2 is None:
            self.camera_preview_label.setText(
                "OpenCV is required for API video-feed preview.\n"
                "Install opencv-python on this Windows app."
            )
            self.set_camera_state_badge(False)
            return

        if getattr(self, "_camera_preview_running", False):
            return

        self._local_face_base_url()
        self.camera_feed_url = self.local_face_service.rtsp_url()

        has_recent_engine_frame = False
        try:
            from services.local_recognition_engine import ENGINE

            age = ENGINE.last_frame_age_seconds()
            has_recent_engine_frame = bool(ENGINE.latest_frame is not None and age is not None and age <= 30.0)
        except Exception:
            pass

        self.camera_preview_label.setObjectName("CameraPreviewLabel")
        self.camera_preview_label.style().unpolish(self.camera_preview_label)
        self.camera_preview_label.style().polish(self.camera_preview_label)
        if not has_recent_engine_frame:
            self.camera_preview_label.setPixmap(QPixmap())
            self.camera_preview_label.setText("Connecting to RTSP camera feed...")
            self.set_camera_state_badge(bool(getattr(self, "pi_connected", False)))
        else:
            self.set_camera_state_badge(True)

        self._camera_preview_running = True
        self._camera_preview_generation = int(getattr(self, "_camera_preview_generation", 0) or 0) + 1
        preview_generation = int(getattr(self, "_camera_preview_generation", 0) or 0)
        self.camera_frame_count = 0
        self.camera_last_tick = datetime.now()
        self.camera_capture = None

        def camera_worker():
            cv2_worker = cast(Any, cv2)
            fail_count = 0

            try:
                from services.local_recognition_engine import ENGINE

                if not ENGINE.running:
                    ENGINE.configure(getattr(self, "pi_api_host", ""))
                    ENGINE.start()

                self.qt_after(0, lambda: self.append_face_log("CAMERA_FEED: Using local recognition stream"))
                self.qt_after(0, lambda: self.set_camera_state_badge(True))

                def show_waiting_message(clear_preview: bool = True):
                    if (
                        not getattr(self, "_camera_preview_running", False)
                        or preview_generation != int(getattr(self, "_camera_preview_generation", 0) or 0)
                    ):
                        return
                    try:
                        frame_age = ENGINE.last_frame_age_seconds()
                    except Exception:
                        frame_age = None
                    if ENGINE.latest_frame is not None and frame_age is not None and frame_age <= 30.0:
                        self.set_camera_state_badge(True)
                        return
                    if ENGINE.running or getattr(self, "pi_connected", False):
                        self.set_camera_state_badge(True)
                    else:
                        self.set_camera_state_badge(False)
                    if hasattr(self, "camera_preview_label"):
                        if clear_preview:
                            self.camera_preview_label.setPixmap(QPixmap())
                        self.camera_preview_label.setText(
                            "Waiting for RTSP camera feed...\n"
                            "Preview and face unlock will resume automatically when the source is online."
                        )

                while (
                    getattr(self, "_camera_preview_running", False)
                    and preview_generation == int(getattr(self, "_camera_preview_generation", 0) or 0)
                ):
                    frame_rgb = ENGINE.latest_frame if ENGINE.stream_healthy() else None
                    if frame_rgb is None:
                        try:
                            frame_age = ENGINE.last_frame_age_seconds()
                        except Exception:
                            frame_age = None
                        if (
                            ENGINE.latest_frame is not None
                            and frame_age is not None
                            and frame_age <= 15.0
                        ):
                            frame_rgb = ENGINE.latest_frame

                    if frame_rgb is None:
                        fail_count += 1
                        if fail_count == 1:
                            self.qt_after(0, lambda: self.set_camera_state_badge(bool(getattr(self, "pi_connected", False))))
                        if fail_count == 40:
                            self.qt_after(0, lambda: show_waiting_message(True))
                            self.qt_after(0, lambda: self.append_face_log("CAMERA_FEED: Waiting for local RTSP frame..."))
                        if fail_count % 150 == 0:
                            self.qt_after(0, lambda: show_waiting_message(True))
                        time.sleep(0.12)
                        continue

                    fail_count = 0

                    match = getattr(ENGINE, "latest_match", None)
                    overlay_frame = self._draw_recognition_overlay_rgb(frame_rgb.copy(), match)
                    frame_copy = cv2_worker.cvtColor(overlay_frame, cv2_worker.COLOR_RGB2BGR)
                    self.qt_after(0, lambda f=frame_copy: self.render_camera_frame_from_worker(f))

                    time.sleep(0.06)

            except Exception as e:
                err = str(e)
                self.qt_after(0, lambda err=err: self.handle_camera_feed_unavailable(f"Local camera preview error: {err}"))

            finally:
                if preview_generation == int(getattr(self, "_camera_preview_generation", 0) or 0):
                    self.camera_capture = None
                    self._camera_preview_running = False

        Thread(target=camera_worker, daemon=True).start()

    def update_camera_frame(self: Any):
        """Compatibility no-op.

        Camera frames are now read in a background worker thread to avoid UI
        freeze when camera is powered off or network drops.
        """
        return

    def face_controls_card(self: Any):
        card = GlassCard()
        card.setMinimumHeight(260 if not self.compact_mode else 238)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            20 if not self.compact_mode else 14,
            16 if not self.compact_mode else 12,
            20 if not self.compact_mode else 14,
            14 if not self.compact_mode else 10,
        )
        layout.setSpacing(7)

        title = QLabel("PRIMARY CONTROLS")
        title.setObjectName("FaceSectionTitle")
        layout.addWidget(title)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("NtidInput")
        self.name_input.setPlaceholderText("Enter employee name for registration")
        self.name_input.setClearButtonEnabled(True)
        self.name_input.setFixedHeight(34 if not self.compact_mode else 30)
        layout.addWidget(self.name_input)

        self.ntid_input = QLineEdit()
        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter employee ID / NTID for register / delete")
        self.ntid_input.setClearButtonEnabled(True)
        self.ntid_input.setFixedHeight(34 if not self.compact_mode else 30)
        self.ntid_input.textChanged.connect(self.clear_ntid_input_error)
        layout.addWidget(self.ntid_input)

        # Compact action area.
        # Row 1: Register
        # Row 2: Recognize full width
        # Row 3: Stop + Delete
        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(8)
        button_grid.setVerticalSpacing(8)

        capture = QPushButton("＋  CAPTURE")
        capture.setObjectName("OutlineActionButton")
        capture.setText("REGISTER")

        recognize = QPushButton("⌁  RECOGNIZE")
        recognize.setObjectName("GreenActionButton")

        stop = QPushButton("STOP")
        stop.setObjectName("StopButton")

        delete = QPushButton("DELETE")
        delete.setObjectName("DeleteButton")

        self.face_capture_btn = capture
        self.face_recognize_btn = recognize
        self.face_stop_btn = stop
        self.face_delete_btn = delete

        for btn in (capture, recognize, stop, delete):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        small_h = 32 if not self.compact_mode else 28
        main_h = 34 if not self.compact_mode else 30

        capture.setFixedHeight(main_h)
        recognize.setFixedHeight(main_h)
        stop.setFixedHeight(small_h)
        delete.setFixedHeight(small_h)

        capture.clicked.connect(self._local_face_capture_user)
        recognize.clicked.connect(self._local_face_get_result)
        stop.clicked.connect(self._local_face_stop_recognition)
        delete.clicked.connect(self._local_face_delete_user)

        button_grid.addWidget(capture, 0, 0, 1, 2)
        button_grid.addWidget(recognize, 1, 0, 1, 2)
        button_grid.addWidget(stop, 2, 0)
        button_grid.addWidget(delete, 2, 1)

        layout.addLayout(button_grid)
        layout.addStretch(1)

        # Disabled until local recognition engine connection is confirmed.
        QTimer.singleShot(0, lambda: self.set_face_controls_connection_enabled(getattr(self, "pi_connected", False)))
        return card

    def system_log_card(self: Any):
        card = GlassCard()
        card.setObjectName("SystemLogCard")
        card.setMinimumHeight(205 if not self.compact_mode else 185)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16 if not self.compact_mode else 12, 12 if not self.compact_mode else 10, 16 if not self.compact_mode else 12, 10 if not self.compact_mode else 8)
        layout.setSpacing(5)

        top = QHBoxLayout()
        title = QLabel("SYSTEM LOG")
        title.setObjectName("FaceSectionTitle")
        dot = QLabel("●")
        dot.setObjectName("GreenDot")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(dot)
        layout.addLayout(top)

        # Scrollable Face Recognition System Log.
        # This section should show action status, not dashboard/settings noise.
        self.system_log_scroll = QScrollArea()
        self.system_log_scroll.setObjectName("FaceSystemLogScroll")
        self.system_log_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.system_log_scroll.setWidgetResizable(True)
        self.system_log_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.system_log_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Keep the System Log scrollable and visible. Do not hide this scrollbar,
        # because operators need to review older log entries.
        self.system_log_scroll.setStyleSheet(self.system_log_scroll.styleSheet() + """
            QScrollBar:vertical {
                width: 7px;
                background: transparent;
                margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.22);
                border-radius: 3px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        log_body = QWidget()
        self.system_log_body = log_body
        log_body.setObjectName("FaceSystemLogBody")
        log_layout = QVBoxLayout(log_body)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(0)

        logs = QLabel(
            "&gt; FACE RECOGNITION SYSTEM LOG READY<br>"
            "&gt; WAITING FOR CAMERA CONNECTION"
        )
        self.system_log_label = logs
        logs.setObjectName("LogText")
        logs.setWordWrap(True)
        logs.setTextFormat(Qt.TextFormat.RichText)
        logs.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        logs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        log_layout.addWidget(logs)
        # No bottom stretch here; the QLabel should define the scrollable height.

        self.system_log_scroll.setWidget(log_body)
        layout.addWidget(self.system_log_scroll, 1)
        return card

    def face_users_card(self: Any):
        card = GlassCard()
        card.setMinimumHeight(0)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            16 if not self.compact_mode else 12,
            16 if not self.compact_mode else 12,
            16 if not self.compact_mode else 12,
            16 if not self.compact_mode else 12,
        )
        layout.setSpacing(8 if not self.compact_mode else 6)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AUTHORIZED USERS")
        title.setObjectName("UsersTitle")
        sub = QLabel("CONNECT CAMERA FIRST")
        sub.setObjectName("UsersStatus")
        title_box.addWidget(title)
        title_box.addWidget(sub)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setObjectName("SmallIconButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setFixedSize(30 if not self.compact_mode else 26, 30 if not self.compact_mode else 26)
        refresh_btn.clicked.connect(self._local_face_refresh_users)

        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        # Search bar for large user lists.
        search_box = QFrame()
        search_box.setObjectName("FaceUserSearchBox")
        search_box.setFixedHeight(36 if not self.compact_mode else 32)
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 0, 10, 0)
        search_layout.setSpacing(8)

        search_icon = QLabel("⌕")
        search_icon.setObjectName("FaceUserSearchIcon")

        self.face_user_search_input = QLineEdit()
        self.face_user_search_input.setObjectName("FaceUserSearchInput")
        self.face_user_search_input.setPlaceholderText("Search NTID...")
        self.face_user_search_input.setClearButtonEnabled(True)
        self.face_user_search_input.textChanged.connect(lambda _: self.render_face_users(getattr(self, "face_users_cache", [])))

        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.face_user_search_input, 1)
        layout.addWidget(search_box)

        # Scrollable list. The card size stays fixed even for 100+ users.
        self.face_users_scroll = QScrollArea()
        self.face_users_scroll.setObjectName("FaceUsersScroll")
        self.face_users_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.face_users_scroll.setWidgetResizable(True)
        self.face_users_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.face_users_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.make_scrollbar_invisible(self.face_users_scroll)

        self.face_users_body = QWidget()
        self.face_users_body.setObjectName("FaceUsersBody")
        self.face_users_list_layout = QVBoxLayout(self.face_users_body)
        self.face_users_list_layout.setContentsMargins(0, 2, 0, 2)
        self.face_users_list_layout.setSpacing(10 if not self.compact_mode else 8)

        self.face_users_scroll.setWidget(self.face_users_body)
        layout.addWidget(self.face_users_scroll, 1)

        self.face_users_layout = layout
        self.face_users_subtitle = sub

        self.render_face_users(getattr(self, "face_users_cache", []))
        QTimer.singleShot(300, self._local_face_refresh_users)

        return card

    def face_user_row(self: Any, user_id, frames):
        """Expandable authorised user card using the uploaded card UI concept.

        Click row to smoothly expand the card and reveal Capture/Delete actions.
        Expanding/collapsing does not write into System Log.
        """
        user_id = str(user_id or "").strip().upper()

        # Enough height for header + frames + two action buttons.
        # Keep compact mode slightly smaller but still not clipped.
        expanded_h = 166 if not self.compact_mode else 154
        collapsed_h = 84 if not self.compact_mode else 74

        card = QFrame()
        card.setObjectName("FaceUserExpandCard")
        card.setProperty("expanded", False)
        card.setMinimumHeight(collapsed_h)
        card.setMaximumHeight(collapsed_h)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout(card)
        root.setContentsMargins(14 if not self.compact_mode else 12, 12 if not self.compact_mode else 10, 14 if not self.compact_mode else 12, 14 if not self.compact_mode else 12)
        root.setSpacing(7 if not self.compact_mode else 5)

        top = QHBoxLayout()
        top.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(4)

        ntid_label = QLabel("NTID IDENTIFIER")
        ntid_label.setObjectName("FaceUserCardLabel")

        name = QLabel(user_id)
        name.setObjectName("FaceUserCardNtid")

        left.addWidget(ntid_label)
        left.addWidget(name)

        top.addLayout(left, 1)

        frames_row = QHBoxLayout()
        frames_row.setSpacing(6)

        frames_icon = QLabel("▦")
        frames_icon.setObjectName("FaceUserFramesIcon")
        frames_icon.setFixedWidth(16)

        detail = QLabel(frames)
        detail.setObjectName("FaceUserCardDetail")

        frames_row.addWidget(frames_icon)
        frames_row.addWidget(detail)
        frames_row.addStretch()

        actions = QFrame()
        actions.setObjectName("FaceUserCardActions")
        actions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions.setVisible(False)
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 2 if not self.compact_mode else 2)
        actions_layout.setSpacing(6 if not self.compact_mode else 5)

        capture_btn = QPushButton("REGISTER")
        capture_btn.setObjectName("FaceUserCardCaptureButton")
        capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        capture_btn.setMinimumHeight(32 if not self.compact_mode else 30)

        delete_btn = QPushButton("DELETE USER")
        delete_btn.setObjectName("FaceUserCardDeleteButton")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setMinimumHeight(34 if not self.compact_mode else 32)

        actions_layout.addWidget(capture_btn)
        actions_layout.addWidget(delete_btn)

        root.addLayout(top)
        root.addLayout(frames_row)
        root.addWidget(actions)

        def animate_card_height(target_h: int, expanding: bool):
            """Animate both min and max height to avoid clipping/jumping."""
            old_min = card.minimumHeight()
            old_max = card.maximumHeight()

            if expanding:
                actions.setVisible(True)

            min_anim = QPropertyAnimation(card, b"minimumHeight", card)
            min_anim.setDuration(230)
            min_anim.setStartValue(old_min)
            min_anim.setEndValue(target_h)
            min_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            max_anim = QPropertyAnimation(card, b"maximumHeight", card)
            max_anim.setDuration(230)
            max_anim.setStartValue(old_max)
            max_anim.setEndValue(target_h)
            max_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            # Keep references so Qt does not garbage-collect the animations.
            card.setProperty("_min_height_anim", min_anim)
            card.setProperty("_max_height_anim", max_anim)

            def finish():
                card.setMinimumHeight(target_h)
                card.setMaximumHeight(target_h)
                if not expanding:
                    actions.setVisible(False)

            max_anim.finished.connect(finish)
            min_anim.start()
            max_anim.start()

        def collapse_other_card():
            old_card = getattr(self, "_open_face_user_expand_card", None)
            if old_card is not None and old_card is not card:
                try:
                    old_actions = old_card.property("_actions_frame")
                    old_min_anim = old_card.property("_min_height_anim")
                    old_max_anim = old_card.property("_max_height_anim")

                    if isinstance(old_min_anim, QPropertyAnimation):
                        old_min_anim.stop()
                    if isinstance(old_max_anim, QPropertyAnimation):
                        old_max_anim.stop()

                    old_card.setProperty("expanded", False)
                    old_card.style().unpolish(old_card)
                    old_card.style().polish(old_card)

                    # Collapse old card smoothly too.
                    old_card.setMinimumHeight(collapsed_h)
                    old_card.setMaximumHeight(collapsed_h)
                    if isinstance(old_actions, QWidget):
                        old_actions.setVisible(False)
                except Exception:
                    pass

        def set_expanded(expand: bool):
            if user_id in ("CONNECT CAMERA", "OFFLINE", ""):
                return

            if expand:
                collapse_other_card()

            card.setProperty("expanded", expand)
            card.style().unpolish(card)
            card.style().polish(card)

            animate_card_height(expanded_h if expand else collapsed_h, expand)

            if expand:
                self._open_face_user_expand_card = card

        def toggle_card():
            set_expanded(not bool(card.property("expanded")))

        def capture_this_user():
            if hasattr(self, "ntid_input"):
                self.ntid_input.setText(user_id)
                self.clear_ntid_input_error()
            self.face_action_feedback(f"QUICK_CAPTURE: {user_id}")
            self._local_face_capture_user()

        def delete_this_user():
            if hasattr(self, "ntid_input"):
                self.ntid_input.setText(user_id)
                self.clear_ntid_input_error()
            self.face_action_feedback(f"QUICK_DELETE: {user_id}")
            self._local_face_delete_user()

        card.mousePressEvent = lambda event: toggle_card()
        capture_btn.clicked.connect(lambda checked=False: capture_this_user())
        delete_btn.clicked.connect(lambda checked=False: delete_this_user())

        # Prevent button clicks from toggling the parent card.
        capture_btn.mousePressEvent = lambda event, old=capture_btn.mousePressEvent: (event.accept(), old(event))[1]
        delete_btn.mousePressEvent = lambda event, old=delete_btn.mousePressEvent: (event.accept(), old(event))[1]

        card.setProperty("_actions_frame", actions)

        return card

    def capture_requested(self: Any):
        """Temporary capture validation before connecting to the real API."""
        ntid = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""

        if not ntid:
            print("[FACE ACTION] Please enter NTID before capture")
            if hasattr(self, "ntid_input"):
                self.ntid_input.setFocus()
                self.ntid_input.setPlaceholderText("NTID is required before capture")
            return

        self.face_action_feedback(f"Capture requested for NTID: {ntid}")

    # --------------------------------------------------------
    # Phase 1 migrated LockApp logic
    # --------------------------------------------------------

    def stop_camera_preview(self: Any, show_prompt: bool = False):
        """Stop camera preview reliably without blocking UI."""
        if (
            bool(getattr(self, "pi_connected", False))
            and not bool(getattr(self, "_camera_user_stopped", False))
            and not bool(getattr(self, "_camera_manual_disconnected", False))
            and not bool(getattr(self, "_closing", False))
            and self.is_local_rtsp_active_for_ui()
        ):
            try:
                from services.local_recognition_engine import ENGINE

                status = ENGINE.status()
                frame_age = status.get("last_frame_age_seconds")
                active = bool(
                    status.get("recognition_running", False)
                    or status.get("capture_running", False)
                    or status.get("stream_healthy", False)
                    or status.get("stream_recovering", False)
                    or (
                        ENGINE.latest_frame is not None
                        and frame_age is not None
                        and float(frame_age) <= 45.0
                    )
                    or str(status.get("connection_state") or "").strip().lower()
                    in {"starting", "connecting", "live", "stale", "restarting"}
                )
                if active:
                    self.append_face_log(
                        f"CAMERA_PREVIEW_STOP_SUPPRESSED: prompt={show_prompt} state={status.get('connection_state')}"
                    )
                    self.set_camera_state_badge(True)
                    if not getattr(self, "_camera_preview_running", False):
                        self.start_camera_preview(force=True)
                    return
            except Exception:
                pass

        self._camera_preview_generation = int(getattr(self, "_camera_preview_generation", 0) or 0) + 1
        self._camera_preview_running = False

        if show_prompt:
            self.show_camera_stopped_prompt("Camera stopped")
        else:
            self.set_camera_state_badge(False)

        if hasattr(self, "camera_timer") and self.camera_timer is not None:
            try:
                self.camera_timer.stop()
            except Exception:
                pass
            self.camera_timer = None

        old_capture = getattr(self, "camera_capture", None)
        self.camera_capture = None

        if old_capture is not None:
            try:
                old_capture.release()
            except Exception:
                pass

    def _local_face_base_url(self: Any, host_override: str | None = None):
        # Local RTSP mode: the user enters only the camera hostname/IP.  The
        # service builds the fixed company RTSP URL and handles recognition on
        # this PC, while the old dashboard keeps its API-shaped method calls.
        commit_host = host_override is None
        if host_override is not None:
            host = str(host_override or "").strip()
        else:
            host = str(getattr(self, "pi_api_host", "") or "").strip()
        port = "5000"

        if not host:
            raise RuntimeError("Camera hostname/IP is not configured. Please set it in Settings first.")

        self.local_face_service.configure(host, port)
        base_url = f"local://{host}"
        if commit_host:
            self.pi_api_host = host
            self.pi_api_port = port
            self.pi_api_base = base_url
            self.camera_feed_url = self.local_face_service.rtsp_url()
            self.configure_local_unlock(host, port, start=False)
        return base_url

    def _local_face_request(self: Any, method, endpoint, payload=None, timeout=10, host_override: str | None = None):
        self._local_face_base_url(host_override=host_override)
        return self.local_face_service.request(method, endpoint, payload=payload, timeout=timeout)

    def set_face_controls_connection_enabled(self: Any, enabled: bool):
        """Enable Face Recognition actions only when local recognition engine is reachable.

        Recognition is deliberately kept disabled while a capture is active.
        camera backend cannot safely run capture and recognition at the same time.
        """
        self.pi_connected = bool(enabled)
        capture_busy = bool(getattr(self, "face_capture_in_progress", False))

        for name in ("face_capture_btn", "face_recognize_btn", "face_delete_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                button_enabled = bool(enabled)
                if name == "face_recognize_btn" and capture_busy:
                    button_enabled = False
                    btn.setToolTip("Recognition is disabled while capture is running. Press STOP before starting recognition.")
                elif name == "face_recognize_btn":
                    btn.setToolTip("Start face recognition.")

                btn.setEnabled(button_enabled)
                btn.setCursor(Qt.CursorShape.PointingHandCursor if button_enabled else Qt.CursorShape.ForbiddenCursor)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()

        # Stop can remain clickable only when connected. If camera is offline it cannot stop anything.
        stop_btn = getattr(self, "face_stop_btn", None)
        if stop_btn is not None:
            stop_btn.setEnabled(bool(enabled))
            stop_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)

        if hasattr(self, "ntid_input"):
            self.ntid_input.setEnabled(bool(enabled))
        if hasattr(self, "name_input"):
            self.name_input.setEnabled(bool(enabled))

    def set_face_capture_in_progress(self: Any, active: bool):
        """Track camera capture state and block Recognition until capture is stopped."""
        self.face_capture_in_progress = bool(active)

        recognize_btn = getattr(self, "face_recognize_btn", None)
        if recognize_btn is None:
            return

        allow_recognition = bool(getattr(self, "pi_connected", False)) and not bool(active)
        recognize_btn.setEnabled(allow_recognition)
        recognize_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
            if allow_recognition
            else Qt.CursorShape.ForbiddenCursor
        )
        recognize_btn.setToolTip(
            "Recognition is disabled while capture is running. Press STOP before starting recognition."
            if active
            else "Start face recognition."
        )
        recognize_btn.style().unpolish(recognize_btn)
        recognize_btn.style().polish(recognize_btn)
        recognize_btn.update()

    def show_connection_dialog(self: Any, origin: str = "settings"):
        """Show card-style connection popup.

        The card uses blurred background and blocks clicks behind it.
        """
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        if not host:
            host = self.pi_api_host

        # Close any old connection card before opening a new one.
        try:
            if self.connection_dialog is not None:
                self.connection_dialog.accept()
        except Exception:
            pass

        root = self.centralWidget()
        blur = None
        if root is not None:
            try:
                root.setEnabled(False)
                blur = QGraphicsBlurEffect(self)
                blur.setBlurRadius(0)
                root.setGraphicsEffect(blur)

                self._connection_blur_anim = QPropertyAnimation(blur, b"blurRadius", self)
                self._connection_blur_anim.setDuration(220)
                self._connection_blur_anim.setStartValue(0)
                self._connection_blur_anim.setEndValue(5)
                self._connection_blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._connection_blur_anim.start()
            except Exception:
                blur = None

        dialog = CameraConnectionDialog(
            self,
            host=host,
            origin=origin,
            compact_mode=self.compact_mode,
        )
        self.connection_dialog = dialog

        def on_finished(*args):
            if self.connection_dialog is dialog:
                self.connection_dialog = None
            if root is not None:
                try:
                    root.setEnabled(True)
                except Exception:
                    pass
            if root is not None and blur is not None:
                try:
                    self.clear_blur_effect(root)
                except Exception:
                    try:
                        root.setGraphicsEffect(cast(QGraphicsEffect, None))  # type: ignore[arg-type]
                    except Exception:
                        pass

        dialog.finished.connect(on_finished)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def finish_connection_dialog_success(self: Any, users: int = 0, recognition: bool = False, capture: bool = False):
        dialog = getattr(self, "connection_dialog", None)
        if dialog is not None:
            dialog.set_success(users=users, recognition=recognition, capture=capture)

    def finish_connection_dialog_failed(self: Any, error_text: str = ""):
        # v200: If this is a camera-disconnect condition, use the single no-close
        # disconnect popup instead of the older failed dialog with a close button.
        if getattr(self, "_pi_disconnect_lock_suspended", False) or getattr(self, "_pi_disconnect_retry_active", False):
            self.show_pi_disconnected_popup(error_text)
            return

        dialog = getattr(self, "connection_dialog", None)
        if dialog is not None:
            dialog.set_failed(error_text)

    def clear_disconnect_popup_overlay(self: Any):
        """Clear modal overlay safely without direct unknown-method access."""
        try:
            hide_overlay = getattr(self, "hide_modal_overlay", None)
            if callable(hide_overlay):
                hide_overlay()
        except Exception:
            pass
        try:
            clear_overlay = getattr(self, "clear_modal_overlay", None)
            if callable(clear_overlay):
                clear_overlay()
        except Exception:
            pass
        try:
            self._modal_open_count = 0
        except Exception:
            pass
        try:
            self.setEnabled(True)
        except Exception:
            pass

    def wire_pi_disconnect_return_button(self: Any, dialog):
        """Connect the camera disconnect dialog's visible action button to restore SAS."""
        try:
            buttons = dialog.findChildren(QPushButton)
        except Exception:
            buttons = []

        for btn in buttons:
            try:
                label = btn.text().strip().lower()
            except Exception:
                label = ""

            if "setting" in label or "return" in label or "connect" in label:
                try:
                    btn.setText("Return to Settings")
                except Exception:
                    pass
                try:
                    btn.clicked.disconnect()
                except Exception:
                    pass
                try:
                    btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                except Exception:
                    pass
                try:
                    btn.setDefault(True)
                    btn.setAutoDefault(True)
                except Exception:
                    pass
                return True

        return False

    def show_face_tab_pi_disconnect_popup(self: Any, reason: str = ""):
        """Show Camera disconnected popup when user tries to open Face Recognition.

        This is a user action, so it must bypass Settings-tab auto-popup
        suppression and stale popup flags.
        """
        try:
            self._allow_settings_disconnect_popup_once = True
            self._pi_disconnect_popup_visible = False
            self.suspend_locking_for_pi_disconnect(reason or "Please connect camera hostname/IP from Settings first.")
            self.show_pi_disconnected_popup(reason or "Please connect camera hostname/IP from Settings first.")
        except Exception as e:
            print("[FACE TAB DISCONNECT POPUP ERROR]", e)

    def convert_connection_dialog_to_disconnect_failed(self: Any, error_text: str = ""):
        """Convert the current Settings Connect progress dialog to failed state.

        Used when the user manually presses Connect in Settings. This prevents
        the dialog from staying stuck at "Connecting..." and reuses the existing
        popup/card UI.
        """
        if getattr(self, "_manual_connect_failed_popup_active", False):
            return
        self._manual_connect_failed_popup_active = True

        dialog = getattr(self, "connection_dialog", None)
        if dialog is None:
            self._allow_settings_disconnect_popup_once = True
            self.show_pi_disconnected_popup(error_text or "RTSP camera disconnected.")
            self._manual_connect_failed_popup_active = False
            return

        try:
            dialog.set_failed(error_text or "RTSP camera disconnected. Please check camera power/network/source.")
        except Exception:
            pass

        try:
            dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
            dialog.setModal(False)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
        except Exception:
            pass

        def _prepare_failed_dialog():
            try:
                for btn in dialog.findChildren(QPushButton):
                    label = (btn.text() or "").strip().lower()
                    obj = (btn.objectName() or "").strip().lower()

                    if label in ("x", "×", "close", "cancel") or "close" in obj or "cancel" in obj:
                        btn.hide()
                        btn.setEnabled(False)
                        continue

                    if (
                        "setting" in label
                        or "return" in label
                        or "connect" in label
                        or "retry" in label
                        or "ok" in label
                        or not label
                    ):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.setDefault(True)
                        btn.setAutoDefault(True)
                        btn.show()
                        btn.setEnabled(True)

                for attr in ("settings_btn", "return_settings_btn", "primary_btn", "retry_btn", "ok_btn"):
                    btn = getattr(dialog, attr, None)
                    if isinstance(btn, QPushButton):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.show()
                        btn.setEnabled(True)
            except Exception:
                pass

        _prepare_failed_dialog()
        QTimer.singleShot(0, _prepare_failed_dialog)
        QTimer.singleShot(200, _prepare_failed_dialog)
        QTimer.singleShot(600, _prepare_failed_dialog)

        self._pi_disconnect_popup_visible = True
        try:
            self._pi_disconnect_popup_last_shown_at = time.monotonic()
        except Exception:
            pass

        def reset_flag(*_args):
            self._pi_disconnect_popup_visible = False
            self._manual_connect_failed_popup_active = False
            if not getattr(self, "pi_connected", False):
                self.suspend_locking_for_pi_disconnect(error_text or "RTSP camera disconnected.")
                self.start_pi_disconnect_retry_loop(error_text or "RTSP camera disconnected.")

        try:
            dialog.finished.connect(reset_flag)
        except Exception:
            pass

        try:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass

    def show_pi_disconnected_popup(self: Any, error_text: str = ""):
        """Show Camera disconnected popup using the original connection card UI.

        v213:
        - Restores the previous disconnect UI/card style.
        - Removes the custom v212 white-card popup.
        - Does not create a separate top-level/new window for minimized mode.
        - Keeps no-close behaviour and Return to Settings action.
        """
        if self.is_login_popup_active():
            self.defer_pi_disconnect_until_after_login(error_text or "RTSP camera disconnected.", "dialog")
            return

        if (
            self.is_settings_tab_active()
            and not self.is_sas_minimized_or_background()
            and not getattr(self, "_allow_settings_disconnect_popup_once", False)
        ):
            return
        self._allow_settings_disconnect_popup_once = False

        # v131: camera-disconnect warning has higher priority than Guidelines.
        # Guidelines is modal, so close it first or the disconnect popup can
        # appear behind it and cannot be clicked until Guidelines is closed.
        try:
            self.close_guidelines_dialog_if_open()
        except Exception:
            pass

        existing = getattr(self, "connection_dialog", None)
        try:
            if existing is not None and existing.isVisible():
                return
        except Exception:
            pass

        try:
            now = time.monotonic()
            last = float(getattr(self, "_pi_disconnect_popup_last_shown_at", 0.0) or 0.0)
            if now - last < 2.5:
                return
            self._pi_disconnect_popup_last_shown_at = now
        except Exception:
            pass

        try:
            if existing is not None:
                existing.blockSignals(True)
                existing.close()
                existing.deleteLater()
        except Exception:
            pass
        self.connection_dialog = None
        self._pi_disconnect_popup_visible = True

        # Use the original connection status card/popup. Do not detach it into a
        # new top-level dialog, because that caused the UI to look different.
        dialog = self.show_connection_dialog(origin="settings")
        dialog.set_failed(error_text or "RTSP camera disconnected. Please check camera power/network/source.")

        try:
            dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
            dialog.setModal(False)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
        except Exception:
            pass

        def _prepare_disconnect_dialog():
            try:
                for btn in dialog.findChildren(QPushButton):
                    label = (btn.text() or "").strip().lower()
                    obj = (btn.objectName() or "").strip().lower()

                    if label in ("x", "×", "close", "cancel") or "close" in obj or "cancel" in obj:
                        btn.hide()
                        btn.setEnabled(False)
                        continue

                    if (
                        "setting" in label
                        or "return" in label
                        or "connect" in label
                        or "retry" in label
                        or "ok" in label
                        or not label
                    ):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.setDefault(True)
                        btn.setAutoDefault(True)
                        btn.show()
                        btn.setEnabled(True)

                for attr in ("settings_btn", "return_settings_btn", "primary_btn", "retry_btn", "ok_btn"):
                    btn = getattr(dialog, attr, None)
                    if isinstance(btn, QPushButton):
                        btn.setText("Return to Settings")
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.return_to_settings_from_pi_disconnect)
                        btn.show()
                        btn.setEnabled(True)
            except Exception:
                pass

        _prepare_disconnect_dialog()
        QTimer.singleShot(0, _prepare_disconnect_dialog)
        QTimer.singleShot(200, _prepare_disconnect_dialog)
        QTimer.singleShot(600, _prepare_disconnect_dialog)

        def reset_flag(*_args):
            self._pi_disconnect_popup_visible = False
            if not getattr(self, "pi_connected", False):
                self.suspend_locking_for_pi_disconnect(error_text or "RTSP camera disconnected.")
                self.start_pi_disconnect_retry_loop(error_text or "RTSP camera disconnected.")

        try:
            dialog.finished.connect(reset_flag)
        except Exception:
            pass

        self.connection_dialog = dialog

        try:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass

    def auto_connect_pi_for_face_tab(self: Any):
        """Compatibility wrapper.

        Face Recognition tab no longer reconnects automatically.
        Users connect from Settings, then Face Recognition uses that successful connection.
        """
        if not getattr(self, "pi_connected", False):
            self.show_face_tab_pi_disconnect_popup("Please connect camera hostname/IP from Settings first.")

    def _local_face_test_connection(self: Any, show_disconnect_popup: bool = False, show_progress: bool = True, origin: str = "settings", force_takeover: bool = False):
        """Connect to camera Face Recognition API and load status/users/logs.

        v110 fixes:
        - Settings Connect tests the hostname currently typed by the user.
        - All API calls inside that attempt use the same typed hostname, not the
          previously connected/saved hostname.
        - Old retry/connect workers are ignored if the user edits the hostname
          before the worker returns.
        """
        origin_safe = str(origin or "")
        host = self.get_pi_host_for_connection_origin(origin_safe)
        attempt_started_at = time.monotonic()
        self.camera_debug("CONNECT_ATTEMPT_BEGIN", origin=origin_safe, host=host, show_progress=show_progress, show_disconnect_popup=show_disconnect_popup)
        if not host:
            if origin_safe == "settings":
                self._settings_connect_in_progress = False
            reason = self.handle_missing_pi_host_disconnect_state(
                origin=origin_safe or "auto",
                force_popup=bool(show_disconnect_popup and origin_safe not in {"settings"}),
            )
            self.configure_local_unlock("", self.pi_api_port, start=False)
            self.append_face_log("SERVER_STATUS: SKIPPED | camera hostname/IP is not configured.")
            if origin_safe == "settings":
                self.show_settings_message(
                    "Camera Host Required",
                    "Please enter the RTSP camera hostname or IP address before connecting.",
                    success=False,
                    issues=[("MISSING CAMERA HOST", "camera hostname/IP is required to start the local recognition engine.")],
                    server_path=self.server_path,
                )
            self.handle_startup_background_check_result(False, reason)
            return

        try:
            self._pi_connect_request_token = int(getattr(self, "_pi_connect_request_token", 0)) + 1
        except Exception:
            self._pi_connect_request_token = 1
        request_token = int(getattr(self, "_pi_connect_request_token", 0))
        self.camera_debug("CONNECT_TOKEN", origin=origin_safe, host=host, token=request_token)

        if origin_safe == "settings":
            # Commit the typed host immediately as the selected runtime host.
            # Even if this connection fails, background checks and future tab
            # changes must keep using this host, not the previous successful camera.
            # Also stop any previous disconnected retry so the manual Settings
            # Connect result cannot be invalidated by a background request.
            self._settings_connect_in_progress = True
            self._pi_disconnect_retry_active = False
            self._pi_disconnect_retry_running = False
            self._manual_connect_failed_popup_active = False
            self.set_selected_pi_host_runtime(host, connected=False, configure_backend=False)
            self._pi_host_dirty_since_edit = False
            self._pi_host_user_editing = False
            self._pi_selected_host_pending_manual_connect = True

        attempt_id = 0
        if show_progress:
            self.show_connection_dialog(origin=origin)
            if origin_safe == "settings":
                self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                attempt_id = self._settings_connect_attempt_id

                def settings_connect_timeout_guard(expected_id=attempt_id, expected_token=request_token):
                    try:
                        if expected_id != getattr(self, "_settings_connect_attempt_id", 0):
                            return
                        if getattr(self, "pi_connected", False):
                            return
                        dialog = getattr(self, "connection_dialog", None)
                        if dialog is not None and dialog.isVisible() and str(getattr(dialog, "state", "") or "").lower() == "loading":
                            # Do not require the token to still match here. A
                            # background retry may have changed the token already;
                            # the visible user action still needs a deterministic
                            # timeout instead of staying stuck at Connecting.
                            self._settings_connect_in_progress = False
                            self._pi_disconnect_retry_active = False
                            self._pi_disconnect_retry_running = False
                            self.pi_connected = False
                            self.pi_connection_checked = True
                            self.suspend_locking_for_pi_disconnect("camera connection timed out. Please check camera hostname/IP and network.")
                            self.convert_connection_dialog_to_disconnect_failed(
                                "camera connection timed out. Please check camera hostname/IP and network."
                            )
                            self.set_pi_status_label(connected=False)
                            self.update_pi_connect_ui_state(connected=False)
                    except Exception as e:
                        print("[SETTINGS CONNECT TIMEOUT GUARD ERROR]", e)

                QTimer.singleShot(18000, settings_connect_timeout_guard)

        self.set_pi_status_label(checking=True)
        self.update_pi_connect_ui_state(connected=False, checking=True)

        def is_stale_request() -> bool:
            try:
                return request_token != int(getattr(self, "_pi_connect_request_token", 0))
            except Exception:
                return True

        def worker():
            session_claimed = False
            self.camera_debug("CONNECT_WORKER_START", origin=origin_safe, host=host, token=request_token)
            try:
                if is_stale_request():
                    return

                session_ok, session_conflict, session_message, session_data = self.claim_pi_oneconnect_session(
                    force=bool(force_takeover),
                    timeout=8,
                    host=host,
                )
                if session_ok:
                    session_claimed = True
                self.camera_debug("CONNECT_SESSION_CLAIMED", origin=origin_safe, host=host, ok=session_ok, conflict=session_conflict, message=session_message)

                if is_stale_request():
                    if session_claimed:
                        try:
                            self.disconnect_pi_oneconnect_session(timeout=5, host=host)
                        except Exception:
                            pass
                    return

                if not session_ok:
                    if session_conflict:
                        def conflict_done(session_data=session_data, session_message=session_message):
                            if is_stale_request():
                                if origin_safe == "settings":
                                    self._settings_connect_in_progress = False
                                return
                            if origin_safe == "settings":
                                self._settings_connect_in_progress = False
                                self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                            self.pi_connection_checked = True
                            self.set_selected_pi_host_runtime(host, connected=False, configure_backend=False)
                            self._pi_selected_host_pending_manual_connect = True
                            self.pi_connected = False
                            self.set_face_controls_connection_enabled(False)
                            self.stop_local_unlock("oneconnect conflict")
                            self.set_pi_status_label(connected=False, message="Status: Already connected")
                            self.update_pi_connect_ui_state(connected=False)
                            self.close_connection_dialog_silently()
                            self.append_face_log(f"CAMERA_CONNECT_BLOCKED: {session_message}")
                            self.write_sas_log(
                                "CAMERA CONNECTION BLOCKED",
                                actor=self.get_audit_actor(),
                                details={
                                    "Requested host": host,
                                    "Result": "Already connected",
                                },
                            )
                            self.show_oneconnect_conflict_prompt(session_data.get("session"), session_message)

                        self.qt_after(0, conflict_done)
                        return
                    raise RuntimeError(session_message)

                # Important: use the SAME host that the user pressed Connect for.
                # Do not fall back to self.pi_api_host here, because it may still
                # contain the previous camera hostname.
                self.camera_debug("CONNECT_START_RECOGNITION_BEGIN", origin=origin_safe, host=host, elapsed=round(time.monotonic() - attempt_started_at, 2))
                data = self._local_face_request("POST", "/start-recognition", {}, timeout=12, host_override=host)
                self.camera_debug("CONNECT_START_RECOGNITION_DONE", origin=origin_safe, host=host, elapsed=round(time.monotonic() - attempt_started_at, 2))
                users_value = data.get("user_count", data.get("users", 0))
                users = len(users_value) if isinstance(users_value, list) else int(users_value or 0)
                rec = data.get("recognition_running", False)
                cap = data.get("capture_running", False)
                stream_healthy = bool(data.get("stream_healthy", False))
                stream_recovering = bool(data.get("stream_recovering", False))
                connection_state = str(data.get("connection_state") or "").strip()
                resolved_ip = str(data.get("resolved_ip") or "").strip()
                pi_hostname = str(data.get("hostname") or data.get("device_name") or "").strip()
                pi_user = str(data.get("system_user") or data.get("ssh_username") or "").strip()
                msg = (
                    f"SERVER_STATUS: ONLINE | HOST={host} | RESOLVED_IP={resolved_ip or '-'} | "
                    f"USERS={users} | RECOGNITION={rec} | CAPTURE={cap} | "
                    f"STREAM={connection_state or '-'} | HEALTHY={stream_healthy} | "
                    f"HOSTNAME={pi_hostname or '-'} | USER={pi_user or '-'}"
                )
                if not stream_healthy:
                    last_error = str(data.get("last_error") or "no fresh RTSP frame").strip()
                    address = f" ({resolved_ip})" if resolved_ip else ""
                    active_recovery_state = str(connection_state or "").strip().lower() in {"starting", "connecting", "live", "stale", "restarting"}
                    if not (rec or cap or stream_recovering or active_recovery_state):
                        raise RuntimeError(f"No fresh RTSP frame from {host}{address}. State={connection_state or 'unknown'}; Error={last_error}")
                    msg = (
                        f"SERVER_STATUS: ONLINE_RECOVERING | HOST={host} | RESOLVED_IP={resolved_ip or '-'} | "
                        f"USERS={users} | RECOGNITION={rec} | CAPTURE={cap} | "
                        f"STREAM={connection_state or '-'} | ERROR={last_error} | "
                        f"HOSTNAME={pi_hostname or '-'} | USER={pi_user or '-'}"
                    )

                if is_stale_request():
                    if session_claimed:
                        try:
                            self.disconnect_pi_oneconnect_session(timeout=5, host=host)
                        except Exception:
                            pass
                    return

                def done():
                    if is_stale_request():
                        if origin_safe == "settings":
                            self._settings_connect_in_progress = False
                        return

                    if origin_safe == "settings":
                        self._settings_connect_in_progress = False

                    # Commit the successfully connected host only after all checks
                    # pass. This prevents a failed/random typed hostname from
                    # becoming the active runtime camera.
                    self.pi_api_host = host
                    self.pi_api_port = "5000"
                    try:
                        self.local_face_service.configure(host, "5000")
                    except Exception:
                        pass
                    self.pi_api_base = f"local://{host}"
                    self.camera_feed_url = self.local_face_service.rtsp_url()

                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self._camera_connected_once_this_run = True
                    self._camera_manual_disconnected = False
                    self._runtime_disconnect_candidate_since = 0.0
                    self._sas_heartbeat_failure_count = 0
                    self._pi_selected_host_pending_manual_connect = False
                    self.resume_locking_after_pi_reconnect()
                    self.pi_device_hostname = pi_hostname
                    self.pi_system_user = pi_user
                    self.set_face_controls_connection_enabled(True)
                    self.configure_local_unlock(host, "5000", start=True)
                    self.camera_debug("CONNECT_SUCCESS_UI", origin=origin_safe, host=host, elapsed=round(time.monotonic() - attempt_started_at, 2), state=connection_state, healthy=stream_healthy)
                    self.append_face_log(msg)

                    # Keep the visible field aligned with the actual committed host.
                    try:
                        if hasattr(self, "pi_host_input") and self.pi_host_input.text().strip() != host:
                            self.pi_host_input.blockSignals(True)
                            self.pi_host_input.setText(host)
                            self.pi_host_input.blockSignals(False)
                    except Exception:
                        pass

                    # Only the Settings Connect button is an explicit user action.
                    # Startup/retry checks must not flood the audit log.
                    if origin_safe == "settings":
                        connected_pi_host = pi_hostname or host or "Not reported"
                        pi_audit_details = {
                            "Camera host": connected_pi_host,
                            "API port": "5000",
                            "OneConnect": "Forced takeover" if force_takeover else "Normal connect",
                        }
                        if host and pi_hostname and host.strip().lower() != pi_hostname.strip().lower():
                            pi_audit_details = {
                                "Requested host": host,
                                **pi_audit_details,
                            }
                        self.write_sas_log(
                            "CAMERA CONNECTED",
                            actor=self.get_audit_actor(),
                            details=pi_audit_details,
                        )

                    self.set_pi_status_label(
                        connected=True,
                        message=f"Status: Connected | Host: {host} | IP: {resolved_ip or '-'}",
                    )
                    self.update_pi_connect_ui_state(connected=True)
                    if hasattr(self, "pi_identity_label"):
                        self.pi_identity_label.setText("")
                        self.pi_identity_label.setVisible(False)

                    # Important:
                    # A previous camera disconnect may have left the camera panel showing
                    # "Camera disconnected". After a successful reconnect, reset that stale
                    # state immediately.
                    self._camera_user_stopped = False
                    self._handling_pi_disconnect = False

                    self.finish_connection_dialog_success(users=users, recognition=rec, capture=cap)

                    self._local_face_refresh_users()
                    self._local_face_load_logs()
                    self.pull_pi_settings_to_sas(silent=True)

                    # If camera is already recognising/capturing, show the feed immediately.
                    # If not, show a normal camera-stopped prompt, not "Camera disconnected".
                    if rec or cap:
                        has_recent_frame = False
                        try:
                            from services.local_recognition_engine import ENGINE

                            age = ENGINE.last_frame_age_seconds()
                            has_recent_frame = bool(ENGINE.latest_frame is not None and age is not None and age <= 30.0)
                        except Exception:
                            has_recent_frame = False
                        if getattr(self, "_camera_preview_running", False) and has_recent_frame:
                            self.set_camera_state_badge(True)
                        elif not getattr(self, "_camera_preview_running", False):
                            self.start_camera_preview(force=True)
                        else:
                            self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                            self.set_camera_state_badge(True)
                    else:
                        self.stop_camera_preview(show_prompt=True)

                    self.handle_startup_background_check_result(True)

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)
                self.camera_debug("CONNECT_EXCEPTION", origin=origin_safe, host=host, elapsed=round(time.monotonic() - attempt_started_at, 2), error=err)
                if session_claimed:
                    try:
                        self.disconnect_pi_oneconnect_session(timeout=5, host=host)
                    except Exception:
                        pass

                def fail(err=err):
                    if is_stale_request():
                        if origin_safe == "settings":
                            # If the visible Settings connection card is still
                            # loading, convert it to failed instead of leaving
                            # the user with a stale infinite Connecting state.
                            dialog = getattr(self, "connection_dialog", None)
                            try:
                                if dialog is not None and dialog.isVisible() and str(getattr(dialog, "state", "") or "").lower() == "loading":
                                    self._settings_connect_in_progress = False
                                    self.pi_connected = False
                                    self.pi_connection_checked = True
                                    self.set_selected_pi_host_runtime(host, connected=False, configure_backend=False)
                                    self.suspend_locking_for_pi_disconnect(err)
                                    self.convert_connection_dialog_to_disconnect_failed(err)
                                    self.set_pi_status_label(connected=False)
                                    self.update_pi_connect_ui_state(connected=False)
                            except Exception:
                                pass
                        return
                    if origin_safe == "settings":
                        self._settings_connect_in_progress = False
                        self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                    self.pi_connection_checked = True
                    if origin_safe == "settings":
                        self.set_selected_pi_host_runtime(host, connected=False, configure_backend=False)
                        self._pi_selected_host_pending_manual_connect = True
                    self.pi_connected = False
                    self.pi_system_user = ""
                    self.pi_device_hostname = ""
                    self.set_face_controls_connection_enabled(False)
                    self.stop_local_unlock("camera service offline")
                    self.camera_debug("CONNECT_FAIL_UI", origin=origin_safe, host=host, elapsed=round(time.monotonic() - attempt_started_at, 2), error=err)
                    self.append_face_log(f"SERVER_STATUS: OFFLINE | {err}")

                    if origin_safe == "settings":
                        self.write_sas_log(
                            "CAMERA CONNECTION FAILED",
                            actor=self.get_audit_actor(),
                            details={
                                "Requested host": host,
                                "Result": "Failed",
                            },
                        )

                    self.set_pi_status_label(connected=False)
                    self.update_pi_connect_ui_state(connected=False)
                    if hasattr(self, "pi_identity_label"):
                        self.pi_identity_label.setText("")
                        self.pi_identity_label.setVisible(False)

                    try:
                        self.clear_all_authorized_users_ui()
                        self._camera_user_stopped = True
                        self.stop_camera_preview(show_prompt=True)
                    except Exception:
                        pass

                    self.finish_connection_dialog_failed(err)

                    if show_disconnect_popup:
                        # Manual/user-visible connection failure.
                        # For Settings Connect, keep the active progress dialog
                        # and convert it to failed. Closing it first can leave the
                        # UI visually stuck at "Connecting...".
                        if not (origin_safe == "settings" and self.is_settings_tab_active()):
                            try:
                                existing = getattr(self, "connection_dialog", None)
                                if existing is not None:
                                    existing.blockSignals(True)
                                    existing.close()
                                    existing.deleteLater()
                            except Exception:
                                pass
                            self.connection_dialog = None

                        if origin_safe == "settings" and self.is_settings_tab_active():
                            # User pressed Connect while already in Settings:
                            # update the SAME progress dialog to failed state.
                            # Do not auto-retry here; the user may be editing the
                            # hostname/IP and should press Connect again when ready.
                            self.suspend_locking_for_pi_disconnect(err)
                            self.convert_connection_dialog_to_disconnect_failed(err)
                            self._pi_disconnect_retry_active = False
                            self._pi_disconnect_retry_running = False
                        elif origin_safe == "startup":
                            self.suspend_locking_for_pi_disconnect(err)
                            if not getattr(self, "_startup_disconnect_popup_shown", False):
                                self._startup_disconnect_popup_shown = True
                                self.show_pi_disconnect_alert_if_needed(err, origin="startup")
                            self.start_pi_disconnect_retry_loop(err)
                        else:
                            self.keep_pi_disconnected_warning_active(err)
                    else:
                        self.suspend_locking_for_pi_disconnect(err)
                        if origin_safe == "settings" and show_progress:
                            self.convert_connection_dialog_to_disconnect_failed(err)
                            self._pi_disconnect_retry_active = False
                            self._pi_disconnect_retry_running = False
                        else:
                            self.start_pi_disconnect_retry_loop(err)

                    self.handle_startup_background_check_result(False, err)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()

    def verify_pi_status_after_action(self: Any, action_name: str = "ACTION"):
        """Check whether local recognition engine is still online after a failed action.

        Some local endpoints can fail because the camera process is busy/stopping,
        but the API is still online. In that case SAS should stay connected and
        should not force the user back to Settings.
        """
        def worker():
            try:
                status = self._local_face_request("GET", "/status", timeout=5)
                if not bool(status.get("stream_healthy", False)) and not bool(status.get("stream_recovering", False)):
                    state = str(status.get("connection_state") or "unknown").strip()
                    error = str(status.get("last_error") or "no fresh RTSP frame").strip()
                    raise RuntimeError(f"RTSP stream is not healthy. State={state}; Error={error}")

                def online(status=status):
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_capture_in_progress(bool(status.get("capture_running", False)))
                    self.set_face_controls_connection_enabled(True)
                    if bool(status.get("stream_healthy", False)):
                        self.set_pi_status_label(connected=True)
                    else:
                        self.set_pi_status_label(connected=True, message="Status: Connected | camera feed recovering")
                    self.append_face_log(f"{action_name}_STATUS: API online")

                self.qt_after(0, online)

            except Exception as e:
                err = str(e)

                def offline(err=err):
                    self.handle_pi_runtime_disconnect(
                        f"Camera disconnected or unreachable after {action_name}. Please check camera. {err}"
                    )

                self.qt_after(0, offline)

        Thread(target=worker, daemon=True).start()

    def _local_face_stop_recognition(self: Any):
        """Handle STOP as a local preview stop.

        The local recognition engine keeps running for workstation unlock; this
        button only closes the Face Recognition tab preview.
        """
        self.face_action_feedback("STOP: Stop requested by user")
        if not getattr(self, "pi_connected", False):
            self.face_action_feedback("STOP_FAILED: Camera service is not connected")
            self.show_pi_disconnected_popup("Camera service is not connected. Please connect from Settings first.")
            return

        self._camera_user_stopped = True
        self.stop_camera_preview(show_prompt=True)
        self.face_action_feedback(
            "STOP: SAS video preview stopped. Local recognition remains active for workstation unlock."
        )

    def _local_face_get_result(self: Any):
        self.face_action_feedback("RECOGNITION: User pressed Recognize")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Camera service is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        # The button is greyed out during capture, but keep this guard as a
        # race-safe fallback in case a click was queued just before it disabled.
        if bool(getattr(self, "face_capture_in_progress", False)):
            self.face_action_feedback(
                "RECOGNITION_BLOCKED: Capture is still running. Press STOP, wait for RTSP camera to stop, then press Recognize."
            )
            return

        """Recognize button starts recognition on the camera."""
        def worker():
            try:
                data = self._local_face_request("POST", "/start-recognition", timeout=20)
                message = data.get("message", "Recognition start requested.")
                def done():
                    self._camera_user_stopped = False
                    self.face_action_feedback(f"RECOGNITION: {message}")
                    try:
                        from services.local_recognition_engine import ENGINE

                        age = ENGINE.last_frame_age_seconds()
                        has_recent_frame = bool(ENGINE.latest_frame is not None and age is not None and age <= 30.0)
                    except Exception:
                        has_recent_frame = False

                    if has_recent_frame and getattr(self, "_camera_preview_running", False):
                        self.set_camera_state_badge(True)
                    else:
                        self.stop_camera_preview()

                        # Give RTSP preview a short moment to warm up before OpenCV connects.
                        # This avoids false "feed lost" when recognition is already running.
                        QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))

                    # Do not call _local_face_test_connection() here.
                    # Recognition should not show the connection-success popup again.
                    self._local_face_refresh_users()

                self.qt_after(0, done)
            except Exception as e:
                err = str(e)
                def fail(err=err):
                    self.face_action_feedback(f"RECOGNITION_FAILED: {err}")
                    # A busy camera can reject /start-recognition while the local recognition engine
                    # is still healthy. Recheck /status instead of treating it as a
                    # network disconnect.
                    self.verify_pi_status_after_action("RECOGNITION")
                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()

    def set_face_controls_busy(self: Any, busy: bool):
        """Grey out face controls while register/delete is running."""
        for name in ("face_capture_btn", "face_recognize_btn", "face_stop_btn", "face_delete_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setEnabled(not busy)
                btn.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.PointingHandCursor)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()

        if hasattr(self, "ntid_input"):
            self.ntid_input.setEnabled(not busy)
        if hasattr(self, "name_input"):
            self.name_input.setEnabled(not busy)

    def set_ntid_input_error(self: Any, message: str = "Please enter NTID before capture"):
        """Highlight NTID field red and show a short prompt in the input."""
        if not hasattr(self, "ntid_input"):
            return

        self.ntid_input.setObjectName("NtidInputError")
        self.ntid_input.setPlaceholderText(message)
        self.ntid_input.style().unpolish(self.ntid_input)
        self.ntid_input.style().polish(self.ntid_input)
        self.ntid_input.update()
        self.ntid_input.setFocus()

    def clear_ntid_input_error(self: Any):
        """Restore NTID field style when user starts typing again."""
        if not hasattr(self, "ntid_input"):
            return

        if self.ntid_input.objectName() != "NtidInputError":
            return

        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter employee ID / NTID for register / delete")
        self.ntid_input.style().unpolish(self.ntid_input)
        self.ntid_input.style().polish(self.ntid_input)
        self.ntid_input.update()

    def validate_primary_ntid(self: Any, action_name: str = "this action") -> str:
        """Validate the manually typed employee ID before Register / Delete."""
        user_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""

        if not user_id:
            self.append_face_log(f"{action_name.upper()}_FAILED: Please enter NTID first")
            self.set_ntid_input_error(f"Please enter NTID before {action_name.lower()}")
            return ""

        # Register validates this value against AD/SOAP before face capture.
        # Delete stays local because the user may already be removed from AD.
        if any(ch.isspace() for ch in user_id):
            self.append_face_log(f"{action_name.upper()}_FAILED: Invalid NTID format {user_id}")
            self.set_ntid_input_error("Employee ID cannot contain spaces")
            return ""

        self.clear_ntid_input_error()
        return user_id

    def _local_face_capture_user(self: Any):
        actor = self.get_audit_actor()
        raw_employee_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""
        raw_display_name = self.name_input.text().strip() if hasattr(self, "name_input") else ""
        audit_employee_id = raw_employee_id.upper() if raw_employee_id else "Not entered"
        audit_name = raw_display_name or "Not entered"

        self.face_action_feedback(
            f"REGISTER: Admin={actor} pressed Register | Name={audit_name} | EmployeeID={audit_employee_id}"
        )
        self.write_sas_log(
            "FACE REGISTER BUTTON PRESSED",
            actor=actor,
            details={
                "Name": audit_name,
                "Employee ID": audit_employee_id,
                "Result": "Register button pressed",
            },
        )

        if not getattr(self, "pi_connected", False):
            reason = "Camera service is not connected."
            self.write_sas_log(
                "FACE USER REGISTER FAILED",
                actor=actor,
                details={
                    "Name": audit_name,
                    "Employee ID": audit_employee_id,
                    "Result": reason,
                },
            )
            self.show_pi_disconnected_popup(reason)
            self.auto_connect_pi_for_face_tab()
            return

        employee_id = self.validate_primary_ntid("register")
        if not employee_id:
            self.write_sas_log(
                "FACE USER REGISTER FAILED",
                actor=actor,
                details={
                    "Name": audit_name,
                    "Employee ID": audit_employee_id,
                    "Result": "Invalid or missing Employee ID / NTID",
                },
            )
            return

        display_name = raw_display_name
        if not display_name:
            self.face_action_feedback(
                f"REGISTER_FAILED: Admin={actor} | EmployeeID={employee_id.upper()} | Error=Employee name is required."
            )
            self.write_sas_log(
                "FACE USER REGISTER FAILED",
                actor=actor,
                details={
                    "Name": "Not entered",
                    "Employee ID": employee_id.upper(),
                    "Result": "Employee name is required",
                },
            )
            if hasattr(self, "name_input"):
                self.name_input.setFocus()
                self.name_input.setPlaceholderText("Employee name is required")
            return

        self.set_face_controls_busy(True)
        self.face_action_feedback(
            f"REGISTER: Validating NTID with AD for {display_name} ({employee_id.upper()}) | Admin={actor}"
        )

        def local_worker():
            try:
                validator = getattr(getattr(self, "ad_service", None), "validate_ntid_exists_with_reason", None)
                if callable(validator):
                    ad_ok, ad_message = validator(employee_id)
                else:
                    ad_ok = bool(self._validate_ntid_in_ad(employee_id))
                    ad_message = (
                        "NTID exists in Active Directory."
                        if ad_ok
                        else "NTID does not exist or AD/SOAP is unreachable."
                    )

                if not ad_ok:
                    def ad_failed(ad_message=ad_message):
                        self.set_face_controls_busy(False)
                        self.face_action_feedback(
                            f"REGISTER_BLOCKED: AD validation failed | Admin={actor} | "
                            f"Name={display_name} | EmployeeID={employee_id.upper()} | Reason={ad_message}"
                        )
                        self.write_sas_log(
                            "FACE USER REGISTER BLOCKED",
                            actor=actor,
                            details={
                                "Name": display_name,
                                "Employee ID": employee_id.upper(),
                                "Result": "AD validation failed",
                                "Reason": ad_message,
                            },
                        )

                    self.qt_after(0, ad_failed)
                    return

                self.qt_after(
                    0,
                    lambda: self.face_action_feedback(
                        f"REGISTER: AD validated | Admin={actor} | "
                        f"Name={display_name} | EmployeeID={employee_id.upper()}"
                    ),
                )

                data = self._local_face_request(
                    "POST",
                    "/capture-user",
                    {
                        "user_id": employee_id,
                        "employee_id": employee_id,
                        "display_name": display_name,
                        "mode": "add",
                    },
                    timeout=30,
                )
                message = data.get("message", "Registration completed.")
                user = data.get("user", {}) if isinstance(data.get("user", {}), dict) else {}
                samples = int(user.get("sample_count", data.get("photos", 0)) or 0)

                def done():
                    self.set_face_controls_busy(False)
                    self.face_action_feedback(
                        f"REGISTER_COMPLETE: Admin={actor} | Name={display_name} | "
                        f"EmployeeID={employee_id.upper()} | samples={samples} | {message}"
                    )
                    self.write_sas_log(
                        "FACE USER REGISTERED",
                        actor=actor,
                        details={
                            "Name": display_name,
                            "Employee ID": employee_id.upper(),
                            "Embeddings": samples,
                            "Result": message,
                        },
                    )
                    if hasattr(self, "name_input"):
                        self.name_input.clear()
                    if hasattr(self, "ntid_input"):
                        self.ntid_input.clear()
                    self._local_face_refresh_users()
                    self._local_face_load_logs()

                self.qt_after(0, done)
            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.set_face_controls_busy(False)
                    self.face_action_feedback(
                        f"REGISTER_FAILED: Admin={actor} | Name={display_name} | "
                        f"EmployeeID={employee_id.upper()} | Error={err}"
                    )
                    self.write_sas_log(
                        "FACE USER REGISTER FAILED",
                        actor=actor,
                        details={
                            "Name": display_name,
                            "Employee ID": employee_id.upper(),
                            "Result": "Failed",
                            "Error": err,
                        },
                    )

                self.qt_after(0, fail)

        Thread(target=local_worker, daemon=True).start()

    def _local_face_delete_user(self: Any):
        actor = self.get_audit_actor()
        raw_user_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""
        audit_user_id = raw_user_id.upper() if raw_user_id else "Not entered"

        self.face_action_feedback(f"DELETE: Admin={actor} pressed Delete | EmployeeID={audit_user_id}")
        self.write_sas_log(
            "FACE DELETE BUTTON PRESSED",
            actor=actor,
            details={
                "Employee ID": audit_user_id,
                "Result": "Delete button pressed",
            },
        )

        if not getattr(self, "pi_connected", False):
            reason = "Camera service is not connected."
            self.write_sas_log(
                "FACE USER DELETE FAILED",
                actor=actor,
                details={"Employee ID": audit_user_id, "Result": reason},
            )
            self.show_pi_disconnected_popup(reason)
            self.auto_connect_pi_for_face_tab()
            return

        user_id = self.validate_primary_ntid("delete")
        if not user_id:
            self.write_sas_log(
                "FACE USER DELETE FAILED",
                actor=actor,
                details={
                    "Employee ID": audit_user_id,
                    "Result": "Invalid or missing Employee ID / NTID",
                },
            )
            return

        self.set_face_controls_busy(True)
        self.face_action_feedback(f"DELETE: Deleting local face data for {user_id.upper()} | Admin={actor}")

        def worker():
            try:
                data = self._local_face_request("POST", "/delete-user", {"user_id": user_id}, timeout=30)
                message = data.get("message", "Delete requested.")
                dataset_removed = bool(data.get("dataset_removed", False))
                encodings_removed = int(data.get("encodings_removed", 0) or 0)

                def done():
                    self.face_action_feedback(
                        f"DELETE_COMPLETE: Admin={actor} | EmployeeID={user_id.upper()} | {message}"
                    )
                    self.write_sas_log(
                        "FACE USER DELETED",
                        actor=actor,
                        details={
                            "Employee ID": user_id.upper(),
                            "Dataset removed": "Yes" if dataset_removed else "No",
                            "Embeddings removed": encodings_removed,
                            "Result": message,
                        },
                    )
                    self.show_delete_complete_popup(
                        ntid=user_id,
                        dataset_removed=dataset_removed,
                        encodings_removed=encodings_removed,
                    )
                    self._local_face_refresh_users()
                    self._local_face_load_logs()
                    self.set_face_controls_busy(False)
                    if hasattr(self, "ntid_input"):
                        self.ntid_input.clear()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.face_action_feedback(
                        f"DELETE_FAILED: Admin={actor} | EmployeeID={user_id.upper()} | Error={err}"
                    )
                    self.write_sas_log(
                        "FACE USER DELETE FAILED",
                        actor=actor,
                        details={"Employee ID": user_id.upper(), "Result": "Failed", "Error": err},
                    )
                    self.set_face_controls_busy(False)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()

    def _local_face_refresh_users(self: Any, show_popup_after: bool = False):
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("CAMERA_SKIPPED: camera hostname/IP is not configured.")
            return

        """Fetch authorised users from local recognition engine /users.

        Background refresh updates UI only. It never opens the View All popup,
        because that caused unstable popups appearing without user action.
        """
        def worker():
            try:
                data = self._local_face_request("GET", "/users")
                users = data.get("users", [])

                def done():
                    was_connected = bool(getattr(self, "pi_connected", False))
                    self.pi_connection_checked = True
                    if was_connected:
                        self.set_face_controls_connection_enabled(True)
                        self.set_pi_status_label(connected=True)
                    self.face_users_cache = users
                    self.render_dashboard_users(users)

                    if hasattr(self, "face_users_layout"):
                        self.render_face_users(users)

                    self.append_face_log(f"USERS_REFRESHED: {len(users)} records")

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    was_connected = getattr(self, "pi_connected", False)
                    self.pi_connection_checked = True
                    if was_connected:
                        try:
                            from services.local_recognition_engine import ENGINE

                            status = ENGINE.status()
                            frame_age = status.get("last_frame_age_seconds")
                            recent_frame = bool(
                                ENGINE.latest_frame is not None
                                and frame_age is not None
                                and float(frame_age) <= 30.0
                            )
                            still_active = bool(
                                status.get("recognition_running", False)
                                or status.get("capture_running", False)
                                or status.get("stream_healthy", False)
                                or status.get("stream_recovering", False)
                                or recent_frame
                            )
                            if still_active:
                                self.pi_connected = True
                                self.set_face_controls_connection_enabled(True)
                                message = "Status: Connected" if status.get("stream_healthy", False) else "Status: Connected | camera feed recovering"
                                self.set_pi_status_label(connected=True, message=message)
                                self.update_pi_connect_ui_state(connected=True)
                                self.set_camera_state_badge(True)
                                self.append_face_log(f"USERS_REFRESH_DELAYED: {err}")
                                return
                        except Exception:
                            pass
                    self.pi_connected = False
                    self.set_face_controls_connection_enabled(False)
                    self.set_pi_status_label(connected=False)
                    self.update_pi_connect_ui_state(connected=False)
                    self.clear_all_authorized_users_ui()
                    if hasattr(self, "face_users_subtitle"):
                        self.face_users_subtitle.setText("CONNECT CAMERA FIRST")
                    self.append_face_log(f"USERS_REFRESH_FAILED: {err}")
                    if was_connected:
                        self.handle_pi_runtime_disconnect("Camera disconnected while refreshing users. Please check camera.")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()

    def render_face_users(self: Any, users):
        """Render Face Recognition authorised users panel.

        Stable repaint version:
        - no row opacity effects
        - no automatic scroll-to-top on every refresh
        - prevents blank/ghost cards after Recognize + scrolling
        """
        if not hasattr(self, "face_users_list_layout"):
            return

        # Preserve current scroll position when refresh is caused by recognition/user refresh.
        current_scroll = 0
        try:
            if hasattr(self, "face_users_scroll"):
                current_scroll = self.face_users_scroll.verticalScrollBar().value()
        except Exception:
            current_scroll = 0

        while self.face_users_list_layout.count():
            item = self.face_users_list_layout.takeAt(0)
            if item is None:
                continue

            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.hide()
                widget.setGraphicsEffect(cast(QGraphicsEffect, None))  # type: ignore[arg-type]
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout_widgets(child_layout)

        users = users or []
        self.face_users_cache = users

        keyword = ""
        if hasattr(self, "face_user_search_input"):
            keyword = self.face_user_search_input.text().strip().lower()

        filtered = [
            u for u in users
            if keyword in str(u.get("id", "")).lower()
        ] if keyword else list(users)

        if hasattr(self, "face_users_subtitle"):
            if users:
                if keyword:
                    self.face_users_subtitle.setText(f"{len(filtered)} / {len(users)} MATCHED")
                else:
                    self.face_users_subtitle.setText(f"{len(users)} ACTIVE RECORDS")
            else:
                self.face_users_subtitle.setText("CONNECT CAMERA FIRST")

        self._open_face_user_expand_card = None

        if not users:
            self.face_users_list_layout.addWidget(
                self.face_user_row("CONNECT CAMERA", "Please connect hostname/IP first")
            )
            self.face_users_list_layout.addStretch()
            return

        if not filtered:
            msg = QLabel("No matching user found.")
            msg.setObjectName("FaceUserEmptyMessage")
            msg.setWordWrap(True)
            self.face_users_list_layout.addWidget(msg)
            self.face_users_list_layout.addStretch()
            return

        for user in filtered:
            uid = str(user.get("id", ""))
            photos = user.get("photos", 0)

            row = self.face_user_row(
                uid.upper(),
                f"{photos} face sample{'s' if int(photos or 0) != 1 else ''}",
            )

            # Prevent rows from stretching into large blank blocks inside QScrollArea.
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.setGraphicsEffect(cast(QGraphicsEffect, None))  # type: ignore[arg-type]

            self.face_users_list_layout.addWidget(row)

        self.face_users_list_layout.addStretch()

        if hasattr(self, "face_users_body"):
            self.face_users_body.updateGeometry()
            self.face_users_body.adjustSize()

        if hasattr(self, "face_users_scroll"):
            self.face_users_scroll.viewport().update()
            self.face_users_scroll.update()

            # Restore old position after refresh; only search clear button naturally changes visible content.
            QTimer.singleShot(
                0,
                lambda value=current_scroll: self.face_users_scroll.verticalScrollBar().setValue(
                    min(value, self.face_users_scroll.verticalScrollBar().maximum())
                )
            )
