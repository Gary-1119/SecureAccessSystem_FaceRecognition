from __future__ import annotations

from typing import Any, cast

from threading import Thread

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QFrame, QGraphicsBlurEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app_config import *
from dialogs import *
from ui_components import *
from services.atomic_file import atomic_write_text


class AuthControllerMixin:
    def has_restricted_tab_access(self: Any) -> bool:
        """Return True only for an authenticated SAS Admin session.

        Unlocking the Windows desktop by face recognition or by the emergency
        hotkey is not an SAS Admin login.  Settings and Face Recognition stay
        protected until an Admin completes the normal login flow.
        """
        return bool(getattr(self, "is_admin", False))

    def require_admin_for_tab(self: Any, tab_name: str) -> bool:
        """Return True when access is allowed.

        Face Recognition and Settings are restricted to Admin login.
        """
        restricted_tabs = {"Face Recognition", "Settings"}

        if tab_name not in restricted_tabs:
            return True

        if self.has_restricted_tab_access():
            return True

        self.pending_restricted_tab = tab_name

        # Keep user on current allowed page.
        if hasattr(self, "top_nav_buttons"):
            current_name = getattr(self, "current_top_tab", "Dashboard")
            for btn_name, btn in self.top_nav_buttons.items():
                btn.set_active(btn_name == current_name)
            if current_name in self.top_nav_buttons:
                self.animate_tab_indicator(current_name, animate=True)

        self.append_system_log(
            f"Restricted tab requested: {tab_name}. Admin login required."
        )

        # Non-admin user should switch account; guest should login.
        self.open_login_popup()
        return False

    def open_pending_restricted_tab_if_allowed(self: Any):
        """After successful login, open the requested restricted tab only if allowed."""
        tab_name = getattr(self, "pending_restricted_tab", None)

        if not tab_name:
            return

        if self.has_restricted_tab_access():
            self.pending_restricted_tab = None
            self.qt_after(250, lambda: self.switch_top_tab(tab_name))
        else:
            self.append_system_log(
                f"Access denied for {tab_name}: Admin role required."
            )
            self.pending_restricted_tab = None

    def open_login_popup(self: Any):
        """Blur the current dashboard and show the login popup."""
        root = self.centralWidget()
        if root is None:
            return

        self._login_popup_active = True

        # Build the popup first.  If its UI construction ever fails, do not
        # leave the dashboard blurred without a visible dialog.
        try:
            dialog = LoginPopupDialog(self, self.compact_mode)
        except Exception as exc:
            self.append_system_log(f"LOGIN_POPUP_ERROR: {exc}")
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
        self.pause_camera_for_modal()
        try:
            dialog.exec()
        finally:
            self._login_popup_active = False
            self.resume_camera_after_modal()
            if getattr(self, "is_logged_in", False):
                QTimer.singleShot(250, self.run_post_login_pi_connection_check)

    def handle_login_button_clicked(self: Any):
        """Login button behaviour.

        - Guest: open login popup
        - Logged in: show account dropdown
        """
        if self.current_user:
            self.append_system_log(f"Account menu opened for {self.current_user.upper()}")
            self.toggle_account_menu()
        else:
            self.open_login_popup()

    def build_account_menu(self: Any):
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

    def get_account_menu_target_geometry(self: Any):
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

    def position_account_menu(self: Any):
        if not hasattr(self, "account_menu"):
            return

        target = self.get_account_menu_target_geometry()
        self.account_menu.setGeometry(target)
        self.account_menu.raise_()

    def toggle_account_menu(self: Any):
        if not hasattr(self, "account_menu"):
            return

        if self.account_menu.isVisible() and self.account_menu.maximumHeight() > 0:
            self.hide_account_menu()
        else:
            self.show_account_menu()

    def show_account_menu(self: Any):
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

        self.append_system_log(
            f"Account menu visible={self.account_menu.isVisible()} "
            f"geometry={self.account_menu.geometry().getRect()}"
        )

    def hide_account_menu(self: Any):
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

    def switch_account_flow(self: Any):
        """Switch account: keep current session until another login succeeds."""
        self.hide_account_menu()
        self.open_login_popup()

    def logout_flow(self: Any):
        self.clear_session_credentials_on_logout()
        """Complete logout flow and return to Dashboard page."""
        old_user = self.current_user.upper() if self.current_user else "Unknown"

        self.hide_account_menu()

        self.is_logged_in = False
        self.current_user = None
        self.clear_session_credentials_on_logout()
        self.current_user_role = "Guest"
        self.is_admin = False
        self.pending_restricted_tab = None

        self.update_account_ui()

        # After logout, always navigate back to Dashboard.
        self.switch_top_tab("Dashboard")

        # After logout, stay on the normal unlocked dashboard.
        # Auto-lock will only occur later through inactivity countdown.
        self.is_locked = False
        self._pending_auto_lock = False
        self.mark_user_activity(reset_countdown=True)
        self.apply_lock_state()

        self.set_face_detected(False)
        self.write_sas_log("LOGOUT", actor=old_user)
        self.append_system_log(f"Logged out: {old_user}")

    def mousePressEvent(self: Any, event):
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

        QMainWindow.mousePressEvent(cast(QMainWindow, self), event)

    def toggle_login_password(self: Any):
        if not hasattr(self, "login_password_input"):
            return

        if self.login_password_input.echoMode() == QLineEdit.EchoMode.Password:
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.login_toggle_btn.setText("Hide")
        else:
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.login_toggle_btn.setText("Show")

    def login_requested(self: Any):
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

    def build_login_page(self: Any):
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

    def _ensure_admin_file(self: Any):
        self.admin_service.ensure_admin_file()

    def _load_admins(self: Any):
        return self.admin_service.load_admins()

    def _save_admin(self: Any, ntid):
        self.admin_service.save_admin(ntid)

    def _remove_admin(self: Any, ntid):
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
        atomic_write_text(ADMIN_FILE, "".join(f"{admin}\n" for admin in admins), encoding="utf-8", keep_backup=True)
        return True, "Admin removed."

    def _check_admin_login(self: Any, ntid):
        return self.admin_service.check_admin_login(ntid)

    def refresh_admin_list_ui(self: Any):
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

    def remove_admin_from_ui(self: Any, ntid: str):
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

    def add_admin_from_ui(self: Any):
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

    def show_login_success_popup(self: Any, ntid: str, role: str):
        """Show premium success modal after NTID/password validation succeeds."""
        popup = LoginSuccessDialog(self, ntid=ntid, role=role, compact_mode=self.compact_mode)

        geo = self.geometry()
        x = geo.x() + (geo.width() - popup.width()) // 2
        y = geo.y() + (geo.height() - popup.height()) // 2
        popup.move(x, y)

        popup.exec()

    def login_debug(self: Any, message: str):
        """Debug helper for login validation flow."""
        line = f"[LOGIN DEBUG] {message}"
        print(line)
        if hasattr(self, "append_system_log"):
            self.append_system_log(line)

    def show_login_failed_popup(self: Any, reason: str, debug_text: str = ""):
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

    def _validate_ntid_password_in_ad_with_debug(self: Any, ntid: str, password: str):
        return self.ad_service.validate_ntid_password_with_debug(ntid, password)

    def _is_hardcoded_admin_login(self: Any, ntid: str, password: str) -> bool:
        """Return True for the built-in local admin login account."""
        configured_id = str(globals().get("HARDCODED_ADMIN_ID", "admin")).strip().lower()
        configured_password = str(globals().get("HARDCODED_ADMIN_PASSWORD", "penAteam"))
        return str(ntid).strip().lower() == configured_id and str(password) == configured_password

    def _handle_successful_login(
        self: Any,
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
            self.clear_session_credentials_on_logout()

        """Apply shared successful login state for AD and built-in admin login."""
        self.current_user = ntid.lower()
        self.is_admin = bool(is_admin)
        self.current_user_role = "Admin" if self.is_admin else "User"
        self.is_logged_in = True

        self.update_account_ui()
        self.refresh_admin_list_ui()

        success_debug = debug_text + f"\nAdmin role check: {role_msg}\nFinal login role: {self.current_user_role}"
        self.login_debug(f"Admin check result: {role_msg}")
        self.append_system_log(f"Login successful: {ntid.upper()} ({self.current_user_role})")
        self.write_sas_log(
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
        self.open_pending_restricted_tab_if_allowed()

    def _handle_login_from_popup(self: Any, ntid: str, password: str, dialog):
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
            self.qt_after(0, lambda: set_dialog_status("Checking NTID in Active Directory..."))
            valid, reason, debug_text = self._validate_ntid_password_in_ad_with_debug(ntid, password)

            def done():
                if not valid:
                    self.login_debug(f"Login failed: {reason}")
                    self.write_sas_log(
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

                is_admin, role_msg = self._check_admin_login(ntid)
                self._handle_successful_login(ntid, is_admin, role_msg, debug_text, dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True).start()

    def update_account_button(self: Any):
        """Compatibility wrapper for older calls."""
        self.update_account_ui()

    def update_account_ui(self: Any):
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
