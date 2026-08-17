from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase
from services.atomic_file import atomic_write_text


class PiConnectionControllerMixin(DashboardMixinBase):
    def load_or_create_sas_client_id(self) -> str:
        """Return a stable ID for this SAS installation.

        The Pi uses this ID to allow only one Windows SAS workstation to own a
        Pi connection at a time.  It is stored beside credential.txt so it stays
        stable across app restarts but remains unique per installed SAS copy.
        """
        path = globals().get("SAS_CLIENT_ID_FILE", os.path.join(RUNTIME_DATA_DIR, "sas_client_id.txt"))
        try:
            if os.path.exists(path):
                value = open(path, "r", encoding="utf-8").read().strip()
                if value:
                    return value
        except Exception:
            pass

        value = str(uuid.uuid4())
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(value + "\n")
        except Exception:
            pass
        return value


    def get_sas_client_display_name(self) -> str:
        try:
            user = os.getlogin()
        except Exception:
            user = os.environ.get("USERNAME") or os.environ.get("USER") or "SAS"
        try:
            host = socket.gethostname()
        except Exception:
            host = "WindowsSAS"
        return f"{host}\\{user}"


    def oneconnect_payload(self, force: bool = False) -> dict:
        return {
            "client_id": str(getattr(self, "sas_client_id", "") or ""),
            "client_name": str(getattr(self, "sas_client_name", "Windows SAS") or "Windows SAS"),
            "client_user": str(getattr(self, "current_user", "") or ""),
            "client_host": str(socket.gethostname() or ""),
            "force": bool(force),
        }


    def format_oneconnect_session_owner(self, session: dict | None) -> str:
        if not isinstance(session, dict) or not session:
            return "another SAS device"
        name = str(session.get("client_name") or "another SAS device").strip()
        host = str(session.get("client_host") or "").strip()
        connected_at = str(session.get("connected_at") or "").strip()
        parts = [name]
        if host and host.lower() not in name.lower():
            parts.append(f"Host: {host}")
        if connected_at:
            parts.append(f"Connected at: {connected_at}")
        return " | ".join(parts)


    def claim_pi_oneconnect_session(self, force: bool = False, timeout: int = 8, host: str | None = None):
        """Reserve the Pi for this SAS before normal /status connect work."""
        base = self._face_api_base_url(host_override=host)
        url = base + "/sas/connect"
        response = requests.post(url, json=self.oneconnect_payload(force=force), timeout=timeout)
        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code == 409:
            return False, True, str(data.get("message") or "This Pi is already connected with another SAS device."), data
        if not response.ok:
            message = str(data.get("message") or f"Pi session request failed ({response.status_code}).")
            return False, False, message, data
        if not isinstance(data, dict):
            return False, False, "Pi returned an invalid session response.", {}

        self.sas_oneconnect_session = data.get("session") if isinstance(data.get("session"), dict) else None
        return True, False, str(data.get("message") or "Pi connection reserved."), data


    def disconnect_pi_oneconnect_session(self, timeout: int = 8, host: str | None = None):
        try:
            base = self._face_api_base_url(host_override=host)
            response = requests.post(base + "/sas/disconnect", json=self.oneconnect_payload(force=False), timeout=timeout)
            try:
                data = response.json()
            except Exception:
                data = {}
            if not response.ok:
                return False, str(data.get("message") or f"Pi disconnect failed ({response.status_code})."), data
            return True, str(data.get("message") or "Pi disconnected."), data
        except Exception as exc:
            return False, str(exc), {}


    def send_sas_oneconnect_heartbeat(self):
        if not bool(getattr(self, "pi_connected", False)):
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return

        def worker():
            try:
                base = self._face_api_base_url()
                response = requests.post(base + "/sas/heartbeat", json=self.oneconnect_payload(force=False), timeout=5)
                if response.ok:
                    return
                try:
                    data = response.json()
                except Exception:
                    data = {}
                reason = str(data.get("message") or "Pi connection ownership was lost.")
                self.qt_after(0, lambda: self.handle_oneconnect_connection_lost(reason, data.get("session")))
            except Exception:
                # Normal network disconnect path will be handled by status/video checks.
                pass

        Thread(target=worker, daemon=True).start()


    def set_selected_pi_host_runtime(self, host: str, *, connected: bool = False):
        """Commit the user-selected Pi hostname/IP into runtime state.

        This is intentionally separate from a successful API connection.  When
        the user types/saves/connects to a wrong hostname, SAS must remember
        that selected host and stay disconnected instead of silently falling
        back to the previous working Pi.
        """
        host = str(host or "").strip()
        self.pi_api_host = host
        self.pi_api_port = "5000"

        if host:
            try:
                self.face_api_service.configure(host, "5000")
            except Exception:
                pass
            try:
                self.configure_recognition_websocket(host, "5000", start=False)
            except Exception:
                pass
            self.pi_api_base = str(host).rstrip("/") if str(host).startswith("http") else f"http://{host}:5000"
            self.camera_feed_url = f"{self.pi_api_base}/video-feed"
        else:
            self.pi_api_base = ""
            self.camera_feed_url = ""
            try:
                self.configure_recognition_websocket("", "5000", start=False)
            except Exception:
                pass

        if not connected:
            self.pi_connected = False
            self.pi_connection_checked = True
            self.pi_system_user = ""
            self.pi_device_hostname = ""
            self.sas_oneconnect_session = None

        try:
            if hasattr(self, "pi_host_input"):
                current = self.pi_host_input.text().strip()
                if current != host:
                    self.pi_host_input.blockSignals(True)
                    self.pi_host_input.setText(host)
                    self.pi_host_input.blockSignals(False)
        except Exception:
            pass


    def handle_pi_host_text_edited(self, _text: str = ""):
        """Let users type a Pi hostname/IP without triggering background auto-connect.

        Only the explicit Connect button should use the live text in this field.
        Startup/retry/health checks continue to use the last connected/saved host,
        and are paused while the Settings host field is dirty or focused.
        """
        self.mark_settings_modified_by_user()
        self._pi_host_dirty_since_edit = True
        self._pi_host_user_editing = True
        self._pi_selected_host_pending_manual_connect = True
        # Invalidate any in-flight connect/retry worker started for the old host.
        try:
            self._pi_connect_request_token = int(getattr(self, "_pi_connect_request_token", 0)) + 1
        except Exception:
            self._pi_connect_request_token = 1
        self.pi_connected = False
        self.pi_connection_checked = False
        self.sas_oneconnect_session = None
        self._startup_background_check_pending = False
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._pi_disconnect_lock_suspended = False
        try:
            self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
        except Exception:
            pass
        try:
            self.stop_recognition_websocket("Pi host edited")
        except Exception:
            pass
        try:
            self.clear_all_authorized_users_ui()
        except Exception:
            pass
        try:
            self.set_face_controls_connection_enabled(False)
        except Exception:
            pass
        try:
            self.set_pi_status_label(connected=False, message="Status: Disconnected")
        except Exception:
            pass
        try:
            self.update_pi_connect_ui_state(connected=False, checking=False)
        except Exception:
            pass


    def is_manual_settings_connect_in_progress(self) -> bool:
        """True while the user-pressed Settings Connect dialog is still active.

        Background retry must not run during this window.  Otherwise a retry
        request can change the global connect token before the manual failed
        request returns, so the manual failure is ignored as stale and the
        dialog remains stuck in the loading state.
        """
        if getattr(self, "_settings_connect_in_progress", False):
            return True
        dialog = getattr(self, "connection_dialog", None)
        if dialog is None:
            return False
        try:
            if not dialog.isVisible():
                return False
            return str(getattr(dialog, "origin", "") or "").lower() == "settings" and str(getattr(dialog, "state", "") or "").lower() == "loading"
        except Exception:
            return False


    def is_pi_host_editing_blocking_auto_connect(self) -> bool:
        """True when background auto-connect/retry should not read the Settings field."""
        try:
            if not self.is_settings_tab_active():
                return False
        except Exception:
            pass
        host_input = getattr(self, "pi_host_input", None)
        focused = False
        try:
            focused = bool(host_input is not None and host_input.hasFocus())
        except Exception:
            focused = False
        return bool(getattr(self, "_pi_host_dirty_since_edit", False) or focused)


    def get_pi_host_for_connection_origin(self, origin: str = "") -> str:
        """Settings Connect uses the typed field; background checks use active host only."""
        origin_safe = str(origin or "").strip().lower()
        if origin_safe == "settings":
            return self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else str(getattr(self, "pi_api_host", "") or "").strip()
        return str(getattr(self, "pi_api_host", "") or "").strip()


    def update_pi_connect_ui_state(self, connected: bool | None = None, checking: bool = False):
        connected = bool(getattr(self, "pi_connected", False)) if connected is None else bool(connected)
        btn = getattr(self, "pi_connect_btn", None)
        host_input = getattr(self, "pi_host_input", None)

        if btn is not None:
            if checking:
                btn.setText("Connecting...")
                btn.setEnabled(False)
                btn.setObjectName("SettingsPrimaryButton")
            elif connected:
                btn.setText("Disconnect")
                btn.setEnabled(True)
                btn.setObjectName("SettingsDangerButton")
            else:
                btn.setText("Connect")
                btn.setEnabled(True)
                btn.setObjectName("SettingsPrimaryButton")
            # Keep the Disconnect/disabled states using the normal cursor.
            # The button text/color already communicates the state, so avoid the
            # disabled/forbidden cursor when hovering Disconnect or Connecting.
            if checking or connected:
                btn.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

        if host_input is not None:
            editable = not connected and not checking
            host_input.setEnabled(editable)
            host_input.setReadOnly(not editable)
            host_input.setToolTip(
                "Disconnect before editing the Pi hostname/IP."
                if connected else "Enter the Pi hostname or IP address."
            )


    def toggle_pi_connection_from_settings(self):
        if bool(getattr(self, "pi_connected", False)):
            self.disconnect_pi_from_settings()
            return

        # v122: a user-pressed Connect must own the connection attempt.
        # Stop any disconnected/background retry first; otherwise the retry
        # can invalidate the manual request token and leave the popup showing
        # "Connecting..." forever for wrong hostnames or powered-off Pis.
        self._settings_connect_in_progress = True
        self._pi_disconnect_retry_active = False
        self._pi_disconnect_retry_running = False
        self._manual_connect_failed_popup_active = False
        try:
            self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
        except Exception:
            self._settings_connect_attempt_id = 1

        self._face_api_test_connection(
            show_disconnect_popup=True,
            show_progress=True,
            origin="settings",
        )


    def disconnect_pi_from_settings(self):
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        self.set_pi_status_label(checking=True, message="Status: Disconnecting...")
        self.update_pi_connect_ui_state(connected=True, checking=True)

        def worker():
            ok, message, _data = self.disconnect_pi_oneconnect_session(timeout=8)

            def done():
                self._pi_disconnect_retry_active = False
                self._pi_disconnect_retry_running = False
                self._pi_disconnect_lock_suspended = False
                self.pi_connected = False
                self.pi_connection_checked = True
                self._pi_selected_host_pending_manual_connect = True
                self.pi_system_user = ""
                self.pi_device_hostname = ""
                self.sas_oneconnect_session = None
                self.stop_recognition_websocket("manual disconnect")
                self.set_face_controls_connection_enabled(False)
                self.clear_all_authorized_users_ui()
                self.stop_camera_preview(show_prompt=True)
                self.set_pi_status_label(connected=False, message="Status: Disconnected")
                self.update_pi_connect_ui_state(connected=False)
                self.append_face_log(f"PI_DISCONNECT: {message}")
                self.write_sas_log(
                    "PI DISCONNECTED",
                    actor=self.get_audit_actor(),
                    details={"Pi host": host or "-", "Result": "Manual disconnect" if ok else message},
                )

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()


    def close_connection_dialog_silently(self):
        """Close the Settings Connect progress card before showing a conflict-only modal."""
        dialog = getattr(self, "connection_dialog", None)
        if dialog is None:
            return
        try:
            dialog.accept()
        except Exception:
            try:
                dialog.close()
            except Exception:
                pass
        self.connection_dialog = None


    def show_oneconnect_conflict_prompt(self, active_session: dict | None, message: str = ""):
        """Show the premium close-only popup only when another SAS owns the selected Pi."""
        host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else ""
        if not host:
            host = str(getattr(self, "pi_api_host", "") or "").strip()
        if not host and isinstance(active_session, dict):
            host = str(active_session.get("hostname") or active_session.get("host") or "").strip()
        self.show_oneconnect_conflict_dialog(host or "selected hostname")
        self.append_face_log("PI_CONNECT_CANCELLED: Pi is already connected with another SAS device.")


    def show_oneconnect_conflict_dialog(self, hostname: str = "selected hostname"):
        """Close-only dialog for the 'hostname already connected by others' case."""
        if self.is_login_popup_active():
            self.append_face_log("PI_CONNECT_BLOCKED: Active connection popup suppressed while login is open.")
            return

        existing = getattr(self, "_oneconnect_conflict_dialog", None)
        try:
            if existing is not None and existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return
        except Exception:
            pass

        safe_host = html.escape(str(hostname or "selected hostname").strip() or "selected hostname")

        dialog = QDialog(self)
        self._oneconnect_conflict_dialog = dialog
        dialog.setObjectName("OneConnectConflictDialog")
        dialog.setModal(True)
        dialog.setWindowTitle("Active Connection Detected")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setFixedSize(520 if not self.compact_mode else 460, 390 if not self.compact_mode else 360)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("OneConnectConflictCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        try:
            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(22)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 45))
            card.setGraphicsEffect(shadow)
        except Exception:
            pass

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("OneConnectConflictTopBar")
        top_bar.setFixedHeight(4)
        layout.addWidget(top_bar)

        body = QVBoxLayout()
        body.setContentsMargins(38, 26, 38, 24)
        body.setSpacing(0)

        icon_circle = QLabel("⊘")
        icon_circle.setObjectName("OneConnectConflictIcon")
        icon_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_circle.setFixedSize(64, 64)
        icon_font = QFont("Inter")
        icon_font.setPointSize(32)
        icon_font.setWeight(QFont.Weight.Light)
        icon_circle.setFont(icon_font)
        body.addWidget(icon_circle, 0, Qt.AlignmentFlag.AlignHCenter)
        body.addSpacing(16)

        title = QLabel("Active Connection Detected")
        title.setObjectName("OneConnectConflictTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        body.addWidget(title)
        body.addSpacing(6)

        desc = QLabel(
            'The hostname <span style="font-family: Consolas, Courier New, monospace; '
            'font-weight: 800; color: #000000; background-color: #e8e8e8;">'
            f'&nbsp;{safe_host}&nbsp;</span> is currently occupied by other authorized users.'
        )
        desc.setObjectName("OneConnectConflictDescription")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(desc)
        body.addSpacing(20)

        close_btn = QPushButton("CLOSE")
        close_btn.setObjectName("OneConnectConflictCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(190, 44)
        close_btn.clicked.connect(dialog.reject)
        body.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(body)
        outer.addWidget(card)

        dialog.setStyleSheet("""
            QDialog#OneConnectConflictDialog {
                background: rgba(0, 0, 0, 95);
            }
            QFrame#OneConnectConflictCard {
                background: #ffffff;
                border: 1px solid #c4c7c7;
                border-radius: 12px;
            }
            QFrame#OneConnectConflictTopBar {
                background: #000000;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#OneConnectConflictIcon {
                background: #e8e8e8;
                color: #000000;
                border-radius: 32px;
            }
            QLabel#OneConnectConflictTitle {
                color: #000000;
                font-family: Inter, Segoe UI, Arial;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#OneConnectConflictDescription {
                color: #5e5e5e;
                font-family: Inter, Segoe UI, Arial;
                font-size: 12px;
                line-height: 17px;
            }
            QPushButton#OneConnectConflictCloseButton {
                background: #000000;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 1.2px;
            }
            QPushButton#OneConnectConflictCloseButton:hover {
                background: #00174b;
            }
            QPushButton#OneConnectConflictCloseButton:pressed {
                background: #000000;
                padding-top: 2px;
            }
        """)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            try:
                if getattr(self, "_oneconnect_conflict_dialog", None) is dialog:
                    self._oneconnect_conflict_dialog = None
            except Exception:
                pass
            self.resume_camera_after_modal()


    def handle_oneconnect_connection_lost(self, reason: str = "Pi connection ownership lost.", active_session: dict | None = None):
        self.pi_connection_checked = True
        self.pi_connected = False
        self.pi_system_user = ""
        self.pi_device_hostname = ""
        self.sas_oneconnect_session = None
        self.stop_recognition_websocket("oneconnect lost")
        self.set_face_controls_connection_enabled(False)
        self.clear_all_authorized_users_ui()
        # Silent disconnect only: do not show a modal popup when another SAS
        # takes over the Pi connection or when ownership is lost. The Settings
        # status label, Connect button state, and face log are enough feedback.
        self.stop_camera_preview(show_prompt=False)
        self.set_pi_status_label(connected=False, message="Status: Disconnected")
        self.update_pi_connect_ui_state(connected=False)
        self.append_face_log(f"PI_ONECONNECT_LOST: {reason}")


    def camera_feed_card(self):
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
        self.camera_guidance_message = ""

        layout.addLayout(top)
        layout.addWidget(self.camera_preview_label, 1)

        QTimer.singleShot(300, self.check_pi_camera_status_and_update_panel)
        return card


    def set_camera_guidance_message(self, message: str = ""):
        self.camera_guidance_message = str(message or "").strip()


    def draw_camera_guidance_overlay(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap

        try:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            w = max(1, pixmap.width())
            h = max(1, pixmap.height())
            guide_w = int(w * (0.34 if w >= 700 else 0.42))
            guide_h = int(h * 0.62)
            x = (w - guide_w) // 2
            y = max(14, int(h * 0.13))

            message = str(getattr(self, "camera_guidance_message", "") or "").strip()
            color = QColor(245, 158, 11) if message else QColor(34, 197, 94)
            painter.setPen(QPen(color, 3))
            painter.drawRoundedRect(QRect(x, y, guide_w, guide_h), 14, 14)

            corner = max(20, int(min(guide_w, guide_h) * 0.12))
            painter.setPen(QPen(color, 5))
            painter.drawLine(x, y, x + corner, y)
            painter.drawLine(x, y, x, y + corner)
            painter.drawLine(x + guide_w, y, x + guide_w - corner, y)
            painter.drawLine(x + guide_w, y, x + guide_w, y + corner)
            painter.drawLine(x, y + guide_h, x + corner, y + guide_h)
            painter.drawLine(x, y + guide_h, x, y + guide_h - corner)
            painter.drawLine(x + guide_w, y + guide_h, x + guide_w - corner, y + guide_h)
            painter.drawLine(x + guide_w, y + guide_h, x + guide_w, y + guide_h - corner)

            if message:
                band_h = 44 if not self.compact_mode else 38
                band = QRect(12, max(12, h - band_h - 12), max(1, w - 24), band_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(15, 23, 42, 210))
                painter.drawRoundedRect(band, 10, 10)
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                font = painter.font()
                font.setPointSize(10 if not self.compact_mode else 9)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(band.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, message)

            painter.end()
        except Exception:
            pass

        return pixmap



    def check_pi_camera_status_and_update_panel(self):
        host = str(getattr(self, "pi_api_host", "") or "").strip()
        if not host:
            self.append_face_log("PI_SKIPPED: Pi hostname/IP is not configured.")
            return

        """Check Pi /status before opening /video-feed.

        This prevents startup from showing a stale MJPEG frame when the Pi camera
        is already stopped.
        """
        # If Pi is connected, always verify /status instead of trusting old
        # _camera_user_stopped state from a previous disconnect.
        if getattr(self, "_camera_user_stopped", False) and not getattr(self, "pi_connected", False):
            self.show_camera_stopped_prompt("Camera stopped")
            return

        self.set_pi_status_label(checking=True)

        def worker():
            try:
                self._face_api_base_url()
                data = self._face_api_request("GET", "/status", timeout=8, host_override=host)

                rec = bool(data.get("recognition_running", False))
                cap = bool(data.get("capture_running", False))

                def done():
                    if str(locals().get("origin", locals().get("origin_safe", "")) or "") == "settings":
                        self._settings_connect_attempt_id = int(getattr(self, "_settings_connect_attempt_id", 0)) + 1
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self.pi_api_host = host
                    self.pi_api_port = "5000"
                    self._face_api_base_url()
                    self.resume_locking_after_pi_reconnect()
                    self.set_face_capture_in_progress(cap)
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self._handling_pi_disconnect = False

                    # An explicit SAS Stop must remain stopped in the Windows UI.
                    # The Pi can need a short cleanup interval before /status changes,
                    # so do not re-open the preview just because one status response
                    # still reports an active camera mode.
                    if getattr(self, "_camera_user_stopped", False):
                        self.stop_camera_preview(show_prompt=True)
                    elif rec or cap:
                        self.stop_camera_preview()
                        QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))
                    else:
                        self.stop_camera_preview(show_prompt=True)
                        self.append_face_log("CAMERA_STATUS: Pi API online, camera is stopped.")

                    # Keep Dashboard and Face Recognition authorised users aligned.
                    self._face_api_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.stop_camera_preview(show_prompt=True)
                    self.append_face_log(f"CAMERA_STATUS_FAILED: {err}")
                    self.handle_pi_runtime_disconnect("Pi disconnected or unreachable. Please check Pi.")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()


    def set_camera_state_badge(self, live: bool = False, stopped: bool = False):
        if not hasattr(self, "camera_state_badge"):
            return

        if stopped:
            self.camera_state_badge.setText("●  Stop")
            self.camera_state_badge.setObjectName("CameraStateStopBadge")
        elif live:
            self.camera_state_badge.setText("●  Live")
            self.camera_state_badge.setObjectName("CameraStateLiveBadge")
        else:
            self.camera_state_badge.setText("●  End")
            self.camera_state_badge.setObjectName("CameraStateEndBadge")

        self.camera_state_badge.style().unpolish(self.camera_state_badge)
        self.camera_state_badge.style().polish(self.camera_state_badge)
        self.camera_state_badge.update()



    def show_camera_stopped_prompt(self, message: str = "Camera stopped"):
        """Blacken camera panel and prompt user after Stop is pressed.

        Important: clear the QLabel pixmap first. Otherwise the last video frame
        can remain painted until the second Stop click.
        """
        if not hasattr(self, "camera_preview_label"):
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



    def pause_camera_for_modal(self):
        """Temporarily pause camera repainting while a heavy popup animation is shown."""
        self._modal_open_count = getattr(self, "_modal_open_count", 0) + 1

        timer = getattr(self, "camera_timer", None)
        if timer is not None:
            self._camera_resume_after_modal = True
            try:
                timer.stop()
            except Exception:
                pass


    def resume_camera_after_modal(self):
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


    def handle_camera_feed_unavailable(self, reason: str = "Pi camera feed unavailable."):
        """Camera feed failure is not always Pi disconnect.

        The Pi API can be online while /video-feed is unavailable or stopped.
        In that case, keep Pi connected and only show the camera-stopped prompt.
        Only mark Pi disconnected if /status also fails.
        """
        def worker():
            try:
                data = self._face_api_request("GET", "/status", timeout=5)
                time.sleep(0.45)
                data = self._face_api_request("GET", "/status", timeout=5)
                rec = bool(data.get("recognition_running", False))
                cap = bool(data.get("capture_running", False))
                users = data.get("users", None)

                def api_online():
                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self._handling_pi_disconnect = False

                    self._camera_preview_running = False
                    self.camera_capture = None
                    self.set_camera_state_badge(False)

                    if hasattr(self, "camera_preview_label"):
                        self.camera_preview_label.setPixmap(QPixmap())
                        if rec or cap:
                            self.camera_preview_label.setText("Camera feed unavailable.\nPi API is online. Please retry Recognize or check camera.")
                        else:
                            self.show_camera_stopped_prompt("Camera stopped")

                    self.append_face_log(f"CAMERA_FEED_UNAVAILABLE: {reason} | API online")

                    # Keep authorised users/dashboard consistent if /status only returns count.
                    try:
                        self._face_api_refresh_users()
                    except Exception:
                        pass

                self.qt_after(0, api_online)

            except Exception:
                self.qt_after(0, lambda: self.handle_pi_runtime_disconnect("Pi disconnected or unreachable. Please check Pi power/network."))

        Thread(target=worker, daemon=True).start()



    def handle_pi_runtime_disconnect(self, reason: str = "Pi disconnected. Please check Pi power/network and reconnect from Settings."):
        """Handle Pi shutdown / network loss without freezing the SAS UI."""
        if getattr(self, "_handling_pi_disconnect", False):
            return

        self._handling_pi_disconnect = True

        try:
            self.pi_connection_checked = True
            self.pi_connected = False
            self.set_face_controls_connection_enabled(False)
            self.set_pi_status_label(connected=False)
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
                self.camera_preview_label.setText("Pi disconnected.\nPlease check Pi power/network and reconnect from Settings.")

            self.set_camera_state_badge(False)
            self.clear_all_authorized_users_ui()
            self.append_face_log(f"PI_DISCONNECTED: {reason}")
            try:
                self.mark_locked_notification_camera_unavailable("Disconnected")
            except Exception:
                pass
            self.keep_pi_disconnected_warning_active(reason)
            self.show_pi_disconnect_alert_if_needed(reason, force=True, origin="runtime")

        finally:
            # Allow a future disconnect popup after user reconnects/fails again.
            self.qt_after(1200, lambda: setattr(self, "_handling_pi_disconnect", False))



    def render_camera_frame_from_worker(self, frame):
        """Render camera frame sent from background camera worker.

        This keeps OpenCV read() away from the Qt UI thread, preventing
        the whole SAS app from becoming Not Responding when Pi power/network drops.
        """
        if getattr(self, "_modal_open_count", 0) > 0:
            return

        if frame is None or not hasattr(self, "camera_preview_label"):
            return

        if cv2 is None:
            return

        cv2_mod = cv2

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
            pixmap = self.draw_camera_guidance_overlay(pixmap)

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

        except Exception as e:
            self.append_face_log(f"CAMERA_RENDER_FAILED: {e}")



    def start_camera_preview(self, force: bool = False):
        """Start camera preview from Raspberry Pi API /video-feed.

        v113:
        OpenCV VideoCapture/read is moved to a background thread.
        This prevents the whole SAS application from freezing if the Pi is
        powered off while recognition/video-feed is running.
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

        cv2_mod = cv2

        self._face_api_base_url()
        self.camera_feed_url = f"{self.pi_api_base}/video-feed"

        self.camera_preview_label.setObjectName("CameraPreviewLabel")
        self.camera_preview_label.style().unpolish(self.camera_preview_label)
        self.camera_preview_label.style().polish(self.camera_preview_label)
        self.camera_preview_label.setPixmap(QPixmap())
        self.camera_preview_label.setText("Connecting to Pi camera feed...")
        self.set_camera_state_badge(False)

        self._camera_preview_running = True
        self.camera_frame_count = 0
        self.camera_last_tick = datetime.now()

        def camera_worker(feed_url=self.camera_feed_url):
            cap = None
            fail_count = 0
            reconnect_count = 0
            first_frame_received = False

            def open_capture():
                new_cap = cv2_mod.VideoCapture(feed_url)

                # Best effort timeout settings. Some OpenCV builds ignore these,
                # but when supported they prevent long blocking during Pi shutdown.
                try:
                    new_cap.set(cv2_mod.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
                    new_cap.set(cv2_mod.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
                    new_cap.set(cv2_mod.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass

                return new_cap

            try:
                cap = open_capture()
                self.camera_capture = cap

                if not cap.isOpened():
                    # Do not instantly mark unavailable. Pi recognition may still be warming up.
                    time.sleep(0.6)
                    try:
                        cap.release()
                    except Exception:
                        pass

                    cap = open_capture()
                    self.camera_capture = cap

                    if not cap.isOpened():
                        self.qt_after(0, lambda: self.handle_camera_feed_unavailable(f"Unable to open Pi camera feed: {feed_url}"))
                        return

                self.qt_after(0, lambda: self.append_face_log("CAMERA_FEED: Connected to Pi /video-feed"))
                self.qt_after(0, lambda: self.set_camera_state_badge(True))

                while getattr(self, "_camera_preview_running", False):
                    ok, frame = cap.read()

                    if not ok or frame is None:
                        fail_count += 1

                        # Early frames can fail when Pi recognition is already running but
                        # Flask/OpenCV stream is still warming up. Retry longer before showing
                        # unavailable.
                        max_fail = 18 if not first_frame_received else 10

                        if fail_count >= max_fail:
                            reconnect_count += 1
                            fail_count = 0

                            try:
                                cap.release()
                            except Exception:
                                pass

                            time.sleep(0.35)

                            cap = open_capture()
                            self.camera_capture = cap

                            if cap.isOpened() and reconnect_count <= 3:
                                self.qt_after(0, lambda n=reconnect_count: self.append_face_log(f"CAMERA_FEED: Reconnected stream attempt {n}"))
                                continue

                            self.qt_after(0, lambda: self.handle_camera_feed_unavailable("Pi camera feed lost after retry."))
                            break

                        time.sleep(0.12)
                        continue

                    first_frame_received = True
                    fail_count = 0
                    reconnect_count = 0

                    # Copy because OpenCV reuses frame memory.
                    frame_copy = frame.copy()
                    self.qt_after(0, lambda f=frame_copy: self.render_camera_frame_from_worker(f))

                    # Limit UI updates; video preview does not need 30 FPS.
                    time.sleep(0.06)

            except Exception as e:
                err = str(e)
                self.qt_after(0, lambda err=err: self.handle_camera_feed_unavailable(f"Pi camera feed error: {err}"))

            finally:
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass

                self.camera_capture = None
                self._camera_preview_running = False

        Thread(target=camera_worker, daemon=True).start()




    def update_camera_frame(self):
        """Compatibility no-op.

        Camera frames are now read in a background worker thread to avoid UI
        freeze when Pi is powered off or network drops.
        """
        return



    def stop_camera_preview(self, show_prompt: bool = False):
        """Stop camera preview reliably without blocking UI."""
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



    def _face_api_base_url(self, host_override: str | None = None):
        # Pi API port is fixed to 5000. User only configures hostname/IP.
        # Runtime/API calls use the last committed Pi host. Explicit Settings
        # Connect passes host_override so half-typed text is never used by
        # background retry/health checks.
        commit_host = host_override is None
        if host_override is not None:
            host = str(host_override or "").strip()
        else:
            host = str(getattr(self, "pi_api_host", "") or "").strip()
        port = "5000"

        if not host:
            raise RuntimeError("Pi hostname/IP is not configured. Please set it in Settings first.")

        if host.startswith("http"):
            base_url = host.rstrip("/")
            self.face_api_service.configure(host, port)
            if commit_host:
                self.pi_api_base = base_url
                self.pi_api_host = host
                self.pi_api_port = port
                self.configure_recognition_websocket(host, port, start=False)
                self.camera_feed_url = f"{self.pi_api_base}/video-feed"
            return base_url

        base_url = f"http://{host}:{port}"
        self.face_api_service.configure(host, port)
        if commit_host:
            self.pi_api_host = host
            self.pi_api_port = port
            self.pi_api_base = base_url
            self.camera_feed_url = f"{self.pi_api_base}/video-feed"
            self.configure_recognition_websocket(host, port, start=False)
        return base_url



    def _face_api_request(self, method, endpoint, payload=None, timeout=10, host_override: str | None = None):
        self._face_api_base_url(host_override=host_override)
        return self.face_api_service.request(method, endpoint, payload=payload, timeout=timeout)



    def show_connection_dialog(self, origin: str = "settings"):
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

        dialog = PiConnectionDialog(
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


    def finish_connection_dialog_success(self, users: int = 0, recognition: bool = False, capture: bool = False):
        dialog = getattr(self, "connection_dialog", None)
        if dialog is not None:
            dialog.set_success(users=users, recognition=recognition, capture=capture)


    def finish_connection_dialog_failed(self, error_text: str = ""):
        # v200: If this is a Pi-disconnect condition, use the single no-close
        # disconnect popup instead of the older failed dialog with a close button.
        if getattr(self, "_pi_disconnect_lock_suspended", False) or getattr(self, "_pi_disconnect_retry_active", False):
            self.show_pi_disconnected_popup(error_text)
            return

        dialog = getattr(self, "connection_dialog", None)
        if dialog is not None:
            dialog.set_failed(error_text)




    def clear_disconnect_popup_overlay(self):
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



    def wire_pi_disconnect_return_button(self, dialog):
        """Connect the Pi disconnect dialog's visible action button to restore SAS."""
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



    def show_face_tab_pi_disconnect_popup(self, reason: str = ""):
        """Show Pi disconnected popup when user tries to open Face Recognition.

        This is a user action, so it must bypass Settings-tab auto-popup
        suppression and stale popup flags.
        """
        try:
            self._allow_settings_disconnect_popup_once = True
            self._pi_disconnect_popup_visible = False
            self.suspend_locking_for_pi_disconnect(reason or "Please connect Pi hostname/IP from Settings first.")
            self.show_pi_disconnected_popup(reason or "Please connect Pi hostname/IP from Settings first.")
        except Exception as e:
            print("[FACE TAB DISCONNECT POPUP ERROR]", e)



    def convert_connection_dialog_to_disconnect_failed(self, error_text: str = ""):
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
            self.show_pi_disconnected_popup(error_text or "Raspberry Pi disconnected.")
            self._manual_connect_failed_popup_active = False
            return

        try:
            dialog.set_failed(error_text or "Raspberry Pi disconnected. Please check Pi power/network.")
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
                self.suspend_locking_for_pi_disconnect(error_text or "Raspberry Pi disconnected.")
                self.start_pi_disconnect_retry_loop(error_text or "Raspberry Pi disconnected.")

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


    def show_pi_disconnected_popup(self, error_text: str = ""):
        """Show Pi disconnected popup using the original connection card UI.

        v213:
        - Restores the previous disconnect UI/card style.
        - Removes the custom v212 white-card popup.
        - Restores/raises SAS first when minimized/background.
        - Keeps no-close behaviour and Return to Settings action.
        """
        if self.is_login_popup_active():
            self.defer_pi_disconnect_until_after_login(error_text or "Raspberry Pi disconnected.", "dialog")
            return

        if (
            self.is_settings_tab_active()
            and not self.is_sas_minimized_or_background()
            and not getattr(self, "_allow_settings_disconnect_popup_once", False)
        ):
            return
        self._allow_settings_disconnect_popup_once = False

        # v131: Pi-disconnect warning has higher priority than Guidelines.
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

        if self.is_sas_minimized_or_background():
            try:
                self.ensure_taskbar_window_identity()
            except Exception:
                pass
            try:
                self._minimized_by_sas = False
            except Exception:
                pass
            try:
                self.setWindowState(
                    (self.windowState() & ~Qt.WindowState.WindowMinimized)
                    | Qt.WindowState.WindowActive
                )
                self.show()
                self.showMaximized()
                self.raise_()
                self.activateWindow()
                QApplication.setActiveWindow(self)
            except Exception:
                pass

        # Use the original connection status card/popup. Do not detach it into a
        # new top-level dialog, because that caused the UI to look different.
        dialog = self.show_connection_dialog(origin="settings")
        dialog.set_failed(error_text or "Raspberry Pi disconnected. Please check Pi power/network.")

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
                self.suspend_locking_for_pi_disconnect(error_text or "Raspberry Pi disconnected.")
                self.start_pi_disconnect_retry_loop(error_text or "Raspberry Pi disconnected.")

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



    def auto_connect_pi_for_face_tab(self):
        """Compatibility wrapper.

        Face Recognition tab no longer reconnects automatically.
        Users connect from Settings, then Face Recognition uses that successful connection.
        """
        if not getattr(self, "pi_connected", False):
            self.show_face_tab_pi_disconnect_popup("Please connect Pi hostname/IP from Settings first.")



    def _face_api_test_connection(self, show_disconnect_popup: bool = False, show_progress: bool = True, origin: str = "settings", force_takeover: bool = False):
        """Connect to Pi Face Recognition API and load status/users/logs.

        v110 fixes:
        - Settings Connect tests the hostname currently typed by the user.
        - All API calls inside that attempt use the same typed hostname, not the
          previously connected/saved hostname.
        - Old retry/connect workers are ignored if the user edits the hostname
          before the worker returns.
        """
        origin_safe = str(origin or "")
        host = self.get_pi_host_for_connection_origin(origin_safe)
        if not host:
            if origin_safe == "settings":
                self._settings_connect_in_progress = False
            reason = self.handle_missing_pi_host_disconnect_state(
                origin=origin_safe or "auto",
                force_popup=bool(show_disconnect_popup and origin_safe not in {"settings"}),
            )
            self.configure_recognition_websocket("", self.pi_api_port, start=False)
            self.append_face_log("SERVER_STATUS: SKIPPED | Pi hostname/IP is not configured.")
            if origin_safe == "settings":
                self.show_settings_message(
                    "Pi Host Required",
                    "Please enter the Raspberry Pi hostname or IP address before connecting.",
                    success=False,
                    issues=[("MISSING PI HOST", "Pi hostname/IP is required to connect to the Face Recognition API.")],
                    server_path=self.server_path,
                )
            self.handle_startup_background_check_result(False, reason)
            return

        try:
            self._pi_connect_request_token = int(getattr(self, "_pi_connect_request_token", 0)) + 1
        except Exception:
            self._pi_connect_request_token = 1
        request_token = int(getattr(self, "_pi_connect_request_token", 0))

        if origin_safe == "settings":
            # Commit the typed host immediately as the selected runtime host.
            # Even if this connection fails, background checks and future tab
            # changes must keep using this host, not the previous successful Pi.
            # Also stop any previous disconnected retry so the manual Settings
            # Connect result cannot be invalidated by a background request.
            self._settings_connect_in_progress = True
            self._pi_disconnect_retry_active = False
            self._pi_disconnect_retry_running = False
            self._manual_connect_failed_popup_active = False
            self.set_selected_pi_host_runtime(host, connected=False)
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
                            self.suspend_locking_for_pi_disconnect("Pi connection timed out. Please check Pi hostname/IP and network.")
                            self.convert_connection_dialog_to_disconnect_failed(
                                "Pi connection timed out. Please check Pi hostname/IP and network."
                            )
                            self.set_pi_status_label(connected=False)
                            self.update_pi_connect_ui_state(connected=False)
                    except Exception as e:
                        print("[SETTINGS CONNECT TIMEOUT GUARD ERROR]", e)

                QTimer.singleShot(10000, settings_connect_timeout_guard)

        self.set_pi_status_label(checking=True)
        self.update_pi_connect_ui_state(connected=False, checking=True)

        def is_stale_request() -> bool:
            try:
                return request_token != int(getattr(self, "_pi_connect_request_token", 0))
            except Exception:
                return True

        def worker():
            session_claimed = False
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
                            self.set_selected_pi_host_runtime(host, connected=False)
                            self._pi_selected_host_pending_manual_connect = True
                            self.pi_connected = False
                            self.set_face_controls_connection_enabled(False)
                            self.stop_recognition_websocket("oneconnect conflict")
                            self.set_pi_status_label(connected=False, message="Status: Already connected")
                            self.update_pi_connect_ui_state(connected=False)
                            self.close_connection_dialog_silently()
                            self.append_face_log(f"PI_CONNECT_BLOCKED: {session_message}")
                            self.write_sas_log(
                                "PI CONNECTION BLOCKED",
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
                # contain the previous Pi hostname.
                data = self._face_api_request("GET", "/status", timeout=8, host_override=host)
                users = data.get("users", 0)
                rec = data.get("recognition_running", False)
                cap = data.get("capture_running", False)
                pi_hostname = str(data.get("hostname") or data.get("device_name") or "").strip()
                pi_user = str(data.get("system_user") or data.get("ssh_username") or "").strip()
                msg = f"SERVER_STATUS: ONLINE | USERS={users} | RECOGNITION={rec} | CAPTURE={cap} | HOSTNAME={pi_hostname or '-'} | USER={pi_user or '-'}"

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
                    # becoming the active runtime Pi.
                    self.pi_api_host = host
                    self.pi_api_port = "5000"
                    if str(host).startswith("http"):
                        self.pi_api_base = str(host).rstrip("/")
                    else:
                        self.pi_api_base = f"http://{host}:5000"
                    self.camera_feed_url = f"{self.pi_api_base}/video-feed"
                    try:
                        self.face_api_service.configure(host, "5000")
                    except Exception:
                        pass

                    self.pi_connection_checked = True
                    self.pi_connected = True
                    self._pi_selected_host_pending_manual_connect = False
                    self.resume_locking_after_pi_reconnect()
                    self.pi_device_hostname = pi_hostname
                    self.pi_system_user = pi_user
                    self.set_face_controls_connection_enabled(True)
                    self.configure_recognition_websocket(host, "5000", start=True)
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
                            "Pi host": connected_pi_host,
                            "API port": "5000",
                            "OneConnect": "Forced takeover" if force_takeover else "Normal connect",
                        }
                        if host and pi_hostname and host.strip().lower() != pi_hostname.strip().lower():
                            pi_audit_details = {
                                "Requested host": host,
                                **pi_audit_details,
                            }
                        self.write_sas_log(
                            "PI CONNECTED",
                            actor=self.get_audit_actor(),
                            details=pi_audit_details,
                        )

                    self.set_pi_status_label(connected=True, message=f"Status: Connected | Hostname: {pi_hostname or '-'} | Username: {pi_user or '-'}")
                    self.update_pi_connect_ui_state(connected=True)
                    if hasattr(self, "pi_identity_label"):
                        self.pi_identity_label.setText("")
                        self.pi_identity_label.setVisible(False)

                    # Important:
                    # A previous Pi disconnect may have left the camera panel showing
                    # "Pi disconnected". After a successful reconnect, reset that stale
                    # state immediately.
                    self._camera_user_stopped = False
                    self._handling_pi_disconnect = False

                    self.finish_connection_dialog_success(users=users, recognition=rec, capture=cap)

                    self._face_api_refresh_users()
                    self._face_api_load_logs()
                    self.pull_pi_settings_to_sas(silent=True)
                    self.refresh_pi_storage_from_pi(silent=True)

                    # If Pi is already recognising/capturing, show the feed immediately.
                    # If not, show a normal camera-stopped prompt, not "Pi disconnected".
                    if rec or cap:
                        self.stop_camera_preview()
                        self.start_camera_preview(force=True)
                    else:
                        self.stop_camera_preview(show_prompt=True)

                    self.handle_startup_background_check_result(True)

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)
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
                                    self.set_selected_pi_host_runtime(host, connected=False)
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
                        self.set_selected_pi_host_runtime(host, connected=False)
                        self._pi_selected_host_pending_manual_connect = True
                    self.pi_connected = False
                    self.pi_system_user = ""
                    self.pi_device_hostname = ""
                    self.set_face_controls_connection_enabled(False)
                    self.stop_recognition_websocket("Pi API offline")
                    self.append_face_log(f"SERVER_STATUS: OFFLINE | {err}")

                    if origin_safe == "settings":
                        self.write_sas_log(
                            "PI CONNECTION FAILED",
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



    def verify_pi_status_after_action(self, action_name: str = "ACTION"):
        """Check whether Pi API is still online after a failed action.

        Some Pi endpoints can fail because the camera process is busy/stopping,
        but the API is still online. In that case SAS should stay connected and
        should not force the user back to Settings.
        """
        def worker():
            try:
                status = self._face_api_request("GET", "/status", timeout=5)

                def online(status=status):
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_capture_in_progress(bool(status.get("capture_running", False)))
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self.append_face_log(f"{action_name}_STATUS: API online")

                self.qt_after(0, online)

            except Exception as e:
                err = str(e)

                def offline(err=err):
                    self.handle_pi_runtime_disconnect(
                        f"Pi disconnected or unreachable after {action_name}. Please check Pi. {err}"
                    )

                self.qt_after(0, offline)

        Thread(target=worker, daemon=True).start()

