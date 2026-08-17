from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class AuthControllerMixin(DashboardMixinBase):
    def _auth_call(self, method_name: str, *args, **kwargs) -> Any:
        method = getattr(self, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
        return None


    def _auth_append_system_log(self, message: str) -> None:
        self._auth_call("append_system_log", message)


    def _auth_write_sas_log(self, action: str, actor=None, details=None) -> None:
        self._auth_call("write_sas_log", action, actor=actor, details=details)


    def _auth_clear_session_credentials_on_logout(self) -> None:
        self._auth_call("clear_session_credentials_on_logout")


    def _auth_qt_after(self, ms: int, callback) -> None:
        runner = getattr(self, "qt_after", None)
        if callable(runner):
            runner(ms, callback)
            return
        QTimer.singleShot(ms, callback)


    def _auth_check_admin_login(self, ntid: str) -> tuple[bool, str]:
        checker = getattr(self, "_check_admin_login", None)
        if callable(checker):
            result = checker(ntid)
            if isinstance(result, tuple) and len(result) >= 2:
                return bool(result[0]), str(result[1])
            return False, "Admin check returned invalid result."
        return False, "Admin check unavailable."


    def clear_blur_effect(self, widget):
        """Clear blur effect safely with a smooth blur-out animation."""
        old_effect = widget.graphicsEffect()

        if old_effect is None:
            return

        self._blur_out_anim = QPropertyAnimation(old_effect, b"blurRadius", self)
        self._blur_out_anim.setDuration(180)
        self._blur_out_anim.setStartValue(10)
        self._blur_out_anim.setEndValue(0)
        self._blur_out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finish_clear():
            old_effect.setEnabled(False)
            old_effect.deleteLater()

        self._blur_out_anim.finished.connect(finish_clear)
        self._blur_out_anim.start()


    def open_login_popup(self):
        """Blur the current dashboard and show the login popup."""
        root = self.centralWidget()
        if root is None:
            return

        # Login must be the top modal. Close any connection/duplicate dialogs
        # first so two modal overlays cannot trap each other.
        try:
            closer = getattr(self, "close_connection_dialog_silently", None)
            if callable(closer):
                closer()
        except Exception:
            pass
        try:
            conflict = getattr(self, "_oneconnect_conflict_dialog", None)
            if conflict is not None:
                conflict.reject()
        except Exception:
            pass

        self._login_popup_active = True

        # Build the popup first.  If its UI construction ever fails, do not
        # leave the dashboard blurred without a visible dialog.
        try:
            dialog = LoginPopupDialog(self, self.compact_mode)
        except Exception as exc:
            self._auth_append_system_log(f"LOGIN_POPUP_ERROR: {exc}")
            print(f"[LOGIN POPUP ERROR] {exc}")
            return

        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(0)
        root.setGraphicsEffect(blur)

        # Smooth background blur.
        self._blur_anim = QPropertyAnimation(blur, b"blurRadius", self)
        self._blur_anim.setDuration(220)
        self._blur_anim.setStartValue(0)
        self._blur_anim.setEndValue(5)
        self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._blur_anim.start()

        # Centre popup relative to the main window.
        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        dialog.finished.connect(lambda _: self.clear_blur_effect(root))
        self._auth_call("pause_camera_for_modal")
        try:
            dialog.exec()
        finally:
            self._login_popup_active = False
            self._auth_call("resume_camera_after_modal")
            if getattr(self, "is_logged_in", False):
                QTimer.singleShot(250, lambda: self._auth_call("run_post_login_pi_connection_check"))


    def handle_login_button_clicked(self):
        """Login button behaviour.

        - Guest: open login popup
        - Logged in: show account dropdown
        """
        if self.current_user:
            self._auth_append_system_log(f"Account menu opened for {self.current_user.upper()}")
            self.toggle_account_menu()
        else:
            self.open_login_popup()


    def build_account_menu(self):
        """Animated dropdown menu shown when the logged-in NTID button is pressed."""
        self.account_menu = QFrame(self.centralWidget() if self.centralWidget() is not None else self)
        self.account_menu.setObjectName("AccountDropdown")
        self.account_menu.setFixedWidth(190 if not self.compact_mode else 170)
        self.account_menu.resize(190 if not self.compact_mode else 170, 0)
        self.account_menu.hide()

        self.account_menu_effect = QGraphicsOpacityEffect(self.account_menu)
        self.account_menu_effect.setOpacity(0.0)
        self.account_menu.setGraphicsEffect(self.account_menu_effect)

        menu_layout = QVBoxLayout(self.account_menu)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(6)

        self.account_menu_title = QLabel("SIGNED IN")
        self.account_menu_title.setObjectName("AccountDropdownTitle")

        self.account_menu_user = QLabel("Guest")
        self.account_menu_user.setObjectName("AccountDropdownUser")

        switch_btn = QPushButton("Switch Account")
        switch_btn.setObjectName("AccountDropdownButton")
        switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        switch_btn.clicked.connect(self.switch_account_flow)

        logout_btn = QPushButton("Log Out")
        logout_btn.setObjectName("AccountDropdownDangerButton")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self.logout_flow)

        menu_layout.addWidget(self.account_menu_title)
        menu_layout.addWidget(self.account_menu_user)
        menu_layout.addWidget(switch_btn)
        menu_layout.addWidget(logout_btn)

        self.account_menu_height = 166 if not self.compact_mode else 148
        self.account_menu_anim = None
        self.account_menu_opacity_anim = None


    def get_account_menu_target_geometry(self):
        if not hasattr(self, "account_menu") or not hasattr(self, "login_btn"):
            return QRect(0, 0, 190 if not self.compact_mode else 170, self.account_menu_height)

        menu_w = 190 if not self.compact_mode else 170
        menu_h = self.account_menu_height

        parent_widget = self.account_menu.parentWidget()
        if parent_widget is None:
            parent_widget = self

        global_bottom_right = self.login_btn.mapToGlobal(QPoint(self.login_btn.width(), self.login_btn.height()))
        global_bottom_left = self.login_btn.mapToGlobal(QPoint(0, self.login_btn.height()))

        btn_bottom_right = parent_widget.mapFromGlobal(global_bottom_right)
        btn_bottom_left = parent_widget.mapFromGlobal(global_bottom_left)

        x = btn_bottom_right.x() - menu_w
        y = btn_bottom_left.y() + 8

        x = max(12, min(x, parent_widget.width() - menu_w - 12))
        y = max(12, y)

        return QRect(x, y, menu_w, menu_h)


    def position_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        target = self.get_account_menu_target_geometry()
        self.account_menu.setGeometry(target)
        self.account_menu.raise_()


    def toggle_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        if self.account_menu.isVisible() and self.account_menu.maximumHeight() > 0:
            self.hide_account_menu()
        else:
            self.show_account_menu()


    def show_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        if self.current_user:
            display_user = self.current_user.upper()
            role = self.current_user_role
            if display_user == "ADMIN":
                self.account_menu_user.setText("ADMIN")
            else:
                self.account_menu_user.setText(f"{display_user} • {role}")
        else:
            self.account_menu_user.setText("Guest")

        target = self.get_account_menu_target_geometry()
        start = QRect(target.x(), target.y(), target.width(), 0)

        self.account_menu.setEnabled(True)
        self.account_menu.setGeometry(start)
        self.account_menu.show()
        self.account_menu.raise_()

        if self.account_menu_anim is not None:
            self.account_menu_anim.stop()
        if self.account_menu_opacity_anim is not None:
            self.account_menu_opacity_anim.stop()

        self.account_menu_effect.setOpacity(0.0)

        self.account_menu_anim = QPropertyAnimation(self.account_menu, b"geometry", self)
        self.account_menu_anim.setDuration(220)
        self.account_menu_anim.setStartValue(start)
        self.account_menu_anim.setEndValue(target)
        self.account_menu_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.account_menu_opacity_anim = QPropertyAnimation(self.account_menu_effect, b"opacity", self)
        self.account_menu_opacity_anim.setDuration(180)
        self.account_menu_opacity_anim.setStartValue(0.0)
        self.account_menu_opacity_anim.setEndValue(1.0)
        self.account_menu_opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.account_menu_anim.start()
        self.account_menu_opacity_anim.start()

        self._auth_append_system_log(
            f"Account menu visible={self.account_menu.isVisible()} "
            f"geometry={self.account_menu.geometry().getRect()}"
        )


    def hide_account_menu(self):
        if not hasattr(self, "account_menu"):
            return

        if not self.account_menu.isVisible():
            return

        if self.account_menu_anim is not None:
            self.account_menu_anim.stop()
        if self.account_menu_opacity_anim is not None:
            self.account_menu_opacity_anim.stop()

        start = self.account_menu.geometry()
        end = QRect(start.x(), start.y(), start.width(), 0)

        self.account_menu_anim = QPropertyAnimation(self.account_menu, b"geometry", self)
        self.account_menu_anim.setDuration(180)
        self.account_menu_anim.setStartValue(start)
        self.account_menu_anim.setEndValue(end)
        self.account_menu_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        self.account_menu_opacity_anim = QPropertyAnimation(self.account_menu_effect, b"opacity", self)
        self.account_menu_opacity_anim.setDuration(150)
        self.account_menu_opacity_anim.setStartValue(self.account_menu_effect.opacity())
        self.account_menu_opacity_anim.setEndValue(0.0)
        self.account_menu_opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def after_hide():
            self.account_menu.hide()

        self.account_menu_anim.finished.connect(after_hide)
        self.account_menu_anim.start()
        self.account_menu_opacity_anim.start()


    def switch_account_flow(self):
        """Switch account: keep current session until another login succeeds."""
        self.hide_account_menu()
        self.open_login_popup()


    def logout_flow(self):
        self._auth_clear_session_credentials_on_logout()
        """Complete logout flow and return to Dashboard page."""
        old_user = self.current_user.upper() if self.current_user else "Unknown"

        self.hide_account_menu()

        self.is_logged_in = False
        self.current_user = None
        self._auth_clear_session_credentials_on_logout()
        self.current_user_role = "Guest"
        self.is_admin = False
        self.pending_restricted_tab = None

        self.update_account_ui()

        # After logout, always navigate back to Dashboard.
        self._auth_call("switch_top_tab", "Dashboard")

        # After logout, stay on the normal unlocked dashboard.
        # Auto-lock will only occur later through inactivity countdown.
        self.is_locked = False
        self._pending_auto_lock = False
        self._auth_call("mark_user_activity", reset_countdown=True)
        self._auth_call("apply_lock_state")

        self._auth_call("set_face_detected", False)
        self._auth_write_sas_log("LOGOUT", actor=old_user)
        self._auth_append_system_log(f"Logged out: {old_user}")


    def mousePressEvent(self, event):
        if hasattr(self, "account_menu") and self.account_menu.isVisible():
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

            # login_btn.geometry() is relative to its parent, not QMainWindow.
            # Convert it to main-window coordinates before checking.
            btn_top_left = self.login_btn.mapTo(self, QPoint(0, 0))
            btn_rect = QRect(
                btn_top_left.x(),
                btn_top_left.y(),
                self.login_btn.width(),
                self.login_btn.height()
            )

            clicked_menu = self.account_menu.geometry().contains(pos)
            clicked_login_button = btn_rect.contains(pos)

            if not clicked_menu and not clicked_login_button:
                self.hide_account_menu()

        base_mouse_press = getattr(super(), "mousePressEvent", None)
        if callable(base_mouse_press):
            base_mouse_press(event)


    # --------------------------------------------------------
    # Login helpers
    # --------------------------------------------------------

    def toggle_login_password(self):
        if not hasattr(self, "login_password_input"):
            return

        if self.login_password_input.echoMode() == QLineEdit.EchoMode.Password:
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.login_toggle_btn.setText("Hide")
        else:
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.login_toggle_btn.setText("Show")


    def login_requested(self):
        ntid = self.login_ntid_input.text().strip() if hasattr(self, "login_ntid_input") else ""
        password = self.login_password_input.text().strip() if hasattr(self, "login_password_input") else ""

        if not ntid:
            self.login_status_label.setText("Please enter your NTID.")
            self.login_ntid_input.setFocus()
            return

        if not password:
            self.login_status_label.setText("Please enter your password.")
            self.login_password_input.setFocus()
            return

        # Temporary only. Later connect this to your SOAP / AD validation.
        self.login_status_label.setText(f"Authentication requested for NTID: {ntid}")

    # --------------------------------------------------------
    # Pages
    # --------------------------------------------------------

    def login_debug(self, message: str):
        """Debug helper for login validation flow."""
        line = f"[LOGIN DEBUG] {message}"
        print(line)
        if hasattr(self, "append_system_log"):
            self._auth_append_system_log(line)


    def show_login_failed_popup(self, reason: str, debug_text: str = ""):
        """Show premium failure modal for invalid login or AD/SOAP errors."""
        popup = LoginFailedDialog(
            self,
            reason=reason,
            debug_text=debug_text,
            compact_mode=self.compact_mode
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - popup.width()) // 2
        y = geo.y() + (geo.height() - popup.height()) // 2
        popup.move(x, y)

        popup.exec()


    def _validate_ntid_password_in_ad_with_debug(self, ntid: str, password: str):
        return self.ad_service.validate_ntid_password_with_debug(ntid, password)


    def _is_hardcoded_admin_login(self, ntid: str, password: str) -> bool:
        """Return True for the built-in local admin login account."""
        configured_id = str(globals().get("HARDCODED_ADMIN_ID", "admin")).strip().lower()
        configured_password = str(globals().get("HARDCODED_ADMIN_PASSWORD", "penAteam"))
        return str(ntid).strip().lower() == configured_id and str(password) == configured_password


    def _handle_successful_login(
        self,
        ntid: str,
        is_admin: bool,
        role_msg: str,
        debug_text: str,
        dialog,
        login_method: str = "ACTIVE_DIRECTORY",
    ):
        previous_user_for_credentials = str(getattr(self, "current_user", "") or "").strip().lower()
        incoming_user_for_credentials = str(ntid or "").strip().lower()
        if previous_user_for_credentials and previous_user_for_credentials != incoming_user_for_credentials:
            self._auth_clear_session_credentials_on_logout()

        """Apply shared successful login state for AD and built-in admin login."""
        self.current_user = ntid.lower()
        self.is_admin = bool(is_admin)
        self.current_user_role = "Admin" if self.is_admin else "User"
        self.is_logged_in = True

        self.update_account_ui()
        self._auth_call("refresh_admin_list_ui")

        success_debug = debug_text + f"\nAdmin role check: {role_msg}\nFinal login role: {self.current_user_role}"
        self.login_debug(f"Admin check result: {role_msg}")
        self._auth_append_system_log(f"Login successful: {ntid.upper()} ({self.current_user_role})")
        self._auth_write_sas_log(
            "LOGIN SUCCESS",
            actor=ntid.upper(),
            details={
                "Role": self.current_user_role,
                "Method": login_method,
            },
        )

        self.login_debug("Validation success. Switching login popup to success state.")
        dialog.show_success_state(ntid, self.current_user_role, success_debug)

        # If login was requested because user clicked Face Recognition / Settings,
        # open it only after Admin validation succeeds.
        self._auth_call("open_pending_restricted_tab_if_allowed")


    def _handle_login_from_popup(self, ntid: str, password: str, dialog):
        dialog.set_validation_state("Starting login validation...")
        self.login_debug("Login button clicked.")
        self.login_debug(f"Received NTID from login popup: {ntid}")

        # Built-in local admin fallback. This account bypasses AD validation and
        # always receives Admin role. The login ID/password are configurable from
        # app_config.py / environment variables.
        if self._is_hardcoded_admin_login(ntid, password):
            debug_text = (
                "Built-in local admin login matched.\n"
                "Active Directory validation skipped for this fallback account."
            )
            self.login_debug("Built-in local admin login accepted.")
            self._handle_successful_login(
                "admin",
                True,
                "Built-in local Admin login successful.",
                debug_text,
                dialog,
                login_method="BUILT_IN_LOCAL_ADMIN",
            )
            return

        def set_dialog_status(message: str):
            if dialog is not None:
                dialog.set_validation_message(message)

        def worker():
            self._auth_qt_after(0, lambda: set_dialog_status("Checking NTID in Active Directory..."))
            valid, reason, debug_text = self._validate_ntid_password_in_ad_with_debug(ntid, password)

            def done():
                if not valid:
                    self.login_debug(f"Login failed: {reason}")
                    self._auth_write_sas_log(
                        "LOGIN FAILED",
                        actor=str(ntid).strip().upper() or "UNKNOWN",
                        details={
                            "Method": "ACTIVE_DIRECTORY",
                            "Result": "Failed",
                        },
                    )
                    user_reason = "Invalid NTID or password. Please check your credentials and try again."
                    dialog.show_failed_state(user_reason, debug_text)
                    return

                is_admin, role_msg = self._auth_check_admin_login(ntid)
                self._handle_successful_login(ntid, is_admin, role_msg, debug_text, dialog)

            self._auth_qt_after(0, done)

        Thread(target=worker, daemon=True).start()


    def update_account_button(self):
        """Compatibility wrapper for older calls."""
        self.update_account_ui()


    def update_account_ui(self):
        if hasattr(self, "login_btn"):
            if self.current_user:
                display_user = self.current_user.upper()
                display_role = self.current_user_role

                self.login_btn.setText(f"{display_user} ▾")
                self.login_btn.setFixedWidth(122 if not self.compact_mode else 104)

                if display_user == "ADMIN":
                    self.login_btn.setToolTip("Logged in as ADMIN")
                else:
                    self.login_btn.setToolTip(f"Logged in as {display_user} ({display_role})")
                self.login_btn.setObjectName("LoginButtonLoggedIn")
            else:
                self.login_btn.setText("Login")
                self.login_btn.setToolTip("")
                self.login_btn.setObjectName("LoginButton")
                self.login_btn.setFixedWidth(96 if not self.compact_mode else 82)

            self.login_btn.style().unpolish(self.login_btn)
            self.login_btn.style().polish(self.login_btn)
            self.login_btn.update()


