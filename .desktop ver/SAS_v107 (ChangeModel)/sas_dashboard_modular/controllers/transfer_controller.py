from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class TransferControllerMixin(DashboardMixinBase):
    def clear_transfer_text_selection(self, dialog=None):
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


    def _force_clear_card_dialog_background(self, force: bool = False):
        """Restore the dashboard after all frameless card popups are closed.

        Multiple card dialogs can overlap.  For example, the user can keep the
        SFTP send/success card open while the Pending Received card appears.
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


    def _show_card_dialog(self, dialog: QDialog):
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
            # overlapping SFTP and received-data popups.
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



    def transfer_input_row(self, label_text: str, value: str = "", readonly: bool = False, password: bool = False, placeholder: str = ""):
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


    def add_path_browse_button(self, row_layout, path_edit):
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



    def create_transfer_dialog_base(self, title_text: str, subtitle_text: str, icon_text: str, height: int = 620):
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


    def rebuild_export_loading_card(self, root, dialog):
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
        node_value = QLabel("PI API")
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
                    status = getattr(self, "sftp_status_label", None) or QLabel("")
                    status.setText(status_messages[dialog._export_status_index])
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start(90)
        dialog._export_loading_timer = timer



    def stop_export_loading_timer(self, dialog):
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



    def finish_export_progress_then_success(self, root, dialog, message: str, filename: str = ""):
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


    def rebuild_export_success_card(self, root, dialog, message: str, filename: str = ""):
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


    def rebuild_export_failed_card(self, root, dialog, error_text: str):
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

        subtitle = QLabel(error_text or "Export failed. Please check NTID, password, server path, and Pi API.")
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



    def rebuild_import_loading_card(self, root, dialog, source_name: str = ""):
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
                    status = getattr(self, "sftp_status_label", None) or QLabel("")
                    status.setText(status_messages[dialog._export_status_index])
            except Exception:
                pass

        timer.timeout.connect(tick)
        timer.start(90)
        dialog._export_loading_timer = timer


    def finish_import_progress_then_success(self, root, dialog, source_name: str, imported_users, skipped_users_count: int = 0, message: str = ""):
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


    def rebuild_import_success_card(self, root, dialog, source_name: str, imported_users, skipped_users_count: int = 0, message: str = ""):
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


    def rebuild_import_failed_card(self, root, dialog, error_text: str):
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

        subtitle = QLabel(error_text or "Import failed. Please check the ZIP file and Pi API.")
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



    def _set_transfer_tab_selected(self, buttons, stack, index: int):
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


    def _create_transfer_tabs(self, root, names):
        """Create Auto-Capture-style snake tabs and a QStackedWidget for transfer dialogs."""
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


    def _browse_zip_file_into(self, row_layout, path_edit):
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


    def _validate_windows_download_inputs(self, windows_username: str, windows_password: str, save_folder: str, status) -> bool:
        if not windows_username.strip():
            self.set_transfer_status(status, "Windows Username / NTID is required.", "error")
            return False
        if not windows_password.strip():
            self.set_transfer_status(status, "Windows Password is required.", "error")
            return False
        if not save_folder.strip():
            self.set_transfer_status(status, "Windows save folder is required.", "error")
            return False
        return True


    def _download_dataset_sftp_to_windows(self, windows_username: str, windows_password: str, save_folder: str, status, button, done_callback=None):
        """Shared Export tab logic: SFTP pull from connected Pi and save ZIP on Windows."""
        if not getattr(self, "pi_connected", False):
            self.set_transfer_status(status, "Pi API is not connected. Please connect from Settings first.", "error")
            return
        if paramiko is None:
            self.set_transfer_status(status, "Paramiko is required for SFTP download in SAS. Please include/install paramiko in the Windows build.", "error")
            return
        if not self._validate_windows_download_inputs(windows_username, windows_password, save_folder, status):
            return

        host, port, username, password = self._get_backend_pi_sftp_config()
        if not host:
            self.set_transfer_status(status, "Pi hostname/IP is not configured. Please connect the Pi in Settings first.", "error")
            return
        if not username:
            self.set_transfer_status(status, "Unable to fetch connected Pi username for SFTP. Please reconnect the Pi and try again.", "error")
            return
        if not password:
            self.set_transfer_status(status, "Unable to derive Pi SFTP password from username. Please reconnect the Pi and try again.", "error")
            return

        self.start_transfer_button_loading(button, "Export")
        self.set_transfer_status(status, "Validating Windows credentials and preparing dataset ZIP on Raspberry Pi...", "normal")
        actor = self.get_audit_actor()

        def worker():
            transport = None
            sftp = None
            try:
                ad_user = windows_username.split("\\")[-1].split("@", 1)[0].strip()
                if not self._validate_ntid_password_in_ad(ad_user, windows_password):
                    raise RuntimeError("Windows credential validation failed. Please check username/password.")

                self._connect_smb_share_if_needed(save_folder, windows_username, windows_password)

                prepare = self._face_api_request("POST", "/face-data/sftp-prepare-download", {}, timeout=90)
                remote_path = prepare.get("remote_path") or prepare.get("zip_path") or ""
                filename = prepare.get("filename") or os.path.basename(str(remote_path))
                if not remote_path or not filename:
                    raise RuntimeError("Pi did not return a downloadable ZIP path.")

                os.makedirs(save_folder, exist_ok=True)
                local_path = os.path.join(save_folder, filename)

                self.qt_after(0, lambda: self.set_transfer_status(status, f"Connecting to current Pi {host}:{port} by SFTP and downloading dataset...", "normal"))

                ssh_lib = cast(Any, paramiko)
                transport = ssh_lib.Transport((host, int(port)))
                transport.connect(username=username, password=password)
                sftp = ssh_lib.SFTPClient.from_transport(transport)
                if sftp is None:
                    raise RuntimeError("SFTP connection was not created.")
                sftp.get(remote_path, local_path)

                message = prepare.get("message", "Dataset ZIP downloaded to Windows successfully.")

                def done():
                    self.show_transfer_button_success(button, "Downloaded", "Export  →")
                    self.set_transfer_status(status, f"{message}\nSaved to: {local_path}", "success")
                    self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS: {remote_path} -> {local_path}")
                    self.write_sas_log(
                        "FACE DATA DOWNLOADED TO LOCAL",
                        actor=actor,
                        details={
                            "Pi host": host,
                            "ZIP file": filename,
                            "Local folder": save_folder,
                        },
                    )
                    if callable(done_callback):
                        try:
                            done_callback(local_path)
                        except Exception:
                            pass

                self.qt_after(0, done)
            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.show_transfer_button_failed(button, "Export  →")
                    self.set_transfer_status(status, f"Download failed: {err}", "error")
                    self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS_FAILED: {err}")
                    self.write_sas_log(
                        "FACE DATA LOCAL DOWNLOAD FAILED",
                        actor=actor,
                        details={"Pi host": host, "Local folder": save_folder, "Result": "Failed"},
                    )

                self.qt_after(0, fail)
            finally:
                try:
                    if sftp is not None:
                        sftp.close()
                except Exception:
                    pass
                try:
                    if transport is not None:
                        transport.close()
                except Exception:
                    pass

        Thread(target=worker, daemon=True).start()



    def _face_api_export_data(self):
        """Open export popup with Server Path and SFTP download tabs."""
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

        sftp_page = QWidget()
        sftp_layout = QVBoxLayout(sftp_page)
        sftp_layout.setContentsMargins(0, 8, 0, 0)
        sftp_layout.setSpacing(9)
        win_row, win_user_edit, _, _ = self.transfer_input_row("Windows Username / NTID", "", readonly=False, placeholder="e.g. 1234567")
        win_pwd_row, win_pwd_edit, _, _ = self.transfer_input_row("Windows Password", "", readonly=False, password=True)
        save_default = ""
        save_row, save_edit, _, save_row_layout = self.transfer_input_row("Windows Save Folder", "", readonly=False, placeholder="e.g. C:\\Users\\Public\\Documents")
        self.add_path_browse_button(save_row_layout, save_edit)
        sftp_layout.addLayout(win_row)
        sftp_layout.addLayout(win_pwd_row)
        sftp_layout.addLayout(save_row)
        sftp_status = QLabel("")
        sftp_status.setObjectName("TransferStatus")
        sftp_status.setWordWrap(True)
        sftp_layout.addWidget(sftp_status)
        sftp_actions = QHBoxLayout()
        sftp_cancel = QPushButton("Cancel")
        sftp_cancel.setObjectName("TransferCancelButton")
        sftp_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        sftp_cancel.clicked.connect(dialog.reject)
        download_btn = QPushButton("Export  →")
        download_btn.setObjectName("TransferPrimaryButton")
        download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sftp_actions.addWidget(sftp_cancel)
        sftp_actions.addStretch()
        sftp_actions.addWidget(download_btn)
        sftp_layout.addLayout(sftp_actions)
        stack.addWidget(sftp_page)

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
                    data = self._face_api_request("POST", "/face-data/export", {"username": nt, "password": pw, "pc_save_path": sp, "target_folder": None}, timeout=300)
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
            self._download_dataset_sftp_to_windows(win_user_edit.text().strip(), win_pwd_edit.text(), save_edit.text().strip(), sftp_status, download_btn)

        export_btn.clicked.connect(do_export)
        download_btn.clicked.connect(do_download)
        self._show_card_dialog(dialog)


    def _face_api_import_data(self):
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
        local_layout.addLayout(local_ntid_row)
        local_layout.addLayout(local_pwd_row)
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
                    data = self._face_api_request("POST", "/face-data/list-server-zips", {"username": nt, "password": pw, "pc_save_path": sp}, timeout=90)
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
                    data = self._face_api_request("POST", "/face-data/import", {"zip_path": selected_path}, timeout=120)
                    message = data.get("message", "Face data imported.")
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
                        self._face_api_refresh_users()
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
            if not getattr(self, "pi_connected", False):
                self.set_transfer_status(local_status, "Pi API is not connected. Please connect from Settings first.", "error")
                return
            if paramiko is None:
                self.set_transfer_status(local_status, "Paramiko is required for local ZIP import because SAS uploads the ZIP to Pi by SFTP.", "error")
                return
            windows_username = local_ntid_edit.text().strip()
            windows_password = local_pwd_edit.text()
            local_zip = zip_edit.text().strip()
            if not windows_username:
                self.set_transfer_status(local_status, "Windows Username / NTID is required.", "error")
                return
            if not windows_password:
                self.set_transfer_status(local_status, "Windows Password is required.", "error")
                return
            if not local_zip:
                self.set_transfer_status(local_status, "Local Path file is required.", "error")
                return
            if not os.path.isfile(local_zip):
                self.set_transfer_status(local_status, "Local Path file was not found.", "error")
                return
            if not local_zip.lower().endswith(".zip"):
                self.set_transfer_status(local_status, "Please select a ZIP file.", "error")
                return
            host, port, username, password = self._get_backend_pi_sftp_config()
            if not host or not username or not password:
                self.set_transfer_status(local_status, "Unable to resolve connected Pi SFTP account. Please reconnect the Pi and try again.", "error")
                return
            self.start_transfer_button_loading(local_import_btn, "Import")
            self.set_transfer_status(local_status, "Validating Windows credentials and uploading local ZIP to Pi...", "normal")
            selected_name = os.path.basename(local_zip)
            actor = self.get_audit_actor()

            def worker():
                transport = None
                sftp = None
                try:
                    ad_user = windows_username.split("\\")[-1].split("@", 1)[0].strip()
                    if not self._validate_ntid_password_in_ad(ad_user, windows_password):
                        raise RuntimeError("Windows credential validation failed. Please check username/password.")
                    target = self._face_api_request("POST", "/face-data/sftp-import-target", {}, timeout=45)
                    remote_dir = str(target.get("remote_dir") or target.get("import_dir") or "").replace("\\", "/").rstrip("/")
                    if not remote_dir:
                        raise RuntimeError("Pi did not return an SFTP import target folder.")
                    remote_path = f"{remote_dir}/{selected_name}"
                    ssh_lib = cast(Any, paramiko)
                    transport = ssh_lib.Transport((host, int(port)))
                    transport.connect(username=username, password=password)
                    sftp = ssh_lib.SFTPClient.from_transport(transport)
                    if sftp is None:
                        raise RuntimeError("SFTP connection was not created.")
                    sftp.put(local_zip, remote_path)
                    self.qt_after(0, lambda: self.set_transfer_status(local_status, "ZIP uploaded. Importing on Raspberry Pi...", "normal"))
                    data = self._face_api_request("POST", "/face-data/import", {"zip_path": remote_path}, timeout=120)
                    message = data.get("message", "Face data imported.")
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
                                "Imported users": ", ".join(str(item).upper() for item in imported_users) or "No new users",
                            },
                        )
                        self._face_api_refresh_users()
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
                finally:
                    try:
                        if sftp is not None:
                            sftp.close()
                    except Exception:
                        pass
                    try:
                        if transport is not None:
                            transport.close()
                    except Exception:
                        pass
            Thread(target=worker, daemon=True).start()

        connect.clicked.connect(load_zip_files)
        import_btn.clicked.connect(import_selected)
        local_import_btn.clicked.connect(import_local_zip)
        self._show_card_dialog(dialog)


    def normalize_sftp_pending_path(self, path_text: str) -> str:
        """Return receiver pending folder path.

        User can enter the receiver project folder only, e.g. /home/pi/New.
        The app will automatically append /received_face_data/pending.
        If user already enters the pending folder, it is kept as-is.
        """
        path = str(path_text or "").strip().replace("\\", "/").rstrip("/")
        if not path:
            return ""

        if path.endswith("/received_face_data/pending"):
            return path

        if path.endswith("/received_face_data"):
            return path + "/pending"

        return path + "/received_face_data/pending"

    # --------------------------------------------------------
    # FACE DATA TRANSFER - MULTI-PI SFTP (Pi API owns state)
    # --------------------------------------------------------

    def _multi_sftp_set_status(self, label, text: str, state: str = "normal"):
        """Update a status label only when its visible state actually changes.

        Transfer polling runs in the background. Re-polishing an unchanged Qt
        widget every refresh makes tab animations and dialogs feel sluggish.
        """
        if label is None:
            return

        new_text = str(text or "")
        new_object_name = "MultiSftpStatusError" if state == "error" else "MultiSftpStatus"
        text_changed = label.text() != new_text
        style_changed = label.objectName() != new_object_name

        if text_changed:
            label.setText(new_text)

        if style_changed:
            label.setObjectName(new_object_name)
            try:
                label.style().unpolish(label)
                label.style().polish(label)
            except Exception:
                pass

        if text_changed or style_changed:
            try:
                label.update()
            except Exception:
                pass


    def _multi_sftp_filtered_targets(self, state):
        query = str(state.get("filter", "") or "").strip().casefold()
        targets = list(state.get("targets", []) or [])
        if not query:
            return targets
        return [target for target in targets if query in str(target).casefold()]


    def _multi_sftp_update_select_all(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        checkbox = state.get("select_all")
        if checkbox is None:
            return

        visible = self._multi_sftp_filtered_targets(state)
        selected = set(state.get("selected", set()) or set())
        all_visible_selected = bool(visible) and all(target in selected for target in visible)

        # Programmatic changes must not run select_all_changed(), otherwise
        # updating one target row could accidentally clear the full selection.
        state["updating_select_all"] = True
        try:
            checkbox.setChecked(all_visible_selected)
        finally:
            state["updating_select_all"] = False


    def _multi_sftp_refresh_target_rows(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        layout = state.get("target_layout")
        if layout is None:
            return

        self.clear_layout_widgets(layout)
        visible = self._multi_sftp_filtered_targets(state)
        selected = set(state.get("selected", set()) or set())

        if not visible:
            empty = QLabel("No saved target Pis match this search.")
            empty.setObjectName("MultiSftpHint")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(90)
            layout.addWidget(empty)
        else:
            for index, hostname in enumerate(visible):
                row = QFrame()
                row.setObjectName("MultiSftpTargetRow")
                row.setMinimumHeight(52 if not self.compact_mode else 46)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 8, 10, 8)
                row_layout.setSpacing(10)

                # Use a checkable QPushButton so the selected state always has
                # a visible ✓. The old styled QCheckBox used a black background
                # but did not render a tick on this deployed Windows environment.
                check = QPushButton("✓")
                check.setObjectName("MultiSftpTargetCheck")
                check.setCheckable(True)
                check.setChecked(hostname in selected)
                check.setCursor(Qt.CursorShape.PointingHandCursor)
                check.setToolTip(f"Select {hostname}")
                check.setFixedSize(28 if not self.compact_mode else 25, 28 if not self.compact_mode else 25)

                icon = QLabel("▣")
                icon.setObjectName("MultiSftpTargetIcon")
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon.setFixedSize(34 if not self.compact_mode else 30, 34 if not self.compact_mode else 30)

                name = QLabel(hostname)
                name.setObjectName("MultiSftpTargetName")
                name.setToolTip(hostname)

                delete = QPushButton("×")
                delete.setObjectName("MultiSftpDeleteButton")
                delete.setCursor(Qt.CursorShape.PointingHandCursor)
                delete.setToolTip(f"Remove {hostname} from the Pi target list")
                delete.setFixedSize(30 if not self.compact_mode else 27, 30 if not self.compact_mode else 27)

                def selection_changed(is_checked, host=hostname):
                    live_state = getattr(dialog, "_multi_sftp_state", {})
                    picked = set(live_state.get("selected", set()) or set())
                    if bool(is_checked):
                        picked.add(host)
                    else:
                        picked.discard(host)
                    live_state["selected"] = picked
                    self._multi_sftp_update_select_all(dialog)
                    self._multi_sftp_update_transfer_button(dialog)

                check.toggled.connect(selection_changed)
                delete.clicked.connect(lambda _checked=False, host=hostname: self._multi_sftp_remove_target(dialog, host))

                row_layout.addWidget(check)
                row_layout.addWidget(icon)
                row_layout.addWidget(name, 1)
                row_layout.addWidget(delete)
                layout.addWidget(row)

        layout.addStretch(1)
        self._multi_sftp_update_select_all(dialog)
        self._multi_sftp_update_transfer_button(dialog)


    def _multi_sftp_update_transfer_button(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        button = state.get("transfer_button")
        if button is None:
            return
        count = len(state.get("selected", set()) or set())
        button.setText("Transfer Selected" if count <= 0 else f"Transfer Selected ({count})")
        button.setEnabled(not bool(state.get("loading", False)))


    def _multi_sftp_render_setup(self, dialog):
        root = getattr(dialog, "_multi_sftp_root", None)
        state = getattr(dialog, "_multi_sftp_state", {})
        if root is None:
            return

        self.clear_layout_widgets(root)
        root.setContentsMargins(24 if not self.compact_mode else 20, 20 if not self.compact_mode else 16, 24 if not self.compact_mode else 20, 0)
        root.setSpacing(14 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("SFTP Transfer")
        title.setObjectName("MultiSftpTitle")
        badge = QLabel("Total Nodes: 0")
        badge.setObjectName("MultiSftpCountBadge")
        title_box.addWidget(title)
        title_box.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        close = QPushButton("×")
        close.setObjectName("MultiSftpCloseButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Close")
        close.clicked.connect(lambda: dialog.accept())
        header.addLayout(title_box, 1)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        hint = QLabel("Manage saved target Pis on the connected Raspberry Pi. The Pi creates one ZIP and sends to up to four targets at a time.")
        hint.setObjectName("MultiSftpHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        search = QLineEdit()
        search.setObjectName("MultiSftpSearch")
        search.setPlaceholderText("⌕  Search Nodes...")
        search.setClearButtonEnabled(True)
        # Keep the Select All control separate from its text so the same
        # visible ✓-button style is used as the target Pi rows.
        select_all_wrap = QWidget()
        select_all_wrap.setObjectName("MultiSftpSelectAllWrap")
        select_all_layout = QHBoxLayout(select_all_wrap)
        select_all_layout.setContentsMargins(0, 0, 0, 0)
        select_all_layout.setSpacing(8)

        select_all = QPushButton("✓")
        select_all.setObjectName("MultiSftpSelectAll")
        select_all.setCheckable(True)
        select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all.setToolTip("Select all visible target Pis")
        select_all.setFixedSize(30 if not self.compact_mode else 27, 30 if not self.compact_mode else 27)

        select_all_text = QPushButton("Select All")
        select_all_text.setObjectName("MultiSftpSelectAllText")
        select_all_text.setCursor(Qt.CursorShape.PointingHandCursor)
        select_all_text.setToolTip("Select all visible target Pis")
        select_all_text.setFlat(True)

        select_all_layout.addWidget(select_all)
        select_all_layout.addWidget(select_all_text)

        controls.addWidget(search, 1)
        controls.addWidget(select_all_wrap)
        root.addLayout(controls)

        scroll = QScrollArea()
        scroll.setObjectName("MultiSftpTargetScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(252 if not self.compact_mode else 220)
        scroll.setMaximumHeight(288 if not self.compact_mode else 252)
        target_container = QFrame()
        target_container.setObjectName("MultiSftpTargetList")
        target_layout = QVBoxLayout(target_container)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(0)
        scroll.setWidget(target_container)
        root.addWidget(scroll)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        host_input = QLineEdit()
        host_input.setObjectName("MultiSftpAddInput")
        host_input.setPlaceholderText("Enter Hostname or IP")
        add_btn = QPushButton("＋  Add Hostname")
        add_btn.setObjectName("MultiSftpAddButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_row.addWidget(host_input, 1)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        status = QLabel("")
        status.setObjectName("MultiSftpStatus")
        status.setWordWrap(True)
        root.addWidget(status)

        footer = QFrame()
        footer.setObjectName("MultiSftpFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(8)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("MultiSftpFooterCancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer = QPushButton("Transfer Selected")
        transfer.setObjectName("MultiSftpPrimaryButton")
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_layout.addWidget(cancel)
        footer_layout.addStretch(1)
        footer_layout.addWidget(transfer)
        root.addWidget(footer)

        state.update({
            "title": title,
            "count_badge": badge,
            "search": search,
            "select_all": select_all,
            "target_layout": target_layout,
            "host_input": host_input,
            "add_button": add_btn,
            "status": status,
            "transfer_button": transfer,
            "cancel_button": cancel,
            "loading": False,
            "showing_progress": False,
        })

        def search_changed(text):
            live = getattr(dialog, "_multi_sftp_state", {})
            live["filter"] = str(text or "")
            self._multi_sftp_refresh_target_rows(dialog)

        def select_all_changed(is_checked):
            live = getattr(dialog, "_multi_sftp_state", {})
            if live.get("updating_select_all"):
                return
            visible = self._multi_sftp_filtered_targets(live)
            selected = set(live.get("selected", set()) or set())
            if bool(is_checked):
                selected.update(visible)
            else:
                selected.difference_update(visible)
            live["selected"] = selected
            self._multi_sftp_refresh_target_rows(dialog)

        search.textChanged.connect(search_changed)
        select_all.toggled.connect(select_all_changed)
        select_all_text.clicked.connect(select_all.click)
        add_btn.clicked.connect(lambda: self._multi_sftp_add_target(dialog))
        host_input.returnPressed.connect(lambda: self._multi_sftp_add_target(dialog))
        transfer.clicked.connect(lambda: self._multi_sftp_start_batch(dialog))
        cancel.clicked.connect(dialog.accept)

        self._multi_sftp_refresh_target_rows(dialog)


    def _multi_sftp_load_targets(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        self._multi_sftp_set_status(state.get("status"), "Loading saved target Pis from the Raspberry Pi...", "normal")

        def worker():
            try:
                data = self.face_api_service.list_multi_sftp_targets()
                targets = data.get("targets", []) if isinstance(data, dict) else []
                config = data.get("config", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                targets, config, error = [], {}, str(exc)

            def done():
                # This callback can finish before QDialog.exec() makes the
                # modal card visible, so do not reject it based on isVisible().
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if error:
                    self._multi_sftp_set_status(live.get("status"), f"Could not load SFTP target list: {error}", "error")
                else:
                    live["targets"] = [str(item).strip() for item in targets if str(item).strip()]
                    live["selected"] = set(live.get("selected", set()) or set()).intersection(set(live["targets"]))
                    live["config"] = config if isinstance(config, dict) else {}
                    max_workers = int(live["config"].get("max_concurrent_transfers", 4) or 4)
                    self._multi_sftp_set_status(live.get("status"), f"Loaded {len(live['targets'])} saved target Pi(s). Pi will run up to {max_workers} uploads at one time.", "normal")
                    badge = live.get("count_badge")
                    if badge is not None:
                        badge.setText(f"Total Nodes: {len(live['targets'])}")
                self._multi_sftp_refresh_target_rows(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasLoadMultiSftpTargets").start()


    def _multi_sftp_add_target(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        host_input = state.get("host_input")
        hostname = host_input.text().strip() if host_input is not None else ""
        if not hostname:
            self._multi_sftp_set_status(state.get("status"), "Enter a hostname or IP address first.", "error")
            return
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        if state.get("add_button") is not None:
            state["add_button"].setEnabled(False)
        self._multi_sftp_set_status(state.get("status"), f"Saving {hostname} to the Pi target list...", "normal")

        def worker():
            try:
                data = self.face_api_service.add_multi_sftp_target(hostname)
                targets = data.get("targets", []) if isinstance(data, dict) else []
                message = str(data.get("message", "Target added.")) if isinstance(data, dict) else "Target added."
                error = ""
            except Exception as exc:
                targets, message, error = [], "", str(exc)

            def done():
                if not dialog.isVisible():
                    return
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if live.get("add_button") is not None:
                    live["add_button"].setEnabled(True)
                if error:
                    self._multi_sftp_set_status(live.get("status"), f"Could not add target: {error}", "error")
                else:
                    live["targets"] = [str(item).strip() for item in targets if str(item).strip()]
                    if live.get("host_input") is not None:
                        live["host_input"].clear()
                    self._multi_sftp_set_status(live.get("status"), message, "normal")
                    badge = live.get("count_badge")
                    if badge is not None:
                        badge.setText(f"Total Nodes: {len(live['targets'])}")
                self._multi_sftp_refresh_target_rows(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasAddMultiSftpTarget").start()


    def _multi_sftp_remove_target(self, dialog, hostname: str):
        state = getattr(dialog, "_multi_sftp_state", {})
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        self._multi_sftp_set_status(state.get("status"), f"Removing {hostname} from the Pi target list...", "normal")

        def worker():
            try:
                data = self.face_api_service.remove_multi_sftp_target(hostname)
                targets = data.get("targets", []) if isinstance(data, dict) else []
                message = str(data.get("message", "Target removed.")) if isinstance(data, dict) else "Target removed."
                error = ""
            except Exception as exc:
                targets, message, error = [], "", str(exc)

            def done():
                if not dialog.isVisible():
                    return
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if error:
                    self._multi_sftp_set_status(live.get("status"), f"Could not remove target: {error}", "error")
                else:
                    live["targets"] = [str(item).strip() for item in targets if str(item).strip()]
                    selected = set(live.get("selected", set()) or set())
                    selected.discard(hostname)
                    live["selected"] = selected
                    self._multi_sftp_set_status(live.get("status"), message, "normal")
                    badge = live.get("count_badge")
                    if badge is not None:
                        badge.setText(f"Total Nodes: {len(live['targets'])}")
                self._multi_sftp_refresh_target_rows(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasRemoveMultiSftpTarget").start()


    def _multi_sftp_start_batch(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        targets = [host for host in state.get("targets", []) if host in set(state.get("selected", set()) or set())]
        if not targets:
            self._multi_sftp_set_status(state.get("status"), "Select at least one target Pi before transferring.", "error")
            return
        if state.get("loading"):
            return
        state["loading"] = True
        self._multi_sftp_update_transfer_button(dialog)
        self._multi_sftp_set_status(state.get("status"), f"Creating transfer batch for {len(targets)} target Pi(s)...", "normal")

        def worker():
            try:
                data = self.face_api_service.start_multi_sftp_transfer(targets)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                message = str(data.get("message", "Multi-Pi transfer started.")) if isinstance(data, dict) else "Multi-Pi transfer started."
                error = ""
            except Exception as exc:
                snapshot, message, error = {}, "", str(exc)

            def done():
                if not dialog.isVisible():
                    return
                live = getattr(dialog, "_multi_sftp_state", {})
                live["loading"] = False
                if error or not snapshot.get("batch_id"):
                    self._multi_sftp_set_status(live.get("status"), f"Could not start transfer: {error or 'Pi did not return a transfer batch.'}", "error")
                    self.write_sas_log(
                        "SFTP FACE DATA SEND FAILED",
                        actor=self.get_audit_actor(),
                        details={
                            "Target Pi": ", ".join(targets),
                            "Target count": len(targets),
                            "Result": "Failed",
                        },
                    )
                    self._multi_sftp_update_transfer_button(dialog)
                    return
                live["batch_id"] = str(snapshot.get("batch_id"))
                live["snapshot"] = snapshot
                live["audit_actor"] = self.get_audit_actor()
                live["audit_targets"] = list(targets)
                live["audit_completion_logged"] = False
                self.append_face_log(f"SFTP_MULTI_STARTED: {message} | {len(targets)} target Pi(s)")
                self.write_sas_log(
                    "SFTP FACE DATA SEND STARTED",
                    actor=live["audit_actor"],
                    details={
                        "Target Pi": ", ".join(targets),
                        "Target count": len(targets),
                        "ZIP file": os.path.basename(str(snapshot.get("local_zip", "") or "")) or "Face data package",
                    },
                )

                # The target-selection popup is finished.  Close it first;
                # _face_api_sftp_send() will open a separate modeless progress
                # window for this same Pi-owned batch immediately afterwards.
                dialog._multi_sftp_launch_progress = {
                    "batch_id": live["batch_id"],
                    "snapshot": snapshot,
                    "audit_actor": live["audit_actor"],
                    "audit_targets": list(live["audit_targets"]),
                }
                dialog.accept()

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasStartMultiSftpBatch").start()


    def _multi_sftp_render_progress(self, dialog, snapshot):
        root = getattr(dialog, "_multi_sftp_root", None)
        state = getattr(dialog, "_multi_sftp_state", {})
        if root is None:
            return

        self.clear_layout_widgets(root)
        root.setContentsMargins(24 if not self.compact_mode else 20, 20 if not self.compact_mode else 16, 24 if not self.compact_mode else 20, 0)
        root.setSpacing(12 if not self.compact_mode else 10)

        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("SFTP Transfer in Progress")
        title.setObjectName("MultiSftpTitle")
        badge = QLabel("")
        badge.setObjectName("MultiSftpCountBadge")
        title_box.addWidget(title)
        title_box.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        minimize = None
        if state.get("modeless_progress", False):
            minimize = QPushButton("−")
            minimize.setObjectName("MultiSftpMinimizeButton")
            minimize.setCursor(Qt.CursorShape.PointingHandCursor)
            minimize.setToolTip("Hide progress window; transfer continues on the Raspberry Pi")
            minimize.clicked.connect(lambda: self._multi_sftp_minimize_progress(dialog))

        close = QPushButton("×")
        close.setObjectName("MultiSftpCloseButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Close and delete the temporary ZIP when transfers have stopped")
        close.clicked.connect(lambda: self._multi_sftp_request_close(dialog))
        header.addLayout(title_box, 1)
        if minimize is not None:
            header.addWidget(minimize, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        overall = QProgressBar()
        overall.setObjectName("MultiSftpOverallProgress")
        overall.setTextVisible(False)
        overall.setRange(0, 100)
        overall.setFixedHeight(8)
        root.addWidget(overall)

        scroll = QScrollArea()
        scroll.setObjectName("MultiSftpTargetScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(252 if not self.compact_mode else 220)
        scroll.setMaximumHeight(290 if not self.compact_mode else 254)
        list_widget = QFrame()
        list_widget.setObjectName("MultiSftpTargetList")
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        scroll.setWidget(list_widget)
        root.addWidget(scroll)

        status = QLabel("")
        status.setObjectName("MultiSftpStatus")
        status.setWordWrap(True)
        root.addWidget(status)

        footer = QFrame()
        footer.setObjectName("MultiSftpFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(8)

        # The left footer control is used only after a completed batch has
        # failed targets.  During an active transfer it stays hidden so there
        # is one clear cancellation action: Abort Transfer.
        back = QPushButton("Back")
        back.setObjectName("MultiSftpFooterCancel")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.hide()

        action = QPushButton("Abort Transfer")
        action.setObjectName("MultiSftpAbortButton")
        action.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_layout.addWidget(back)
        footer_layout.addStretch(1)
        footer_layout.addWidget(action)
        root.addWidget(footer)

        state.update({
            "showing_progress": True,
            "progress_title": title,
            "progress_badge": badge,
            "overall_progress": overall,
            "progress_list_layout": list_layout,
            "progress_rows": {},
            "progress_status": status,
            "progress_cancel": back,
            "progress_action": action,
            "progress_minimize": minimize,
        })
        # Back safely cleans up the batch and returns to target selection.  It
        # is hidden while a transfer is running; Abort Transfer performs the
        # equivalent cancel-and-return flow for active transfers.
        back.clicked.connect(lambda: self._multi_sftp_request_close(dialog))
        action.clicked.connect(lambda: self._multi_sftp_progress_action(dialog))
        self._multi_sftp_apply_snapshot(dialog, snapshot)


    def _multi_sftp_build_progress_row(self, hostname: str):
        row = QFrame()
        row.setObjectName("MultiSftpProgressRow")
        row.setMinimumHeight(54 if not self.compact_mode else 48)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon = QLabel("▣")
        icon.setObjectName("MultiSftpTargetIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(34 if not self.compact_mode else 30, 34 if not self.compact_mode else 30)

        centre = QVBoxLayout()
        centre.setSpacing(3)
        host_label = QLabel(hostname)
        host_label.setObjectName("MultiSftpProgressHost")
        row_progress = QProgressBar()
        row_progress.setObjectName("MultiSftpRowProgress")
        row_progress.setRange(0, 100)
        row_progress.setTextVisible(False)
        row_progress.setFixedHeight(4)
        row_progress.setFixedWidth(120 if not self.compact_mode else 90)
        row_progress.hide()
        centre.addWidget(host_label)
        centre.addWidget(row_progress)

        status = QLabel("Queued")
        status.setObjectName("MultiSftpStatusQueued")
        status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status.setWordWrap(False)
        status.setMaximumWidth(190 if not self.compact_mode else 145)

        layout.addWidget(icon)
        layout.addLayout(centre, 1)
        layout.addWidget(status)
        return row, {"status": status, "progress": row_progress, "host": host_label}


    def _multi_sftp_apply_snapshot(self, dialog, snapshot):
        """Apply Pi batch state with minimal Qt work.

        The Pi owns transfer state. SAS only needs to redraw parts that changed.
        This avoids restyling every row every polling cycle, which previously
        made tab switches and modal transitions feel heavy.
        """
        state = getattr(dialog, "_multi_sftp_state", {})
        if not isinstance(snapshot, dict):
            return

        state["snapshot"] = snapshot
        jobs = list(snapshot.get("jobs", []) or [])
        summary = dict(snapshot.get("summary", {}) or {})
        total = int(summary.get("total", len(jobs)) or len(jobs))
        success = int(summary.get("success", 0) or 0)
        failed = int(summary.get("failed", 0) or 0)
        cancelled = int(summary.get("cancelled", 0) or 0)
        completed = min(total, success + failed + cancelled)
        running = bool(snapshot.get("running", False))

        title_text = "SFTP Transfer in Progress" if running else "SFTP Transfer Complete"
        title = state.get("progress_title")
        if title is not None and title.text() != title_text:
            title.setText(title_text)

        extra = f" • {failed} Failed" if failed else ""
        if cancelled:
            extra += f" • {cancelled} Cancelled"
        badge_text = f"{completed} / {total} Nodes Completed{extra}"
        badge = state.get("progress_badge")
        if badge is not None and badge.text() != badge_text:
            badge.setText(badge_text)

        overall_percent = int((completed / total) * 100) if total else 0
        overall = state.get("overall_progress")
        if overall is not None and overall.value() != overall_percent:
            overall.setValue(overall_percent)

        layout = state.get("progress_list_layout")
        rows = state.setdefault("progress_rows", {})
        hosts = [
            str(job.get("hostname", "")).strip()
            for job in jobs
            if str(job.get("hostname", "")).strip()
        ]

        # The host list normally stays fixed for a batch. Rebuild only if it
        # genuinely changes, not on every status refresh.
        if layout is not None and set(rows.keys()) != set(hosts):
            self.clear_layout_widgets(layout)
            rows.clear()
            for job in jobs:
                host = str(job.get("hostname", "")).strip()
                if not host:
                    continue
                row, widgets = self._multi_sftp_build_progress_row(host)
                widgets["last_visible_state"] = None
                rows[host] = widgets
                layout.addWidget(row)
            layout.addStretch(1)

        for job in jobs:
            host = str(job.get("hostname", "")).strip()
            widgets = rows.get(host)
            if not widgets:
                continue

            status_value = str(job.get("status", "Waiting") or "Waiting")
            progress_value = max(0, min(100, int(job.get("progress", 0) or 0)))

            # Keep Multi-Pi SFTP results simple for SAS users.  The Pi may
            # return technical details such as timeouts or hostname-resolution
            # errors, but SAS deliberately exposes only the final result:
            # Completed or Failed.  Detailed diagnostics remain available in
            # the Pi-side logs for troubleshooting.
            status_tooltip = ""
            if status_value == "Success":
                display = "✓  Completed"
                object_name = "MultiSftpStatusSuccess"
                show_progress = False
            elif status_value.startswith("Failed") or status_value == "Cancelled":
                display = "Failed"
                object_name = "MultiSftpStatusError"
                show_progress = False
            elif status_value in ("Connecting", "Uploading"):
                display = (
                    f"{status_value} {progress_value}%"
                    if status_value == "Uploading"
                    else "Connecting..."
                )
                object_name = "MultiSftpStatusActive"
                show_progress = True
            else:
                display = "Queued"
                object_name = "MultiSftpStatusQueued"
                show_progress = False

            visible_state = (
                display,
                object_name,
                status_tooltip,
                progress_value if show_progress else None,
                show_progress,
            )

            # A row only changes when Pi reports a different visible state.
            if widgets.get("last_visible_state") == visible_state:
                continue

            status_label = widgets["status"]
            progress = widgets["progress"]

            if status_label.toolTip() != status_tooltip:
                status_label.setToolTip(status_tooltip)

            if status_label.text() != display:
                status_label.setText(display)

            if status_label.objectName() != object_name:
                status_label.setObjectName(object_name)
                try:
                    status_label.style().unpolish(status_label)
                    status_label.style().polish(status_label)
                except Exception:
                    pass

            if show_progress:
                if progress.value() != progress_value:
                    progress.setValue(progress_value)
                if progress.isHidden():
                    progress.show()
            elif progress.isVisible():
                progress.hide()

            try:
                status_label.update()
            except Exception:
                pass

            widgets["last_visible_state"] = visible_state

        status_label = state.get("progress_status")
        batch_state = str(snapshot.get("state", "") or "")
        local_zip = str(snapshot.get("local_zip", "") or "")
        if running:
            progress_status_text = batch_state or "Transfer is running on the Raspberry Pi."
        elif failed or cancelled:
            progress_status_text = (
                "Transfer stopped. Retry failed targets or close this popup "
                "to delete the temporary ZIP."
            )
        else:
            progress_status_text = (
                "All selected target Pis received the package. Close this "
                "popup to delete the temporary ZIP."
            )

        if status_label is not None:
            self._multi_sftp_set_status(status_label, progress_status_text, "normal")
            if status_label.toolTip() != local_zip:
                status_label.setToolTip(local_zip)

        cancel_button = state.get("progress_cancel")
        action = state.get("progress_action")
        cancelling = bool(state.get("cancel_in_progress", False))

        if running:
            # While running there is only one cancellation control: the red
            # Abort Transfer button.  The left Back button stays hidden.
            if cancel_button is not None:
                cancel_button.hide()

            if action is not None:
                action_style_changed = action.objectName() != "MultiSftpAbortButton"
                next_text = "Aborting..." if cancelling else "Abort Transfer"
                if action.text() != next_text:
                    action.setText(next_text)
                if action_style_changed:
                    action.setObjectName("MultiSftpAbortButton")
                    try:
                        action.style().unpolish(action)
                        action.style().polish(action)
                    except Exception:
                        pass
                action.setEnabled(not cancelling)
                action.show()

        else:
            has_retry = bool(failed or cancelled)

            # A failed batch can return to the saved target list.  This is an
            # actual outlined button, not plain hover-only text.
            if cancel_button is not None:
                if has_retry:
                    if cancel_button.text() != "Back":
                        cancel_button.setText("Back")
                    cancel_button.setEnabled(True)
                    cancel_button.show()
                else:
                    cancel_button.hide()

            if action is not None:
                next_text = "Retry Failed" if has_retry else "Close"
                action_style_changed = action.objectName() != "MultiSftpPrimaryButton"
                if action.text() != next_text:
                    action.setText(next_text)
                if action_style_changed:
                    action.setObjectName("MultiSftpPrimaryButton")
                    try:
                        action.style().unpolish(action)
                        action.style().polish(action)
                    except Exception:
                        pass
                action.setEnabled(True)
                action.show()

        if not running and not state.get("audit_completion_logged", False):
            actor = str(state.get("audit_actor") or self.get_audit_actor()).upper()
            target_results = []
            for job in jobs:
                target_host = str(job.get("hostname", "") or "").strip()
                if not target_host:
                    continue
                target_status = str(job.get("status", "") or "").strip()
                result = "Completed" if target_status == "Success" else "Failed"
                target_results.append(f"{target_host}: {result}")

            self.write_sas_log(
                "SFTP FACE DATA SEND COMPLETED" if success == total and total > 0 else "SFTP FACE DATA SEND FINISHED",
                actor=actor,
                details={
                    "ZIP file": os.path.basename(local_zip) or "Face data package",
                    "Target results": ", ".join(target_results) or "No target result returned",
                    "Completed": success,
                    "Failed": failed + cancelled,
                },
            )
            state["audit_completion_logged"] = True

        minimize_button = state.get("progress_minimize")
        if minimize_button is not None:
            minimize_button.setEnabled(running)
            minimize_button.setToolTip(
                "Hide progress window; transfer continues on the Raspberry Pi"
                if running
                else "Transfer has finished"
            )

        if not running:
            timer = state.get("poll_timer")
            if timer is not None:
                timer.stop()

            # A hidden modeless window returns only after all Pi jobs are done,
            # allowing Retry Failed without disturbing normal SAS use.
            if state.get("modeless_progress") and state.get("minimized"):
                self._multi_sftp_restore_progress_window(dialog)

            if state.get("close_after_cancel"):
                self._multi_sftp_cleanup_and_close(
                    dialog,
                    reopen_targets=bool(
                        state.get("return_to_targets_after_close", True)
                    ),
                )


    def _multi_sftp_poll_interval_ms(self, dialog):
        """Use a gentle poll rate so normal SAS navigation stays smooth."""
        state = getattr(dialog, "_multi_sftp_state", {})
        # When minimized there is no visible progress UI to refresh. A slower
        # check is enough, while still detecting completion and restoring it.
        return 3000 if state.get("minimized") else 1500


    def _multi_sftp_apply_poll_interval(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        timer = state.get("poll_timer")
        if timer is not None:
            timer.setInterval(self._multi_sftp_poll_interval_ms(dialog))


    def _multi_sftp_start_polling(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        timer = state.get("poll_timer")
        if timer is None:
            timer = QTimer(dialog)
            timer.timeout.connect(lambda: self._multi_sftp_poll_batch(dialog))
            state["poll_timer"] = timer

        self._multi_sftp_apply_poll_interval(dialog)
        timer.start()

        # Refresh once immediately when the progress window opens or returns;
        # later refreshes use the calmer adaptive interval.
        self._multi_sftp_poll_batch(dialog)


    def _multi_sftp_poll_batch(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        batch_id = str(state.get("batch_id", "") or "")
        if not batch_id or state.get("poll_in_progress") or state.get("cleanup_requested"):
            return
        state["poll_in_progress"] = True

        def worker():
            try:
                data = self.face_api_service.get_multi_sftp_transfer(batch_id)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                snapshot, error = {}, str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                live["poll_in_progress"] = False
                if live.get("cleanup_requested"):
                    return
                if error:
                    self._multi_sftp_set_status(
                        live.get("progress_status"),
                        f"Could not refresh transfer status: {error}",
                        "error",
                    )
                    return
                self._multi_sftp_apply_snapshot(dialog, snapshot)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasPollMultiSftpBatch").start()


    def _multi_sftp_cancel_batch(self, dialog, close_after: bool = False):
        """Request Pi cancellation once; later close clicks can still queue return."""
        state = getattr(dialog, "_multi_sftp_state", {})
        batch_id = str(state.get("batch_id", "") or "")
        if not batch_id:
            return

        if close_after:
            state["close_after_cancel"] = True
            state["return_to_targets_after_close"] = True

        cancel_button = state.get("progress_cancel")
        action = state.get("progress_action")

        # Abort may already be in flight.  A later × click still marks the
        # dialog to return to the target list after the Pi has stopped.
        if state.get("cancel_in_progress"):
            if close_after:
                self._multi_sftp_set_status(
                    state.get("progress_status"),
                    "Cancellation is already in progress. This window will return to target selection after the Pi stops.",
                    "normal",
                )
            return

        state["cancel_in_progress"] = True
        self._multi_sftp_set_status(
            state.get("progress_status"),
            "Requesting transfer cancellation from the Raspberry Pi...",
            "normal",
        )

        if action is not None:
            action.setText("Aborting...")
            action.setEnabled(False)

        # The left Back button is intentionally hidden during active work.
        # Abort Transfer now owns the cancel-and-return behavior.
        if cancel_button is not None:
            cancel_button.hide()

        def worker():
            try:
                data = self.face_api_service.cancel_multi_sftp_transfer(batch_id)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                snapshot, error = {}, str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                live["cancel_in_progress"] = False
                if live.get("cleanup_requested"):
                    return

                if error:
                    # Cancellation did not reach the Pi. Restore controls so
                    # the user can retry instead of leaving a stuck popup.
                    live["close_after_cancel"] = False
                    live["return_to_targets_after_close"] = False
                    self._multi_sftp_set_status(
                        live.get("progress_status"),
                        f"Could not cancel transfer: {error}",
                        "error",
                    )
                    if live.get("progress_action") is not None:
                        live["progress_action"].setText("Abort Transfer")
                        live["progress_action"].setEnabled(True)
                    if live.get("progress_cancel") is not None:
                        live["progress_cancel"].hide()
                    return

                # A Pi cancel response can arrive before all worker threads
                # have fully stopped. Apply it when available, then continue
                # polling until the Pi reports running=False.
                if isinstance(snapshot, dict) and snapshot:
                    self._multi_sftp_apply_snapshot(dialog, snapshot)
                self._multi_sftp_start_polling(dialog)

            self.qt_after(0, done)

        Thread(
            target=worker,
            daemon=True,
            name="SasCancelMultiSftpBatch",
        ).start()


    def _multi_sftp_progress_action(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        snapshot = dict(state.get("snapshot", {}) or {})
        if bool(snapshot.get("running", False)):
            # Abort Transfer replaces the old separate Cancel & Return control:
            # request cancellation, then clean up and reopen target selection
            # once the Pi reports that all transfer workers have stopped.
            self._multi_sftp_cancel_batch(dialog, close_after=True)
            return

        summary = dict(snapshot.get("summary", {}) or {})
        if int(summary.get("failed", 0) or 0) or int(summary.get("cancelled", 0) or 0):
            self._multi_sftp_retry_failed(dialog)
        else:
            self._multi_sftp_cleanup_and_close(dialog, reopen_targets=True)


    def _multi_sftp_retry_failed(self, dialog):
        state = getattr(dialog, "_multi_sftp_state", {})
        batch_id = str(state.get("batch_id", "") or "")
        if not batch_id or state.get("retry_in_progress"):
            return
        state["retry_in_progress"] = True
        state["close_after_cancel"] = False
        self._multi_sftp_set_status(state.get("progress_status"), "Requesting retry for failed target Pis...", "normal")
        if state.get("progress_action") is not None:
            state["progress_action"].setEnabled(False)

        def worker():
            try:
                data = self.face_api_service.retry_multi_sftp_failed(batch_id)
                snapshot = data.get("batch", {}) if isinstance(data, dict) else {}
                error = ""
            except Exception as exc:
                snapshot, error = {}, str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                live["retry_in_progress"] = False
                if live.get("cleanup_requested"):
                    return
                if error:
                    self._multi_sftp_set_status(live.get("progress_status"), f"Could not retry failed targets: {error}", "error")
                    if live.get("progress_action") is not None:
                        live["progress_action"].setEnabled(True)
                    return
                self.append_face_log("SFTP_MULTI_RETRY: Retry requested for failed target Pi(s).")
                live["audit_completion_logged"] = False
                live["minimized"] = False
                self._multi_sftp_apply_snapshot(dialog, snapshot)
                self._multi_sftp_start_polling(dialog)

            self.qt_after(0, done)

        Thread(target=worker, daemon=True, name="SasRetryMultiSftpBatch").start()


    def _multi_sftp_request_close(self, dialog):
        """Close progress safely, then return to the target-selection popup."""
        state = getattr(dialog, "_multi_sftp_state", {})
        snapshot = dict(state.get("snapshot", {}) or {})

        if not state.get("showing_progress"):
            dialog.accept()
            return

        # The user expects × / Close to return to the previous target-selection
        # interface after this Pi-owned batch has been cleaned up.
        state["return_to_targets_after_close"] = True

        if bool(snapshot.get("running", False)):
            self._multi_sftp_cancel_batch(dialog, close_after=True)
            return

        self._multi_sftp_cleanup_and_close(dialog, reopen_targets=True)


    def _multi_sftp_cleanup_and_close(self, dialog, reopen_targets: bool = False):
        """Delete Pi temporary ZIP, close progress, then optionally reopen target selection."""
        state = getattr(dialog, "_multi_sftp_state", {})
        reopen_targets = bool(
            reopen_targets or state.get("return_to_targets_after_close", False)
        )
        batch_id = str(state.get("batch_id", "") or "")

        if not batch_id:
            try:
                dialog.accept()
            finally:
                if reopen_targets:
                    self._multi_sftp_progress_dialog = None
                    QTimer.singleShot(0, self._face_api_sftp_send)
            return

        if state.get("cleanup_requested"):
            # A second click during cleanup should not start a second API call,
            # but it can still request that selection reopens afterward.
            state["return_to_targets_after_close"] = bool(
                state.get("return_to_targets_after_close", False) or reopen_targets
            )
            return

        state["cleanup_requested"] = True
        state["return_to_targets_after_close"] = reopen_targets
        self._multi_sftp_set_status(
            state.get("progress_status"),
            "Deleting temporary ZIP on the Raspberry Pi...",
            "normal",
        )

        for name in ("progress_cancel", "progress_action", "progress_minimize"):
            button = state.get(name)
            if button is not None:
                button.setEnabled(False)

        timer = state.get("poll_timer")
        if timer is not None:
            timer.stop()

        def worker():
            try:
                self.face_api_service.cleanup_multi_sftp_transfer(batch_id)
                error = ""
            except Exception as exc:
                error = str(exc)

            def done():
                live = getattr(dialog, "_multi_sftp_state", {})
                reopen = bool(live.get("return_to_targets_after_close", False))

                if error:
                    self.append_face_log(f"SFTP_MULTI_CLEANUP_FAILED: {error}")
                else:
                    self.append_face_log(
                        "SFTP_MULTI_CLEANUP: Temporary ZIP deleted after popup close."
                    )

                try:
                    dialog.accept()
                except Exception:
                    pass

                # Clear the modeless reference before opening a new selection
                # dialog; otherwise _face_api_sftp_send would restore the old
                # closed progress window instead.
                if getattr(self, "_multi_sftp_progress_dialog", None) is dialog:
                    self._multi_sftp_progress_dialog = None

                if reopen:
                    QTimer.singleShot(0, self._face_api_sftp_send)

            self.qt_after(0, done)

        Thread(
            target=worker,
            daemon=True,
            name="SasCleanupMultiSftpBatch",
        ).start()


    def _multi_sftp_position_progress_window(self, dialog):
        """Centre the modeless progress window without disabling SAS."""
        try:
            geo = self.geometry()
            x = geo.x() + (geo.width() - dialog.width()) // 2
            y = geo.y() + max(20, (geo.height() - dialog.height()) // 2)
            dialog.move(x, y)
        except Exception:
            pass


    def _multi_sftp_minimize_progress(self, dialog):
        """Hide the progress window while Pi-side transfers continue."""
        state = getattr(dialog, "_multi_sftp_state", {})
        snapshot = dict(state.get("snapshot", {}) or {})
        if not bool(snapshot.get("running", False)):
            return
        state["minimized"] = True
        self._multi_sftp_apply_poll_interval(dialog)
        dialog.hide()
        self.append_face_log("SFTP_MULTI_PROGRESS_HIDDEN: Pi transfer continues in the background.")


    def _multi_sftp_restore_progress_window(self, dialog):
        """Show hidden transfer progress again, especially after completion."""
        state = getattr(dialog, "_multi_sftp_state", {})
        if state.get("cleanup_requested"):
            return
        state["minimized"] = False
        self._multi_sftp_apply_poll_interval(dialog)
        self._multi_sftp_position_progress_window(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        try:
            QApplication.setActiveWindow(dialog)
        except Exception:
            pass


    def create_multi_sftp_progress_dialog(
        self,
        batch_id: str,
        snapshot: dict,
        audit_actor: str = "",
        audit_targets: list[str] | None = None,
    ):
        """Create a separate modeless transfer-progress popup.

        The target-selection card closes after the Pi starts a batch. This
        popup deliberately does not use _show_card_dialog(), so users can
        continue using SAS while the Raspberry Pi performs uploads.
        """
        dialog = QDialog(self)
        dialog.setObjectName("MultiSftpDialog")
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(620 if not self.compact_mode else 540, 600 if not self.compact_mode else 540)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("MultiSftpCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QVBoxLayout(card)
        setattr(dialog, "_multi_sftp_root", root)
        setattr(dialog, "_multi_sftp_state", {
            "targets": [],
            "selected": set(),
            "filter": "",
            "batch_id": str(batch_id or ""),
            "snapshot": dict(snapshot or {}),
            "loading": False,
            "poll_in_progress": False,
            "showing_progress": True,
            "modeless_progress": True,
            "minimized": False,
            "close_after_cancel": False,
            "return_to_targets_after_close": False,
            "cleanup_requested": False,
            # Keep the initiating user and selected target list even though
            # this modeless popup is created after the setup card closes.
            "audit_actor": str(audit_actor or self.get_audit_actor()),
            "audit_targets": list(audit_targets or []),
            "audit_completion_logged": False,
        })

        def clear_reference(*_args):
            if getattr(self, "_multi_sftp_progress_dialog", None) is dialog:
                self._multi_sftp_progress_dialog = None

        dialog.finished.connect(clear_reference)
        dialog.destroyed.connect(clear_reference)
        self._multi_sftp_render_progress(dialog, dict(snapshot or {}))
        return dialog


    def _multi_sftp_open_progress_window(
        self,
        batch_id: str,
        snapshot: dict,
        audit_actor: str = "",
        audit_targets: list[str] | None = None,
    ):
        """Show and start polling a modeless Pi-owned transfer batch."""
        existing = getattr(self, "_multi_sftp_progress_dialog", None)
        if existing is not None:
            existing_state = getattr(existing, "_multi_sftp_state", {})
            if not existing_state.get("cleanup_requested"):
                self._multi_sftp_restore_progress_window(existing)
                return existing

        progress = self.create_multi_sftp_progress_dialog(
            batch_id,
            snapshot,
            audit_actor=audit_actor,
            audit_targets=audit_targets,
        )
        self._multi_sftp_progress_dialog = progress
        self._multi_sftp_position_progress_window(progress)
        progress.show()
        progress.raise_()
        progress.activateWindow()
        self._multi_sftp_start_polling(progress)
        return progress


    def create_multi_sftp_transfer_dialog(self):
        dialog = QDialog(self)
        dialog.setObjectName("MultiSftpDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(620 if not self.compact_mode else 540, 610 if not self.compact_mode else 550)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("MultiSftpCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        root = QVBoxLayout(card)

        setattr(dialog, "_multi_sftp_root", root)
        setattr(dialog, "_multi_sftp_state", {
            "targets": [],
            "selected": set(),
            "filter": "",
            "batch_id": "",
            "snapshot": {},
            "loading": False,
            "poll_in_progress": False,
            "showing_progress": False,
            "close_after_cancel": False,
            "cleanup_requested": False,
        })
        self._multi_sftp_render_setup(dialog)
        return dialog


    def create_sftp_transfer_dialog(self):
        """Create SFTP transfer popup using the uploaded split-card UI direction."""
        dialog = QDialog(self)
        dialog.setObjectName("SftpTransferDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(760 if not self.compact_mode else 680, 575 if not self.compact_mode else 535)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("SftpMainCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QHBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left dark technical panel
        left = QFrame()
        left.setObjectName("SftpLeftPanel")
        left.setFixedWidth(255 if not self.compact_mode else 220)

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(28 if not self.compact_mode else 22, 30, 24, 26)
        left_layout.setSpacing(18)

        icon = QLabel("🛡")
        icon.setObjectName("SftpLargeIcon")

        title = QLabel("SFTP\nTransfer")
        title.setObjectName("SftpSideTitle")
        title.setWordWrap(True)

        desc = QLabel("Secure File Transfer Protocol authentication for enterprise node synchronisation.")
        desc.setObjectName("SftpSideDesc")
        desc.setWordWrap(True)

        left_layout.addWidget(icon)
        left_layout.addWidget(title)
        left_layout.addWidget(desc)
        left_layout.addStretch()

        hint = QLabel("Select the receiver project folder only.\nThe pending route is fixed automatically.")
        hint.setObjectName("SftpSideHint")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)

        # Right form panel
        right = QFrame()
        right.setObjectName("SftpRightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(38 if not self.compact_mode else 28, 30 if not self.compact_mode else 24, 38 if not self.compact_mode else 28, 26 if not self.compact_mode else 22)
        right_layout.setSpacing(12)

        top = QHBoxLayout()
        top_title = QLabel("Secure Access System")
        top_title.setObjectName("SftpShellTitle")
        close_btn = QPushButton("×")
        close_btn.setObjectName("SftpCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        top.addWidget(top_title)
        top.addStretch()
        top.addWidget(close_btn)
        right_layout.addLayout(top)

        heading = QLabel("Connection Details")
        heading.setObjectName("SftpFormTitle")
        sub = QLabel("Configure receiver endpoint access.")
        sub.setObjectName("SftpFormSubtitle")
        right_layout.addWidget(heading)
        right_layout.addWidget(sub)

        form = QVBoxLayout()
        form.setSpacing(10)

        def field(label_text, placeholder="", value="", password=False, browse=False):
            wrap = QVBoxLayout()
            wrap.setSpacing(5)

            lbl = QLabel(label_text)
            lbl.setObjectName("SftpFieldLabel")

            box = QFrame()
            box.setObjectName("SftpInputBox")
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(12, 0, 10, 0)
            box_layout.setSpacing(8)

            inp = QLineEdit()
            inp.setObjectName("SftpBoxInput")
            font = inp.font()
            font.setWeight(QFont.Weight.Normal)
            inp.setFont(font)
            inp.setPlaceholderText(placeholder)
            inp.setText(value)
            inp.setMinimumHeight(34 if not self.compact_mode else 31)
            box_layout.addWidget(inp, 1)

            if password:
                inp.setEchoMode(QLineEdit.EchoMode.Password)
                show_btn = QPushButton("SHOW")
                show_btn.setObjectName("SftpFieldIconButton")
                show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                show_btn.setToolTip("Show / hide password")
                show_btn.setFixedSize(48, 28)

                def toggle_password():
                    if inp.echoMode() == QLineEdit.EchoMode.Password:
                        inp.setEchoMode(QLineEdit.EchoMode.Normal)
                        show_btn.setText("HIDE")
                    else:
                        inp.setEchoMode(QLineEdit.EchoMode.Password)
                        show_btn.setText("SHOW")

                show_btn.clicked.connect(toggle_password)
                box_layout.addWidget(show_btn)

            if browse:
                browse_btn = QPushButton("⌕")
                browse_btn.setObjectName("SftpFieldIconButton")
                browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                browse_btn.setToolTip("Select receiver project folder")
                browse_btn.setFixedSize(28, 28)

                def browse_folder():
                    start_dir = inp.text().strip() or os.path.expanduser("~")
                    selected = QFileDialog.getExistingDirectory(
                        dialog,
                        "Select Receiver Project Folder",
                        start_dir,
                        QFileDialog.Option.ShowDirsOnly,
                    )
                    if selected:
                        # User selects only the base/project folder.
                        # /received_face_data/pending is fixed by normalize_sftp_pending_path().
                        inp.setText(selected.replace("\\", "/"))

                browse_btn.clicked.connect(browse_folder)
                box_layout.addWidget(browse_btn)

            wrap.addWidget(lbl)
            wrap.addWidget(box)
            return wrap, inp

        host_port = QHBoxLayout()
        host_layout, host_input = field("Receiver Host / IP", "facerecognition2 or 10.121.xxx.xxx")
        port_layout, port_input = field("Port", "", "22")
        port_input.setFixedWidth(58 if not self.compact_mode else 50)
        host_port.addLayout(host_layout, 1)
        host_port.addLayout(port_layout)
        form.addLayout(host_port)

        user_layout, user_input = field("Username", "receiver Pi username", "jbl_facerec")
        pass_layout, pass_input = field("Password", "••••••••••••", "", password=True)
        form.addLayout(user_layout)
        form.addLayout(pass_layout)

        folder_layout, folder_input = field(
            "Receiver Project Folder",
            "/home/jbl_facerec/New",
            "/home/jbl_facerec/New",
            browse=True,
        )
        form.addLayout(folder_layout)

        pending_card = QFrame()
        pending_card.setObjectName("SftpPendingCard")
        pending_layout = QHBoxLayout(pending_card)
        pending_layout.setContentsMargins(12, 12, 12, 12)
        pending_layout.setSpacing(10)

        folder_icon = QLabel("▣")
        folder_icon.setObjectName("SftpFolderIcon")
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setFixedSize(40 if not self.compact_mode else 36, 40 if not self.compact_mode else 36)

        pending_text_box = QVBoxLayout()
        pending_text_box.setSpacing(4)
        pending_label = QLabel("Receiver Pending Folder")
        pending_label.setObjectName("SftpPendingLabel")
        pending_path = QLabel("")
        pending_path.setObjectName("SftpPendingPath")
        pending_path.setWordWrap(True)
        pending_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pending_path.setMinimumHeight(34 if not self.compact_mode else 30)
        pending_path.setMaximumHeight(48 if not self.compact_mode else 42)
        fixed_label = QLabel("Fixed suffix: /received_face_data/pending")
        fixed_label.setObjectName("SftpFixedSuffix")
        fixed_label.setWordWrap(True)

        pending_text_box.addWidget(pending_label)
        pending_text_box.addWidget(pending_path)
        pending_text_box.addWidget(fixed_label)

        pending_layout.addWidget(folder_icon, 0, Qt.AlignmentFlag.AlignTop)
        pending_layout.addLayout(pending_text_box, 1)

        form.addWidget(pending_card)

        status = QLabel("")
        status.setObjectName("SftpStatus")
        status.setWordWrap(True)
        form.addWidget(status)

        right_layout.addLayout(form)
        right_layout.addStretch()

        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SftpCancelButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setAutoDefault(False)
        cancel.setDefault(False)
        cancel.clicked.connect(dialog.reject)

        transfer = QPushButton("Transfer  →")
        transfer.setObjectName("SftpTransferButton")
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer.setAutoDefault(False)
        transfer.setDefault(False)

        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(transfer)
        right_layout.addLayout(actions)

        root.addWidget(left)
        root.addWidget(right, 1)

        def update_pending_path():
            full_path = self.normalize_sftp_pending_path(folder_input.text())
            pending_path.setText(full_path if full_path else "/received_face_data/pending")
            return full_path

        folder_input.textChanged.connect(lambda _: update_pending_path())
        update_pending_path()

        return dialog, {
            "host": host_input,
            "port": port_input,
            "username": user_input,
            "password": pass_input,
            "folder": folder_input,
            "pending_path": pending_path,
            "status": status,
            "transfer": transfer,
            "cancel": cancel,
        }



    def set_sftp_status(self, label, text: str, state: str = "normal"):
        label.setText(text)
        if state == "success":
            label.setObjectName("SftpStatusSuccess")
        elif state == "error":
            label.setObjectName("SftpStatusError")
        else:
            label.setObjectName("SftpStatus")
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()


    def show_sftp_transfer_success(self, dialog, widgets, message: str, remote_path: str):
        """Replace SFTP form content with a success state inside the same card."""
        self.set_sftp_status(widgets["status"], f"{message}\nDestination: {remote_path}", "success")
        self.show_transfer_button_success(widgets["transfer"], "Link Active", "Transfer  →")


    def _face_api_sftp_send(self):
        """Open the Pi-backed multi-target SFTP popup.

        SAS is intentionally only a client/UI here. The connected Pi owns the
        saved target list, creates the one ZIP file, runs the four-worker SFTP
        queue, and exposes live batch state through its HTTP API.
        """
        active_progress = getattr(self, "_multi_sftp_progress_dialog", None)
        if active_progress is not None:
            active_state = getattr(active_progress, "_multi_sftp_state", {})
            if not active_state.get("cleanup_requested"):
                self._multi_sftp_restore_progress_window(active_progress)
                return

        dialog = self.create_multi_sftp_transfer_dialog()
        try:
            # Configure the shared FaceApiService from the currently selected
            # Pi hostname/IP before the popup starts any background API call.
            self._face_api_base_url()
            self._multi_sftp_load_targets(dialog)
        except Exception as exc:
            state = getattr(dialog, "_multi_sftp_state", {})
            self._multi_sftp_set_status(
                state.get("status"),
                f"Pi API is not connected. Please connect the Pi in Settings first. ({exc})",
                "error",
            )

        self._show_card_dialog(dialog)

        # The setup dialog stores this only after the Pi has accepted a new
        # batch. Opening progress here ensures the setup card has closed and
        # released its blur/dim overlay before the modeless window appears.
        launch = getattr(dialog, "_multi_sftp_launch_progress", None)
        if isinstance(launch, dict):
            batch_id = str(launch.get("batch_id", "") or "")
            snapshot = dict(launch.get("snapshot", {}) or {})
            audit_actor = str(launch.get("audit_actor", "") or "")
            audit_targets = list(launch.get("audit_targets", []) or [])
            if batch_id:
                QTimer.singleShot(
                    0,
                    lambda batch_id=batch_id, snapshot=snapshot, audit_actor=audit_actor, audit_targets=audit_targets:
                        self._multi_sftp_open_progress_window(
                            batch_id,
                            snapshot,
                            audit_actor=audit_actor,
                            audit_targets=audit_targets,
                        ),
                )



    def create_sftp_windows_transfer_dialog(self):
        """Create SFTP pull popup for downloading face data from Pi to Windows.

        User-facing fields are Windows identity/save destination only. The Pi SFTP
        credential is treated as a backend/build configuration so normal users do
        not need to know or type the Pi SSH account.
        """
        dialog = QDialog(self)
        dialog.setObjectName("SftpTransferDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(760 if not self.compact_mode else 680, 555 if not self.compact_mode else 520)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("SftpMainCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QHBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QFrame()
        left.setObjectName("SftpLeftPanel")
        left.setFixedWidth(255 if not self.compact_mode else 220)

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(28 if not self.compact_mode else 22, 30, 24, 26)
        left_layout.setSpacing(18)

        icon = QLabel("⇩")
        icon.setObjectName("SftpLargeIcon")

        title = QLabel("SFTP\nWindows")
        title.setObjectName("SftpSideTitle")
        title.setWordWrap(True)

        desc = QLabel("Download face data from the connected Raspberry Pi to this Windows laptop using SFTP pull mode.")
        desc.setObjectName("SftpSideDesc")
        desc.setWordWrap(True)

        left_layout.addWidget(icon)
        left_layout.addWidget(title)
        left_layout.addWidget(desc)
        left_layout.addStretch()

        hint = QLabel("User enters Windows credentials and save path. SAS fetches the connected Pi username automatically and uses username = password for SFTP.")
        hint.setObjectName("SftpSideHint")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)

        right = QFrame()
        right.setObjectName("SftpRightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(38 if not self.compact_mode else 28, 30 if not self.compact_mode else 24, 38 if not self.compact_mode else 28, 26 if not self.compact_mode else 22)
        right_layout.setSpacing(12)

        top = QHBoxLayout()
        top_title = QLabel("Secure Access System")
        top_title.setObjectName("SftpShellTitle")
        close_btn = QPushButton("×")
        close_btn.setObjectName("SftpCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        top.addWidget(top_title)
        top.addStretch()
        top.addWidget(close_btn)
        right_layout.addLayout(top)

        heading = QLabel("Transfer to Windows")
        heading.setObjectName("SftpFormTitle")
        sub = QLabel("SAS downloads the prepared ZIP from the Pi by SFTP, then saves it to the selected Windows local or SMB folder.")
        sub.setObjectName("SftpFormSubtitle")
        sub.setWordWrap(True)
        right_layout.addWidget(heading)
        right_layout.addWidget(sub)

        form = QVBoxLayout()
        form.setSpacing(10)

        def field(label_text, placeholder="", value="", password=False, browse=False):
            wrap = QVBoxLayout()
            wrap.setSpacing(5)

            lbl = QLabel(label_text)
            lbl.setObjectName("SftpFieldLabel")

            box = QFrame()
            box.setObjectName("SftpInputBox")
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(12, 0, 10, 0)
            box_layout.setSpacing(8)

            inp = QLineEdit()
            inp.setObjectName("SftpBoxInput")
            font = inp.font()
            font.setWeight(QFont.Weight.Normal)
            inp.setFont(font)
            inp.setPlaceholderText(placeholder)
            inp.setText(value)
            inp.setMinimumHeight(34 if not self.compact_mode else 31)
            box_layout.addWidget(inp, 1)

            if password:
                inp.setEchoMode(QLineEdit.EchoMode.Password)
                show_btn = QPushButton("SHOW")
                show_btn.setObjectName("SftpFieldIconButton")
                show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                show_btn.setToolTip("Show / hide password")
                show_btn.setFixedSize(48, 28)

                def toggle_password():
                    if inp.echoMode() == QLineEdit.EchoMode.Password:
                        inp.setEchoMode(QLineEdit.EchoMode.Normal)
                        show_btn.setText("HIDE")
                    else:
                        inp.setEchoMode(QLineEdit.EchoMode.Password)
                        show_btn.setText("SHOW")

                show_btn.clicked.connect(toggle_password)
                box_layout.addWidget(show_btn)

            if browse:
                browse_btn = QPushButton("⌕")
                browse_btn.setObjectName("SftpFieldIconButton")
                browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                browse_btn.setToolTip("Select Windows save folder")
                browse_btn.setFixedSize(28, 28)

                def browse_folder():
                    start_dir = inp.text().strip() or os.path.expanduser("~")
                    selected = QFileDialog.getExistingDirectory(
                        dialog,
                        "Select Windows Save Folder",
                        start_dir,
                        QFileDialog.Option.ShowDirsOnly,
                    )
                    if selected:
                        inp.setText(selected)

                browse_btn.clicked.connect(browse_folder)
                box_layout.addWidget(browse_btn)

            wrap.addWidget(lbl)
            wrap.addWidget(box)
            return wrap, inp

        current_user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        username_layout, username_input = field("Windows Username / NTID", "4261233 or DOMAIN\\4261233", current_user)
        password_layout, password_input = field("Windows Password", "••••••••••••", "", password=True)
        form.addLayout(username_layout)
        form.addLayout(password_layout)

        folder_layout, folder_input = field(
            "Windows Save Folder",
            "C:\\JE_SFTP or \\\\server\\share\\folder",
            os.path.join(os.path.expanduser("~"), "Documents"),
            browse=True,
        )
        form.addLayout(folder_layout)

        info_card = QFrame()
        info_card.setObjectName("SftpPendingCard")
        info_layout = QHBoxLayout(info_card)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(10)

        folder_icon = QLabel("▣")
        folder_icon.setObjectName("SftpFolderIcon")
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setFixedSize(40 if not self.compact_mode else 36, 40 if not self.compact_mode else 36)

        info_text_box = QVBoxLayout()
        info_text_box.setSpacing(4)
        info_label = QLabel("Transfer Mode")
        info_label.setObjectName("SftpPendingLabel")
        info_path = QLabel("SFTP pull: SAS fetches the connected Pi username, uses the same value as the Pi SFTP password, downloads ZIP, then saves to the Windows path.")
        info_path.setObjectName("SftpPendingPath")
        info_path.setWordWrap(True)
        fixed_label = QLabel("Supported save destinations: local C drive folder or SMB/UNC shared folder path.")
        fixed_label.setObjectName("SftpFixedSuffix")
        fixed_label.setWordWrap(True)

        info_text_box.addWidget(info_label)
        info_text_box.addWidget(info_path)
        info_text_box.addWidget(fixed_label)

        info_layout.addWidget(folder_icon, 0, Qt.AlignmentFlag.AlignTop)
        info_layout.addLayout(info_text_box, 1)

        form.addWidget(info_card)

        status = QLabel("")
        status.setObjectName("SftpStatus")
        status.setWordWrap(True)
        form.addWidget(status)

        right_layout.addLayout(form)
        right_layout.addStretch()

        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SftpCancelButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(dialog.reject)

        transfer = QPushButton("Export  →")
        transfer.setObjectName("SftpTransferButton")
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)

        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(transfer)
        right_layout.addLayout(actions)

        root.addWidget(left)
        root.addWidget(right, 1)

        return dialog, {
            "windows_username": username_input,
            "windows_password": password_input,
            "folder": folder_input,
            "status": status,
            "transfer": transfer,
            "cancel": cancel,
        }



    def show_sftp_download_success(self, widgets, message: str, local_path: str):
        self.set_sftp_status(widgets["status"], f"{message}\nSaved to: {local_path}", "success")
        self.show_transfer_button_success(widgets["transfer"], "Downloaded", "Export  →")




    def _clean_pi_sftp_host(self, host: str) -> str:
        """Return hostname/IP only, without protocol or API port."""
        host = str(host or "").strip()
        if host.startswith("http://"):
            host = host.replace("http://", "", 1).split(":")[0].strip("/")
        elif host.startswith("https://"):
            host = host.replace("https://", "", 1).split(":")[0].strip("/")
        return host


    def _resolve_connected_pi_sftp_user(self, host: str) -> str:
        """Resolve the connected Pi Linux username for SFTP pull.

        Transfer to Windows rule: SAS gets the Pi username from the connected
        Pi /status API and uses the same value as the SFTP password. This lets
        SAS download from whichever Pi is currently connected without showing
        Pi SSH credentials in the user popup.
        """
        cached = str(getattr(self, "pi_system_user", "") or "").strip()
        if cached:
            return cached

        try:
            base = str(getattr(self, "pi_api_base", "") or "").rstrip("/")
            if base:
                response = requests.get(f"{base}/status", timeout=5)
                response.raise_for_status()
                data = response.json() if response.content else {}
                api_user = str(data.get("system_user") or data.get("ssh_username") or "").strip()
                api_hostname = str(data.get("hostname") or data.get("device_name") or "").strip()
                if api_hostname:
                    self.pi_device_hostname = api_hostname
                if api_user:
                    self.pi_system_user = api_user
                    return api_user
        except Exception:
            pass

        # Final fallback remains configurable for old Pi patches that do not yet
        # return system_user in /status.
        return str(globals().get("PI_SFTP_USERNAME", os.environ.get("SAS_PI_SFTP_USERNAME", "jbl_facerec")) or "").strip()


    def _get_backend_pi_sftp_config(self):
        """Return internal Pi SFTP config for Windows pull download.

        The user should not type Pi SSH credentials in the Windows transfer popup.
        SAS uses the currently connected Pi hostname/IP as the SFTP host, fetches
        the Pi Linux username from /status, and uses that same username as the
        SFTP password.
        """
        host = getattr(self, "pi_api_host", "") or ""
        if hasattr(self, "pi_host_input"):
            host = self.pi_host_input.text().strip() or host
        host = self._clean_pi_sftp_host(host)

        username = self._resolve_connected_pi_sftp_user(host) if host else ""
        password = username
        try:
            port = int(globals().get("PI_SFTP_PORT", os.environ.get("SAS_PI_SFTP_PORT", "22")) or 22)
        except Exception:
            port = 22
        return host, port, username, password


    def _unc_share_root(self, path: str) -> str:
        r"""Return \\server\share root for a UNC path, otherwise empty string."""
        p = (path or "").replace("/", "\\").strip()
        if not p.startswith("\\\\"):
            return ""
        parts = [part for part in p.split("\\") if part]
        if len(parts) < 2:
            return ""
        return "\\\\" + parts[0] + "\\" + parts[1]


    def _connect_smb_share_if_needed(self, save_folder: str, username: str, password: str):
        """Authenticate a UNC share with Windows credentials when needed.

        Local C/D drive paths do not use these credentials; SAS writes using the
        current Windows session. For SMB paths, Windows may require a net use
        session before Python can create/write files there.
        """
        share = self._unc_share_root(save_folder)
        if not share:
            return
        if platform.system().lower() != "windows":
            return
        if not username or not password:
            raise RuntimeError("Windows username/password are required for SMB shared folder saving.")

        cmd = ["net", "use", share, password, f"/user:{username}", "/persistent:no"]
        result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0 and "multiple connections" not in output.lower():
            raise RuntimeError(f"Unable to authenticate SMB share {share}: {output.strip() or 'net use failed'}")


    def _face_api_sftp_download_to_windows(self):
        """Download a prepared face-data ZIP from the connected Pi to this Windows laptop by SFTP."""
        dialog, widgets = self.create_sftp_windows_transfer_dialog()

        def do_transfer():
            if paramiko is None:
                self.set_sftp_status(widgets["status"], "Paramiko is required for SFTP download in SAS. Please include/install paramiko in the Windows build.", "error")
                return

            windows_username = widgets["windows_username"].text().strip()
            windows_password = widgets["windows_password"].text()
            save_folder = widgets["folder"].text().strip()
            host, port, username, password = self._get_backend_pi_sftp_config()

            if not windows_username:
                self.set_sftp_status(widgets["status"], "Windows username / NTID is required.", "error")
                return
            if not windows_password:
                self.set_sftp_status(widgets["status"], "Windows password is required.", "error")
                return
            if not save_folder:
                self.set_sftp_status(widgets["status"], "Windows save folder is required.", "error")
                return
            if not host:
                self.set_sftp_status(widgets["status"], "Pi hostname/IP is not configured. Please set and connect the Pi in Settings first.", "error")
                return
            if not username:
                self.set_sftp_status(widgets["status"], "Unable to fetch connected Pi username for SFTP. Please reconnect the Pi and try again.", "error")
                return
            if not password:
                self.set_sftp_status(widgets["status"], "Unable to derive Pi SFTP password from username. Please reconnect the Pi and try again.", "error")
                return

            self.start_transfer_button_loading(widgets["transfer"], "Export")
            self.set_sftp_status(widgets["status"], "Validating Windows credentials and preparing ZIP on Raspberry Pi...", "normal")

            def worker():
                transport = None
                sftp = None
                try:
                    # Windows credentials are used for user authorisation and SMB save path access.
                    ad_user = windows_username.split("\\")[-1].split("@", 1)[0].strip()
                    if not self._validate_ntid_password_in_ad(ad_user, windows_password):
                        raise RuntimeError("Windows credential validation failed. Please check username/password.")

                    self._connect_smb_share_if_needed(save_folder, windows_username, windows_password)

                    prepare = self._face_api_request(
                        "POST",
                        "/face-data/sftp-prepare-download",
                        {},
                        timeout=90,
                    )
                    remote_path = prepare.get("remote_path") or prepare.get("zip_path") or ""
                    filename = prepare.get("filename") or os.path.basename(str(remote_path))
                    if not remote_path or not filename:
                        raise RuntimeError("Pi did not return a downloadable ZIP path.")

                    os.makedirs(save_folder, exist_ok=True)
                    local_path = os.path.join(save_folder, filename)

                    def connecting():
                        self.set_sftp_status(widgets["status"], f"Connecting to current Pi {host}:{port} by SFTP and downloading package...", "normal")
                    self.qt_after(0, connecting)

                    ssh_lib = cast(Any, paramiko)
                    transport = ssh_lib.Transport((host, int(port)))
                    transport.connect(username=username, password=password)
                    sftp = ssh_lib.SFTPClient.from_transport(transport)
                    if sftp is None:
                        raise RuntimeError("SFTP connection was not created.")

                    sftp.get(remote_path, local_path)

                    message = prepare.get("message", "Face data downloaded to Windows successfully.")

                    def done():
                        self.show_sftp_download_success(widgets, message, local_path)
                        self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS: {remote_path} -> {local_path}")

                    self.qt_after(0, done)

                except Exception as e:
                    err = str(e)

                    def fail(err=err):
                        self.show_transfer_button_failed(widgets["transfer"], "Export  →")
                        self.set_sftp_status(widgets["status"], f"SFTP download failed: {err}", "error")
                        self.append_face_log(f"SFTP_DOWNLOAD_WINDOWS_FAILED: {err}")

                    self.qt_after(0, fail)

                finally:
                    try:
                        if sftp is not None:
                            sftp.close()
                    except Exception:
                        pass
                    try:
                        if transport is not None:
                            transport.close()
                    except Exception:
                        pass

            Thread(target=worker, daemon=True).start()

        widgets["transfer"].clicked.connect(do_transfer)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
        self._show_card_dialog(dialog)




    def _position_sas_received_badge(self):
        """Keep Check Received count badge on the right and vertically centred."""
        try:
            count = int(getattr(self, "_sas_received_badge_count", 0) or 0)
            badge = getattr(self, "sas_received_badge_label", None)
            btn = getattr(self, "sas_check_received_btn", None)
            if badge is None or btn is None:
                return
            if count <= 0:
                badge.hide()
                return
            bw = badge.width() or 22
            bh = badge.height() or 22
            btn_w = max(btn.width(), btn.sizeHint().width())
            btn_h = max(btn.height(), btn.sizeHint().height())
            if btn_w <= 0 or btn_h <= 0:
                return
            # Reserve a little breathing room from the right edge and centre
            # the badge with the Check Received label line.
            x = max(0, btn_w - bw - 12)
            y = max(0, int((btn_h - bh) / 2))
            badge.move(x, y)
            badge.raise_()
            badge.show()
        except RuntimeError:
            pass
        except Exception:
            pass


    def _update_sas_received_badge(self, count: int = 0):
        try:
            self._sas_received_badge_count = int(count or 0)
            badge = getattr(self, "sas_received_badge_label", None)
            if badge is None:
                return
            if count <= 0:
                badge.hide()
                return
            text = "99+" if count > 99 else str(count)
            badge.setText(text)
            if len(text) <= 2:
                badge.setFixedSize(22, 22)
                badge.setProperty("pill", False)
            else:
                badge.setFixedSize(30, 22)
                badge.setProperty("pill", True)
            try:
                badge.style().unpolish(badge)
                badge.style().polish(badge)
            except Exception:
                pass
            self._position_sas_received_badge()
            # The button width is not reliable during startup/layout creation.
            # Re-position again after Qt finishes the first layout pass so the
            # badge does not start on the left before the first user click.
            QTimer.singleShot(0, self._position_sas_received_badge)
            QTimer.singleShot(120, self._position_sas_received_badge)
        except Exception:
            pass


    def _show_sas_desktop_notification(self, count: int, filenames=None):
        """Show one Windows notification for pending face data using the SAS app identity."""
        filenames = filenames or []
        if count <= 0:
            return
        title = "New received face data"
        message = "1 pending ZIP is waiting for review." if count == 1 else f"{count} pending ZIP files are waiting for review."
        if filenames:
            preview = ", ".join(map(str, filenames[:2]))
            if len(filenames) > 2:
                preview += ", ..."
            message = f"{message}\n{preview}"

        shown = False
        if platform.system().lower() == "windows":
            try:
                # Make notifications identify as Secure Access System instead of python.exe where Windows allows it.
                try:
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Secure.Access.System")
                except Exception:
                    pass

                import base64
                logo_path = app_resource_path("assets", "sas_logo.png")
                logo_uri = ""
                if os.path.exists(logo_path):
                    try:
                        logo_uri = "file:///" + os.path.abspath(logo_path).replace("\\", "/").replace(" ", "%20")
                    except Exception:
                        logo_uri = ""

                ps_template = r"""
$Title = __TITLE__
$Message = __MESSAGE__
$Logo = __LOGO__
$AppId = "Secure.Access.System"
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$templateType = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
if ($Logo -and $Logo.Length -gt 0) {
    $templateType = [Windows.UI.Notifications.ToastTemplateType]::ToastImageAndText02
}
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($templateType)
if ($Logo -and $Logo.Length -gt 0) {
    $imageNodes = $template.GetElementsByTagName("image")
    if ($imageNodes.Length -gt 0) {
        $imageNodes.Item(0).Attributes.GetNamedItem("src").NodeValue = $Logo
        $imageNodes.Item(0).Attributes.GetNamedItem("alt").NodeValue = "Secure Access System"
    }
}
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode($Title)) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode($Message)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId)
$notifier.Show($toast)
"""
                ps = (
                    ps_template
                    .replace("__TITLE__", repr(title))
                    .replace("__MESSAGE__", repr(message))
                    .replace("__LOGO__", repr(logo_uri))
                )
                encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                shown = True
            except Exception:
                shown = False

        # Do not use Qt tray balloon fallback here. In development/source runs,
        # Qt tray notifications can appear as "Python" in Windows notification
        # centre.  Keep only the Windows toast path so users do not receive a
        # duplicate Python-branded notification.

        try:
            app = QApplication.instance()
            if isinstance(app, QApplication):
                app.alert(self, 5000)
        except Exception:
            pass


    def _normalise_received_pending_items(self, pending):
        """Return [{'filename': str, 'size': int|None, 'modified': float|None}, ...]."""
        items = []
        for item in pending or []:
            if isinstance(item, dict):
                filename = str(item.get("filename") or item.get("name") or "").strip()
                if not filename:
                    continue
                items.append({
                    "filename": filename,
                    "size": item.get("size"),
                    "modified": item.get("modified"),
                })
            else:
                filename = str(item).strip()
                if filename:
                    items.append({"filename": filename, "size": None, "modified": None})
        return items


    def _received_item_display_text(self, item: dict) -> str:
        return str(item.get("filename") or "").strip()


    def _poll_received_face_data_for_sas(self):
        if not getattr(self, "pi_connected", False):
            self._update_sas_received_badge(0)
            return

        def worker():
            try:
                data = self._face_api_request("GET", "/face-data/received", timeout=20)
                pending = self._normalise_received_pending_items(data.get("pending", []))
                self.qt_after(0, lambda pending=pending: self._handle_sas_received_pending(pending, manual=False))
            except Exception:
                # Keep background polling quiet to avoid noisy logs when Pi is temporarily unreachable.
                pass

        Thread(target=worker, daemon=True).start()


    def _handle_sas_received_pending(self, pending, manual: bool = False):
        pending_items = self._normalise_received_pending_items(pending)
        self._update_sas_received_badge(len(pending_items))

        current = {str(item.get("filename") or "").strip() for item in pending_items if item.get("filename")}
        if not getattr(self, "sas_received_poll_initialized", False):
            self.sas_received_seen_files = set(current)
            self.sas_received_poll_initialized = True
            if manual and pending_items:
                self._show_sas_received_popup(pending_items, auto_prompt=False)
            elif manual:
                self.append_face_log("RECEIVED: No pending face data.")
            return

        new_files = [item.get("filename") for item in pending_items if item.get("filename") not in self.sas_received_seen_files]
        self.sas_received_seen_files = set(current)

        if manual:
            if pending_items:
                self._show_sas_received_popup(pending_items, auto_prompt=False)
            else:
                self.append_face_log("RECEIVED: No pending face data.")
            return

        if new_files:
            self.append_face_log(f"RECEIVED: {len(new_files)} new pending package(s): {', '.join(new_files[:5])}")
            self._show_sas_desktop_notification(len(new_files), new_files)
            self._show_sas_received_popup(pending_items, auto_prompt=True)


    def _face_api_check_received(self):
        def worker():
            try:
                data = self._face_api_request("GET", "/face-data/received", timeout=30)
                pending = self._normalise_received_pending_items(data.get("pending", []))
                self.qt_after(0, lambda pending=pending: self._handle_sas_received_pending(pending, manual=True))
            except Exception as e:
                self.qt_after(0, lambda e=e: self.append_face_log(f"RECEIVED_CHECK_FAILED: {e}"))

        Thread(target=worker, daemon=True).start()


    def _show_sas_received_popup(self, pending, auto_prompt: bool = False):
        if getattr(self, "sas_received_popup_visible", False):
            return
        pending_items = self._normalise_received_pending_items(pending)
        if not pending_items:
            return

        self.sas_received_popup_visible = True
        dialog = QDialog(self)
        dialog.setObjectName("TransferDialog")
        dialog.setModal(False)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setFixedSize(680 if not self.compact_mode else 560, 520 if not self.compact_mode else 455)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame(dialog)
        card.setObjectName("TransferCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(18)
        icon = QLabel("⇩")
        icon.setObjectName("TransferHeaderIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(58, 58)
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Pending Received Face Data")
        title.setObjectName("TransferTitle")
        subtitle = QLabel(f"{len(pending_items)} ZIP file(s) waiting for review. Select one to accept or reject.")
        subtitle.setObjectName("TransferHint")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        close_btn = QPushButton("×")
        close_btn.setObjectName("TransferIconButton")
        close_btn.setFixedSize(34, 34)
        close_btn.clicked.connect(dialog.close)
        header.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        source_card = QFrame()
        source_card.setObjectName("ReceivedSourceCard")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(18, 16, 18, 16)
        source_layout.setSpacing(10)

        source_header = QHBoxLayout()
        source_icon = QLabel("▣")
        source_icon.setObjectName("ReceivedSourceIcon")
        source_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source_icon.setFixedSize(26, 26)
        source_header.addWidget(source_icon)
        source_label = QLabel("METADATA SOURCE")
        source_label.setObjectName("TransferSubtitle")
        source_header.addWidget(source_label, 1)
        source_layout.addLayout(source_header)

        search_box = QFrame()
        search_box.setObjectName("TransferInputBox")
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(12, 0, 10, 0)
        search_layout.setSpacing(8)
        search = QLineEdit()
        search.setObjectName("TransferInput")
        search.setPlaceholderText("Search received zip files...")
        search.setMinimumHeight(32 if not self.compact_mode else 30)
        search_icon = QLabel("⌕")
        search_icon.setObjectName("TransferSearchIcon")
        search_layout.addWidget(search, 1)
        search_layout.addWidget(search_icon)
        source_layout.addWidget(search_box)

        list_box = QListWidget()
        list_box.setObjectName("ReceivedZipList")
        list_box.setFrameShape(QFrame.Shape.NoFrame)
        list_box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        list_box.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        list_box.setSpacing(3)
        list_box.setUniformItemSizes(True)
        row_h = 32 if not self.compact_mode else 30
        max_visible_rows = 5
        list_box.setFixedHeight(row_h * max_visible_rows + 10)

        received_state = {"all_items": list(pending_items)}

        def populate_received_list(items, keep_selection: str = ""):
            list_box.blockSignals(True)
            list_box.clear()
            for item in items:
                filename = self._received_item_display_text(item)
                list_box.addItem(filename)
            list_box.clearSelection()
            list_box.setCurrentRow(-1)
            if keep_selection:
                for i in range(list_box.count()):
                    if list_box.item(i).text().strip() == keep_selection:
                        list_box.setCurrentRow(i)
                        break
            list_box.blockSignals(False)

        def apply_received_search():
            query = search.text().strip().lower()
            selected = list_box.currentItem().text().strip() if list_box.currentItem() else ""
            if query:
                filtered = [i for i in received_state["all_items"] if query in self._received_item_display_text(i).lower()]
            else:
                filtered = list(received_state["all_items"])
            populate_received_list(filtered, selected)
            if filtered:
                status = getattr(self, "sftp_status_label", None) or QLabel("")
                status.setText(f"{len(filtered)} ZIP file(s) shown. Select one to accept or reject.")
            else:
                status = getattr(self, "sftp_status_label", None) or QLabel("")
                status.setText("No matching ZIP files found.")

        populate_received_list(received_state["all_items"])
        search.textChanged.connect(apply_received_search)
        source_layout.addWidget(list_box, 0)
        source_card.setMaximumHeight(row_h * max_visible_rows + 132)
        layout.addWidget(source_card, 0)

        status = QLabel("Waiting for manual validation...")
        status.setObjectName("TransferHint")
        status.setWordWrap(True)
        layout.addWidget(status)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("TransferCancelButton")
        reject = QPushButton("Reject")
        reject.setObjectName("TransferSecondaryActionButton")
        accept = QPushButton("Accept")
        accept.setObjectName("TransferPrimaryButton")
        row.addWidget(close)
        row.addWidget(reject)
        row.addWidget(accept)
        layout.addLayout(row)
        accept.setEnabled(False)
        reject.setEnabled(False)

        def update_received_action_state():
            has_selection = list_box.currentItem() is not None
            accept.setEnabled(has_selection)
            reject.setEnabled(has_selection)
            if has_selection:
                status.setText("Selected ZIP is ready for manual validation.")

        list_box.itemSelectionChanged.connect(update_received_action_state)

        def current_filename():
            item = list_box.currentItem()
            if item is None:
                status.setText("Please select a ZIP file first.")
                return ""
            return item.text().strip()

        def refresh_list_from_pi():
            def worker():
                try:
                    data = self._face_api_request("GET", "/face-data/received", timeout=30)
                    latest = self._normalise_received_pending_items(data.get("pending", []))

                    def done():
                        received_state["all_items"] = list(latest)
                        if latest:
                            apply_received_search()
                            status.setText(f"{len(latest)} ZIP file(s) still waiting for review. Select one to accept or reject.")
                        else:
                            status.setText("No pending received ZIP files remain.")
                            dialog.close()
                        self._update_sas_received_badge(len(latest))
                        self.sas_received_seen_files = {str(i.get("filename") or "").strip() for i in latest if i.get("filename")}

                    self.qt_after(0, done)
                except Exception as e:
                    self.qt_after(0, lambda e=e: status.setText(f"Refresh failed: {e}"))

            Thread(target=worker, daemon=True).start()

        def do_action(action: str):
            filename = current_filename()
            if not filename:
                return
            endpoint = "/face-data/received/accept" if action == "accept" else "/face-data/received/reject"
            label = "Accept" if action == "accept" else "Reject"
            actor = self.get_audit_actor()
            accept.setEnabled(False)
            reject.setEnabled(False)

            if action == "accept":
                # Reuse the same import progress/success UI used by the normal Import flow.
                self.rebuild_import_loading_card(layout, dialog, filename)
            else:
                status.setText(f"Rejecting {filename}...")

            def worker():
                try:
                    data = self._face_api_request("POST", endpoint, payload={"filename": filename}, timeout=120)
                    message = data.get("message", f"{label} completed.")
                    imported_users = data.get("imported_users", [])
                    skipped_users_count = int(data.get("skipped_users_count", 0) or 0)
                    if data.get("import_mode") in ("add_on", "add_new_only"):
                        skipped_users_count = 0
                    for k in ("added_ids", "merged_users", "imported_ids"):
                        if not imported_users and isinstance(data.get(k, None), list):
                            imported_users = data.get(k, [])

                    def done():
                        self.append_face_log(f"RECEIVED_{action.upper()}: {filename}")
                        if action == "accept":
                            self.write_sas_log(
                                "RECEIVED FACE DATA IMPORTED",
                                actor=actor,
                                details={
                                    "Source": "Check Received pending folder",
                                    "ZIP file": filename,
                                    "Imported users": ", ".join(str(item).upper() for item in imported_users) or "No new users",
                                },
                            )
                            self.finish_import_progress_then_success(layout, dialog, filename, imported_users, skipped_users_count, message)
                            self._face_api_refresh_users()
                            self._face_api_check_received()
                        else:
                            self.write_sas_log(
                                "RECEIVED FACE DATA REJECTED",
                                actor=actor,
                                details={"Source": "Check Received pending folder", "ZIP file": filename},
                            )
                            status = getattr(self, "sftp_status_label", None) or QLabel("")
                            status.setText(message)
                            accept.setEnabled(True)
                            reject.setEnabled(True)
                            refresh_list_from_pi()

                    self.qt_after(0, done)
                except Exception as e:
                    err = str(e)

                    def fail():
                        if action == "accept":
                            self.rebuild_import_failed_card(layout, dialog, f"Import failed: {err}")
                        else:
                            status = getattr(self, "sftp_status_label", None) or QLabel("")
                            status.setText(f"{label} failed: {err}")
                            accept.setEnabled(True)
                            reject.setEnabled(True)

                        self.write_sas_log(
                            f"RECEIVED FACE DATA {label.upper()} FAILED",
                            actor=actor,
                            details={"Source": "Check Received pending folder", "ZIP file": filename, "Result": "Failed"},
                        )

                    self.qt_after(0, fail)

            Thread(target=worker, daemon=True).start()

        close.clicked.connect(dialog.close)
        reject.clicked.connect(lambda: do_action("reject"))
        accept.clicked.connect(lambda: do_action("accept"))

        def on_finished(*args):
            self.sas_received_popup_visible = False

        dialog.finished.connect(on_finished)
        self._show_card_dialog(dialog)



