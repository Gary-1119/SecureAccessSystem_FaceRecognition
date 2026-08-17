from __future__ import annotations

from typing import Any

from threading import Thread

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app_config import *
from ui_components import *


class SettingsViewMixin:
    def build_settings_page(self: Any):
        """Settings page based on the uploaded settings UI reference."""
        outer = QWidget()
        outer.setObjectName("Page")

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("MainContent")
        # Settings has many form controls, so keep it slightly narrower than
        # the dashboard/face pages and give it wider side padding. This prevents
        # the cards/inputs from looking over-stretched on wide monitors.
        settings_max_width = min(self.content_max_width(), 1420 if not self.compact_mode else 1180)
        main.setMaximumWidth(settings_max_width)
        main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(main)
        layout.setContentsMargins(
            58 if not self.compact_mode else 28,
            28 if not self.compact_mode else 18,
            58 if not self.compact_mode else 28,
            28 if not self.compact_mode else 18,
        )
        layout.setSpacing(20 if not self.compact_mode else 14)

        # Settings header row:
        # Left = page title and description
        # Right = Cancel / Save Connect action buttons
        settings_header = QHBoxLayout()
        settings_header.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("System Configuration")
        title.setObjectName("SettingsTitle")

        desc = QLabel("Manage administrative credentials and security protocol thresholds.")
        desc.setObjectName("SettingsDesc")

        title_box.addWidget(title)
        title_box.addWidget(desc)

        header_actions = QHBoxLayout()
        header_actions.setSpacing(8)

        save = QPushButton("Save")
        self.settings_save_connect_btn = save
        save.setObjectName("SettingsPrimaryButton")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setMinimumHeight(40 if not self.compact_mode else 34)
        save.setMinimumWidth(118 if not self.compact_mode else 104)
        save.clicked.connect(self.save_settings_from_ui)

        header_actions.addWidget(save)

        settings_header.addLayout(title_box, 1)
        settings_header.addLayout(header_actions, 0)

        layout.addLayout(settings_header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20 if not self.compact_mode else 12)
        grid.setVerticalSpacing(20 if not self.compact_mode else 12)
        grid.setColumnStretch(0, 7)
        grid.setColumnStretch(1, 5)

        grid.addWidget(self.pi_connectivity_card(), 0, 0)
        grid.addWidget(self.camera_rotation_card(), 0, 1)
        grid.addWidget(self.server_credentials_card(), 1, 0)
        grid.addWidget(self.face_data_transfer_card(), 1, 1)
        grid.addWidget(self.security_options_card(), 2, 0)
        grid.addWidget(self.admin_management_card(), 2, 1)

        layout.addLayout(grid)


        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    def settings_card_base(self: Any, title_text: str, icon_text: str):
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            24 if not self.compact_mode else 18,
            22 if not self.compact_mode else 16,
            24 if not self.compact_mode else 18,
            22 if not self.compact_mode else 16,
        )
        layout.setSpacing(14 if not self.compact_mode else 10)

        header = QHBoxLayout()
        icon = QLabel(icon_text)
        icon.setObjectName("SettingsCardIcon")
        title = QLabel(title_text)
        title.setObjectName("SettingsCardTitle")
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        line = QFrame()
        line.setObjectName("SettingsDivider")
        line.setFixedHeight(1)
        layout.addWidget(line)

        return card, layout

    def settings_label(self: Any, text: str):
        label = QLabel(text)
        label.setObjectName("SettingsLabel")
        return label

    def settings_input(self: Any, value: str = "", placeholder: str = "", password: bool = False, readonly: bool = False):
        field = QLineEdit()
        field.setObjectName("SettingsInput")
        field.setText(value)
        field.setPlaceholderText(placeholder)
        field.setReadOnly(readonly)

        # Settings text fields only: make typed/displayed text thinner.
        # Buttons keep their original bold style.
        font = field.font()
        font.setWeight(QFont.Weight.Normal)
        field.setFont(font)

        if password:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setMinimumHeight(38 if not self.compact_mode else 34)
        return field

    def settings_button(self: Any, text: str, primary: bool = False):
        btn = QPushButton(text)
        btn.setObjectName("SettingsPrimaryButton" if primary else "SettingsSecondaryButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(38 if not self.compact_mode else 34)
        return btn

    def add_form_row(self: Any, layout: QVBoxLayout, label_text: str, widget: QWidget):
        label = self.settings_label(label_text)
        layout.addWidget(label)
        layout.addWidget(widget)

    def server_credentials_card(self: Any):
        card, layout = self.settings_card_base("Server Credentials", "▣")

        two_col = QGridLayout()
        two_col.setHorizontalSpacing(14)
        two_col.setVerticalSpacing(8)

        ntid_box = QVBoxLayout()
        ntid_box.addWidget(self.settings_label("NTID / Username"))
        self.settings_ntid_input = self.settings_input("", "Enter NTID", readonly=False)
        self.settings_ntid_input.textEdited.connect(lambda _text="": self.mark_settings_modified_by_user())
        ntid_box.addWidget(self.settings_ntid_input)

        pass_box = QVBoxLayout()
        pass_box.addWidget(self.settings_label("Password"))
        self.settings_password_input = self.settings_input("", password=True)
        self.settings_password_input.textEdited.connect(lambda _text="": self.mark_settings_modified_by_user())
        pass_box.addWidget(self.settings_password_input)

        two_col.addLayout(ntid_box, 0, 0)
        two_col.addLayout(pass_box, 0, 1)
        layout.addLayout(two_col)

        # Domain is fixed internally and is not shown to users.

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.settings_server_path_input = self.settings_input("", "Select or enter shared server path")
        self.settings_server_path_input.textEdited.connect(lambda _text="": self.mark_settings_modified_by_user())
        browse = self.settings_button("Browse")
        browse.clicked.connect(self.browse_server_path)
        path_row.addWidget(self.settings_server_path_input, 1)
        path_row.addWidget(browse)
        layout.addWidget(self.settings_label("Server Path"))
        layout.addLayout(path_row)

        self.clear_sensitive_server_credentials_ui(clear_server_path=False)

        return card

    def set_pi_status_label(self: Any, connected: bool = False, checking: bool = False, message: str = ""):
        """Keep Settings > Camera Connectivity status aligned with actual camera connection state."""
        if not hasattr(self, "pi_status_label"):
            return

        try:
            if (
                not checking
                and not connected
                and callable(getattr(self, "is_local_rtsp_active_for_ui", None))
                and self.is_local_rtsp_active_for_ui()
            ):
                connected = True
                message = "Status: Connected | camera feed recovering"
                self.pi_connected = True
                self.pi_connection_checked = True
                self._camera_user_stopped = False
        except Exception:
            pass

        if checking:
            text = message or "Status: Checking..."
            obj = "SettingsDisconnected"
        elif connected:
            text = message or "Status: Connected"
            obj = "SettingsConnected"
        else:
            text = message or "Status: Disconnected"
            obj = "SettingsDisconnected"

        self.pi_status_label.setText("●  " + text)
        self.pi_status_label.setObjectName(obj)
        self.pi_status_label.style().unpolish(self.pi_status_label)
        self.pi_status_label.style().polish(self.pi_status_label)
        self.pi_status_label.update()
        try:
            self.update_pi_connect_ui_state(connected=connected, checking=checking)
        except Exception:
            pass

    def pi_connectivity_card(self: Any):
        card, layout = self.settings_card_base("Camera Connectivity", "⌁")

        host_row = QHBoxLayout()
        host_row.setSpacing(8)

        # Port is fixed to 5000 for safety. User only enters hostname/IP.
        self.pi_host_input = self.settings_input(self.pi_api_host, "e.g. 192.168.1.50")
        self.pi_host_input.textEdited.connect(self.handle_pi_host_text_edited)
        self.pi_api_port = "5000"

        connect = self.settings_button("Connect", primary=True)
        self.pi_connect_btn = connect
        connect.clicked.connect(lambda checked=False: self.toggle_pi_connection_from_settings())

        host_row.addWidget(self.pi_host_input, 1)
        host_row.addWidget(connect)

        layout.addWidget(self.settings_label("Camera Hostname / IP"))
        layout.addLayout(host_row)

        try:
            if callable(getattr(self, "is_local_rtsp_active_for_ui", None)) and self.is_local_rtsp_active_for_ui():
                self.pi_connected = True
                self.pi_connection_checked = True
                self._camera_user_stopped = False
        except Exception:
            pass

        # API port is fixed internally and is not shown to users.

        initial_status = "●  Status: Connected" if getattr(self, "pi_connected", False) else "●  Status: Disconnected"
        self.pi_status_label = QLabel(initial_status)
        self.pi_status_label.setObjectName("SettingsConnected" if getattr(self, "pi_connected", False) else "SettingsDisconnected")
        layout.addWidget(self.pi_status_label)
        self.update_pi_connect_ui_state(connected=getattr(self, "pi_connected", False))

        # Keep the label object for internal compatibility, but do not show the
        # connected camera identity summary line in the Settings UI.
        self.pi_identity_label = QLabel("")
        self.pi_identity_label.setObjectName("SettingsHint")
        self.pi_identity_label.setWordWrap(True)
        self.pi_identity_label.setVisible(False)

        return card

    def face_data_transfer_card(self: Any):
        card, layout = self.settings_card_base("Face Data Transfer", "◎")

        # Main import/export panel for local users, embeddings and photos.
        server_panel = QFrame()
        server_panel.setObjectName("SettingsInnerPanel")
        server_layout = QVBoxLayout(server_panel)
        server_layout.setContentsMargins(16, 14, 16, 14)
        server_layout.setSpacing(10)

        server_title = QLabel("Import and Export Data")
        server_title.setObjectName("SettingsMiniTitle")
        server_desc = QLabel("Export or import users, embeddings and face photos through Server Path or local ZIP.")
        server_desc.setObjectName("SettingsMiniDesc")
        server_desc.setWordWrap(True)

        server_actions = QHBoxLayout()
        server_actions.setSpacing(12)
        export_btn = self.settings_button("⇧  Export")
        import_btn = self.settings_button("⇩  Import")
        restore_btn = QPushButton("R")
        restore_btn.setObjectName("SettingsSquareButton")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setToolTip("Restore local face data backup")
        restore_btn.setFixedSize(40 if not self.compact_mode else 36, 38 if not self.compact_mode else 34)
        export_btn.clicked.connect(self._local_face_export_data)
        import_btn.clicked.connect(self._local_face_import_data)
        restore_btn.clicked.connect(self._local_face_restore_backup)
        import_group = QHBoxLayout()
        import_group.setSpacing(8)
        import_group.addWidget(import_btn, 1)
        import_group.addWidget(restore_btn)
        server_actions.addWidget(export_btn, 1)
        server_actions.addLayout(import_group, 1)

        server_layout.addWidget(server_title)
        server_layout.addWidget(server_desc)
        server_layout.addLayout(server_actions)
        layout.addWidget(server_panel)

        return card

    def create_timeout_input(self: Any, value: str = "0", max_value: int = 59):
        """Create a numeric timeout field.

        Minutes and seconds are restricted to 0-59 so users cannot enter values
        like 100 seconds or 100 minutes.
        """
        inp = self.settings_input(value, "0")
        inp.setValidator(QIntValidator(0, max_value, inp))
        inp.setFixedWidth(90 if not self.compact_mode else 70)
        inp.setToolTip(f"Allowed range: 0-{max_value}")
        inp.textEdited.connect(lambda _text="": self.mark_settings_modified_by_user())
        inp.editingFinished.connect(lambda field=inp, max_v=max_value: self.normalize_timeout_input(field, max_v))
        return inp

    def normalize_timeout_input(self: Any, field, max_value: int = 59):
        """Clamp empty/out-of-range timeout values for a friendlier UI."""
        try:
            raw = field.text().strip()
            value = int(raw) if raw else 0
        except Exception:
            value = 0

        value = max(0, min(value, max_value))
        field.setText(str(value))

    def security_options_card(self: Any):
        card, layout = self.settings_card_base("Security Options", "◈")

        self.security_option_buttons = {}

        for key, text, default in [
            ("disable_keyboard", "Disable Keyboard When Locked", True),
            ("disable_mouse", "Disable Mouse When Locked", True),
        ]:
            row = QHBoxLayout()
            label = QLabel(text)
            label.setObjectName("SettingsOptionText")
            cb = QPushButton("✓")
            cb.setObjectName("SettingsCheckBoxButton")
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setCheckable(True)
            cb.setChecked(default)
            cb.setFixedSize(26, 26)
            cb.clicked.connect(lambda _checked=False: self.mark_settings_modified_by_user())
            self.security_option_buttons[key] = cb
            row.addWidget(label)
            row.addStretch()
            row.addWidget(cb)
            layout.addLayout(row)

        layout.addSpacing(4)
        layout.addWidget(self.settings_label("Inactivity Lock Time"))

        time_grid = QGridLayout()
        time_grid.setHorizontalSpacing(8)

        self.timeout_inputs = {}
        for col, (key, label, value, max_value) in enumerate([
            ("hours", "Hours", "0", 23),
            ("minutes", "Minutes", "5", 59),
            ("seconds", "Seconds", "0", 59),
        ]):
            box = QVBoxLayout()
            inp = self.create_timeout_input(value, max_value)
            self.timeout_inputs[key] = inp
            cap = QLabel(f"{label} (0-{max_value})" if key in ("minutes", "seconds") else label)
            cap.setObjectName("SettingsLabel")
            box.addWidget(inp)
            box.addWidget(cap)
            time_grid.addLayout(box, 0, col)

        layout.addLayout(time_grid)
        layout.addStretch()
        return card

    @staticmethod
    def normalize_camera_rotation(value, default: int = 0) -> int:
        """Normalize a local camera rotation to 0/90/180/270 degrees clockwise."""
        try:
            rotation = int(str(value).strip())
        except Exception:
            rotation = int(default)
        rotation %= 360
        return rotation if rotation in (0, 90, 180, 270) else int(default)

    @staticmethod
    def camera_rotation_label(value) -> str:
        rotation = SettingsViewMixin.normalize_camera_rotation(value)
        return {
            0: "0° (Normal)",
            90: "90° Clockwise",
            180: "180°",
            270: "270° Clockwise",
        }[rotation]

    def camera_rotation_card(self: Any):
        """Create the SAS control that persists camera orientation on the camera."""
        card, layout = self.settings_card_base("Camera Orientation", "↻")

        desc = QLabel(
            "Correct the image when the RTSP camera is mounted sideways or upside down. "
            "The setting is saved on the camera, so the camera preview and SAS live camera panel match."
        )
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.camera_rotation_buttons = {}

        for rotation, text in ((0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")):
            button = self.settings_button(text, primary=False)
            button.setCheckable(True)
            button.setMinimumWidth(54 if not self.compact_mode else 46)
            button.clicked.connect(
                lambda _checked=False, degrees=rotation: self.set_camera_rotation_from_ui(degrees)
            )
            row.addWidget(button)
            self.camera_rotation_buttons[rotation] = button

        row.addStretch()
        layout.addLayout(row)

        self.camera_rotation_status_label = QLabel("●  Local setting: 0°")
        self.camera_rotation_status_label.setObjectName("SettingsHint")
        self.camera_rotation_status_label.setWordWrap(True)
        layout.addWidget(self.camera_rotation_status_label)

        self.update_camera_rotation_ui(
            self.camera_rotation,
            status=f"●  Local setting: {self.camera_rotation_label(self.camera_rotation)}",
            ok=True,
        )

        layout.addStretch()
        return card

    def poll_camera_rotation_from_pi(self: Any):
        """Refresh camera rotation silently while the SAS Settings page is visible."""
        if str(getattr(self, "current_top_tab", "") or "").lower() != "settings":
            return
        if not bool(getattr(self, "pi_connected", False)):
            return
        if getattr(self, "_camera_rotation_poll_in_progress", False):
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return

        self._camera_rotation_poll_in_progress = True

        def worker():
            try:
                data = self._local_face_request("GET", "/settings", timeout=8)
                nested = data.get("settings", {}) if isinstance(data, dict) else {}
                if not isinstance(nested, dict):
                    nested = {}
                rotation = data.get("camera_rotation", nested.get("camera_rotation")) if isinstance(data, dict) else None

                def done():
                    self._camera_rotation_poll_in_progress = False
                    if rotation is not None and not getattr(self, "_camera_rotation_sync_in_progress", False):
                        self.update_camera_rotation_ui(
                            rotation,
                            status=f"●  Local setting: {self.camera_rotation_label(rotation)}",
                            ok=True,
                        )

                self.qt_after(0, done)
            except Exception:
                self.qt_after(0, lambda: setattr(self, "_camera_rotation_poll_in_progress", False))

        Thread(target=worker, daemon=True, name="PiCameraRotationPoll").start()

    def update_camera_rotation_ui(self: Any, rotation, status: str | None = None, ok: bool = True):
        """Reflect the camera rotation value in the Settings page without changing it."""
        degrees = self.normalize_camera_rotation(rotation, default=getattr(self, "camera_rotation", 0))
        self.camera_rotation = degrees

        for value, button in getattr(self, "camera_rotation_buttons", {}).items():
            selected = value == degrees
            button.setChecked(selected)
            button.setObjectName("SettingsPrimaryButton" if selected else "SettingsSecondaryButton")
            try:
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
            except Exception:
                pass

        label = getattr(self, "camera_rotation_status_label", None)
        if label is not None:
            label.setText(status or f"●  Local setting: {self.camera_rotation_label(degrees)}")
            label.setObjectName("SettingsConnected" if ok else "SettingsHint")
            try:
                label.style().unpolish(label)
                label.style().polish(label)
                label.update()
            except Exception:
                pass

    def set_camera_rotation_from_ui(self: Any, rotation):
        """Apply the selected rotation to the local RTSP recognition engine."""
        requested = self.normalize_camera_rotation(rotation, default=self.camera_rotation)
        previous = self.camera_rotation

        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.update_camera_rotation_ui(
                previous,
                status="●  Local setting: hostname/IP is not configured",
                ok=False,
            )
            self.append_system_log("CAMERA_ROTATION_SYNC_FAILED: Camera hostname/IP is not configured.")
            return

        if getattr(self, "_camera_rotation_sync_in_progress", False):
            return

        self._camera_rotation_sync_in_progress = True
        self.update_camera_rotation_ui(requested, status="●  Applying local camera rotation...", ok=False)

        def worker():
            try:
                data = self._local_face_request(
                    "POST",
                    "/settings",
                    {
                        "camera_rotation": requested,
                        "source": "Windows SAS",
                    },
                    timeout=15,
                )

                nested = data.get("settings", {}) if isinstance(data, dict) else {}
                applied = self.normalize_camera_rotation(
                    data.get("camera_rotation", nested.get("camera_rotation", requested))
                    if isinstance(data, dict) else requested,
                    default=requested,
                )
                message = data.get("message", "Local camera orientation saved.") if isinstance(data, dict) else "Local camera orientation saved."

                def done():
                    self._camera_rotation_sync_in_progress = False
                    self.update_camera_rotation_ui(
                        applied,
                        status=f"●  Local setting: {self.camera_rotation_label(applied)}",
                        ok=True,
                    )
                    actor = self.get_audit_actor()
                    self.write_sas_log(
                        f"CAMERA ROTATION CHANGED | ACTOR={actor} | ROTATION={applied} | TARGET=LOCAL_RTSP | METHOD=SETTINGS"
                    )
                    self.append_system_log(f"CAMERA_ROTATION_SYNCED: {self.camera_rotation_label(applied)} | {message}")

                self.qt_after(0, done)
            except Exception as exc:
                error = str(exc)

                def failed():
                    self._camera_rotation_sync_in_progress = False
                    self.update_camera_rotation_ui(
                        previous,
                        status="●  Local setting: failed",
                        ok=False,
                    )
                    self.append_system_log(f"CAMERA_ROTATION_SYNC_FAILED: {error}")

                self.qt_after(0, failed)

        Thread(target=worker, daemon=True, name="PiCameraRotationSync").start()

    def admin_management_card(self: Any):
        card, layout = self.settings_card_base("Admin Management", "👥")

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.admin_add_input = self.settings_input("", "Enter NTID to add...")
        add_btn = self.settings_button("Add", primary=True)
        add_btn.clicked.connect(self.add_admin_from_ui)
        add_row.addWidget(self.admin_add_input, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        admin_box = QFrame()
        admin_box.setObjectName("AdminListBox")
        self.admin_list_layout = QVBoxLayout(admin_box)
        self.admin_list_layout.setContentsMargins(0, 0, 0, 0)
        self.admin_list_layout.setSpacing(0)

        # Keep the Admin Management card stable.
        # If more than 5 admins are added, the list scrolls instead of making the box/card taller.
        self.admin_list_scroll = QScrollArea()
        self.admin_list_scroll.setObjectName("AdminListScroll")
        self.admin_list_scroll.setWidgetResizable(True)
        self.admin_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.admin_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.admin_list_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.admin_list_scroll.setFixedHeight((40 * 5) + 2 if not self.compact_mode else (36 * 5) + 2)
        self.admin_list_scroll.setWidget(admin_box)

        # Visible thin scrollbar, same style as the Face Recognition System Log.
        self.admin_list_scroll.setStyleSheet(self.admin_list_scroll.styleSheet() + """
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

        layout.addWidget(self.admin_list_scroll)
        QTimer.singleShot(0, self.refresh_admin_list_ui)
        layout.addStretch()
        return card

    def admin_row(self: Any, ntid: str, tag: str = "", removable: bool = False):
        row = QFrame()
        row.setObjectName("AdminRow")
        row_h = 36 if self.compact_mode else 40
        row.setMinimumHeight(row_h)
        row.setMaximumHeight(row_h)
        row.setFixedHeight(row_h)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)

        name = QLabel(ntid + (f"  {tag}" if tag else ""))
        name.setObjectName("AdminName")
        layout.addWidget(name)
        layout.addStretch()

        if removable:
            remove = QPushButton("Remove")
            remove.setObjectName("RemoveButton")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _=False, admin_ntid=ntid: self.remove_admin_from_ui(admin_ntid))
            layout.addWidget(remove)

        return row
