from __future__ import annotations

import os
from threading import Thread
from typing import Any, cast

from PySide6.QtCore import QEasingCurve, Qt, QPropertyAnimation
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from app_config import *
from dialogs import *
from services.resource_service import app_resource_path


class SettingsControllerMixin:
    def _validate_ntid_in_ad(self: Any, ntid: str) -> bool:
        return self.ad_service.validate_ntid_in_ad(ntid)

    def _parse_ad_response(self: Any, response: str) -> bool:
        return self.ad_service.parse_ad_response(response)

    def _read_credentials(self: Any):
        return self.credential_service.read_credentials()

    def _encrypt_password(self: Any, password: str):
        return self.ad_service.encrypt_password(password)

    def _validate_ntid_password_in_ad(self: Any, ntid: str, password: str) -> bool:
        return self.ad_service.validate_ntid_password_in_ad(ntid, password)

    def _save_credentials(self: Any, ntid, password, server, timeout, disable_keyboard=False, disable_mouse=False, disable_usb=False, enable_hotkey=True):
        if not getattr(self, "_settings_validation_passed", False):
            self.append_system_log("CREDENTIAL_SAVE_BLOCKED: strict validation was not completed.")
            return
        self._settings_validation_passed = False

        pi_host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        pi_port = "5000"
        camera_rotation = self.normalize_camera_rotation(getattr(self, "camera_rotation", 0))

        self.credential_service.save_credentials(
            ntid,
            password,
            server,
            timeout,
            disable_keyboard=disable_keyboard,
            disable_mouse=disable_mouse,
            disable_usb=disable_usb,
            enable_hotkey=enable_hotkey,
            pi_host=pi_host,
            pi_port=pi_port,
            camera_rotation=camera_rotation,
            video_source="rtsp",
        )

    def browse_server_path(self: Any):
        """Browse and select the server folder used for SAS_LOG and file transfers."""
        start_dir = self.settings_server_path_input.text().strip() if hasattr(self, "settings_server_path_input") else self.server_path
        if not start_dir or not os.path.exists(start_dir):
            start_dir = self.server_path if os.path.exists(self.server_path) else os.path.expanduser("~")

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Server Path",
            start_dir,
        )

        if folder:
            self.settings_server_path_input.setText(folder)
            self.mark_settings_modified_by_user()
            self.append_system_log(f"Server path selected: {folder}")

    def show_settings_message(
        self: Any,
        title: str,
        message: str,
        success: bool = True,
        issues=None,
        server_path: str = "",
        timeout_seconds: int = 300,
    ):
        """Show custom settings result dialog instead of native QMessageBox."""
        dialog = SettingsConnectionDialog(
            self,
            success=success,
            title=title,
            subtitle=message,
            server_path=server_path or self.server_path,
            timeout_seconds=timeout_seconds,
            issues=issues or [],
            compact_mode=self.compact_mode,
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

    def show_missing_credentials_setup_popup_if_needed(self: Any):
        """Show first-launch setup guidance when credential.txt is blank/incomplete."""
        if getattr(self, "_missing_credentials_popup_shown", False):
            return

        if getattr(self, "server_configured", False):
            return

        if not getattr(self, "first_launch_setup_mode", False):
            return

        self._missing_credentials_popup_shown = True
        self.append_system_log("FIRST_LAUNCH_SETUP: Missing credentials popup shown.")

        dialog = MissingCredentialsSetupDialog(self, self.compact_mode)
        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self.resume_camera_after_modal()

        # User must login first because Settings is an Admin-restricted tab.
        self.pending_restricted_tab = "Settings"
        if self.has_restricted_tab_access():
            self.switch_top_tab("Settings")
        else:
            self.open_login_popup()

    def _locked_input_options_summary(self: Any, disable_keyboard: bool, disable_mouse: bool, disable_usb: bool = False) -> str:
        """Describe exactly which input options are disabled while SAS is locked."""
        disabled = []
        if bool(disable_keyboard):
            disabled.append("Keyboard")
        if bool(disable_mouse):
            disabled.append("Mouse")
        if bool(disable_usb):
            disabled.append("USB")
        return ", ".join(disabled) if disabled else "None"

    def apply_timeout_to_countdown(self: Any, reset: bool = False):
        self.total_seconds = max(1, int(self.lock_timeout_seconds))
        if reset:
            self.time_left = self.total_seconds
        if hasattr(self, "ring"):
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)
        if hasattr(self, "countdown_label"):
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")

    def apply_security_options_runtime(self: Any):
        """Apply saved security option flags using runtime_lock_service."""
        self.append_system_log(
            "Security options applied: "
            f"keyboard={self.disable_keyboard_when_locked}, "
            f"mouse={self.disable_mouse_when_locked}, "
            f"usb={self.disable_usb_when_locked}, "
            f"hotkey={self.enable_hotkey}"
        )
        self.runtime_lock_service.apply_security_options(self)

    def is_server_configured(self: Any, creds: dict[str, Any] | None = None) -> bool:
        """Return True only when usable server credentials exist.

        On first EXE launch, credential.txt may not exist yet. In that case
        SAS should enter setup mode instead of starting lock/unlock services.
        """
        raw_creds = creds if creds is not None else self._read_credentials()
        if not isinstance(raw_creds, dict):
            raw_creds = {}
        ntid = str(raw_creds.get("ntid", "") or "").strip()
        password = str(raw_creds.get("password", "") or "").strip()
        server = str(raw_creds.get("server", "") or "").strip()

        if not ntid or not password or not server:
            return False

        # C:\temp is only the built-in placeholder/default, not a real saved setup.
        if server.replace("/", "\\").rstrip("\\").lower() == str(SERVER_PATH).replace("/", "\\").rstrip("\\").lower():
            return False

        return True

    def enter_first_launch_setup_mode(self: Any):
        """Safe startup mode for newly copied EXE / blank configuration.

        Behaviour:
        - Do not show a system-lock notification.
        - Do not depend on old SMB recognition_result.json polling.
        - Allow the first valid AD login to become Admin.
        - Keep Face Recognition blocked until camera/server settings are configured.
        """
        self.first_launch_setup_mode = True
        self.server_configured = False
        self.is_locked = False
        self.face_detected = False
        self._pending_auto_lock = False
        self.time_left = max(1, int(self.lock_timeout_seconds))

        if hasattr(self, "status_title"):
            self.status_title.setText("SETUP REQUIRED")
        if hasattr(self, "face_state_label"):
            self.face_state_label.setText("Login as Admin and configure Settings first.")

        self.hide_system_locked_notification()
        self.apply_lock_state()
        self.update_account_ui()
        self.append_system_log("FIRST_LAUNCH_SETUP: Missing server credentials. System-lock notification suppressed until setup is saved.")

    def exit_first_launch_setup_mode(self: Any):
        """Leave setup mode after Save & Connect succeeds."""
        self.first_launch_setup_mode = False
        self.server_configured = True
        self._suppress_lock_notification = False
        self.append_system_log("FIRST_LAUNCH_SETUP: Configuration completed.")

    def load_settings_from_credentials(self: Any):
        creds = self._read_credentials()
        self._settings_programmatic_update = True
        self.server_configured = self.is_server_configured(creds)

        # Use saved server only when it is real/configured. Otherwise keep blank
        # in Settings UI instead of showing the placeholder C:\temp as if it was configured.
        if self.server_configured:
            self.server_path = creds.get("server", self.server_path)
        else:
            self.server_path = ""

        try:
            self.lock_timeout_seconds = int(creds.get("timeout", self.lock_timeout_seconds))
        except Exception:
            self.lock_timeout_seconds = DEFAULT_LOCK_TIMEOUT_SECONDS

        self.disable_keyboard_when_locked = creds.get("disable_keyboard", "false").lower() == "true"
        self.disable_mouse_when_locked = creds.get("disable_mouse", "false").lower() == "true"
        self.disable_usb_when_locked = creds.get("disable_usb", "false").lower() == "true"
        self.enable_hotkey = creds.get("enable_hotkey", "true").lower() == "true"
        saved_pi_host = str(creds.get("pi_host", "") or "").strip()
        self.pi_api_host = saved_pi_host
        self.pi_api_port = "5000"
        self.pi_connected = False
        self.pi_connection_checked = False
        self._pi_selected_host_pending_manual_connect = bool(saved_pi_host)
        self.camera_rotation = self.normalize_camera_rotation(creds.get("camera_rotation", 0))

        if self.pi_api_host:
            self.local_face_service.configure(self.pi_api_host, self.pi_api_port)
            self.local_face_service.set_camera_rotation(self.camera_rotation)
            self.configure_local_unlock(self.pi_api_host, self.pi_api_port, start=False)
            self.pi_api_base = f"local://{self.pi_api_host}"
            self.camera_feed_url = self.local_face_service.rtsp_url()
        else:
            self.pi_api_base = ""
            self.camera_feed_url = ""
            self.pi_connected = False
            self.pi_connection_checked = False
            self.configure_local_unlock("", self.pi_api_port, start=False)

        if hasattr(self, "settings_ntid_input"):
            self.settings_ntid_input.setText("")
        if hasattr(self, "settings_password_input"):
            self.settings_password_input.setText("")
        if hasattr(self, "settings_server_path_input"):
            self.settings_server_path_input.setText(self.server_path)
            if not self.server_configured:
                self.settings_server_path_input.setPlaceholderText("Enter server path, e.g. \\\\server\\share\\folder")
        if hasattr(self, "pi_host_input"):
            self.pi_host_input.setText(self.pi_api_host)
            if not self.pi_api_host:
                self.pi_host_input.setPlaceholderText("Enter camera hostname or IP")
        if hasattr(self, "pi_identity_label"):
            self.pi_identity_label.setText("")
            self.pi_identity_label.setVisible(False)
        # camera port is fixed to 5000, so no editable port field is shown.
        if hasattr(self, "security_option_buttons"):
            if "disable_keyboard" in self.security_option_buttons:
                self.security_option_buttons["disable_keyboard"].setChecked(self.disable_keyboard_when_locked)
            if "disable_mouse" in self.security_option_buttons:
                self.security_option_buttons["disable_mouse"].setChecked(self.disable_mouse_when_locked)

            # Hidden developer-only settings:
            # USB storage control is not exposed to normal users.
            # Emergency hotkey is always enabled internally and is not user-configurable.
            self.disable_usb_when_locked = creds.get("disable_usb", "false").lower() == "true"
            self.enable_hotkey = True
        if hasattr(self, "timeout_inputs"):
            total = int(self.lock_timeout_seconds)
            self.timeout_inputs["hours"].setText(str(total // 3600))
            self.timeout_inputs["minutes"].setText(str((total % 3600) // 60))
            self.timeout_inputs["seconds"].setText(str(total % 60))

        self.apply_timeout_to_countdown(reset=True)
        self.apply_security_options_runtime()
        self.update_footer_info()

        if not self.server_configured:
            self._suppress_lock_notification = True
            self.enter_first_launch_setup_mode()
        else:
            self.first_launch_setup_mode = False
            self._suppress_lock_notification = False

        self.clear_sensitive_server_credentials_ui(clear_server_path=False)
        self._settings_programmatic_update = False
        self.refresh_settings_unsaved_baseline()

    def discard_unsaved_settings_changes(self: Any):
        """Discard Settings edits without breaking an existing camera connection."""
        previous_connected = bool(getattr(self, "pi_connected", False))
        previous_host = str(getattr(self, "pi_api_host", "") or "").strip()
        previous_session = getattr(self, "sas_oneconnect_session", None)
        saved_snapshot = self.get_saved_settings_snapshot_for_save_prompt()
        saved_host = str(saved_snapshot.get("pi_host", "") or "").strip()

        self._settings_discard_restore_in_progress = True
        try:
            self.load_settings_from_credentials()

            same_saved_host = (
                previous_connected
                and previous_host
                and saved_host
                and previous_host.lower() == saved_host.lower()
            )
            if same_saved_host:
                self.pi_api_host = previous_host
                self.pi_api_port = "5000"
                self.pi_connected = True
                self.pi_connection_checked = True
                self.sas_oneconnect_session = previous_session
                self._pi_selected_host_pending_manual_connect = False
                self._pi_disconnect_retry_active = False
                self._pi_disconnect_retry_running = False
                self._handling_pi_disconnect = False
                self._pi_disconnect_reason = ""
                self.local_face_service.configure(self.pi_api_host, self.pi_api_port)
                self.configure_local_unlock(self.pi_api_host, self.pi_api_port, start=False)
                self.pi_api_base = f"local://{self.pi_api_host}"
                self.camera_feed_url = self.local_face_service.rtsp_url()
                try:
                    self.resume_locking_after_pi_reconnect()
                except Exception:
                    pass
                try:
                    self.set_face_controls_connection_enabled(True)
                except Exception:
                    pass
                try:
                    self.set_pi_status_label(connected=True)
                except Exception:
                    pass

            self.refresh_settings_unsaved_baseline()
        finally:
            self._settings_discard_restore_in_progress = False

    def mark_settings_modified_by_user(self: Any):
        """Mark Settings dirty only for real user interaction, not programmatic refresh."""
        if getattr(self, "_settings_programmatic_update", False):
            return
        if getattr(self, "_settings_save_prompt_active", False):
            return
        if not hasattr(self, "settings_page"):
            return
        self._settings_dirty_since_baseline = True

    def refresh_settings_unsaved_baseline(self: Any):
        """Capture the current Settings UI as the clean baseline."""
        if not hasattr(self, "settings_page"):
            return
        try:
            self._settings_unsaved_baseline = self.get_settings_ui_snapshot_for_save_prompt(fill_blank_sensitive=True)
            self._settings_dirty_since_baseline = False
        except Exception as e:
            try:
                self.append_system_log(f"UNSAVED_SETTINGS_BASELINE_ERROR: {e}")
            except Exception:
                pass

    def _normalized_settings_snapshot_for_compare(self: Any, snapshot):
        """Normalize snapshots so harmless case/spacing changes do not prompt."""
        snap = dict(snapshot or {})
        for key in ("ntid", "server", "pi_host", "pi_port", "video_source", "timeout"):
            if key in snap:
                snap[key] = str(snap.get(key, "") or "").strip()
        if "ntid" in snap:
            snap["ntid"] = snap["ntid"].lower()
        if "pi_host" in snap:
            snap["pi_host"] = snap["pi_host"].lower()
        for key in ("disable_keyboard", "disable_mouse", "disable_usb", "enable_hotkey"):
            if key in snap:
                snap[key] = bool(snap.get(key))
        if "camera_rotation" in snap:
            snap["camera_rotation"] = self.normalize_camera_rotation(snap.get("camera_rotation", 0))
        return snap

    def get_settings_ui_snapshot_for_save_prompt(self: Any, fill_blank_sensitive: bool = True):
        """Return Settings UI values normalized for credential.txt comparison.

        Sensitive fields are normally cleared after load. A blank NTID/password
        field therefore means "keep the saved value" unless the user typed a new
        non-empty value.
        """
        creds = self._read_credentials()

        def text_of(widget_name: str, fallback: str = "") -> str:
            widget = getattr(self, widget_name, None)
            try:
                if widget is not None:
                    return str(widget.text() or "").strip()
            except Exception:
                pass
            return str(fallback or "").strip()

        saved_ntid = str(creds.get("ntid", "") or "").strip()
        saved_password = str(creds.get("password", "") or "")
        saved_server = str(creds.get("server", "") or "").strip()
        saved_pi_host = str(creds.get("pi_host", "") or "").strip()

        ui_ntid = text_of("settings_ntid_input")
        try:
            ui_password = str(getattr(self, "settings_password_input").text() or "") if hasattr(self, "settings_password_input") else ""
        except Exception:
            ui_password = ""

        if fill_blank_sensitive:
            ntid = ui_ntid or saved_ntid
            password = ui_password if ui_password else saved_password
        else:
            ntid = ui_ntid
            password = ui_password

        def timeout_field_value(key: str, max_value: int) -> int:
            field = getattr(self, "timeout_inputs", {}).get(key)
            if field is None:
                return 0
            try:
                value = int(str(field.text() or "0").strip() or 0)
            except Exception:
                value = 0
            return max(0, min(value, max_value))

        try:
            h = timeout_field_value("hours", 23)
            m = timeout_field_value("minutes", 59)
            s = timeout_field_value("seconds", 59)
            timeout = str(max(1, h * 3600 + m * 60 + s))
        except Exception:
            timeout = str(getattr(self, "lock_timeout_seconds", DEFAULT_LOCK_TIMEOUT_SECONDS))

        option_buttons = getattr(self, "security_option_buttons", {})
        keyboard_button = option_buttons.get("disable_keyboard")
        mouse_button = option_buttons.get("disable_mouse")
        disable_keyboard = (
            bool(keyboard_button.isChecked())
            if keyboard_button is not None
            else bool(getattr(self, "disable_keyboard_when_locked", False))
        )
        disable_mouse = (
            bool(mouse_button.isChecked())
            if mouse_button is not None
            else bool(getattr(self, "disable_mouse_when_locked", False))
        )
        disable_usb = bool(getattr(self, "disable_usb_when_locked", False))
        enable_hotkey = True

        return {
            "ntid": ntid.strip(),
            "password": password,
            "server": text_of("settings_server_path_input", saved_server),
            "timeout": timeout,
            "disable_keyboard": disable_keyboard,
            "disable_mouse": disable_mouse,
            "disable_usb": disable_usb,
            "enable_hotkey": enable_hotkey,
            "pi_host": text_of("pi_host_input", saved_pi_host),
            "pi_port": "5000",
            "camera_rotation": self.normalize_camera_rotation(getattr(self, "camera_rotation", 0)),
            "video_source": "pi",
        }

    def get_saved_settings_snapshot_for_save_prompt(self: Any):
        """Return credential.txt values normalized the same way as the UI snapshot."""
        creds = self._read_credentials()

        def as_bool(value, default=False):
            if value is None:
                return bool(default)
            return str(value).strip().lower() in {"1", "true", "yes", "on"}

        try:
            timeout = str(max(1, int(str(creds.get("timeout", DEFAULT_LOCK_TIMEOUT_SECONDS) or DEFAULT_LOCK_TIMEOUT_SECONDS))))
        except Exception:
            timeout = str(DEFAULT_LOCK_TIMEOUT_SECONDS)

        return {
            "ntid": str(creds.get("ntid", "") or "").strip(),
            "password": str(creds.get("password", "") or ""),
            "server": str(creds.get("server", "") or "").strip(),
            "timeout": timeout,
            "disable_keyboard": as_bool(creds.get("disable_keyboard"), False),
            "disable_mouse": as_bool(creds.get("disable_mouse"), False),
            "disable_usb": as_bool(creds.get("disable_usb"), False),
            "enable_hotkey": True,
            "pi_host": str(creds.get("pi_host", "") or "").strip(),
            "pi_port": "5000",
            "camera_rotation": self.normalize_camera_rotation(creds.get("camera_rotation", 0)),
            "video_source": "pi",
        }

    def has_unsaved_settings_changes(self: Any) -> bool:
        """True when the user edited Settings after the clean baseline."""
        if not hasattr(self, "settings_page"):
            return False
        if not getattr(self, "_settings_dirty_since_baseline", False):
            return False
        try:
            current = self._normalized_settings_snapshot_for_compare(
                self.get_settings_ui_snapshot_for_save_prompt(fill_blank_sensitive=True)
            )
            baseline = getattr(self, "_settings_unsaved_baseline", None)
            if baseline is None:
                self.refresh_settings_unsaved_baseline()
                return False
            baseline = self._normalized_settings_snapshot_for_compare(baseline)
            return current != baseline
        except Exception as e:
            try:
                self.append_system_log(f"UNSAVED_SETTINGS_COMPARE_ERROR: {e}")
            except Exception:
                pass
            return False

    def close_guidelines_dialog_if_open(self: Any):
        """Close the Guidelines modal before urgent camera-disconnect popups.

        The Guidelines window is modal. If a camera-disconnect alert appears while
        Guidelines is open, the disconnect card can end up behind the Guidelines
        modal and cannot be clicked. Close Guidelines first so the disconnect
        popup becomes the active actionable dialog.
        """
        closed = False
        try:
            dialog = getattr(self, "_guidelines_dialog", None)
            if dialog is not None:
                try:
                    if dialog.isVisible():
                        closed = True
                except Exception:
                    closed = True
                try:
                    dialog.accept()
                except Exception:
                    try:
                        dialog.close()
                    except Exception:
                        pass
                try:
                    dialog.deleteLater()
                except Exception:
                    pass
                self._guidelines_dialog = None
        except Exception:
            pass

        try:
            for widget in QApplication.topLevelWidgets():
                if widget is not None and widget.objectName() == "GuidelinesDialog":
                    try:
                        if widget.isVisible():
                            closed = True
                    except Exception:
                        pass
                    try:
                        if isinstance(widget, QDialog):
                            cast(QDialog, widget).accept()
                        else:
                            widget.close()
                    except Exception:
                        pass
                    try:
                        widget.deleteLater()
                    except Exception:
                        pass
        except Exception:
            pass

        if closed:
            try:
                QApplication.processEvents()
            except Exception:
                pass
        return closed

    def show_guidelines_dialog(self: Any):
        """Show the SAS guideline carousel from the header help button.

        v130: uses a single fixed-size dialog card.  The dialog itself is the
        modal window, so there is no second old card behind it.  Layout is
        strictly reserved in this order:
        GUIDELINES -> 16:9 picture -> description -> tiny progress -> buttons.
        """
        # Close any older Guidelines dialogs left from previous versions before
        # opening the new card.  This avoids the old white panel showing behind.
        try:
            old_dialog = getattr(self, "_guidelines_dialog", None)
            if old_dialog is not None:
                try:
                    old_dialog.close()
                except Exception:
                    pass
                try:
                    old_dialog.deleteLater()
                except Exception:
                    pass
                self._guidelines_dialog = None
        except Exception:
            pass
        try:
            for widget in QApplication.topLevelWidgets():
                if widget is not None and widget.objectName() == "GuidelinesDialog":
                    try:
                        widget.close()
                    except Exception:
                        pass
                    try:
                        widget.deleteLater()
                    except Exception:
                        pass
        except Exception:
            pass

        dialog = QDialog(self)
        dialog.setObjectName("GuidelinesDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowOpacity(1.0)
        self._guidelines_dialog = dialog
        try:
            dialog.finished.connect(lambda _=0: setattr(self, "_guidelines_dialog", None))
        except Exception:
            pass

        # Fixed card size.  Keep a little margin against the current SAS window.
        parent_w, parent_h = 1024, 720
        try:
            parent_w = max(860, self.frameGeometry().width())
            parent_h = max(680, self.frameGeometry().height())
        except Exception:
            pass
        card_width = min(760, max(700, parent_w - 140))
        card_height = min(640, max(600, parent_h - 100))
        if self.compact_mode:
            card_width = min(card_width, 720)
            card_height = min(card_height, 610)
        dialog.setFixedSize(card_width, card_height)

        try:
            parent_geo = self.frameGeometry()
            x = parent_geo.x() + (parent_geo.width() - card_width) // 2
            y = parent_geo.y() + (parent_geo.height() - card_height) // 2
            dialog.move(max(parent_geo.x(), x), max(parent_geo.y(), y))
        except Exception:
            pass

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame(dialog)
        card.setObjectName("GuidelinesCard")
        card.setFixedSize(card_width, card_height)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 18, 28, 22)
        card_layout.setSpacing(0)

        # Header: title centered, close button on the right.
        header = QFrame(card)
        header.setObjectName("GuidelinesHeader")
        header.setFixedHeight(32)
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        header_left = QWidget(header)
        header_left.setFixedSize(30, 30)
        header_title = QLabel("G U I D E L I N E S", header)
        header_title.setObjectName("GuidelinesHeaderTitle")
        header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close_btn = QPushButton("×", header)
        close_btn.setObjectName("GuidelinesCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(dialog.accept)

        header_layout.addWidget(header_left, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(header_title, 0, 1, Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(close_btn, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_layout.setColumnStretch(0, 0)
        header_layout.setColumnStretch(1, 1)
        header_layout.setColumnStretch(2, 0)
        card_layout.addWidget(header)
        card_layout.addSpacing(16)

        # The fixed-size content frame uses a fade effect only.  No old stacked
        # carousel pages are kept behind, so there is nothing to show through.
        content_frame = QFrame(card)
        content_frame.setObjectName("GuidelinesContentFrame")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        content_effect = QGraphicsOpacityEffect(content_frame)
        content_effect.setOpacity(1.0)
        content_frame.setGraphicsEffect(content_effect)

        available_width = card_width - 56
        image_width = min(680, available_width)
        image_height = int(image_width * 9 / 16)
        reserved_non_image = 18 + 32 + 16 + 14 + 54 + 10 + 20 + 18 + 42 + 22
        max_image_height = max(300, card_height - reserved_non_image)
        if image_height > max_image_height:
            image_height = max_image_height
            image_width = int(image_height * 16 / 9)
        image_width = max(560, image_width)
        image_height = int(image_width * 9 / 16)
        if image_height > max_image_height:
            image_height = max_image_height
            image_width = int(image_height * 16 / 9)

        image_frame = QFrame(content_frame)
        image_frame.setObjectName("GuidelinesImageFrame")
        image_frame.setFixedSize(image_width, image_height)
        image_layout = QVBoxLayout(image_frame)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)
        image_label = QLabel(image_frame)
        image_label.setObjectName("GuidelinesImage")
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setFixedSize(image_width, image_height)
        image_layout.addWidget(image_label)

        desc = QLabel(content_frame)
        desc.setObjectName("GuidelinesDescription")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setFixedSize(min(560, card_width - 130), 54)

        content_layout.addWidget(image_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        content_layout.addSpacing(14)
        content_layout.addWidget(desc, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(content_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addSpacing(10)

        progress_pill = QFrame(card)
        progress_pill.setObjectName("GuidelinesProgressPill")
        progress_pill.setFixedSize(150, 20)
        progress_layout = QHBoxLayout(progress_pill)
        progress_layout.setContentsMargins(8, 3, 8, 3)
        progress_layout.setSpacing(6)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        progress_label = QLabel("1 / 12", progress_pill)
        progress_label.setObjectName("GuidelinesProgressText")
        progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_label.setFixedWidth(30)
        progress_layout.addWidget(progress_label)

        dots_row = QHBoxLayout()
        dots_row.setContentsMargins(0, 0, 0, 0)
        dots_row.setSpacing(3)
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addLayout(dots_row)
        card_layout.addWidget(progress_pill, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addSpacing(18)

        actions = QFrame(card)
        actions.setObjectName("GuidelinesActions")
        actions.setFixedHeight(42)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(0)

        back_btn = QPushButton("‹  Previous", actions)
        back_btn.setObjectName("GuidelinesBackButton")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFixedSize(112, 40)

        next_btn = QPushButton("Next  ›", actions)
        next_btn.setObjectName("GuidelinesNextButton")
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.setFixedSize(112, 40)

        actions_layout.addWidget(back_btn, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        actions_layout.addStretch(1)
        actions_layout.addWidget(next_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        card_layout.addWidget(actions)

        steps = [
            {
                "image": app_resource_path("assets", "guideline_step_1.png"),
                "description": "Normal user will be only can access to the Dashboard interface. It only have system locked , system unlocked , manual locked , and view authorized user.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_2.png"),
                "description": "Use the manual lock workflow to protect the workstation when stepping away from the production area.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_3.png"),
                "description": "Configure the camera hostname, server path, and connection settings before enabling recognition in daily operation.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_4.png"),
                "description": "Verify camera connection status and confirm the SAS dashboard is connected to the correct RTSP source.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_5.png"),
                "description": "Use Register to save the user name, employee ID, face photo, and embedding on this PC.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_6.png"),
                "description": "Maintain a clear audit trail for system changes, login events, connection events, and access activity.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_7.png"),
                "description": "Review the registered local embeddings so the PC can identify authorized users from the RTSP stream.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_8.png"),
                "description": "Review imported face data carefully before accepting merged enrolment records.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_9.png"),
                "description": "Monitor local face-data storage and camera network status to prevent recognition or transfer failures during production use.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_10.png"),
                "description": "Use the admin controls only for authorized configuration changes and controlled system maintenance.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_11.png"),
                "description": "Confirm the recognition preview and connection status remain responsive during normal production usage.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_12.png"),
                "description": "Complete setup by confirming workstation lock, camera connection, preview, and recognition unlock behavior.",
            },
        ]

        state = {"index": 0, "animating": False}
        dots = []

        def object_cover_pixmap(path: str, target_w: int, target_h: int) -> QPixmap:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                fallback = QPixmap(target_w, target_h)
                fallback.fill(QColor("#f3f3f3"))
                return fallback
            scaled = pixmap.scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - target_w) // 2)
            y = max(0, (scaled.height() - target_h) // 2)
            return scaled.copy(x, y, target_w, target_h)

        def rebuild_dots():
            while dots_row.count():
                item = dots_row.takeAt(0)
                if item is None:
                    continue
                widget = cast(Any, item).widget()
                if widget is not None:
                    widget.deleteLater()
            dots.clear()
            for i in range(len(steps)):
                dot = QPushButton("", progress_pill)
                dot.setObjectName("GuidelinesDot")
                dot.setCursor(Qt.CursorShape.PointingHandCursor)
                dot.clicked.connect(lambda checked=False, index=i: go_to_step(index))
                dots.append(dot)
                dots_row.addWidget(dot)

        def update_state_only():
            idx = state["index"]
            progress_label.setText(f"{idx + 1} / {len(steps)}")
            for dot_index, dot in enumerate(dots):
                active = dot_index == idx
                dot.setProperty("active", active)
                dot.setFixedSize(16 if active else 4, 4)
                dot.style().unpolish(dot)
                dot.style().polish(dot)

            back_btn.setEnabled(idx > 0)
            back_btn.setProperty("hiddenState", idx == 0)
            back_btn.style().unpolish(back_btn)
            back_btn.style().polish(back_btn)

            next_btn.setText("Complete  ✓" if idx == len(steps) - 1 else "Next  ›")

        def apply_step_content():
            item = steps[state["index"]]
            image_label.setPixmap(object_cover_pixmap(item["image"], image_width, image_height))
            desc.setText(item["description"])
            update_state_only()

        def animate_step_change(new_index: int):
            if state["animating"] or new_index == state["index"]:
                return
            if not (0 <= new_index < len(steps)):
                return
            state["animating"] = True
            fade_out = QPropertyAnimation(content_effect, b"opacity", dialog)
            fade_out.setDuration(160)
            fade_out.setStartValue(float(content_effect.opacity()))
            fade_out.setEndValue(0.18)
            fade_out.setEasingCurve(QEasingCurve.Type.InOutCubic)

            def swap_and_fade_in():
                state["index"] = new_index
                apply_step_content()
                fade_in = QPropertyAnimation(content_effect, b"opacity", dialog)
                fade_in.setDuration(240)
                fade_in.setStartValue(0.18)
                fade_in.setEndValue(1.0)
                fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

                def finish_anim():
                    state["animating"] = False
                    dialog._guideline_anim = None  # type: ignore[attr-defined]

                fade_in.finished.connect(finish_anim)
                dialog._guideline_anim = fade_in  # type: ignore[attr-defined]
                fade_in.start()

            fade_out.finished.connect(swap_and_fade_in)
            dialog._guideline_anim = fade_out  # type: ignore[attr-defined]
            fade_out.start()

        def go_to_step(index: int):
            animate_step_change(index)

        def next_step():
            if state["index"] < len(steps) - 1:
                animate_step_change(state["index"] + 1)
            else:
                dialog.accept()

        def prev_step():
            if state["index"] > 0:
                animate_step_change(state["index"] - 1)

        back_btn.clicked.connect(prev_step)
        next_btn.clicked.connect(next_step)

        dialog.setStyleSheet("""
            QDialog#GuidelinesDialog {
                background: transparent;
            }
            QFrame#GuidelinesCard {
                background: #ffffff;
                border: 1px solid #c4c7c7;
                border-radius: 12px;
            }
            QFrame#GuidelinesHeader,
            QFrame#GuidelinesContentFrame,
            QFrame#GuidelinesActions {
                background: transparent;
                border: none;
            }
            QLabel#GuidelinesHeaderTitle {
                color: rgba(94, 94, 94, 150);
                font-family: Inter, Segoe UI, Arial;
                font-size: 11px;
                line-height: 13px;
                font-weight: 500;
                letter-spacing: 2px;
            }
            QFrame#GuidelinesImageFrame {
                background: #f3f3f3;
                border: 1px solid rgba(196, 199, 199, 80);
                border-radius: 8px;
            }
            QLabel#GuidelinesImage {
                background: transparent;
                border: none;
                border-radius: 8px;
            }
            QLabel#GuidelinesDescription {
                color: #5e5e5e;
                font-family: Inter, Segoe UI, Arial;
                font-size: 12px;
                line-height: 16px;
                font-weight: 400;
            }
            QPushButton#GuidelinesCloseButton {
                background: transparent;
                color: #444748;
                border: none;
                border-radius: 15px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 22px;
                font-weight: 400;
                padding: 0px 0px 5px 0px;
            }
            QPushButton#GuidelinesCloseButton:hover {
                color: #000000;
                background: #e8e8e8;
            }
            QFrame#GuidelinesProgressPill {
                background: #f3f3f3;
                border: none;
                border-radius: 10px;
            }
            QLabel#GuidelinesProgressText {
                color: rgba(94, 94, 94, 175);
                font-family: Inter, Segoe UI, Arial;
                font-size: 9px;
                line-height: 11px;
                font-weight: 500;
            }
            QPushButton#GuidelinesDot {
                background: #e1dfdf;
                border: none;
                border-radius: 2px;
                min-height: 4px;
                max-height: 4px;
                padding: 0px;
            }
            QPushButton#GuidelinesDot:hover {
                background: rgba(94, 94, 94, 100);
            }
            QPushButton#GuidelinesDot[active="true"] {
                background: #000000;
            }
            QPushButton#GuidelinesBackButton {
                background: transparent;
                color: #5e5e5e;
                border: none;
                border-radius: 8px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton#GuidelinesBackButton:hover {
                color: #000000;
                background: #e8e8e8;
            }
            QPushButton#GuidelinesBackButton[hiddenState="true"] {
                color: transparent;
                background: transparent;
            }
            QPushButton#GuidelinesNextButton {
                background: #000000;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 22px;
            }
            QPushButton#GuidelinesNextButton:hover {
                background: #474646;
            }
            QPushButton#GuidelinesNextButton:pressed, QPushButton#GuidelinesBackButton:pressed, QPushButton#GuidelinesCloseButton:pressed {
                padding-top: 2px;
            }
        """)

        rebuild_dots()
        apply_step_content()
        try:
            close_btn.raise_()
            header.raise_()
        except Exception:
            pass

        def key_press(event):
            try:
                if event.key() == Qt.Key.Key_Escape:
                    dialog.accept()
                    return
                if event.key() == Qt.Key.Key_Right:
                    next_step()
                    return
                if event.key() == Qt.Key.Key_Left:
                    prev_step()
                    return
            except Exception:
                pass
            try:
                QDialog.keyPressEvent(dialog, event)
            except Exception:
                pass

        try:
            dialog.keyPressEvent = key_press  # type: ignore[method-assign]
        except Exception:
            pass

        try:
            self.pause_camera_for_modal()
        except Exception:
            pass
        try:
            dialog.exec()
        finally:
            try:
                self.resume_camera_after_modal()
            except Exception:
                pass

    def show_unsaved_settings_dialog(self: Any) -> str:
        """Return 'save', 'dont_save', or 'cancel'.

        v121: Same pasted Unsaved Changes layout, but with a smaller
        action row so the three buttons do not look oversized or overlap.
        """
        dialog = QDialog(self)
        dialog.setObjectName("UnsavedSettingsDialog")
        dialog.setModal(True)
        dialog.setWindowTitle("Unsaved Changes")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setFixedSize(540, 268)
        dialog._choice = "cancel"  # type: ignore[attr-defined]

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("UnsavedSettingsCard")
        try:
            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(20)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 12))
            card.setGraphicsEffect(shadow)
        except Exception:
            pass

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        content = QFrame()
        content.setObjectName("UnsavedSettingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 36, 40, 0)
        content_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.setContentsMargins(0, 0, 0, 0)

        icon = QLabel("⚠")
        icon.setObjectName("UnsavedSettingsIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(24, 32)
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(8)
        text_box.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Unsaved Changes")
        title.setObjectName("UnsavedSettingsTitle")

        desc = QLabel(
            "You have unsaved changes in your setting configuration. "
            "If you leave now, your progress will be lost. Would you like "
            "to save before proceeding?"
        )
        desc.setObjectName("UnsavedSettingsDescription")
        desc.setWordWrap(True)
        desc.setMaximumWidth(420)

        text_box.addWidget(title)
        text_box.addWidget(desc)
        header.addLayout(text_box, 1)
        content_layout.addLayout(header)
        content_layout.addSpacing(22)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setObjectName("UnsavedSettingsCancelButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFixedSize(82, 38)

        dont_btn = QPushButton("DON'T SAVE")
        dont_btn.setObjectName("UnsavedSettingsSecondaryButton")
        dont_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dont_btn.setFixedSize(132, 38)

        save_btn = QPushButton("SAVE && CONTINUE")
        save_btn.setObjectName("UnsavedSettingsPrimaryButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFixedSize(166, 38)

        def choose(value: str):
            dialog._choice = value  # type: ignore[attr-defined]
            dialog.accept()

        cancel_btn.clicked.connect(lambda: choose("cancel"))
        dont_btn.clicked.connect(lambda: choose("dont_save"))
        save_btn.clicked.connect(lambda: choose("save"))

        actions.addWidget(cancel_btn, 0, Qt.AlignmentFlag.AlignLeft)
        actions.addStretch(1)
        actions.addWidget(dont_btn)
        actions.addWidget(save_btn)
        content_layout.addLayout(actions)
        content_layout.addStretch(1)

        card_layout.addWidget(content, 1)

        accent = QFrame()
        accent.setObjectName("UnsavedSettingsAccent")
        accent.setFixedHeight(4)
        card_layout.addWidget(accent)

        outer.addWidget(card)
        dialog.setStyleSheet("""
            QDialog#UnsavedSettingsDialog {
                background: rgba(249, 249, 249, 178);
            }
            QFrame#UnsavedSettingsCard {
                background: #ffffff;
                border: 1px solid #c4c7c7;
                border-radius: 24px;
            }
            QFrame#UnsavedSettingsContent {
                background: transparent;
                border: none;
            }
            QLabel#UnsavedSettingsIcon {
                color: #000000;
                font-family: Segoe UI Symbol, Segoe UI, Arial;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#UnsavedSettingsTitle {
                color: #000000;
                font-family: Inter, Segoe UI, Arial;
                font-size: 24px;
                line-height: 32px;
                font-weight: 800;
                letter-spacing: -0.2px;
            }
            QLabel#UnsavedSettingsDescription {
                color: #5e5e5e;
                font-family: Inter, Segoe UI, Arial;
                font-size: 16px;
                line-height: 24px;
                font-weight: 400;
            }
            QPushButton#UnsavedSettingsPrimaryButton {
                background: #000000;
                color: #ffffff;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 9px 16px;
                min-width: 0px;
                min-height: 0px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#UnsavedSettingsPrimaryButton:hover { background: #00174b; }
            QPushButton#UnsavedSettingsSecondaryButton {
                background: #e2e2e2;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 9px 16px;
                min-height: 0px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#UnsavedSettingsSecondaryButton:hover { background: #c4c7c7; }
            QPushButton#UnsavedSettingsCancelButton {
                background: transparent;
                color: #5e5e5e;
                border: none;
                padding: 9px 8px;
                min-height: 0px;
                font-family: Inter, Segoe UI, Arial;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#UnsavedSettingsCancelButton:hover { color: #000000; }
            QFrame#UnsavedSettingsAccent {
                background: #f3f3f3;
                border: none;
                border-bottom-left-radius: 24px;
                border-bottom-right-radius: 24px;
            }
        """)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        self.pause_camera_for_modal()
        try:
            dialog.exec()
            return str(getattr(dialog, "_choice", "cancel") or "cancel")
        finally:
            self.resume_camera_after_modal()

    def maybe_prompt_unsaved_settings_before_leave(self: Any, continue_callback=None, context: str = "leave-settings") -> bool:
        """Prompt when leaving Settings with unsaved values.

        Returns True when the attempted navigation/close has been handled or
        cancelled. Returns False when there are no unsaved changes.
        """
        if getattr(self, "_settings_save_prompt_active", False):
            return True
        if not self.has_unsaved_settings_changes():
            return False

        self._settings_save_prompt_active = True
        try:
            choice = self.show_unsaved_settings_dialog()
        finally:
            self._settings_save_prompt_active = False

        if choice == "cancel":
            return True

        if choice == "dont_save":
            # Discard visible edits so returning to Settings shows saved values,
            # not a stale unsaved form. Preserve an existing connection to the
            # same saved camera host.
            try:
                self.discard_unsaved_settings_changes()
            except Exception as e:
                try:
                    self.append_system_log(f"UNSAVED_SETTINGS_DISCARD_RELOAD_ERROR: {e}")
                except Exception:
                    pass
            if callable(continue_callback):
                self._settings_bypass_unsaved_prompt_once = True
                try:
                    continue_callback()
                finally:
                    self._settings_bypass_unsaved_prompt_once = False
            return True

        if choice == "save":
            if callable(continue_callback):
                self.save_settings_from_ui(
                    after_success=lambda: continue_callback(),
                    show_success_message=False,
                )
            else:
                self.save_settings_from_ui(show_success_message=False)
            return True

        return True

    def validate_server_path_for_settings(self: Any, server: str):
        """Validate server path used for SAS_LOG, backups, and data transfer.

        Face unlock no longer reads recognition_result.json from SMB.  The path
        still needs to exist and be writable/readable for logs and file transfer.
        """
        issues = []

        if not server:
            issues.append(("SERVER PATH MISSING", "Please select or enter the shared server path."))
            return False, issues

        if not os.path.isdir(server):
            issues.append(("SERVER PATH UNREACHABLE", "The selected server path does not exist or cannot be reached."))
            return False, issues

        try:
            log_dir = os.path.join(server, "SAS_LOG")
            os.makedirs(log_dir, exist_ok=True)
            test_file = os.path.join(log_dir, ".sas_write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(test_file)
            except Exception:
                pass
        except Exception as e:
            issues.append(("SERVER PATH NOT WRITABLE", f"Unable to create SAS_LOG under this path: {e}"))
            return False, issues

        return True, issues

    def validate_settings_credentials_strict(self: Any, ntid: str, password: str, server: str):
        """Strict validation before writing credential.txt.

        This is used for first-time setup too. Credentials must not be saved
        unless AD user check, AD password check, and server path write-test all
        pass in the same Save Connect attempt.
        """
        issues = []

        ntid = (ntid or "").strip()
        password = password or ""
        server = (server or "").strip()

        if not ntid:
            issues.append(("INVALID NTID", "Please enter a valid NTID before saving settings."))
        if not password:
            issues.append(("PASSWORD REQUIRED", "Please enter the password before saving settings."))
        if not server:
            issues.append(("SERVER PATH MISSING", "Please select or enter the shared server path."))

        if issues:
            return False, issues

        ntid_ok = self._validate_ntid_in_ad(ntid)
        if not ntid_ok:
            issues.append(("INVALID NTID", "Subject token verification failed. The NTID does not exist or AD is unreachable."))

        password_ok = False
        if ntid_ok:
            password_ok = self._validate_ntid_password_in_ad(ntid, password)
            if not password_ok:
                issues.append(("CREDENTIAL MISMATCH", "Password validation failed. Please check the password and try again."))

        server_ok, server_issues = self.validate_server_path_for_settings(server)
        if not server_ok:
            issues.extend(server_issues)

        return len(issues) == 0, issues

    def set_save_connect_busy(self: Any, busy: bool):
        btn = getattr(self, "settings_save_connect_btn", None)
        if btn is None:
            return

        btn.setEnabled(not busy)
        btn.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.PointingHandCursor)
        btn.setText("Saving..." if busy else "Save")

        try:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
        except Exception:
            pass

    def sync_settings_to_pi_async(
        self: Any,
        ntid: str,
        password: str,
        server: str,
        camera_rotation: int | None = None,
    ):
        """Sync Settings to the local recognition adapter without blocking the UI."""
        def worker():
            ok = self._local_face_sync_settings(ntid, password, server, camera_rotation)
            if not ok:
                self.qt_after(0, lambda: self.append_face_log("LOCAL_SETTINGS_SYNC_FAILED"))

        Thread(target=worker, daemon=True).start()

    def save_settings_from_ui(self: Any, after_success=None, show_success_message: bool = True):
        # clicked(bool) may pass a checked state when connected as a Qt slot.
        if isinstance(after_success, bool):
            after_success = None
        ntid = self.settings_ntid_input.text().strip() if hasattr(self, "settings_ntid_input") else ""
        password = self.settings_password_input.text().strip() if hasattr(self, "settings_password_input") else ""
        server = self.settings_server_path_input.text().strip() if hasattr(self, "settings_server_path_input") else self.server_path

        # The Settings page intentionally clears NTID/password after startup for safety.
        # If the user saves another setting without retyping credentials, keep the
        # existing saved credentials. A non-empty typed value still replaces them.
        saved_for_blank_sensitive = self._read_credentials()
        if not ntid:
            ntid = str(saved_for_blank_sensitive.get("ntid", "") or "").strip()
        if not password:
            password = str(saved_for_blank_sensitive.get("password", "") or "")

        if not ntid:
            self.show_settings_message(
                "Connection Failed",
                "Authentication or path error detected",
                success=False,
                issues=[("INVALID NTID", "Please enter a valid NTID before saving settings.")],
                server_path=server,
            )
            return

        if not password:
            self.show_settings_message(
                "Connection Failed",
                "Authentication or path error detected",
                success=False,
                issues=[("PASSWORD REQUIRED", "Please enter the password before saving settings.")],
                server_path=server,
            )
            return

        try:
            h = max(0, min(int(self.timeout_inputs["hours"].text() or 0), 23))
            m = max(0, min(int(self.timeout_inputs["minutes"].text() or 0), 59))
            s = max(0, min(int(self.timeout_inputs["seconds"].text() or 0), 59))

            # Reflect clamped values back to UI, so the user sees the corrected range.
            self.timeout_inputs["hours"].setText(str(h))
            self.timeout_inputs["minutes"].setText(str(m))
            self.timeout_inputs["seconds"].setText(str(s))

            timeout = max(1, h * 3600 + m * 60 + s)
        except Exception:
            timeout = DEFAULT_LOCK_TIMEOUT_SECONDS

        disable_keyboard = self.security_option_buttons["disable_keyboard"].isChecked()
        disable_mouse = self.security_option_buttons["disable_mouse"].isChecked()

        # Hidden developer-only settings.
        # Do not expose to users in the Settings UI.
        disable_usb = getattr(self, "disable_usb_when_locked", False)
        enable_hotkey = True

        camera_rotation = self.normalize_camera_rotation(getattr(self, "camera_rotation", 0))

        # Keep the previous saved values so the audit log can say exactly what
        # changed after Save Connect succeeds, without ever exposing a password.
        previous_saved_settings = self._read_credentials()
        configured_pi_host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host

        self.append_system_log("Validating settings NTID/password/server path before saving...")
        self.set_save_connect_busy(True)

        def worker():
            validation_ok, issues = self.validate_settings_credentials_strict(ntid, password, server)

            def done():
                if issues or not validation_ok:
                    self._settings_validation_passed = False
                    self.set_save_connect_busy(False)
                    for issue_title, issue_desc in issues:
                        self.append_system_log(f"Settings validation failed: {issue_title} - {issue_desc}")

                    self.show_settings_message(
                        "Connection Failed",
                        "Authentication or path error detected",
                        success=False,
                        issues=issues,
                        server_path=server,
                        timeout_seconds=timeout,
                    )
                    return

                self._settings_validation_passed = True

                self._save_credentials(
                    ntid,
                    password,
                    server,
                    timeout,
                    disable_keyboard,
                    disable_mouse,
                    disable_usb,
                    enable_hotkey,
                )

                # Save the selected camera host into runtime too.  If the user saved
                # a wrong hostname, SAS must keep that wrong hostname visible and
                # disconnected instead of reverting/reconnecting to the previous camera.
                connected_to_same_host = bool(getattr(self, "pi_connected", False)) and (
                    str(getattr(self, "pi_api_host", "") or "").strip().lower() == configured_pi_host.lower()
                )
                self.set_selected_pi_host_runtime(configured_pi_host, connected=connected_to_same_host)
                self._pi_host_dirty_since_edit = False
                self._pi_host_user_editing = False
                self._pi_selected_host_pending_manual_connect = not connected_to_same_host

                self.server_path = server
                self.remember_session_credentials_after_save(ntid, password, server)
                self._keep_session_credentials_visible = True
                self.apply_session_credentials_to_settings_ui()
                self.exit_first_launch_setup_mode()
                self.lock_timeout_seconds = timeout
                self.disable_keyboard_when_locked = disable_keyboard
                self.disable_mouse_when_locked = disable_mouse
                self.disable_usb_when_locked = disable_usb
                self.enable_hotkey = True

                self.apply_timeout_to_countdown(reset=True)
                self.apply_security_options_runtime()
                self.update_footer_info()

                # Do not call the local recognition engine on the UI thread.
                # If camera is slow/offline, this avoids "window not responding".
                if bool(getattr(self, "pi_connected", False)) and str(getattr(self, "pi_api_host", "") or "").strip():
                    self.sync_settings_to_pi_async(
                        ntid, password, server, camera_rotation
                    )

                actor = self.get_audit_actor()
                previous_ntid = str(previous_saved_settings.get("ntid", "") or "").strip()
                previous_password = str(previous_saved_settings.get("password", "") or "")
                previous_server = str(previous_saved_settings.get("server", "") or "").strip()
                previous_pi_host = str(previous_saved_settings.get("pi_host", "") or "").strip()
                previous_timeout = str(previous_saved_settings.get("timeout", "") or "").strip()
                previous_disabled = self._locked_input_options_summary(
                    str(previous_saved_settings.get("disable_keyboard", "false")).lower() == "true",
                    str(previous_saved_settings.get("disable_mouse", "false")).lower() == "true",
                    str(previous_saved_settings.get("disable_usb", "false")).lower() == "true",
                )
                current_disabled = self._locked_input_options_summary(
                    disable_keyboard,
                    disable_mouse,
                    disable_usb,
                )

                credential_changed = (
                    not previous_ntid
                    or previous_ntid.lower() != ntid.lower()
                    or previous_password != password
                    or previous_server != server
                )
                credential_status = "Configured" if not previous_ntid else ("Updated" if credential_changed else "Confirmed")

                try:
                    previous_timeout_text = self.format_lock_interval(int(previous_timeout)) if previous_timeout else "Not configured"
                except Exception:
                    previous_timeout_text = "Not configured"
                current_timeout_text = self.format_lock_interval(timeout)

                pi_host_detail = (
                    f"{previous_pi_host or 'Not configured'} → {configured_pi_host or 'Not configured'}"
                    if previous_pi_host != configured_pi_host
                    else (configured_pi_host or "Not configured")
                )
                lock_time_detail = (
                    f"{previous_timeout_text} → {current_timeout_text}"
                    if previous_timeout_text != current_timeout_text
                    else current_timeout_text
                )
                disabled_detail = (
                    f"{previous_disabled} → {current_disabled}"
                    if previous_disabled != current_disabled
                    else current_disabled
                )

                # Keep the audit focused on meaningful credential changes.
                # The password value is never recorded; only an update status is.
                settings_audit_details = {}
                if credential_status != "Confirmed":
                    settings_audit_details["Server credentials"] = credential_status
                    settings_audit_details["Server account"] = ntid.upper()
                    if previous_password != password:
                        settings_audit_details["Password"] = "Updated"

                settings_audit_details.update({
                    "Server path": server,
                    "Camera host": pi_host_detail,
                    "Inactivity lock": lock_time_detail,
                    "Disabled while locked": disabled_detail,
                    "Camera rotation": f"{camera_rotation}°",
                })

                self.write_sas_log(
                    "SETTINGS SAVED",
                    actor=actor,
                    details=settings_audit_details,
                )
                self.append_system_log("Settings saved")
                self.set_save_connect_busy(False)
                self.refresh_settings_unsaved_baseline()

                if show_success_message:
                    self.show_settings_message(
                        "Settings Saved",
                        "Configuration saved successfully",
                        success=True,
                        server_path=server,
                        timeout_seconds=timeout,
                    )

                if callable(after_success):
                    try:
                        after_success()
                    except Exception as e:
                        self.append_system_log(f"SETTINGS_AFTER_SAVE_CALLBACK_ERROR: {e}")

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()

    def coerce_bool(self: Any, value, default=False) -> bool:
        """Parse bool from camera/SAS JSON safely."""
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

    def remember_session_credentials_after_save(self: Any, ntid: str, password: str, server: str):
        """Keep credentials visible only during the current logged-in session."""
        self._session_settings_ntid = (ntid or "").strip()
        self._session_settings_password = password or ""
        self._session_settings_server = (server or "").strip()

    def apply_session_credentials_to_settings_ui(self: Any):
        """Show current-session credentials after successful Save Connect."""
        try:
            if hasattr(self, "settings_ntid_input"):
                self.settings_ntid_input.setText(getattr(self, "_session_settings_ntid", "") or "")
        except Exception:
            pass
        try:
            if hasattr(self, "settings_password_input"):
                self.settings_password_input.setText(getattr(self, "_session_settings_password", "") or "")
        except Exception:
            pass
        try:
            if hasattr(self, "settings_server_path_input"):
                server = getattr(self, "_session_settings_server", "") or self.server_path
                if server:
                    self.settings_server_path_input.setText(server)
        except Exception:
            pass

    def clear_session_credentials_on_logout(self: Any):
        """Clear visible/session NTID and password on logout."""
        self._session_settings_ntid = ""
        self._session_settings_password = ""
        self._session_settings_server = ""
        self._keep_session_credentials_visible = False
        try:
            if hasattr(self, "settings_ntid_input"):
                self.settings_ntid_input.setText("")
        except Exception:
            pass
        try:
            if hasattr(self, "settings_password_input"):
                self.settings_password_input.setText("")
        except Exception:
            pass

    def clear_sensitive_server_credentials_ui(self: Any, clear_server_path: bool = False):
        """Clear sensitive NTID/password while keeping server path visible.

        Server path can remain visible for convenience. NTID/password are only
        shown after the current logged-in user successfully presses Save Connect,
        and are cleared again on logout/restart.
        """
        try:
            if hasattr(self, "settings_ntid_input") and not getattr(self, "_keep_session_credentials_visible", False):
                self.settings_ntid_input.setText("")
                self.settings_ntid_input.setPlaceholderText("Enter NTID")
        except Exception:
            pass

        try:
            if hasattr(self, "settings_password_input") and not getattr(self, "_keep_session_credentials_visible", False):
                self.settings_password_input.setText("")
                self.settings_password_input.setPlaceholderText("Enter password")
        except Exception:
            pass

        if clear_server_path:
            try:
                if hasattr(self, "settings_server_path_input"):
                    self.settings_server_path_input.setText("")
                    self.settings_server_path_input.setPlaceholderText("Select or enter shared server path")
            except Exception:
                pass

    def pull_pi_settings_to_sas(self: Any, silent: bool = True):
        """Read non-sensitive Camera settings only.

        Security: do not auto-fill Server Credentials from the local recognition engine.
        Another user may start SAS on the same workstation, so NTID/password/
        server path must not appear just because local settings returned them.
        """
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("CAMERA_SKIPPED: camera hostname/IP is not configured.")
            return

        def worker():
            try:
                data = self._local_face_request("GET", "/settings", timeout=10)

                def done():
                    old_programmatic = getattr(self, "_settings_programmatic_update", False)
                    self._settings_programmatic_update = True
                    try:
                        if isinstance(data, dict):
                            nested = data.get("settings", {})
                            if not isinstance(nested, dict):
                                nested = {}

                            # Camera rotation is also non-sensitive. It is stored on
                            # the camera so its local preview and SAS camera feed agree.
                            rotation = data.get("camera_rotation", nested.get("camera_rotation"))
                            if rotation is not None:
                                self.update_camera_rotation_ui(
                                    rotation,
                                    status=f"●  Local setting: {self.camera_rotation_label(rotation)}",
                                    ok=True,
                                )

                        # Never show credentials fetched from camera.
                        self.clear_sensitive_server_credentials_ui(clear_server_path=False)

                        if not silent:
                            self.append_system_log("Camera settings pulled securely. Server credentials were not displayed.")
                    except Exception as e:
                        self.append_system_log(f"Camera settings UI update skipped: {e}")
                    finally:
                        self._settings_programmatic_update = old_programmatic
                        if not getattr(self, "_settings_dirty_since_baseline", False):
                            self.refresh_settings_unsaved_baseline()

                self.qt_after(0, done)
            except Exception as e:
                def failed(err=e):
                    if not silent:
                        self.append_system_log(f"Unable to pull Camera settings: {err}")
                self.qt_after(0, failed)

        Thread(target=worker, daemon=True).start()
