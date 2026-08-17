from __future__ import annotations

import os
from threading import Thread
from typing import Any, cast

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
    QLineEdit,
    QFileDialog,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsEffect,
)

from dialogs import DeleteCompleteDialog
from ui_components import ExportCircleSpinnerWidget, TransferSnakeTabs


class FaceDataTransferMixin:
    def get_saved_server_credentials(self: Any):
        """Read NTID/password/server path from the Settings page first, then credential.txt."""
        creds = self._read_credentials()

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

    def validate_transfer_inputs(self: Any, ntid: str, password: str, server: str, status_label=None) -> bool:
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


    def set_transfer_status(self: Any, label, text: str, state: str = "normal"):
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

    def start_transfer_button_loading(self: Any, button, base_text: str):
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


    def stop_transfer_button_loading(self: Any, button):
        timer = getattr(button, "_transfer_loading_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        button._transfer_loading_timer = None

    def show_transfer_button_success(self: Any, button, success_text: str, normal_text: str):
        """Show tick icon briefly, then return button to normal."""
        self.stop_transfer_button_loading(button)
        button.setEnabled(False)
        button.setText(f"✓  {success_text}")

        def restore():
            button.setText(normal_text)
            button.setEnabled(True)

        QTimer.singleShot(1300, restore)


    def show_transfer_button_failed(self: Any, button, normal_text: str):
        """Return failed button to normal state."""
        self.stop_transfer_button_loading(button)
        button.setText(normal_text)
        button.setEnabled(True)


    def _local_face_sync_settings(
        self: Any,
        ntid: str,
        password: str,
        server: str,
        camera_rotation: int | None = None,
    ):
        """Sync Windows SAS Settings to the local recognition adapter."""
        try:
            rotation = self.normalize_camera_rotation(
                getattr(self, "camera_rotation", 0) if camera_rotation is None else camera_rotation
            )
            payload = {
                "username": ntid,
                "password": password,
                "pc_save_path": server,
                "camera_rotation": rotation,
                "unlock_transport": "local",
                "source": "Windows SAS",
            }

            data = self._local_face_request(
                "POST",
                "/settings",
                payload,
                timeout=45,
            )
            message = data.get("message", "settings saved") if isinstance(data, dict) else "settings saved"

            def ui_done():
                returned_settings = data.get("settings", {}) if isinstance(data, dict) else {}
                applied_rotation = self.normalize_camera_rotation(
                    data.get("camera_rotation", returned_settings.get("camera_rotation", rotation))
                    if isinstance(data, dict) else rotation,
                    default=rotation,
                )
                self.update_camera_rotation_ui(
                    applied_rotation,
                    status=f"●  Local setting: {self.camera_rotation_label(applied_rotation)}",
                    ok=True,
                )
                self.append_face_log(
                    f"LOCAL_SETTINGS_SYNC: {message} | CAMERA_ROTATION={applied_rotation} | "
                    "UNLOCK_TRANSPORT=local"
                )

            self.qt_after(0, ui_done)
            return True

        except Exception as e:
            err = str(e)
            self.qt_after(0, lambda err=err: self.append_face_log(f"LOCAL_SETTINGS_SYNC_FAILED: {err}"))
            return False

    def _local_face_load_logs(self: Any):
        def worker():
            try:
                data = self._local_face_request("GET", "/logs", timeout=20)
                logs = data.get("logs", [])
                if logs:
                    def done():
                        latest = [str(line) for line in logs[-8:]]
                        if latest == getattr(self, "_last_local_face_log_lines", []):
                            return
                        self._last_local_face_log_lines = latest
                        for line in latest:
                            self.append_face_log(f"LOCAL_LOG: {line}")
                    self.qt_after(0, done)
            except Exception as e:
                self.qt_after(0, lambda: self.append_face_log(f"LOG_SYNC_FAILED: {e}"))

        Thread(target=worker, daemon=True).start()

    def clear_transfer_text_selection(self: Any, dialog=None):
        """Prevent NTID / path fields from staying highlighted after button clicks."""
        target = dialog or getattr(self, "active_transfer_dialog", None)
        if target is None:
            return

        try:
            for edit in target.findChildren(QLineEdit):
                edit.deselect()
                edit.setCursorPosition(len(edit.text()))
                edit.clearFocus()
        except Exception:
            pass

    def _force_clear_card_dialog_background(self: Any, force: bool = False):
        """Restore the dashboard after all frameless card popups are closed.

        Multiple card dialogs can overlap.  For example, the user can keep the
        import/export card open while another card appears.
        In that situation closing one card must not clear the blur/dim layer
        for the other card, and closing the last card must clear every leftover
        dim overlay.  The open-count guard prevents stale dark backgrounds.
        """
        if not force and int(getattr(self, "_card_dialog_open_count", 0) or 0) > 0:
            return

        try:
            self._card_dialog_open_count = 0
        except Exception:
            pass

        # Remove every tracked dim overlay.
        overlays = list(getattr(self, "_card_dialog_dim_overlays", []) or [])
        overlay = getattr(self, "_transfer_dim_overlay", None)
        if overlay is not None and overlay not in overlays:
            overlays.append(overlay)
        for overlay in overlays:
            try:
                overlay.hide()
                overlay.deleteLater()
            except Exception:
                pass
        try:
            self._card_dialog_dim_overlays = []
            self._transfer_dim_overlay = None
        except Exception:
            pass

        # Remove any orphan dim overlays that were created before the current
        # tracked-list logic or by a dialog that closed out of order.
        try:
            for orphan in self.findChildren(QFrame, "DialogDimOverlay"):
                try:
                    orphan.hide()
                    orphan.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass

        root = self.centralWidget()
        if root is not None:
            try:
                root.setEnabled(True)
            except Exception:
                pass
            try:
                effect = root.graphicsEffect()
                if effect is not None:
                    root.setGraphicsEffect(cast(QGraphicsEffect, None))
                    effect.deleteLater()
            except Exception:
                try:
                    root.setGraphicsEffect(cast(QGraphicsEffect, None))
                except Exception:
                    pass

    def _show_card_dialog(self: Any, dialog: QDialog):
        """Show a frameless card popup with shared blurred/disabled background."""
        root = self.centralWidget()
        already_open = int(getattr(self, "_card_dialog_open_count", 0) or 0) > 0
        self._card_dialog_open_count = int(getattr(self, "_card_dialog_open_count", 0) or 0) + 1

        if root is not None:
            try:
                root.setEnabled(False)
            except Exception:
                pass

            # Only create the blur/dim layer for the first active card.  If a
            # second card opens while the first one is still active, it shares
            # the same layer.  This fixes the stuck-dark dashboard after closing
            # overlapping import/export popups.
            if not already_open:
                try:
                    blur = QGraphicsBlurEffect(self)
                    blur.setBlurRadius(0)
                    root.setGraphicsEffect(blur)
                    anim = QPropertyAnimation(blur, b"blurRadius", self)
                    anim.setDuration(220)
                    anim.setStartValue(0)
                    anim.setEndValue(5)
                    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    self._transfer_blur_anim = anim
                    anim.start()
                except Exception:
                    pass
                try:
                    dim_overlay = QFrame(self)
                    dim_overlay.setObjectName("DialogDimOverlay")
                    dim_overlay.setStyleSheet("background: rgba(0, 0, 0, 42); border: none;")
                    dim_overlay.setGeometry(self.rect())
                    dim_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    dim_overlay.show()
                    dim_overlay.raise_()
                    self._transfer_dim_overlay = dim_overlay
                    overlays = list(getattr(self, "_card_dialog_dim_overlays", []) or [])
                    overlays.append(dim_overlay)
                    self._card_dialog_dim_overlays = overlays
                except Exception:
                    self._transfer_dim_overlay = None
            else:
                try:
                    overlay = getattr(self, "_transfer_dim_overlay", None)
                    if overlay is not None:
                        overlay.setGeometry(self.rect())
                        overlay.show()
                        overlay.raise_()
                except Exception:
                    pass

        self.active_transfer_dialog = dialog

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y_offset = int(getattr(dialog, "_card_dialog_y_offset", 0) or 0)
        y = geo.y() + max(20, (geo.height() - dialog.height()) // 2) + y_offset
        y = max(geo.y() + 20, y)
        dialog.move(x, y)

        cleaned = {"done": False}

        def cleanup(*args):
            if cleaned["done"]:
                return
            cleaned["done"] = True
            try:
                self._card_dialog_open_count = max(0, int(getattr(self, "_card_dialog_open_count", 0) or 0) - 1)
            except Exception:
                self._card_dialog_open_count = 0
            if int(getattr(self, "_card_dialog_open_count", 0) or 0) <= 0:
                self._force_clear_card_dialog_background(force=True)
            else:
                # Keep the shared overlay alive for the remaining card.
                try:
                    root = self.centralWidget()
                    if root is not None:
                        root.setEnabled(False)
                    overlay = getattr(self, "_transfer_dim_overlay", None)
                    if overlay is not None:
                        overlay.setGeometry(self.rect())
                        overlay.show()
                        overlay.raise_()
                except Exception:
                    pass

        dialog.finished.connect(cleanup)
        dialog.destroyed.connect(cleanup)
        QTimer.singleShot(60, lambda: self.clear_transfer_text_selection(dialog))
        try:
            dialog.exec()
        finally:
            cleanup()
            # Run again after Qt processes deferred deleteLater events, but only
            # clear when all card dialogs have closed.
            QTimer.singleShot(0, lambda: self._force_clear_card_dialog_background(force=False))
            QTimer.singleShot(120, lambda: self._force_clear_card_dialog_background(force=False))
            if getattr(self, "active_transfer_dialog", None) is dialog:
                self.active_transfer_dialog = None


    def transfer_input_row(self: Any, label_text: str, value: str = "", readonly: bool = False, password: bool = False, placeholder: str = ""):
        wrapper = QVBoxLayout()
        wrapper.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("TransferFieldLabel")
        wrapper.addWidget(label)

        box = QFrame()
        box.setObjectName("TransferInputBox")
        row = QHBoxLayout(box)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(8)

        edit = QLineEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        edit.setObjectName("TransferInput")
        edit.setText(value or "")
        edit.setReadOnly(readonly)
        edit.setMinimumHeight(34 if not self.compact_mode else 31)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)

        row.addWidget(edit, 1)
        wrapper.addWidget(box)
        return wrapper, edit, box, row

    def add_path_browse_button(self: Any, row_layout, path_edit):
        """Folder icon opens folder picker and writes selected path into the field."""
        browse_btn = QPushButton("⌕")
        browse_btn.setObjectName("TransferIconButton")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip("Browse server folder")
        browse_btn.setFixedSize(28, 28)

        def browse_path():
            start_dir = path_edit.text().strip() or self.server_path or os.path.expanduser("~")
            parent_dialog = browse_btn.window()

            # Do NOT hide the transfer card here.
            # Hiding a modal QDialog can close/finish the dialog event loop,
            # so the Export/Import popup disappears after folder selection.
            selected = QFileDialog.getExistingDirectory(
                parent_dialog,
                "Select Server Path",
                start_dir,
                QFileDialog.Option.ShowDirsOnly,
            )

            if selected:
                path_edit.setText(selected.replace("\\", "/"))

            try:
                parent_dialog.raise_()
                parent_dialog.activateWindow()
            except Exception:
                pass

        browse_btn.clicked.connect(browse_path)
        row_layout.addWidget(browse_btn)
        return browse_btn


    def create_transfer_dialog_base(self: Any, title_text: str, subtitle_text: str, icon_text: str, height: int = 620):
        dialog = QDialog(self)
        dialog.setObjectName("TransferDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(520 if not self.compact_mode else 470, height if not self.compact_mode else max(520, height - 70))

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("TransferCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(30 if not self.compact_mode else 22, 20 if not self.compact_mode else 18, 30 if not self.compact_mode else 22, 20 if not self.compact_mode else 18)
        root.setSpacing(9 if not self.compact_mode else 8)

        top_line = QFrame()
        top_line.setObjectName("TransferTopLine")
        top_line.setFixedHeight(1)
        root.addWidget(top_line)

        icon = QLabel(icon_text)
        icon.setObjectName("TransferHeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(56 if not self.compact_mode else 48, 56 if not self.compact_mode else 48)

        title = QLabel(title_text)
        title.setObjectName("TransferTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("TransferSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        if subtitle_text:
            root.addWidget(subtitle)

        return dialog, root

    def rebuild_export_loading_card(self: Any, root, dialog):
        """Change the existing Export card content into the loading UI."""
        self.clear_layout_widgets(root)

        # Tighter layout to prevent overlay on laptop-sized screens.
        root.setContentsMargins(
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
        )
        root.setSpacing(12 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(6)

        system = QLabel("SECURE ACCESS")
        system.setObjectName("ExportStateEyebrow")

        active = QLabel("●  SYSTEM ACTIVE")
        active.setObjectName("ExportStateActive")

        left.addWidget(system)
        left.addWidget(active)

        shield = QLabel("🛡")
        shield.setObjectName("ExportStateShield")
        shield.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        header.addLayout(left, 1)
        header.addWidget(shield)
        root.addLayout(header)

        root.addSpacing(22 if not self.compact_mode else 16)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(14 if not self.compact_mode else 11)

        spinner_wrap = ExportCircleSpinnerWidget(
            dialog,
            size=112 if not self.compact_mode else 96,
            icon_text="⇧",
        )
        spinner_wrap.setObjectName("ExportCircleSpinner")

        title = QLabel("EXPORTING DATA")
        title.setObjectName("ExportStateTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(False)
        title.setMinimumWidth(360 if not self.compact_mode else 300)

        status = QLabel("Preparing export package...")
        status.setObjectName("ExportStateSubtitle")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setWordWrap(True)
        status.setMaximumWidth(380 if not self.compact_mode else 320)
        status.setMinimumWidth(320 if not self.compact_mode else 280)

        center.addWidget(spinner_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(status, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addLayout(center)

        root.addStretch(1)

        progress_outer = QFrame()
        progress_outer.setObjectName("ExportProgressOuter")
        progress_outer.setFixedHeight(5)

        progress_layout = QHBoxLayout(progress_outer)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        progress_fill = QFrame()
        progress_fill.setObjectName("ExportProgressFill")
        progress_layout.addWidget(progress_fill)
        progress_layout.addStretch(1)

        root.addWidget(progress_outer)

        footer = QHBoxLayout()
        footer.setSpacing(16)

        node_box = QVBoxLayout()
        node_box.setSpacing(3)
        node_lbl = QLabel("NODE")
        node_lbl.setObjectName("ExportMetricLabel")
        node_value = QLabel("CAMERA API")
        node_value.setObjectName("ExportMetricValue")
        node_box.addWidget(node_lbl)
        node_box.addWidget(node_value)

        load_box = QVBoxLayout()
        load_box.setSpacing(3)
        load_lbl = QLabel("LOAD")
        load_lbl.setObjectName("ExportMetricLabel")
        load_value = QLabel("12.4%")
        load_value.setObjectName("ExportMetricValue")
        load_box.addWidget(load_lbl)
        load_box.addWidget(load_value)

        percentage = QLabel("34%")
        percentage.setObjectName("ExportPercentage")
        percentage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        footer.addLayout(node_box)
        footer.addLayout(load_box)
        footer.addStretch()
        footer.addWidget(percentage)

        root.addLayout(footer)

        dialog._export_spinner_widget = spinner_wrap
        dialog._export_spinner_index = 0
        dialog._export_progress = 34
        dialog._export_progress_fill = progress_fill
        dialog._export_progress_outer = progress_outer
        dialog._export_percentage_label = percentage
        dialog._export_status_label = status

        status_messages = [
            "Preparing export package...",
            "Validating dataset...",
            "Compressing files...",
            "Connecting to server...",
            "Writing backup archive...",
            "Finalising transfer..."
        ]
        dialog._export_status_index = 0

        timer = QTimer(dialog)

        def tick():
            try:
                dialog._export_spinner_index += 1
                # Spinner animation is handled by ExportCircleSpinnerWidget.
                # Do not complete before the real export finishes.
                # It can move slowly to 96%, then success will animate 96 → 100.
                if dialog._export_progress < 96 and dialog._export_spinner_index % 2 == 0:
                    dialog._export_progress += 1
                    percentage.setText(f"{dialog._export_progress}%")
                    progress_fill.setFixedWidth(max(8, int(progress_outer.width() * dialog._export_progress / 100)))

                if dialog._export_spinner_index % 10 == 0:
                    dialog._export_status_index = (dialog._export_status_index + 1) % len(status_messages)
                    status = getattr(self, "local_status_label", None) or QLabel("")
                    status.setText(status_messages[dialog._export_status_index])
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start(90)
        dialog._export_loading_timer = timer


    def stop_export_loading_timer(self: Any, dialog):
        timer = getattr(dialog, "_export_loading_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
            dialog._export_loading_timer = None

        spinner = getattr(dialog, "_export_spinner_widget", None)
        if spinner is not None:
            try:
                spinner.stop()
            except Exception:
                pass


    def finish_export_progress_then_success(self: Any, root, dialog, message: str, filename: str = ""):
        """Animate progress to 100% before changing to success content."""
        self.stop_export_loading_timer(dialog)

        progress_fill = getattr(dialog, "_export_progress_fill", None)
        progress_outer = getattr(dialog, "_export_progress_outer", None)
        percentage = getattr(dialog, "_export_percentage_label", None)
        status = getattr(dialog, "_export_status_label", None)

        if status is not None:
            status.setText("Finalising export package...")

        finish_timer = QTimer(dialog)

        def tick_finish():
            try:
                current = int(getattr(dialog, "_export_progress", 96))
                if current < 100:
                    current += 2
                    if current > 100:
                        current = 100
                    dialog._export_progress = current

                    if percentage is not None:
                        percentage.setText(f"{current}%")

                    if progress_fill is not None and progress_outer is not None:
                        progress_fill.setFixedWidth(max(8, int(progress_outer.width() * current / 100)))
                    return

                finish_timer.stop()
                finish_timer.deleteLater()

                if status is not None:
                    status.setText("Export completed.")

                QTimer.singleShot(260, lambda: self.rebuild_export_success_card(root, dialog, message, filename))
            except Exception:
                try:
                    finish_timer.stop()
                except Exception:
                    pass
                self.rebuild_export_success_card(root, dialog, message, filename)

        finish_timer.timeout.connect(tick_finish)
        finish_timer.start(70)
        tick_finish()

    def rebuild_export_success_card(self: Any, root, dialog, message: str, filename: str = ""):
        """Change the existing Export card content into the success UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(18 if not self.compact_mode else 14)

        root.addStretch(1)

        icon = QLabel("✓")
        icon.setObjectName("ExportSuccessIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("EXPORT SUCCESSFUL")
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        subtitle = QLabel(message or "Face data exported successfully to server path.")
        subtitle.setObjectName("ExportSuccessSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        detail = QFrame()
        detail.setObjectName("ExportDetailBlock")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(8)

        detail_label = QLabel("TECHNICAL DETAIL")
        detail_label.setObjectName("ExportMetricLabel")

        detail_code = QLabel(f"File: {filename}" if filename else "File: exported backup archive")
        detail_code.setObjectName("ExportDetailCode")
        detail_code.setWordWrap(True)

        detail_layout.addWidget(detail_label)
        detail_layout.addWidget(detail_code)
        root.addWidget(detail)

        root.addStretch(1)

        close_btn = QPushButton("RETURN TO CONSOLE  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)

    def rebuild_export_failed_card(self: Any, root, dialog, error_text: str):
        """Change the existing Export card content into an error UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(18 if not self.compact_mode else 14)

        root.addStretch(1)

        icon = QLabel("×")
        icon.setObjectName("ExportFailedIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("EXPORT FAILED")
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(error_text or "Export failed. Please check NTID, password, server path, and local recognition engine.")
        subtitle.setObjectName("TransferStatusError")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addStretch(1)

        close_btn = QPushButton("RETURN TO EXPORT  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)


    def rebuild_import_loading_card(self: Any, root, dialog, source_name: str = ""):
        """Change the existing Import card content into the loading UI."""
        self.clear_layout_widgets(root)
        root.setContentsMargins(
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
            34 if not self.compact_mode else 28,
            28 if not self.compact_mode else 22,
        )
        root.setSpacing(12 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(6)

        system = QLabel("SECURE ACCESS")
        system.setObjectName("ExportStateEyebrow")

        active = QLabel("●  IMPORT ACTIVE")
        active.setObjectName("ExportStateActive")

        left.addWidget(system)
        left.addWidget(active)

        shield = QLabel("🛡")
        shield.setObjectName("ExportStateShield")
        shield.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        header.addLayout(left, 1)
        header.addWidget(shield)
        root.addLayout(header)

        root.addSpacing(22 if not self.compact_mode else 16)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(14 if not self.compact_mode else 11)

        spinner_wrap = ExportCircleSpinnerWidget(
            dialog,
            size=112 if not self.compact_mode else 96,
            icon_text="⇩",
        )
        spinner_wrap.setObjectName("ExportCircleSpinner")

        title = QLabel("IMPORTING DATA")
        title.setObjectName("ExportStateTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(False)
        title.setMinimumWidth(360 if not self.compact_mode else 300)

        status = QLabel("Reading backup package...")
        status.setObjectName("ExportStateSubtitle")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setWordWrap(True)
        status.setMaximumWidth(380 if not self.compact_mode else 320)
        status.setMinimumWidth(320 if not self.compact_mode else 280)

        if source_name:
            source = QLabel(source_name)
            source.setObjectName("ImportSourceFile")
            source.setAlignment(Qt.AlignmentFlag.AlignCenter)
            source.setWordWrap(True)
            source.setMaximumWidth(380 if not self.compact_mode else 320)
        else:
            source = None

        center.addWidget(spinner_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(status, alignment=Qt.AlignmentFlag.AlignCenter)
        if source is not None:
            center.addWidget(source, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addLayout(center)

        root.addStretch(1)

        progress_outer = QFrame()
        progress_outer.setObjectName("ExportProgressOuter")
        progress_outer.setFixedHeight(5)

        progress_layout = QHBoxLayout(progress_outer)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        progress_fill = QFrame()
        progress_fill.setObjectName("ExportProgressFill")
        progress_layout.addWidget(progress_fill)
        progress_layout.addStretch(1)

        root.addWidget(progress_outer)

        footer = QHBoxLayout()
        footer.setSpacing(16)

        node_box = QVBoxLayout()
        node_box.setSpacing(3)
        node_lbl = QLabel("SOURCE")
        node_lbl.setObjectName("ExportMetricLabel")
        node_value = QLabel("SERVER ZIP")
        node_value.setObjectName("ExportMetricValue")
        node_box.addWidget(node_lbl)
        node_box.addWidget(node_value)

        load_box = QVBoxLayout()
        load_box.setSpacing(3)
        load_lbl = QLabel("MODE")
        load_lbl.setObjectName("ExportMetricLabel")
        load_value = QLabel("SYNC")
        load_value.setObjectName("ExportMetricValue")
        load_box.addWidget(load_lbl)
        load_box.addWidget(load_value)

        percentage = QLabel("34%")
        percentage.setObjectName("ExportPercentage")
        percentage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        footer.addLayout(node_box)
        footer.addLayout(load_box)
        footer.addStretch()
        footer.addWidget(percentage)

        root.addLayout(footer)

        dialog._export_spinner_widget = spinner_wrap
        dialog._export_spinner_index = 0
        dialog._export_progress = 34
        dialog._export_progress_fill = progress_fill
        dialog._export_progress_outer = progress_outer
        dialog._export_percentage_label = percentage
        dialog._export_status_label = status

        status_messages = [
            "Reading backup package...",
            "Checking for duplicate images...",
            "Adding new images only...",
            "Adding new encodings only...",
            "Refreshing user registry...",
            "Finalising import..."
        ]
        dialog._export_status_index = 0

        timer = QTimer(dialog)

        def tick():
            try:
                dialog._export_spinner_index += 1

                if dialog._export_progress < 96 and dialog._export_spinner_index % 2 == 0:
                    dialog._export_progress += 1
                    percentage.setText(f"{dialog._export_progress}%")
                    progress_fill.setFixedWidth(max(8, int(progress_outer.width() * dialog._export_progress / 100)))

                if dialog._export_spinner_index % 10 == 0:
                    dialog._export_status_index = (dialog._export_status_index + 1) % len(status_messages)
                    status = getattr(self, "local_status_label", None) or QLabel("")
                    status.setText(status_messages[dialog._export_status_index])
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start(90)
        dialog._export_loading_timer = timer

    def finish_import_progress_then_success(self: Any, root, dialog, source_name: str, imported_users, skipped_users_count: int = 0, message: str = ""):
        """Animate import progress to 100% before changing to success content."""
        self.stop_export_loading_timer(dialog)

        progress_fill = getattr(dialog, "_export_progress_fill", None)
        progress_outer = getattr(dialog, "_export_progress_outer", None)
        percentage = getattr(dialog, "_export_percentage_label", None)
        status = getattr(dialog, "_export_status_label", None)

        if status is not None:
            status.setText("Finalising import...")

        finish_timer = QTimer(dialog)

        def tick_finish():
            try:
                current = int(getattr(dialog, "_export_progress", 96))
                if current < 100:
                    current += 2
                    if current > 100:
                        current = 100
                    dialog._export_progress = current

                    if percentage is not None:
                        percentage.setText(f"{current}%")

                    if progress_fill is not None and progress_outer is not None:
                        progress_fill.setFixedWidth(max(8, int(progress_outer.width() * current / 100)))
                    return

                finish_timer.stop()
                finish_timer.deleteLater()

                if status is not None:
                    status.setText("Import completed.")

                QTimer.singleShot(
                    260,
                    lambda: self.rebuild_import_success_card(
                        root,
                        dialog,
                        source_name,
                        imported_users,
                        skipped_users_count,
                        message,
                    )
                )
            except Exception:
                try:
                    finish_timer.stop()
                except Exception:
                    pass
                self.rebuild_import_success_card(root, dialog, source_name, imported_users, skipped_users_count, message)

        finish_timer.timeout.connect(tick_finish)
        finish_timer.start(70)
        tick_finish()

    def rebuild_import_success_card(self: Any, root, dialog, source_name: str, imported_users, skipped_users_count: int = 0, message: str = ""):
        """Change the existing Import card content into the import completed UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(16 if not self.compact_mode else 13)

        imported_users = imported_users or []
        imported_count = len(imported_users)

        root.addStretch(1)

        icon = QLabel("✓" if imported_count > 0 else "i")
        icon.setObjectName("ExportSuccessIcon" if imported_count > 0 else "ImportInfoIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title_text = "IMPORT SUCCESSFUL" if imported_count > 0 else "IMPORT COMPLETED"
        title = QLabel(title_text)
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        if imported_count > 0:
            subtitle_text = f"{imported_count} user{'s' if imported_count != 1 else ''} processed. New data only was added."
        else:
            subtitle_text = "No valid user data was found to merge from this backup."

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("ExportSuccessSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        detail = QFrame()
        detail.setObjectName("ExportDetailBlock")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(8)

        detail_label = QLabel("TECHNICAL DETAIL")
        detail_label.setObjectName("ExportMetricLabel")

        source_code = QLabel(f"Source: {source_name}" if source_name else "Source: selected backup ZIP")
        source_code.setObjectName("ExportDetailCode")
        source_code.setWordWrap(True)

        detail_layout.addWidget(detail_label)
        detail_layout.addWidget(source_code)

        users_label = QLabel("PROCESSED USERS")
        users_label.setObjectName("ExportMetricLabel")
        detail_layout.addWidget(users_label)

        if imported_count > 0:
            preview = imported_users[:5]
            preview_text = ", ".join(str(u).upper() for u in preview)
            remaining = imported_count - len(preview)
            if remaining > 0:
                preview_text += f"  +{remaining} more"
        else:
            preview_text = "No new data was found in this backup."

        users_code = QLabel(preview_text)
        users_code.setObjectName("ExportDetailCode")
        users_code.setWordWrap(True)
        detail_layout.addWidget(users_code)

        root.addWidget(detail)

        root.addStretch(1)

        close_btn = QPushButton("RETURN TO SETTINGS  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)

    def rebuild_import_failed_card(self: Any, root, dialog, error_text: str):
        """Change the existing Import card content into an error UI."""
        self.stop_export_loading_timer(dialog)
        self.clear_layout_widgets(root)
        root.setContentsMargins(34 if not self.compact_mode else 28, 32 if not self.compact_mode else 26, 34 if not self.compact_mode else 28, 30 if not self.compact_mode else 24)
        root.setSpacing(18 if not self.compact_mode else 14)

        root.addStretch(1)

        icon = QLabel("×")
        icon.setObjectName("ExportFailedIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(68 if not self.compact_mode else 58, 68 if not self.compact_mode else 58)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("IMPORT FAILED")
        title.setObjectName("ExportSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(error_text or "Import failed. Please check the ZIP file and local recognition engine.")
        subtitle.setObjectName("TransferStatusError")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addStretch(1)

        close_btn = QPushButton("RETURN TO IMPORT  →")
        close_btn.setObjectName("ExportReturnButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)


    def _set_transfer_tab_selected(self: Any, buttons, stack, index: int):
        """Switch a transfer popup between tab pages."""
        try:
            stack.setCurrentIndex(index)
        except Exception:
            pass
        for i, btn in enumerate(buttons):
            try:
                btn.setProperty("selected", i == index)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            except Exception:
                pass

    def _create_transfer_tabs(self: Any, root, names):
        """Create segmented tabs and a QStackedWidget for transfer dialogs."""
        stack = QStackedWidget()
        tabs = TransferSnakeTabs(names, self, self.compact_mode)

        def switch_tab(index: int):
            try:
                stack.setCurrentIndex(index)
            except Exception:
                pass

        tabs.on_index_changed = switch_tab  # type: ignore[assignment]
        root.addWidget(tabs)
        root.addWidget(stack, 1)
        return getattr(tabs, "buttons", []), stack

    def _browse_zip_file_into(self: Any, row_layout, path_edit):
        """Add a ZIP file picker to a transfer input row."""
        browse_btn = QPushButton("⌕")
        browse_btn.setObjectName("TransferIconButton")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip("Browse local ZIP file")
        browse_btn.setFixedSize(28, 28)

        def browse_zip():
            start_dir = os.path.dirname(path_edit.text().strip()) if path_edit.text().strip() else os.path.expanduser("~")
            selected, _ = QFileDialog.getOpenFileName(
                browse_btn.window(),
                "Select Face Data ZIP",
                start_dir,
                "ZIP files (*.zip);;All files (*.*)",
            )
            if selected:
                path_edit.setText(selected.replace("/", "\\"))
            try:
                browse_btn.window().raise_()
                browse_btn.window().activateWindow()
            except Exception:
                pass

        browse_btn.clicked.connect(browse_zip)
        row_layout.addWidget(browse_btn)
        return browse_btn

    def _local_face_export_data(self: Any):
        """Open export popup with Server Path and Local Path tabs."""
        ntid, password, server = "", "", ""

        dialog, root = self.create_transfer_dialog_base(
            "Export Face Data",
            "",
            "⇧",
            height=540,
        )

        _, stack = self._create_transfer_tabs(root, ["Server Path", "Local Path"])

        server_page = QWidget()
        server_layout = QVBoxLayout(server_page)
        server_layout.setContentsMargins(0, 8, 0, 0)
        server_layout.setSpacing(9)

        ntid_row, ntid_edit, _, _ = self.transfer_input_row("NTID / Username", "", readonly=False, placeholder="e.g. 1234567")
        pwd_row, pwd_edit, _, _ = self.transfer_input_row("Password", "", readonly=False, password=True)
        path_row, path_edit, _, path_row_layout = self.transfer_input_row("Server Path", "", readonly=False, placeholder="e.g. //server/share/SAS_folder")
        self.add_path_browse_button(path_row_layout, path_edit)
        server_layout.addLayout(ntid_row)
        server_layout.addLayout(pwd_row)
        server_layout.addLayout(path_row)
        server_status = QLabel("")
        server_status.setObjectName("TransferStatus")
        server_status.setWordWrap(True)
        server_layout.addWidget(server_status)
        server_actions = QHBoxLayout()
        server_cancel = QPushButton("Cancel")
        server_cancel.setObjectName("TransferCancelButton")
        server_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        server_cancel.clicked.connect(dialog.reject)
        export_btn = QPushButton("Export  →")
        export_btn.setObjectName("TransferPrimaryButton")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        server_actions.addWidget(server_cancel)
        server_actions.addStretch()
        server_actions.addWidget(export_btn)
        server_layout.addLayout(server_actions)
        stack.addWidget(server_page)

        local_page = QWidget()
        local_layout = QVBoxLayout(local_page)
        local_layout.setContentsMargins(0, 8, 0, 0)
        local_layout.setSpacing(9)
        save_row, save_edit, _, save_row_layout = self.transfer_input_row("Windows Save Folder", "", readonly=False, placeholder="e.g. C:\\Users\\Public\\Documents")
        self.add_path_browse_button(save_row_layout, save_edit)
        local_layout.addLayout(save_row)
        local_status = QLabel("")
        local_status.setObjectName("TransferStatus")
        local_status.setWordWrap(True)
        local_layout.addWidget(local_status)
        local_actions = QHBoxLayout()
        local_cancel = QPushButton("Cancel")
        local_cancel.setObjectName("TransferCancelButton")
        local_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        local_cancel.clicked.connect(dialog.reject)
        download_btn = QPushButton("Export  →")
        download_btn.setObjectName("TransferPrimaryButton")
        download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        local_actions.addWidget(local_cancel)
        local_actions.addStretch()
        local_actions.addWidget(download_btn)
        local_layout.addLayout(local_actions)
        stack.addWidget(local_page)

        def do_export():
            export_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            nt = ntid_edit.text().strip()
            pw = pwd_edit.text().strip()
            sp = path_edit.text().strip()
            if not self.validate_transfer_inputs(nt, pw, sp, server_status):
                return
            self.rebuild_export_loading_card(root, dialog)
            actor = self.get_audit_actor()

            def worker():
                try:
                    data = self._local_face_request("POST", "/face-data/export", {"username": nt, "password": pw, "pc_save_path": sp, "target_folder": None}, timeout=120)
                    message = data.get("message", "Face data exported successfully to server path.")
                    filename = data.get("filename", "")
                    def done():
                        self.finish_export_progress_then_success(root, dialog, message, filename)
                        self.append_face_log(f"EXPORT: {message}")
                        self.write_sas_log(
                            "FACE DATA EXPORTED TO SERVER",
                            actor=actor,
                            details={
                                "Server path": sp,
                                "ZIP file": filename or "Face data package",
                            },
                        )
                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)
                    def failed(err=err):
                        self.rebuild_export_failed_card(root, dialog, f"Export failed: {err}")
                        self.append_face_log(f"EXPORT_FAILED: {err}")
                        self.write_sas_log(
                            "FACE DATA EXPORT FAILED",
                            actor=actor,
                            details={"Server path": sp, "Result": "Failed"},
                        )
                    self.qt_after(0, failed)
            Thread(target=worker, daemon=True).start()

        def do_download():
            download_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            save_folder = save_edit.text().strip()
            if not save_folder:
                self.set_transfer_status(local_status, "Windows save folder is required.", "error")
                return
            actor = self.get_audit_actor()
            self.rebuild_export_loading_card(root, dialog)

            def worker():
                try:
                    data = self._local_face_request("POST", "/face-data/export", {"target_folder": save_folder}, timeout=120)
                    message = data.get("message", "Face data exported successfully.")
                    filename = data.get("filename", "")

                    def done():
                        self.finish_export_progress_then_success(root, dialog, message, filename)
                        self.append_face_log(f"LOCAL_EXPORT: {message}")
                        self.write_sas_log(
                            "FACE DATA EXPORTED TO LOCAL FOLDER",
                            actor=actor,
                            details={
                                "Local folder": save_folder,
                                "ZIP file": filename or "Face data package",
                            },
                        )

                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)

                    def failed(err=err):
                        self.rebuild_export_failed_card(root, dialog, f"Export failed: {err}")
                        self.append_face_log(f"LOCAL_EXPORT_FAILED: {err}")
                        self.write_sas_log(
                            "FACE DATA LOCAL EXPORT FAILED",
                            actor=actor,
                            details={"Local folder": save_folder, "Result": "Failed"},
                        )

                    self.qt_after(0, failed)

            Thread(target=worker, daemon=True).start()

        export_btn.clicked.connect(do_export)
        download_btn.clicked.connect(do_download)
        self._show_card_dialog(dialog)

    def _local_face_import_data(self: Any):
        """Open import popup with Server Path and Local Path tabs."""
        ntid, password, server = "", "", ""
        dialog, root = self.create_transfer_dialog_base(
            "Import Face Data",
            "",
            "⇩",
            height=590,
        )
        # Import has a tall ZIP-list panel. Place this card slightly higher so
        # its actions remain comfortably visible on typical laptop screens.
        setattr(dialog, "_card_dialog_y_offset", -24)
        _, stack = self._create_transfer_tabs(root, ["Server Path", "Local Path"])

        server_page = QWidget()
        server_layout = QVBoxLayout(server_page)
        server_layout.setContentsMargins(0, 8, 0, 0)
        server_layout.setSpacing(8)
        ntid_row, ntid_edit, _, _ = self.transfer_input_row("NTID / Username", "", readonly=False, placeholder="e.g. 1234567")
        pwd_row, pwd_edit, _, _ = self.transfer_input_row("Password", "", readonly=False, password=True)
        path_row, path_edit, _, path_row_layout = self.transfer_input_row("Server Path", "", readonly=False, placeholder="e.g. //server/share/SAS_folder")
        self.add_path_browse_button(path_row_layout, path_edit)
        server_layout.addLayout(ntid_row)
        server_layout.addLayout(pwd_row)
        server_layout.addLayout(path_row)
        zip_label = QLabel("Available ZIP Files")
        zip_label.setObjectName("TransferFieldLabel")
        server_layout.addWidget(zip_label)
        search_box = QFrame()
        search_box.setObjectName("TransferInputBox")
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 0, 10, 0)
        search = QLineEdit()
        search.setObjectName("TransferInput")
        search.setPlaceholderText("Search zip files...")
        search.setMinimumHeight(32 if not self.compact_mode else 30)
        search_icon = QLabel("⌕")
        search_icon.setObjectName("TransferSearchIcon")
        search_layout.addWidget(search, 1)
        search_layout.addWidget(search_icon)
        server_layout.addWidget(search_box)
        list_wrap = QFrame()
        list_wrap.setObjectName("TransferZipList")
        list_layout = QVBoxLayout(list_wrap)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(108 if not self.compact_mode else 96)
        self.make_scrollbar_invisible(scroll)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)
        scroll.setWidget(body)
        list_layout.addWidget(scroll)
        server_layout.addWidget(list_wrap)
        server_status = QLabel("Press Connect to load ZIP files from the server path.")
        server_status.setObjectName("TransferStatus")
        server_status.setWordWrap(True)
        server_layout.addWidget(server_status)
        state = {"files": [], "selected": None, "selected_row": None}

        def clear_body():
            while body_layout.count():
                item = body_layout.takeAt(0)
                if item is None:
                    continue
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        def selected_file_key(file_info):
            return file_info.get("path") or file_info.get("name") or ""

        def render_files():
            clear_body()
            keyword = search.text().strip().lower()
            files = state["files"]
            filtered = [f for f in files if keyword in f.get("name", "").lower()] if keyword else files
            if not filtered:
                msg = QLabel("No ZIP files found." if files else "No server ZIP list loaded.")
                msg.setObjectName("TransferStatus")
                body_layout.addWidget(msg)
                body_layout.addStretch()
                return
            current_selected_key = selected_file_key(state["selected"]) if state.get("selected") else ""
            for file_info in filtered:
                row = QFrame()
                row.setObjectName("TransferZipRow")
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(8, 5, 8, 5)
                row_layout.setSpacing(8)
                icon = QLabel("▣")
                icon.setObjectName("TransferZipIcon")
                icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                name = QLabel(file_info.get("name", ""))
                name.setObjectName("TransferZipName")
                name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                row_layout.addWidget(icon)
                row_layout.addWidget(name, 1)
                is_selected = bool(current_selected_key and selected_file_key(file_info) == current_selected_key)
                row.setProperty("selected", is_selected)
                if is_selected:
                    state["selected_row"] = row

                def select_file(event, fi=file_info, r=row):
                    self.clear_transfer_text_selection(dialog)
                    for i in range(body_layout.count()):
                        item = body_layout.itemAt(i)
                        w = item.widget() if item is not None else None
                        if w is not None and w.objectName() == "TransferZipRow":
                            w.setProperty("selected", False)
                            w.style().unpolish(w)
                            w.style().polish(w)
                    state["selected"] = fi
                    state["selected_row"] = r
                    r.setProperty("selected", True)
                    r.style().unpolish(r)
                    r.style().polish(r)
                    self.set_transfer_status(server_status, f"Selected: {fi.get('name', '')}", "normal")

                row.mousePressEvent = select_file
                body_layout.addWidget(row)
                row.style().unpolish(row)
                row.style().polish(row)
            body_layout.addStretch()

        search.textChanged.connect(render_files)
        render_files()
        server_actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("TransferCancelButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(dialog.reject)
        connect = QPushButton("Connect")
        connect.setObjectName("TransferPrimaryButton")
        connect.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn = QPushButton("Import")
        import_btn.setObjectName("TransferPrimaryButton")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.setEnabled(False)
        server_actions.addWidget(cancel)
        server_actions.addStretch()
        server_actions.addWidget(connect)
        server_actions.addWidget(import_btn)
        server_layout.addLayout(server_actions)
        stack.addWidget(server_page)

        local_page = QWidget()
        local_layout = QVBoxLayout(local_page)
        local_layout.setContentsMargins(0, 8, 0, 0)
        local_layout.setSpacing(9)
        local_ntid_row, local_ntid_edit, _, _ = self.transfer_input_row("Windows Username / NTID", "", readonly=False, placeholder="e.g. 1234567")
        local_pwd_row, local_pwd_edit, _, _ = self.transfer_input_row("Windows Password", "", readonly=False, password=True)
        zip_row, zip_edit, _, zip_row_layout = self.transfer_input_row("Local Path File", "", readonly=False)
        self._browse_zip_file_into(zip_row_layout, zip_edit)
        local_layout.addLayout(zip_row)
        local_status = QLabel("")
        local_status.setObjectName("TransferStatus")
        local_status.setWordWrap(True)
        local_layout.addWidget(local_status)
        local_actions = QHBoxLayout()
        local_cancel = QPushButton("Cancel")
        local_cancel.setObjectName("TransferCancelButton")
        local_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        local_cancel.clicked.connect(dialog.reject)
        local_import_btn = QPushButton("Import  →")
        local_import_btn.setObjectName("TransferPrimaryButton")
        local_import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        local_actions.addWidget(local_cancel)
        local_actions.addStretch()
        local_actions.addWidget(local_import_btn)
        local_layout.addLayout(local_actions)
        stack.addWidget(local_page)

        def load_zip_files():
            connect.setFocus()
            self.clear_transfer_text_selection(dialog)
            self.start_transfer_button_loading(connect, "Connect")
            self.set_transfer_status(server_status, "Connecting to server path and loading ZIP files...", "normal")
            nt = ntid_edit.text().strip()
            pw = pwd_edit.text().strip()
            sp = path_edit.text().strip()
            if not self.validate_transfer_inputs(nt, pw, sp, server_status):
                self.show_transfer_button_failed(connect, "Connect")
                import_btn.setEnabled(False)
                return

            def worker():
                try:
                    data = self._local_face_request("POST", "/face-data/list-server-zips", {"username": nt, "password": pw, "pc_save_path": sp}, timeout=90)
                    files = data.get("files", [])
                    def done():
                        connect.setFocus()
                        self.clear_transfer_text_selection(dialog)
                        state["files"] = files
                        state["selected"] = None
                        state["selected_row"] = None
                        render_files()
                        self.show_transfer_button_success(connect, "Connected", "Refresh List")
                        self.set_transfer_status(server_status, f"Found {len(files)} ZIP file(s)." if files else "No ZIP backup files found in this server path.", "success" if files else "normal")
                        import_btn.setEnabled(bool(files))
                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)
                    def fail(err=err):
                        connect.setFocus()
                        self.clear_transfer_text_selection(dialog)
                        self.set_transfer_status(server_status, f"Load failed: {err}", "error")
                        self.show_transfer_button_failed(connect, "Connect")
                        import_btn.setEnabled(False)
                    self.qt_after(0, fail)
            Thread(target=worker, daemon=True).start()

        def import_selected():
            import_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            selected = state.get("selected")
            if not selected:
                self.set_transfer_status(server_status, "Please select a ZIP file to import.", "error")
                return
            nt = ntid_edit.text().strip()
            pw = pwd_edit.text().strip()
            sp = path_edit.text().strip()
            if not self.validate_transfer_inputs(nt, pw, sp, server_status):
                return
            selected_name = selected.get("name", "")
            selected_path = selected.get("path", "")
            actor = self.get_audit_actor()
            self.rebuild_import_loading_card(root, dialog, selected_name)
            def worker():
                try:
                    data = self._local_face_request("POST", "/face-data/import", {"zip_path": selected_path}, timeout=120)
                    message = data.get("message", "Face data imported.")
                    backup_filename = data.get("backup_filename", "")
                    if backup_filename:
                        message = f"{message} Backup created: {backup_filename}"
                    imported_users = data.get("imported_users", [])
                    skipped_users_count = int(data.get("skipped_users_count", 0) or 0)
                    if data.get("import_mode") in ("add_on", "add_new_only"):
                        skipped_users_count = 0
                    for k in ("added_ids", "merged_users", "imported_ids"):
                        if not imported_users and isinstance(data.get(k, None), list):
                            imported_users = data.get(k, [])
                    def done():
                        self.finish_import_progress_then_success(root, dialog, selected_name, imported_users, skipped_users_count, message)
                        self.append_face_log(f"IMPORT: {message}")
                        self.write_sas_log(
                            "FACE DATA IMPORTED FROM SERVER",
                            actor=actor,
                            details={
                                "Server path": sp,
                                "ZIP file": selected_name or os.path.basename(selected_path),
                                "Imported users": ", ".join(str(item).upper() for item in imported_users) or "No new users",
                            },
                        )
                        self._local_face_refresh_users()
                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)
                    def failed(err=err):
                        self.rebuild_import_failed_card(root, dialog, f"Import failed: {err}")
                        self.append_face_log(f"IMPORT_FAILED: {err}")
                        self.write_sas_log(
                            "FACE DATA SERVER IMPORT FAILED",
                            actor=actor,
                            details={"Server path": sp, "ZIP file": selected_name or os.path.basename(selected_path), "Result": "Failed"},
                        )
                    self.qt_after(0, failed)
            Thread(target=worker, daemon=True).start()

        def import_local_zip():
            local_import_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            local_zip = zip_edit.text().strip()
            if not local_zip:
                self.set_transfer_status(local_status, "Local ZIP file is required.", "error")
                return
            if not os.path.isfile(local_zip):
                self.set_transfer_status(local_status, "Local ZIP file was not found.", "error")
                return
            if not local_zip.lower().endswith(".zip"):
                self.set_transfer_status(local_status, "Please select a ZIP file.", "error")
                return

            self.start_transfer_button_loading(local_import_btn, "Import")
            self.set_transfer_status(local_status, "Importing local face dataset ZIP...", "normal")
            selected_name = os.path.basename(local_zip)
            actor = self.get_audit_actor()

            def local_worker():
                try:
                    data = self._local_face_request("POST", "/face-data/import", {"zip_path": local_zip}, timeout=120)
                    message = data.get("message", "Face data imported.")
                    backup_filename = data.get("backup_filename", "")
                    if backup_filename:
                        message = f"{message} Backup created: {backup_filename}"
                    imported_users = data.get("imported_users", [])
                    skipped_users_count = int(data.get("skipped_users_count", 0) or 0)
                    if data.get("import_mode") in ("add_on", "add_new_only"):
                        skipped_users_count = 0
                    for k in ("added_ids", "merged_users", "imported_ids"):
                        if not imported_users and isinstance(data.get(k, None), list):
                            imported_users = data.get(k, [])

                    def done():
                        self.finish_import_progress_then_success(root, dialog, selected_name, imported_users, skipped_users_count, message)
                        self.append_face_log(f"LOCAL_IMPORT: {message}")
                        self.write_sas_log(
                            "FACE DATA IMPORTED FROM LOCAL",
                            actor=actor,
                            details={
                                "Local ZIP": local_zip,
                                "ZIP file": selected_name,
                                "Imported users": ", ".join(str(item).upper() for item in imported_users) or "Merged/no new users",
                            },
                        )
                        self._local_face_refresh_users()

                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)

                    def fail(err=err):
                        self.show_transfer_button_failed(local_import_btn, "Import  →")
                        self.set_transfer_status(local_status, f"Local import failed: {err}", "error")
                        self.append_face_log(f"LOCAL_IMPORT_FAILED: {err}")
                        self.write_sas_log(
                            "FACE DATA LOCAL IMPORT FAILED",
                            actor=actor,
                            details={"Local ZIP": local_zip, "Result": "Failed"},
                        )

                    self.qt_after(0, fail)

            Thread(target=local_worker, daemon=True).start()

        connect.clicked.connect(load_zip_files)
        import_btn.clicked.connect(import_selected)
        local_import_btn.clicked.connect(import_local_zip)
        self._show_card_dialog(dialog)


    def _local_face_restore_backup(self: Any):
        """Open local backup restore/delete popup."""
        dialog, root = self.create_transfer_dialog_base(
            "Restore Face Data Backup",
            "",
            "R",
            height=560,
        )
        setattr(dialog, "_card_dialog_y_offset", -18)

        title = QLabel("Local Backup Versions")
        title.setObjectName("TransferFieldLabel")
        root.addWidget(title)

        list_wrap = QFrame()
        list_wrap.setObjectName("TransferZipList")
        list_layout = QVBoxLayout(list_wrap)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(210 if not self.compact_mode else 180)
        self.make_scrollbar_invisible(scroll)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)
        scroll.setWidget(body)
        list_layout.addWidget(scroll)
        root.addWidget(list_wrap, 1)

        status = QLabel("Loading local backups...")
        status.setObjectName("TransferStatus")
        status.setWordWrap(True)
        root.addWidget(status)

        state = {
            "backups": [],
            "selected": None,
            "selected_row": None,
            "confirm_restore": "",
            "confirm_delete": "",
        }

        def clear_body():
            while body_layout.count():
                item = body_layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        def backup_key(backup):
            return backup.get("path") or backup.get("name") or ""

        def reset_confirm_buttons():
            state["confirm_restore"] = ""
            state["confirm_delete"] = ""
            restore_btn.setText("Restore")
            delete_btn.setText("Delete Backup")

        def render_backups():
            clear_body()
            backups = state.get("backups", [])
            if not backups:
                msg = QLabel("No local backups found.")
                msg.setObjectName("TransferStatus")
                body_layout.addWidget(msg)
                body_layout.addStretch()
                restore_btn.setEnabled(False)
                delete_btn.setEnabled(False)
                return

            current_selected_key = backup_key(state["selected"]) if state.get("selected") else ""
            for backup in backups:
                row = QFrame()
                row.setObjectName("TransferZipRow")
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row_layout = QVBoxLayout(row)
                row_layout.setContentsMargins(8, 6, 8, 6)
                row_layout.setSpacing(2)

                name = QLabel(str(backup.get("name", "")))
                name.setObjectName("TransferZipName")
                name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                meta_text = "{} | {} | {} user(s)".format(
                    backup.get("modified", ""),
                    backup.get("size_text", ""),
                    backup.get("user_count", 0),
                )
                reason = str(backup.get("reason") or "").replace("_", " ").strip()
                if reason:
                    meta_text = f"{meta_text} | {reason}"
                meta = QLabel(meta_text)
                meta.setObjectName("TransferStatus")
                meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

                row_layout.addWidget(name)
                row_layout.addWidget(meta)

                is_selected = bool(current_selected_key and backup_key(backup) == current_selected_key)
                row.setProperty("selected", is_selected)
                if is_selected:
                    state["selected_row"] = row

                def select_backup(event, selected_backup=backup, selected_row=row):
                    self.clear_transfer_text_selection(dialog)
                    for index in range(body_layout.count()):
                        item = body_layout.itemAt(index)
                        widget = item.widget() if item is not None else None
                        if widget is not None and widget.objectName() == "TransferZipRow":
                            widget.setProperty("selected", False)
                            widget.style().unpolish(widget)
                            widget.style().polish(widget)
                    state["selected"] = selected_backup
                    state["selected_row"] = selected_row
                    reset_confirm_buttons()
                    selected_row.setProperty("selected", True)
                    selected_row.style().unpolish(selected_row)
                    selected_row.style().polish(selected_row)
                    restore_btn.setEnabled(True)
                    delete_btn.setEnabled(True)
                    self.set_transfer_status(status, f"Selected: {selected_backup.get('name', '')}", "normal")

                row.mousePressEvent = select_backup
                body_layout.addWidget(row)
                row.style().unpolish(row)
                row.style().polish(row)
            body_layout.addStretch()
            has_selection = bool(state.get("selected"))
            restore_btn.setEnabled(has_selection)
            delete_btn.setEnabled(has_selection)

        actions = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("TransferCancelButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(dialog.reject)

        delete_btn = QPushButton("Delete Backup")
        delete_btn.setObjectName("TransferSecondaryActionButton")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setEnabled(False)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("TransferCancelButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        restore_btn = QPushButton("Restore")
        restore_btn.setObjectName("TransferPrimaryButton")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setEnabled(False)

        actions.addWidget(cancel_btn)
        actions.addWidget(delete_btn)
        actions.addStretch()
        actions.addWidget(refresh_btn)
        actions.addWidget(restore_btn)
        root.addLayout(actions)

        def load_backups():
            reset_confirm_buttons()
            restore_btn.setEnabled(False)
            delete_btn.setEnabled(False)
            self.set_transfer_status(status, "Loading local backups...", "normal")

            def worker():
                try:
                    data = self.local_face_service.request("GET", "/face-data/backups", payload={}, timeout=30)
                    backups = data.get("backups", [])

                    def done():
                        state["backups"] = backups
                        state["selected"] = None
                        state["selected_row"] = None
                        render_backups()
                        self.set_transfer_status(
                            status,
                            f"Found {len(backups)} backup version(s)." if backups else "No local backups found.",
                            "success" if backups else "normal",
                        )

                    self.qt_after(0, done)
                except Exception as exc:
                    err = str(exc)

                    def failed(err=err):
                        state["backups"] = []
                        state["selected"] = None
                        render_backups()
                        self.set_transfer_status(status, f"Load failed: {err}", "error")

                    self.qt_after(0, failed)

            Thread(target=worker, daemon=True).start()

        def delete_selected():
            selected = state.get("selected")
            if not selected:
                self.set_transfer_status(status, "Please select a backup first.", "error")
                return
            key = backup_key(selected)
            if state.get("confirm_delete") != key:
                state["confirm_delete"] = key
                state["confirm_restore"] = ""
                delete_btn.setText("Confirm Delete")
                restore_btn.setText("Restore")
                self.set_transfer_status(status, "Press Confirm Delete to remove the selected backup.", "error")
                return

            delete_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            self.start_transfer_button_loading(delete_btn, "Delete")
            actor = self.get_audit_actor()

            def worker():
                try:
                    data = self.local_face_service.request(
                        "POST",
                        "/face-data/delete-backup",
                        payload={"zip_path": key},
                        timeout=30,
                    )
                    deleted_name = data.get("deleted_filename") or selected.get("name", "")

                    def done():
                        self.show_transfer_button_success(delete_btn, "Deleted", "Delete Backup")
                        self.append_face_log(f"BACKUP_DELETED: {deleted_name}")
                        self.write_sas_log(
                            "FACE DATA BACKUP DELETED",
                            actor=actor,
                            details={"Backup file": deleted_name},
                        )
                        self.set_transfer_status(status, f"Deleted backup: {deleted_name}", "success")
                        load_backups()

                    self.qt_after(0, done)
                except Exception as exc:
                    err = str(exc)

                    def failed(err=err):
                        self.show_transfer_button_failed(delete_btn, "Delete Backup")
                        self.set_transfer_status(status, f"Delete failed: {err}", "error")
                        self.append_face_log(f"BACKUP_DELETE_FAILED: {err}")

                    self.qt_after(0, failed)

            Thread(target=worker, daemon=True).start()

        def restore_selected():
            selected = state.get("selected")
            if not selected:
                self.set_transfer_status(status, "Please select a backup first.", "error")
                return
            key = backup_key(selected)
            if state.get("confirm_restore") != key:
                state["confirm_restore"] = key
                state["confirm_delete"] = ""
                restore_btn.setText("Confirm Restore")
                delete_btn.setText("Delete Backup")
                self.set_transfer_status(status, "Press Confirm Restore to replace the current face data.", "error")
                return

            restore_btn.setFocus()
            self.clear_transfer_text_selection(dialog)
            self.start_transfer_button_loading(restore_btn, "Restore")
            actor = self.get_audit_actor()

            def worker():
                try:
                    data = self.local_face_service.request(
                        "POST",
                        "/face-data/restore-backup",
                        payload={"zip_path": key},
                        timeout=120,
                    )
                    restored_name = data.get("backup_filename") or selected.get("name", "")
                    safety_name = data.get("safety_backup_filename", "")

                    def done():
                        self.show_transfer_button_success(restore_btn, "Restored", "Restore")
                        message = f"Restored backup: {restored_name}"
                        if safety_name:
                            message = f"{message}. Safety backup created: {safety_name}"
                        self.set_transfer_status(status, message, "success")
                        self.append_face_log(f"BACKUP_RESTORED: {restored_name}")
                        self.write_sas_log(
                            "FACE DATA BACKUP RESTORED",
                            actor=actor,
                            details={
                                "Backup file": restored_name,
                                "Safety backup": safety_name or "Created before restore",
                            },
                        )
                        self._local_face_refresh_users()
                        load_backups()

                    self.qt_after(0, done)
                except Exception as exc:
                    err = str(exc)

                    def failed(err=err):
                        self.show_transfer_button_failed(restore_btn, "Restore")
                        self.set_transfer_status(status, f"Restore failed: {err}", "error")
                        self.append_face_log(f"BACKUP_RESTORE_FAILED: {err}")

                    self.qt_after(0, failed)

            Thread(target=worker, daemon=True).start()

        refresh_btn.clicked.connect(load_backups)
        delete_btn.clicked.connect(delete_selected)
        restore_btn.clicked.connect(restore_selected)
        load_backups()
        self._show_card_dialog(dialog)

    def show_delete_complete_popup(self: Any, ntid: str, dataset_removed: bool = False, encodings_removed: int = 0):
        dialog = DeleteCompleteDialog(
            self,
            ntid=ntid,
            dataset_removed=dataset_removed,
            encodings_removed=encodings_removed,
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
