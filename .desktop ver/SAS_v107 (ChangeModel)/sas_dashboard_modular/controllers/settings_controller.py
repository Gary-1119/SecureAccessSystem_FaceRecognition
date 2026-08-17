from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase
from services.atomic_file import atomic_write_text


class SettingsControllerMixin(DashboardMixinBase):
    def build_settings_page(self):
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
        grid.addWidget(self.server_credentials_card(), 0, 1)
        grid.addWidget(self.camera_rotation_card(), 1, 0)
        grid.addWidget(self.face_data_transfer_card(), 1, 1)
        grid.addWidget(self.security_options_card(), 2, 0)
        grid.addWidget(self.pi_storage_card(), 2, 1)
        grid.addWidget(self.log_download_card(), 3, 0, 1, 2)
        grid.addWidget(self.admin_management_card(), 4, 0, 1, 2)

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


    def build_login_page(self):
        """Login page based on the uploaded login overlay design, using the same header/footer."""
        outer = QWidget()
        outer.setObjectName("Page")

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        main = QWidget()
        main.setObjectName("LoginMainContent")

        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(
            42 if not self.compact_mode else 24,
            30 if not self.compact_mode else 20,
            42 if not self.compact_mode else 24,
            30 if not self.compact_mode else 20,
        )
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("LoginCard")
        card.setMaximumWidth(430 if not self.compact_mode else 380)
        card.setMinimumWidth(360 if not self.compact_mode else 320)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            34 if not self.compact_mode else 26,
            32 if not self.compact_mode else 24,
            34 if not self.compact_mode else 26,
            30 if not self.compact_mode else 24,
        )
        card_layout.setSpacing(16 if not self.compact_mode else 12)

        icon = QLabel("▣")
        icon.setObjectName("LoginShieldIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(48 if not self.compact_mode else 42, 48 if not self.compact_mode else 42)

        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon)
        icon_row.addStretch()
        card_layout.addLayout(icon_row)

        title = QLabel("SECURE ACCESS SYSTEM")
        title.setObjectName("LoginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Enter your credentials to manage security")
        subtitle.setObjectName("LoginSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        form = QVBoxLayout()
        form.setSpacing(12 if not self.compact_mode else 10)

        ntid_label = QLabel("NTID")
        ntid_label.setObjectName("LoginFieldLabel")

        self.login_ntid_input = QLineEdit()
        self.login_ntid_input.setObjectName("LoginInput")
        self.login_ntid_input.setPlaceholderText("e.g. 1234567")
        self.login_ntid_input.setMinimumHeight(46 if not self.compact_mode else 40)

        password_top = QHBoxLayout()
        password_label = QLabel("Password")
        password_label.setObjectName("LoginFieldLabel")
        forgot = QLabel("Forgot Password?")
        forgot.setObjectName("LoginForgot")
        password_top.addWidget(password_label)
        password_top.addStretch()
        password_top.addWidget(forgot)

        password_row = QHBoxLayout()
        password_row.setSpacing(8)

        self.login_password_input = QLineEdit()
        self.login_password_input.setObjectName("LoginInput")
        self.login_password_input.setPlaceholderText("••••••••")
        self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password_input.setMinimumHeight(46 if not self.compact_mode else 40)

        self.login_toggle_btn = QPushButton("Show")
        self.login_toggle_btn.setObjectName("LoginToggleButton")
        self.login_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_toggle_btn.setFixedSize(64 if not self.compact_mode else 56, 40 if not self.compact_mode else 36)
        self.login_toggle_btn.clicked.connect(self.toggle_login_password)

        password_row.addWidget(self.login_password_input, 1)
        password_row.addWidget(self.login_toggle_btn)

        self.login_status_label = QLabel("First valid login becomes Admin if no admin has been registered yet.")
        self.login_status_label.setObjectName("LoginStatus")
        self.login_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_status_label.setWordWrap(True)

        login_btn = QPushButton("Login  →")
        login_btn.setObjectName("LoginSubmitButton")
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.setMinimumHeight(46 if not self.compact_mode else 40)
        login_btn.clicked.connect(self.login_requested)
        login_btn.setDefault(True)
        login_btn.setAutoDefault(True)

        self.login_ntid_input.returnPressed.connect(self.login_requested)
        self.login_password_input.returnPressed.connect(self.login_requested)

        form.addWidget(ntid_label)
        form.addWidget(self.login_ntid_input)
        form.addLayout(password_top)
        form.addLayout(password_row)
        form.addWidget(login_btn)
        card_layout.addLayout(form)

        divider = QFrame()
        divider.setObjectName("LoginDivider")
        divider.setFixedHeight(1)
        card_layout.addWidget(divider)
        card_layout.addWidget(self.login_status_label)

        main_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(main)
        self.make_scrollbar_invisible(scroll)

        outer_layout.addWidget(scroll)
        return outer

    # --------------------------------------------------------
    # Settings page parts
    # --------------------------------------------------------

    def settings_card_base(self, title_text: str, icon_text: str):
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


    def settings_label(self, text: str):
        label = QLabel(text)
        label.setObjectName("SettingsLabel")
        return label


    def settings_input(self, value: str = "", placeholder: str = "", password: bool = False, readonly: bool = False):
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


    def settings_button(self, text: str, primary: bool = False):
        btn = QPushButton(text)
        btn.setObjectName("SettingsPrimaryButton" if primary else "SettingsSecondaryButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(38 if not self.compact_mode else 34)
        return btn


    def add_form_row(self, layout: QVBoxLayout, label_text: str, widget: QWidget):
        label = self.settings_label(label_text)
        layout.addWidget(label)
        layout.addWidget(widget)


    def server_credentials_card(self):
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


    def log_download_card(self):
        card, layout = self.settings_card_base("Log Download", "▤")

        desc = QLabel("Download today's SAS_LOG or Pi_LOG to a local Windows folder without using the server path.")
        desc.setObjectName("SettingsHint")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(10)

        sas_btn = self.settings_button("Download SAS_LOG", primary=False)
        sas_btn.clicked.connect(self.download_sas_logs_to_local)
        self.download_sas_logs_btn = sas_btn

        pi_btn = self.settings_button("Download Pi_LOG", primary=True)
        pi_btn.clicked.connect(self.download_pi_logs_to_local)
        self.download_pi_logs_btn = pi_btn

        row.addWidget(sas_btn)
        row.addWidget(pi_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.log_download_status_label = QLabel("Select a log type, then choose the local folder to save it.")
        self.log_download_status_label.setObjectName("SettingsHint")
        self.log_download_status_label.setWordWrap(True)
        layout.addWidget(self.log_download_status_label)

        return card


    def set_pi_status_label(self, connected: bool = False, checking: bool = False, message: str = ""):
        """Keep Settings > Pi Connectivity status aligned with actual Pi connection state."""
        if not hasattr(self, "pi_status_label"):
            return

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



    def pi_connectivity_card(self):
        card, layout = self.settings_card_base("Pi Connectivity", "⌁")

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

        layout.addWidget(self.settings_label("Pi Hostname / IP"))
        layout.addLayout(host_row)

        # API port is fixed internally and is not shown to users.

        initial_status = "●  Status: Connected" if getattr(self, "pi_connected", False) else "●  Status: Disconnected"
        self.pi_status_label = QLabel(initial_status)
        self.pi_status_label.setObjectName("SettingsConnected" if getattr(self, "pi_connected", False) else "SettingsDisconnected")
        layout.addWidget(self.pi_status_label)
        self.update_pi_connect_ui_state(connected=getattr(self, "pi_connected", False))

        # Keep the label object for internal compatibility, but do not show the
        # connected Pi identity summary line in the Settings UI.
        self.pi_identity_label = QLabel("")
        self.pi_identity_label.setObjectName("SettingsHint")
        self.pi_identity_label.setWordWrap(True)
        self.pi_identity_label.setVisible(False)

        return card


    def face_data_transfer_card(self):
        card, layout = self.settings_card_base("Face Data Transfer", "◎")

        # Main import/export panel. Export and Import popups now contain
        # separate Server Path and SFTP/Local tabs.
        server_panel = QFrame()
        server_panel.setObjectName("SettingsInnerPanel")
        server_layout = QVBoxLayout(server_panel)
        server_layout.setContentsMargins(16, 14, 16, 14)
        server_layout.setSpacing(10)

        server_title = QLabel("Import and Export Data")
        server_title.setObjectName("SettingsMiniTitle")
        server_desc = QLabel("Export or import dataset and embedding packages through Server Path, SFTP download, or local ZIP import.")
        server_desc.setObjectName("SettingsMiniDesc")
        server_desc.setWordWrap(True)

        server_actions = QHBoxLayout()
        export_btn = self.settings_button("⇧  Export")
        import_btn = self.settings_button("⇩  Import")
        export_btn.clicked.connect(self._face_api_export_data)
        import_btn.clicked.connect(self._face_api_import_data)
        server_actions.addWidget(export_btn)
        server_actions.addWidget(import_btn)

        server_layout.addWidget(server_title)
        server_layout.addWidget(server_desc)
        server_layout.addLayout(server_actions)
        layout.addWidget(server_panel)

        # SFTP node-to-node tools stay here only. Transfer to Windows is now
        # located inside Export -> Local Path.
        sftp_panel = QFrame()
        sftp_panel.setObjectName("SettingsInnerPanel")
        sftp_layout = QVBoxLayout(sftp_panel)
        sftp_layout.setContentsMargins(16, 14, 16, 14)
        sftp_layout.setSpacing(10)

        title = QLabel("Transfer Face Data via SFTP")
        title.setObjectName("SettingsMiniTitle")
        desc = QLabel("Securely send dataset packages to another Pi and review received packages.")
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)

        actions = QHBoxLayout()
        send = self.settings_button("Send to Another Pi", primary=True)
        check = self.settings_button("Check Received")
        self.sas_check_received_btn = check
        check_badge = QLabel("", check)
        check_badge.setObjectName("ReceivedBadge")
        check_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check_badge.setFixedSize(24, 24)
        check_badge.hide()
        self.sas_received_badge_label = check_badge
        self._sas_received_badge_count = 0
        try:
            check.installEventFilter(self)
        except Exception:
            pass
        send.clicked.connect(self._face_api_sftp_send)
        check.clicked.connect(self._face_api_check_received)
        actions.addWidget(send)
        actions.addWidget(check)

        sftp_layout.addWidget(title)
        sftp_layout.addWidget(desc)
        sftp_layout.addLayout(actions)
        layout.addWidget(sftp_panel)

        return card


    def create_timeout_input(self, value: str = "0", max_value: int = 59):
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


    def normalize_timeout_input(self, field, max_value: int = 59):
        """Clamp empty/out-of-range timeout values for a friendlier UI."""
        try:
            raw = field.text().strip()
            value = int(raw) if raw else 0
        except Exception:
            value = 0

        value = max(0, min(value, max_value))
        field.setText(str(value))


    def security_options_card(self):
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


    def auto_capture_card(self):
        card, layout = self.settings_card_base("Auto-Capture", "▣")

        desc = QLabel(
            "Auto-captures up to 10 photos when one face is detected."
        )
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.auto_capture_toggle = AutoCaptureSegment(self, self.compact_mode)
        self.auto_capture_toggle.on_state_changed = self.on_auto_capture_toggle_changed  # type: ignore[assignment]
        layout.addWidget(self.auto_capture_toggle)

        layout.addStretch()
        return card

    # --------------------------------------------------------
    # Pi storage monitoring
    # --------------------------------------------------------
    @staticmethod

    def format_storage_bytes(value) -> str:
        """Format an API byte count for the SAS Settings display."""
        try:
            amount = max(0, int(value))
        except Exception:
            amount = 0

        units = ("B", "KB", "MB", "GB", "TB")
        number = float(amount)
        unit = units[0]
        for unit in units:
            if number < 1024.0 or unit == units[-1]:
                break
            number /= 1024.0
        return f"{int(number)} {unit}" if unit == "B" else f"{number:.1f} {unit}"


    def pi_storage_card(self):
        """Show current SD-card/root-filesystem usage read from the Pi API."""
        card, layout = self.settings_card_base("Pi Storage", "▤")

        desc = QLabel(
            "Live Raspberry Pi SD-card storage. Dataset photos, encodings, logs and face-data packages share this space."
        )
        desc.setObjectName("SettingsMiniDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.pi_storage_summary_label = QLabel("Storage information has not been loaded.")
        self.pi_storage_summary_label.setObjectName("SettingsMiniTitle")
        self.pi_storage_summary_label.setWordWrap(True)
        layout.addWidget(self.pi_storage_summary_label)

        self.pi_storage_progress = QProgressBar()
        self.pi_storage_progress.setObjectName("PiStorageProgressBar")
        self.pi_storage_progress.setRange(0, 1000)
        self.pi_storage_progress.setValue(0)
        self.pi_storage_progress.setTextVisible(False)
        self.pi_storage_progress.setMinimumHeight(14 if not self.compact_mode else 12)
        layout.addWidget(self.pi_storage_progress)

        self.pi_storage_detail_label = QLabel("Connect to the Pi to view its storage.")
        self.pi_storage_detail_label.setObjectName("SettingsHint")
        self.pi_storage_detail_label.setWordWrap(True)
        layout.addWidget(self.pi_storage_detail_label)

        footer = QHBoxLayout()
        self.pi_storage_status_label = QLabel("●  Waiting for Pi connection")
        self.pi_storage_status_label.setObjectName("SettingsHint")
        self.pi_storage_status_label.setWordWrap(True)
        refresh = self.settings_button("↻  Refresh")
        refresh.clicked.connect(lambda checked=False: self.refresh_pi_storage_from_pi(silent=False))
        self.pi_storage_refresh_button = refresh
        footer.addWidget(self.pi_storage_status_label, 1)
        footer.addWidget(refresh, 0)
        layout.addLayout(footer)

        self.set_pi_storage_unavailable("Connect to the Pi to view its storage.")

        # Poll only while Settings is being viewed. A manual refresh is always
        # available, and an immediate refresh is performed after successful Pi
        # connection or opening the Settings tab.
        if not hasattr(self, "pi_storage_poll_timer"):
            self.pi_storage_poll_timer = QTimer(self)
            self.pi_storage_poll_timer.setInterval(30000)
            self.pi_storage_poll_timer.timeout.connect(lambda: self.refresh_pi_storage_from_pi(silent=True))
            self.pi_storage_poll_timer.start()

        layout.addStretch()
        return card


    def set_pi_storage_unavailable(self, message: str = "Storage information unavailable."):
        """Show a safe non-fatal state when Pi storage cannot be fetched."""
        summary = getattr(self, "pi_storage_summary_label", None)
        detail = getattr(self, "pi_storage_detail_label", None)
        status = getattr(self, "pi_storage_status_label", None)
        progress = getattr(self, "pi_storage_progress", None)
        refresh = getattr(self, "pi_storage_refresh_button", None)

        if summary is not None:
            summary.setText("Storage information unavailable")
        if detail is not None:
            detail.setText(str(message or "Storage information unavailable."))
            detail.setObjectName("SettingsHint")
            detail.style().unpolish(detail)
            detail.style().polish(detail)
        if status is not None:
            status.setText("●  Storage not loaded")
            status.setObjectName("SettingsHint")
            status.style().unpolish(status)
            status.style().polish(status)
        if progress is not None:
            progress.setValue(0)
            progress.setStyleSheet(
                "QProgressBar { background: #E3EAF4; border: 1px solid #D9E2EC; border-radius: 7px; }"
                "QProgressBar::chunk { background: #0B72FF; border-radius: 6px; }"
            )
        if refresh is not None and not getattr(self, "_pi_storage_poll_in_progress", False):
            refresh.setEnabled(True)


    def update_pi_storage_ui(self, snapshot: dict, message: str | None = None, ok: bool = True):
        """Render one /system/storage snapshot in the SAS Settings card."""
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        try:
            used_percent = max(0.0, min(100.0, float(snapshot.get("used_percent", 0.0))))
        except Exception:
            used_percent = 0.0

        total_human = str(snapshot.get("total_human") or self.format_storage_bytes(snapshot.get("total_bytes", 0)))
        used_human = str(snapshot.get("used_human") or self.format_storage_bytes(snapshot.get("used_bytes", 0)))
        available_human = str(snapshot.get("available_human") or self.format_storage_bytes(snapshot.get("available_bytes", 0)))
        mount_point = str(snapshot.get("mount_point") or "/")
        updated_at = str(snapshot.get("updated_at") or "")

        if used_percent >= 90.0:
            color = "#DC2626"
            state_label = "Storage critical"
            detail_object = "SettingsDisconnected"
        elif used_percent >= 80.0:
            color = "#EA580C"
            state_label = "Storage warning"
            detail_object = "SettingsHint"
        else:
            color = "#0B72FF"
            state_label = "Storage healthy"
            detail_object = "SettingsHint"

        summary = getattr(self, "pi_storage_summary_label", None)
        detail = getattr(self, "pi_storage_detail_label", None)
        status = getattr(self, "pi_storage_status_label", None)
        progress = getattr(self, "pi_storage_progress", None)
        refresh = getattr(self, "pi_storage_refresh_button", None)

        if summary is not None:
            summary.setText(f"{used_human} used of {total_human}")
        if detail is not None:
            detail.setText(
                f"{available_human} available  •  {used_percent:.1f}% used  •  Root filesystem: {mount_point}"
            )
            detail.setObjectName(detail_object)
            detail.style().unpolish(detail)
            detail.style().polish(detail)
        if progress is not None:
            progress.setValue(int(round(used_percent * 10)))
            progress.setStyleSheet(
                "QProgressBar { background: #E3EAF4; border: 1px solid #D9E2EC; border-radius: 7px; }"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 6px; }}"
            )
        if status is not None:
            status_text = message or f"●  {state_label}"
            if updated_at:
                status_text += f"  •  Updated: {updated_at}"
            status.setText(status_text)
            status.setObjectName("SettingsConnected" if ok else "SettingsDisconnected")
            status.style().unpolish(status)
            status.style().polish(status)
        if refresh is not None:
            refresh.setEnabled(True)


    def refresh_pi_storage_from_pi(self, silent: bool = True):
        """Fetch current Pi storage in a background thread, never blocking SAS UI."""
        if str(getattr(self, "current_top_tab", "") or "").lower() != "settings" and silent:
            return
        if not bool(getattr(self, "pi_connected", False)):
            self.set_pi_storage_unavailable("Connect to the Pi to view its storage.")
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.set_pi_storage_unavailable("Pi hostname/IP is not configured.")
            return
        if getattr(self, "_pi_storage_poll_in_progress", False):
            return

        self._pi_storage_poll_in_progress = True
        refresh = getattr(self, "pi_storage_refresh_button", None)
        status = getattr(self, "pi_storage_status_label", None)
        if refresh is not None:
            refresh.setEnabled(False)
        if status is not None:
            status.setText("●  Refreshing Pi storage...")
            status.setObjectName("SettingsHint")
            status.style().unpolish(status)
            status.style().polish(status)

        def worker():
            try:
                data = self._face_api_request("GET", "/system/storage", timeout=8)
                if not isinstance(data, dict) or not bool(data.get("ok", True)):
                    raise RuntimeError(str(data.get("message", "Invalid Pi storage response.")) if isinstance(data, dict) else "Invalid Pi storage response.")

                def done():
                    self._pi_storage_poll_in_progress = False
                    self._pi_storage_last_snapshot = data
                    self.update_pi_storage_ui(data, ok=True)
                    if not silent:
                        self.append_system_log(
                            f"PI_STORAGE_REFRESHED: USED={data.get('used_human', '-')} | "
                            f"AVAILABLE={data.get('available_human', '-')} | "
                            f"PERCENT={data.get('used_percent', '-')}"
                        )

                self.qt_after(0, done)
            except Exception as exc:
                error = str(exc)

                def failed():
                    self._pi_storage_poll_in_progress = False
                    self.set_pi_storage_unavailable(f"Could not load Pi storage: {error}")
                    if not silent:
                        self.append_system_log(f"PI_STORAGE_REFRESH_FAILED: {error}")

                self.qt_after(0, failed)

        Thread(target=worker, daemon=True, name="PiStoragePoll").start()

    # --------------------------------------------------------
    # Pi camera orientation
    # --------------------------------------------------------
    @staticmethod

    def normalize_camera_rotation(value, default: int = 0) -> int:
        """Normalize a Pi camera rotation to 0/90/180/270 degrees clockwise."""
        try:
            rotation = int(str(value).strip())
        except Exception:
            rotation = int(default)
        rotation %= 360
        return rotation if rotation in (0, 90, 180, 270) else int(default)

    @staticmethod

    def camera_rotation_label(value) -> str:
        rotation = SettingsControllerMixin.normalize_camera_rotation(value)
        return {
            0: "0° (Normal)",
            90: "90° Clockwise",
            180: "180°",
            270: "270° Clockwise",
        }[rotation]


    def camera_rotation_card(self):
        """Create the SAS control that persists camera orientation on the Pi."""
        card, layout = self.settings_card_base("Camera Orientation", "↻")

        desc = QLabel(
            "Correct the image when the Pi camera is mounted sideways or upside down. "
            "The setting is saved on the Pi, so the Pi preview and SAS live camera panel match."
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

        self.camera_rotation_status_label = QLabel("●  Pi setting: not loaded")
        self.camera_rotation_status_label.setObjectName("SettingsHint")
        self.camera_rotation_status_label.setWordWrap(True)
        layout.addWidget(self.camera_rotation_status_label)

        self.update_camera_rotation_ui(self.camera_rotation, status="●  Pi setting: not loaded", ok=False)

        # While Settings is active, poll the Pi every few seconds. This allows a
        # rotation chosen directly on the Pi screen to appear in SAS without a
        # reconnect or a page reload.
        if not hasattr(self, "camera_rotation_poll_timer"):
            self.camera_rotation_poll_timer = QTimer(self)
            self.camera_rotation_poll_timer.setInterval(3500)
            self.camera_rotation_poll_timer.timeout.connect(self.poll_camera_rotation_from_pi)
            self.camera_rotation_poll_timer.start()

        layout.addStretch()
        return card


    def poll_camera_rotation_from_pi(self):
        """Refresh Pi rotation silently while the SAS Settings page is visible."""
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
                data = self._face_api_request("GET", "/settings", timeout=8)
                nested = data.get("settings", {}) if isinstance(data, dict) else {}
                if not isinstance(nested, dict):
                    nested = {}
                rotation = data.get("camera_rotation", nested.get("camera_rotation")) if isinstance(data, dict) else None

                def done():
                    self._camera_rotation_poll_in_progress = False
                    if rotation is not None and not getattr(self, "_camera_rotation_sync_in_progress", False):
                        self.update_camera_rotation_ui(
                            rotation,
                            status=f"●  Pi setting: {self.camera_rotation_label(rotation)}",
                            ok=True,
                        )

                self.qt_after(0, done)
            except Exception:
                self.qt_after(0, lambda: setattr(self, "_camera_rotation_poll_in_progress", False))

        Thread(target=worker, daemon=True, name="PiCameraRotationPoll").start()


    def update_camera_rotation_ui(self, rotation, status: str | None = None, ok: bool = True):
        """Reflect the Pi rotation value in the Settings page without changing it."""
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
            label.setText(status or f"●  Pi setting: {self.camera_rotation_label(degrees)}")
            label.setObjectName("SettingsConnected" if ok else "SettingsHint")
            try:
                label.style().unpolish(label)
                label.style().polish(label)
                label.update()
            except Exception:
                pass


    def set_camera_rotation_from_ui(self, rotation):
        """Save the selected rotation directly to Pi settings.json via /settings."""
        requested = self.normalize_camera_rotation(rotation, default=self.camera_rotation)
        previous = self.camera_rotation

        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.update_camera_rotation_ui(
                previous,
                status="●  Pi sync: Hostname/IP is not configured",
                ok=False,
            )
            self.append_system_log("CAMERA_ROTATION_SYNC_FAILED: Pi hostname/IP is not configured.")
            return

        if getattr(self, "_camera_rotation_sync_in_progress", False):
            return

        self._camera_rotation_sync_in_progress = True
        self.update_camera_rotation_ui(requested, status="●  Pi sync: Applying camera rotation...", ok=False)

        def worker():
            try:
                data = self._face_api_request(
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
                message = data.get("message", "Pi camera orientation saved.") if isinstance(data, dict) else "Pi camera orientation saved."

                def done():
                    self._camera_rotation_sync_in_progress = False
                    self.update_camera_rotation_ui(
                        applied,
                        status=f"●  Pi synced: {self.camera_rotation_label(applied)}",
                        ok=True,
                    )
                    actor = self.get_audit_actor()
                    self.write_sas_log(
                        f"CAMERA ROTATION CHANGED | ACTOR={actor} | ROTATION={applied} | TARGET=PI | METHOD=SETTINGS"
                    )
                    self.append_system_log(f"CAMERA_ROTATION_SYNCED: {self.camera_rotation_label(applied)} | {message}")

                self.qt_after(0, done)
            except Exception as exc:
                error = str(exc)

                def failed():
                    self._camera_rotation_sync_in_progress = False
                    self.update_camera_rotation_ui(
                        previous,
                        status="●  Pi sync: Failed",
                        ok=False,
                    )
                    self.append_system_log(f"CAMERA_ROTATION_SYNC_FAILED: {error}")

                self.qt_after(0, failed)

        Thread(target=worker, daemon=True, name="PiCameraRotationSync").start()



    def admin_management_card(self):
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


    def admin_row(self, ntid: str, tag: str = "", removable: bool = False):
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

    # --------------------------------------------------------
    # Dashboard page parts
    # --------------------------------------------------------

    def _ensure_admin_file(self):
        self.admin_service.ensure_admin_file()


    def _load_admins(self):
        return self.admin_service.load_admins()


    def _save_admin(self, ntid):
        self.admin_service.save_admin(ntid)


    def _remove_admin(self, ntid):
        if hasattr(self.admin_service, "remove_admin"):
            return self.admin_service.remove_admin(ntid)

        # Fallback for older service object.
        target = str(ntid).strip().lower()
        admins = self._load_admins()
        if not target or target not in admins:
            return False, "Admin not found."
        if admins and target == admins[0]:
            return False, "The first/root admin cannot be removed."
        admins = [admin for admin in admins if admin != target]
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            for admin in admins:
                f.write(admin + "\n")
        return True, "Admin removed."


    def _check_admin_login(self, ntid):
        return self.admin_service.check_admin_login(ntid)


    def refresh_admin_list_ui(self):
        if not hasattr(self, "admin_list_layout"):
            return

        while self.admin_list_layout.count():
            item = self.admin_list_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        admins = self._load_admins()

        if not admins:
            self.admin_list_layout.addWidget(
                self.admin_row(
                    "No admin yet",
                    f"admins.txt not loaded or empty",
                    removable=False
                )
            )
            self.admin_list_layout.addStretch(1)
            return

        for index, admin in enumerate(admins):
            admin_key = str(admin).strip().lower()
            tag = "(you)" if self.current_user and admin_key == self.current_user.lower() else ""
            self.admin_list_layout.addWidget(self.admin_row(admin_key.upper(), tag, removable=(index != 0)))

        # Important: this stretch consumes the remaining space.
        # Without it, Qt stretches each admin row when there are only 1-2 admins.
        self.admin_list_layout.addStretch(1)

        if hasattr(self, "admin_list_scroll"):
            self.admin_list_scroll.viewport().update()
            QTimer.singleShot(0, lambda: self.admin_list_scroll.verticalScrollBar().setValue(0))


    def remove_admin_from_ui(self, ntid: str):
        """Remove admin from admins.txt and refresh the scroll list."""
        target = str(ntid).replace("(you)", "").strip().lower()
        if not target:
            self.append_system_log("Remove admin failed: missing NTID")
            return

        ok, message = self._remove_admin(target)
        if ok:
            actor = self.get_audit_actor()
            self.write_sas_log(
                "ADMIN REMOVED",
                actor=actor,
                details={"Admin": target.upper()},
            )
            self.append_system_log(f"Admin removed: {target.upper()}")
            self.refresh_admin_list_ui()

            # If current signed-in admin removed himself through an edge case,
            # downgrade role immediately.
            if self.current_user and target == self.current_user.lower():
                self.is_admin = False
                self.update_account_button()
        else:
            self.append_system_log(f"Remove admin failed: {target.upper()} - {message}")



    def add_admin_from_ui(self):
        ntid = self.admin_add_input.text().strip().lower() if hasattr(self, "admin_add_input") else ""
        if not ntid:
            self.append_system_log("Please enter NTID to add admin")
            return
        def worker():
            valid = self._validate_ntid_in_ad(ntid)
            def done():
                if not valid:
                    self.append_system_log(f"Invalid NTID or AD unreachable: {ntid}")
                    return
                self._save_admin(ntid)
                actor = self.get_audit_actor()
                self.write_sas_log(
                    "ADMIN ADDED",
                    actor=actor,
                    details={"Admin": ntid.upper()},
                )
                self.admin_add_input.clear()
                self.refresh_admin_list_ui()
                self.append_system_log(f"Admin added: {ntid.upper()}")
            self.qt_after(0, done)
        Thread(target=worker, daemon=True).start()


    def _validate_ntid_in_ad(self, ntid: str) -> bool:
        return self.ad_service.validate_ntid_in_ad(ntid)


    def _parse_ad_response(self, response: str) -> bool:
        return self.ad_service.parse_ad_response(response)


    def _read_credentials(self):
        return self.credential_service.read_credentials()


    def _encrypt_password(self, password: str):
        return self.ad_service.encrypt_password(password)


    def _validate_ntid_password_in_ad(self, ntid: str, password: str) -> bool:
        return self.ad_service.validate_ntid_password_in_ad(ntid, password)


    def _save_credentials(self, ntid, password, server, timeout, disable_keyboard=False, disable_mouse=False, disable_usb=False, enable_hotkey=True):
        if not getattr(self, "_settings_validation_passed", False):
            self.append_system_log("CREDENTIAL_SAVE_BLOCKED: strict validation was not completed.")
            return
        self._settings_validation_passed = False

        pi_host = self.pi_host_input.text().strip() if hasattr(self, "pi_host_input") else self.pi_api_host
        pi_port = "5000"
        auto_capture = False

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
            auto_capture=False,
            video_source="pi",
        )



    def browse_server_path(self):
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
        self,
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



    def show_missing_credentials_setup_popup_if_needed(self):
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



    def _locked_input_options_summary(self, disable_keyboard: bool, disable_mouse: bool, disable_usb: bool = False) -> str:
        """Describe exactly which input options are disabled while SAS is locked."""
        disabled = []
        if bool(disable_keyboard):
            disabled.append("Keyboard")
        if bool(disable_mouse):
            disabled.append("Mouse")
        if bool(disable_usb):
            disabled.append("USB")
        return ", ".join(disabled) if disabled else "None"


    def apply_timeout_to_countdown(self, reset: bool = False):
        self.total_seconds = max(1, int(self.lock_timeout_seconds))
        if reset:
            self._last_user_activity_ts = time.monotonic()
            self._countdown_activity_anchor_ts = self._last_user_activity_ts
            self._last_windows_input_tick = self.get_windows_last_input_tick() if hasattr(self, "get_windows_last_input_tick") else None
            self.time_left = self.total_seconds
        if hasattr(self, "ring"):
            self.ring.set_total_seconds(self.total_seconds)
            self.ring.set_time_left(self.time_left, animate=False)
        if hasattr(self, "countdown_label"):
            mins = self.time_left // 60
            secs = self.time_left % 60
            self.countdown_label.setText(f"{mins:02d}:{secs:02d}")
        if reset and hasattr(self, "count_timer") and self.count_timer is not None:
            try:
                self.count_timer.start(1000)
            except Exception:
                pass


    def apply_security_options_runtime(self):
        """Apply saved security option flags using runtime_lock_service."""
        self.append_system_log(
            "Security options applied: "
            f"keyboard={self.disable_keyboard_when_locked}, "
            f"mouse={self.disable_mouse_when_locked}, "
            f"usb={self.disable_usb_when_locked}, "
            f"hotkey={self.enable_hotkey}"
        )
        self.runtime_lock_service.apply_security_options(self)



    def is_server_configured(self, creds: dict | None = None) -> bool:
        """Return True only when usable server credentials exist.

        On first EXE launch, credential.txt may not exist yet. In that case
        SAS should enter setup mode instead of starting lock/unlock services.
        """
        saved_creds = creds if creds is not None else self._read_credentials()
        creds_map = dict(saved_creds or {})
        ntid = str(creds_map.get("ntid", "") or "").strip()
        password = str(creds_map.get("password", "") or "").strip()
        server = str(creds_map.get("server", "") or "").strip()

        if not ntid or not password or not server:
            return False

        # C:\temp is only the built-in placeholder/default, not a real saved setup.
        if server.replace("/", "\\").rstrip("\\").lower() == str(SERVER_PATH).replace("/", "\\").rstrip("\\").lower():
            return False

        return True


    def enter_first_launch_setup_mode(self):
        """Safe startup mode for newly copied EXE / blank configuration.

        Behaviour:
        - Do not show a system-lock notification.
        - Do not depend on old SMB recognition_result.json polling.
        - Allow the first valid AD login to become Admin.
        - Keep Face Recognition blocked until Pi/server settings are configured.
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


    def exit_first_launch_setup_mode(self):
        """Leave setup mode after Save & Connect succeeds."""
        self.first_launch_setup_mode = False
        self.server_configured = True
        self._suppress_lock_notification = False
        self.append_system_log("FIRST_LAUNCH_SETUP: Configuration completed.")


    def load_settings_from_credentials(self):
        creds = dict(self._read_credentials() or {})
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
        self.auto_capture_enabled = False

        if self.pi_api_host:
            self.face_api_service.configure(self.pi_api_host, self.pi_api_port)
            self.configure_recognition_websocket(self.pi_api_host, self.pi_api_port, start=False)
            self.pi_api_base = f"http://{self.pi_api_host}:{self.pi_api_port}" if not str(self.pi_api_host).startswith("http") else str(self.pi_api_host).rstrip("/")
            self.camera_feed_url = f"{self.pi_api_base}/video-feed"
        else:
            self.pi_api_base = ""
            self.camera_feed_url = ""
            self.pi_connected = False
            self.pi_connection_checked = False
            self.configure_recognition_websocket("", self.pi_api_port, start=False)

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
                self.pi_host_input.setPlaceholderText("Enter Pi hostname or IP")
        if hasattr(self, "pi_identity_label"):
            self.pi_identity_label.setText("")
            self.pi_identity_label.setVisible(False)
        # Pi port is fixed to 5000, so no editable port field is shown.
        if hasattr(self, "auto_capture_toggle"):
            self.auto_capture_toggle.set_checked(self.auto_capture_enabled)
        if hasattr(self, "auto_capture_sync_label"):
            self.set_auto_capture_sync_status(
                f"●  Pi sync: {'Enabled' if self.auto_capture_enabled else 'Disabled'}",
                ok=True,
            )
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


    def discard_unsaved_settings_changes(self):
        """Discard Settings edits without breaking an existing Pi connection.

        v120 fixes two problems from the generic reload path:
        1. DON'T SAVE must restore the visible Settings form from credential.txt.
        2. If SAS is already connected to the same saved Pi host, reloading the
           form must not set pi_connected=False and cause a false Pi disconnect
           popup when the user opens Face Recognition.
        3. If Auto-Capture was preview-synced to the Pi, send the saved value
           back to the Pi after the local form is restored.
        """
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
                self.face_api_service.configure(self.pi_api_host, self.pi_api_port)
                self.configure_recognition_websocket(self.pi_api_host, self.pi_api_port, start=False)
                self.pi_api_base = (
                    f"http://{self.pi_api_host}:{self.pi_api_port}"
                    if not str(self.pi_api_host).startswith("http")
                    else str(self.pi_api_host).rstrip("/")
                )
                self.camera_feed_url = f"{self.pi_api_base}/video-feed"
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

            self.rollback_preview_synced_pi_settings_after_discard(saved_snapshot)
            self.refresh_settings_unsaved_baseline()
        finally:
            self._settings_discard_restore_in_progress = False



    def rollback_preview_synced_pi_settings_after_discard(self, saved_snapshot=None):
        """Send saved Settings values back to Pi after DON'T SAVE.

        Auto-Capture is preview-synced when the user clicks the segmented
        control.  If the user chooses DON'T SAVE, the Pi must be restored to the
        saved credential.txt state so SAS and Pi do not disagree.
        """
        if saved_snapshot is None:
            saved_snapshot = self.get_saved_settings_snapshot_for_save_prompt()

        if not bool(getattr(self, "pi_connected", False)):
            return
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            return

        ntid = str(saved_snapshot.get("ntid", "") or "").strip()
        password = str(saved_snapshot.get("password", "") or "")
        server = str(saved_snapshot.get("server", "") or "").strip()
        auto_capture = bool(saved_snapshot.get("auto_capture", False))

        if not (ntid and password and server):
            return

        try:
            self.sync_settings_to_pi_async(
                ntid,
                password,
                server,
                auto_capture,
                self.normalize_camera_rotation(getattr(self, "camera_rotation", 0)),
            )
            self.append_system_log(
                "UNSAVED_SETTINGS_DISCARDED: Pi Auto-Capture restored to saved state "
                f"({'Enabled' if auto_capture else 'Disabled'})."
            )
        except Exception as e:
            try:
                self.append_system_log(f"UNSAVED_SETTINGS_PI_ROLLBACK_ERROR: {e}")
            except Exception:
                pass



    def mark_settings_modified_by_user(self):
        """Mark Settings dirty only for real user interaction, not programmatic refresh."""
        if getattr(self, "_settings_programmatic_update", False):
            return
        if getattr(self, "_settings_save_prompt_active", False):
            return
        if not hasattr(self, "settings_page"):
            return
        self._settings_dirty_since_baseline = True


    def refresh_settings_unsaved_baseline(self):
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


    def _normalized_settings_snapshot_for_compare(self, snapshot):
        """Normalize snapshots so harmless case/spacing changes do not prompt."""
        snap = dict(snapshot or {})
        for key in ("ntid", "server", "pi_host", "pi_port", "video_source", "timeout"):
            if key in snap:
                snap[key] = str(snap.get(key, "") or "").strip()
        if "ntid" in snap:
            snap["ntid"] = snap["ntid"].lower()
        if "pi_host" in snap:
            snap["pi_host"] = snap["pi_host"].lower()
        for key in ("disable_keyboard", "disable_mouse", "disable_usb", "enable_hotkey", "auto_capture"):
            if key in snap:
                snap[key] = bool(snap.get(key))
        return snap


    def get_settings_ui_snapshot_for_save_prompt(self, fill_blank_sensitive: bool = True):
        """Return Settings UI values normalized for credential.txt comparison.

        Sensitive fields are normally cleared after load. A blank NTID/password
        field therefore means "keep the saved value" unless the user typed a new
        non-empty value.
        """
        creds = dict(self._read_credentials() or {})

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

        try:
            timeout_inputs = cast(dict[str, QLineEdit], getattr(self, "timeout_inputs", {}) or {})
            hours_input = timeout_inputs.get("hours")
            minutes_input = timeout_inputs.get("minutes")
            seconds_input = timeout_inputs.get("seconds")
            h = max(0, min(int(hours_input.text() if hours_input is not None else 0), 23))
            m = max(0, min(int(minutes_input.text() if minutes_input is not None else 0), 59))
            s = max(0, min(int(seconds_input.text() if seconds_input is not None else 0), 59))
            timeout = str(max(1, h * 3600 + m * 60 + s))
        except Exception:
            timeout = str(getattr(self, "lock_timeout_seconds", DEFAULT_LOCK_TIMEOUT_SECONDS))

        try:
            security_options = cast(dict[str, QCheckBox], getattr(self, "security_option_buttons", {}) or {})
            keyboard_option = security_options.get("disable_keyboard")
            disable_keyboard = bool(keyboard_option.isChecked()) if keyboard_option is not None else bool(getattr(self, "disable_keyboard_when_locked", False))
        except Exception:
            disable_keyboard = bool(getattr(self, "disable_keyboard_when_locked", False))
        try:
            security_options = cast(dict[str, QCheckBox], getattr(self, "security_option_buttons", {}) or {})
            mouse_option = security_options.get("disable_mouse")
            disable_mouse = bool(mouse_option.isChecked()) if mouse_option is not None else bool(getattr(self, "disable_mouse_when_locked", False))
        except Exception:
            disable_mouse = bool(getattr(self, "disable_mouse_when_locked", False))
        disable_usb = bool(getattr(self, "disable_usb_when_locked", False))
        enable_hotkey = True

        try:
            auto_capture = False
        except Exception:
            auto_capture = False

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
            "auto_capture": auto_capture,
            "video_source": "pi",
        }


    def get_saved_settings_snapshot_for_save_prompt(self):
        """Return credential.txt values normalized the same way as the UI snapshot."""
        creds = dict(self._read_credentials() or {})

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
            "auto_capture": as_bool(creds.get("auto_capture"), False),
            "video_source": "pi",
        }


    def has_unsaved_settings_changes(self) -> bool:
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




    def close_guidelines_dialog_if_open(self):
        """Close the Guidelines modal before urgent Pi-disconnect popups.

        The Guidelines window is modal. If a Pi-disconnect alert appears while
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
                            widget.accept()
                        else:
                            widget.close()
                    except Exception:
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

        if closed:
            try:
                QApplication.processEvents()
            except Exception:
                pass
        return closed


    def show_guidelines_dialog(self):
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
                "description": "Configure the Pi hostname, server path, and connection settings before enabling recognition in daily operation.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_4.png"),
                "description": "Verify Pi connection status and confirm the SAS dashboard is connected to the correct Raspberry Pi device.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_5.png"),
                "description": "Use Capture to collect face images for the required user before running the training process.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_6.png"),
                "description": "Maintain a clear audit trail for system changes, login events, connection events, and access activity.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_7.png"),
                "description": "Train the recognition model after new face images are captured so the Pi can identify the authorized user.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_8.png"),
                "description": "Review received face data carefully before accepting or rejecting transferred enrolment records.",
            },
            {
                "image": app_resource_path("assets", "guideline_step_9.png"),
                "description": "Monitor Pi storage and network status to prevent recognition or transfer failures during production use.",
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
                "description": "Complete setup by confirming workstation lock, Pi connection, camera preview, and recognition unlock behavior.",
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
                widget = item.widget()
                if widget:
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


    def show_unsaved_settings_dialog(self) -> str:
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


    def maybe_prompt_unsaved_settings_before_leave(self, continue_callback=None, context: str = "leave-settings") -> bool:
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
            # same saved Pi host and restore preview-synced Auto-Capture on Pi.
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


    def validate_server_path_for_settings(self, server: str):
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


    def validate_settings_credentials_strict(self, ntid: str, password: str, server: str):
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



    def set_save_connect_busy(self, busy: bool):
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
        self,
        ntid: str,
        password: str,
        server: str,
        auto_capture: bool,
        camera_rotation: int | None = None,
    ):
        """Sync Settings to Pi without blocking the UI.

        Save & Connect already validates NTID/password/server path in a worker.
        The Pi sync must also run in a worker because HTTP requests to the Pi
        can take several seconds or time out if the Pi is offline.
        """
        auto_capture = False
        self.set_auto_capture_sync_status("●  Pi sync: Syncing...", ok=False)

        def worker():
            ok = self._face_api_sync_settings_to_pi(
                ntid, password, server, auto_capture, camera_rotation
            )

            def done():
                if ok:
                    self.set_auto_capture_sync_status(
                        f"●  Pi sync: {'Enabled' if auto_capture else 'Disabled'}",
                        ok=True,
                    )
                else:
                    self.set_auto_capture_sync_status("●  Pi sync: Failed", ok=False)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()



    def save_settings_from_ui(self, after_success=None, show_success_message: bool = True):
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

        auto_capture = False
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

                # Save the selected Pi host into runtime too.  If the user saved
                # a wrong hostname, SAS must keep that wrong hostname visible and
                # disconnected instead of reverting/reconnecting to the previous Pi.
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

                # Do not call the Pi API on the UI thread.
                # If Pi is slow/offline, this avoids "window not responding".
                if bool(getattr(self, "pi_connected", False)) and str(getattr(self, "pi_api_host", "") or "").strip():
                    self.sync_settings_to_pi_async(
                        ntid, password, server, False, camera_rotation
                    )
                else:
                    self.set_auto_capture_sync_status("●  Pi sync: Pi not connected", ok=False)

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
                    "Pi host": pi_host_detail,
                    "Inactivity lock": lock_time_detail,
                    "Disabled while locked": disabled_detail,
                    "Auto capture": "Disabled",
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




    def set_auto_capture_sync_status(self, text: str, ok: bool = False):
        """Auto-Capture sync status is no longer shown in the UI."""
        return



    def coerce_bool(self, value, default=False) -> bool:
        """Parse bool from Pi/SAS JSON safely."""
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




    def remember_session_credentials_after_save(self, ntid: str, password: str, server: str):
        """Keep credentials visible only during the current logged-in session."""
        self._session_settings_ntid = (ntid or "").strip()
        self._session_settings_password = password or ""
        self._session_settings_server = (server or "").strip()


    def apply_session_credentials_to_settings_ui(self):
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


    def clear_session_credentials_on_logout(self):
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


    def clear_sensitive_server_credentials_ui(self, clear_server_path: bool = False):
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



    def pull_pi_settings_to_sas(self, silent: bool = True):
        """Read non-sensitive Pi settings only.

        Security: do not auto-fill Server Credentials from the Pi API.
        Another user may start SAS on the same workstation, so NTID/password/
        server path must not appear just because Pi /settings returned them.
        """
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("PI_SKIPPED: Pi hostname/IP is not configured.")
            return

        def worker():
            try:
                data = self._face_api_request("GET", "/settings", timeout=10)

                def done():
                    old_programmatic = getattr(self, "_settings_programmatic_update", False)
                    self._settings_programmatic_update = True
                    try:
                        if isinstance(data, dict):
                            nested = data.get("settings", {})
                            if not isinstance(nested, dict):
                                nested = {}

                            # Non-sensitive setting only: auto_capture.
                            auto_capture = data.get("auto_capture", nested.get("auto_capture"))
                            if auto_capture is not None and hasattr(self, "auto_capture_toggle"):
                                self.auto_capture_enabled = bool(auto_capture)
                                self.auto_capture_toggle.set_enabled(self.auto_capture_enabled)

                            # Camera rotation is also non-sensitive. It is stored on
                            # the Pi so its local preview and SAS camera feed agree.
                            rotation = data.get("camera_rotation", nested.get("camera_rotation"))
                            if rotation is not None:
                                self.update_camera_rotation_ui(
                                    rotation,
                                    status=f"●  Pi setting: {self.camera_rotation_label(rotation)}",
                                    ok=True,
                                )

                        # Never show credentials fetched from Pi.
                        self.clear_sensitive_server_credentials_ui(clear_server_path=False)

                        if not silent:
                            self.append_system_log("Pi settings pulled securely. Server credentials were not displayed.")
                    except Exception as e:
                        self.append_system_log(f"Pi settings UI update skipped: {e}")
                    finally:
                        self._settings_programmatic_update = old_programmatic
                        if not getattr(self, "_settings_dirty_since_baseline", False):
                            self.refresh_settings_unsaved_baseline()

                self.qt_after(0, done)
            except Exception as e:
                def failed(err=e):
                    if not silent:
                        self.append_system_log(f"Unable to pull Pi settings: {err}")
                self.qt_after(0, failed)

        Thread(target=worker, daemon=True).start()



    def pull_auto_capture_setting_from_pi(self, silent: bool = True):
        """Backward-compatible wrapper. Now pulls full Pi settings."""
        self.pull_pi_settings_to_sas(silent=silent)




    def get_saved_server_credentials(self):
        """Read NTID/password/server path from the Settings page first, then credential.txt."""
        creds = dict(self._read_credentials() or {})

        ntid = self.settings_ntid_input.text().strip() if hasattr(self, "settings_ntid_input") else creds.get("ntid", "")
        password = self.settings_password_input.text().strip() if hasattr(self, "settings_password_input") else creds.get("password", "")
        server = self.settings_server_path_input.text().strip() if hasattr(self, "settings_server_path_input") else creds.get("server", self.server_path)

        if not ntid:
            ntid = creds.get("ntid", "")
        if not password:
            password = creds.get("password", "")
        if not server:
            server = creds.get("server", self.server_path)

        return ntid, password, server


    def validate_transfer_inputs(self, ntid: str, password: str, server: str, status_label=None) -> bool:
        """Validate transfer fields before export/import server action."""
        if not ntid.strip():
            if status_label is not None:
                self.set_transfer_status(status_label, "NTID / Username is required.", "error")
            return False

        if not password.strip():
            if status_label is not None:
                self.set_transfer_status(status_label, "Password is required.", "error")
            return False

        if not server.strip():
            if status_label is not None:
                self.set_transfer_status(status_label, "Server Path is required.", "error")
            return False

        if not (server.startswith("//") or server.startswith("\\") or ":" in server):
            if status_label is not None:
                self.set_transfer_status(status_label, "Server Path looks invalid. Please browse/select or enter a valid path.", "error")
            return False

        return True



    def set_transfer_status(self, label, text: str, state: str = "normal"):
        """Set Import/Export popup status colour."""
        if label is None:
            return

        label.setText(text)

        if state == "success":
            label.setObjectName("TransferStatusSuccess")
        elif state == "error":
            label.setObjectName("TransferStatusError")
        else:
            label.setObjectName("TransferStatus")

        label.style().unpolish(label)
        label.style().polish(label)
        label.update()


    def start_transfer_button_loading(self, button, base_text: str):
        """Animate a loading icon inside a transfer button."""
        self.stop_transfer_button_loading(button)

        button.setEnabled(False)
        button._transfer_base_text = base_text
        button._transfer_spinner_index = 0
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        timer = QTimer(button)

        def tick():
            frame = frames[button._transfer_spinner_index % len(frames)]
            button._transfer_spinner_index += 1
            button.setText(f"{frame}  {base_text}")

        timer.timeout.connect(tick)
        timer.start(90)
        button._transfer_loading_timer = timer
        tick()



    def stop_transfer_button_loading(self, button):
        timer = getattr(button, "_transfer_loading_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        button._transfer_loading_timer = None


    def show_transfer_button_success(self, button, success_text: str, normal_text: str):
        """Show tick icon briefly, then return button to normal."""
        self.stop_transfer_button_loading(button)
        button.setEnabled(False)
        button.setText(f"✓  {success_text}")

        def restore():
            button.setText(normal_text)
            button.setEnabled(True)

        QTimer.singleShot(1300, restore)



    def show_transfer_button_failed(self, button, normal_text: str):
        """Return failed button to normal state."""
        self.stop_transfer_button_loading(button)
        button.setText(normal_text)
        button.setEnabled(True)



    def on_auto_capture_toggle_changed(self, enabled: bool):
        """Handle user Auto-Capture changes without committing credential.txt.

        v120: The Auto-Capture toggle may sync to the Pi immediately so the Pi
        reflects the visible Settings state, but the change is still considered
        unsaved until the user presses Save.  If the user chooses DON'T SAVE,
        SAS reloads credential.txt and sends the saved Auto-Capture state back
        to the Pi.
        """
        self.auto_capture_enabled = bool(enabled)
        self.mark_settings_modified_by_user()

        if getattr(self, "_settings_programmatic_update", False):
            return
        if getattr(self, "_settings_discard_restore_in_progress", False):
            return

        self.set_auto_capture_sync_status("●  Pi sync: Auto syncing...", ok=False)

        # Do not save credential.txt here. Save must remain the only local
        # commit point for Settings changes.  This keeps DON'T SAVE able to
        # restore the previous local value.
        ntid, password, server = self.get_saved_server_credentials()
        if (
            ntid
            and password
            and server
            and str(getattr(self, "pi_api_host", "") or "").strip()
            and bool(getattr(self, "pi_connected", False))
        ):
            self.sync_auto_capture_setting_now()
        else:
            self.set_auto_capture_sync_status("●  Pi sync: Save required", ok=False)


    def sync_auto_capture_setting_now(self):
        """Auto-sync the Auto-Capture state to Pi using the same /settings endpoint.

        The Pi service stores auto_capture in settings.json and uses it as
        self.auto_capture_enabled, while registration receives the requested capture mode.
        """
        auto_capture = False
        ntid, password, server = self.get_saved_server_credentials()

        if not ntid or not password or not server:
            self.set_auto_capture_sync_status("●  Pi sync: Save required", ok=False)
            self.append_face_log("AUTO_CAPTURE_SYNC_FAILED: Server credentials are missing.")
            return

        self.set_auto_capture_sync_status("●  Pi sync: Syncing...", ok=False)

        def worker():
            ok = self._face_api_sync_settings_to_pi(
                ntid, password, server, auto_capture, self.camera_rotation
            )

            def done():
                if ok:
                    state = "Enabled" if auto_capture else "Disabled"
                    self.set_auto_capture_sync_status(f"●  Pi sync: {state}", ok=True)
                    self.append_face_log(f"AUTO_CAPTURE_SYNCED: {state}")
                else:
                    self.set_auto_capture_sync_status("●  Pi sync: Failed", ok=False)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()


    def _face_api_sync_settings_to_pi(
        self,
        ntid: str,
        password: str,
        server: str,
        auto_capture: bool,
        camera_rotation: int | None = None,
    ):
        """Sync Windows SAS Settings page to the Pi settings.json.

        This method may run in a worker thread. Any UI updates are scheduled
        through qt_after to keep the Qt UI responsive and thread-safe.
        """
        try:
            rotation = self.normalize_camera_rotation(
                getattr(self, "camera_rotation", 0) if camera_rotation is None else camera_rotation
            )
            payload = {
                "username": ntid,
                "password": password,
                "pc_save_path": server,
                "auto_capture": False,
                "camera_rotation": rotation,
                "unlock_transport": "websocket",
                "source": "Windows SAS",
            }

            data = self._face_api_request(
                "POST",
                "/settings",
                payload,
                timeout=45,
            )

            state = "Disabled"
            message = data.get("message", "settings saved")

            def ui_done():
                self.auto_capture_enabled = False
                returned_settings = data.get("settings", {}) if isinstance(data, dict) else {}
                applied_rotation = self.normalize_camera_rotation(
                    data.get("camera_rotation", returned_settings.get("camera_rotation", rotation))
                    if isinstance(data, dict) else rotation,
                    default=rotation,
                )
                self.update_camera_rotation_ui(
                    applied_rotation,
                    status=f"●  Pi synced: {self.camera_rotation_label(applied_rotation)}",
                    ok=True,
                )

                if hasattr(self, "auto_capture_toggle"):
                    self.auto_capture_toggle.set_checked(False)

                self.append_face_log(
                    f"PI_SETTINGS_SYNC: {message} | "
                    f"AUTO_CAPTURE={state} | CAMERA_ROTATION={applied_rotation} | "
                    "UNLOCK_TRANSPORT=websocket"
                )

            self.qt_after(0, ui_done)
            return True

        except Exception as e:
            err = str(e)
            self.qt_after(0, lambda err=err: self.append_face_log(f"PI_SETTINGS_SYNC_FAILED: {err}"))
            return False



    def _face_api_load_logs(self):
        def worker():
            try:
                data = self._face_api_request("GET", "/logs", timeout=20)
                logs = data.get("logs", [])
                if logs:
                    def done():
                        self._system_log_lines = []
                        for line in logs[-8:]:
                            self.append_face_log(str(line))
                    self.qt_after(0, done)
            except Exception as e:
                self.qt_after(0, lambda: self.append_face_log(f"LOG_SYNC_FAILED: {e}"))

        Thread(target=worker, daemon=True).start()

