from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class FaceRecognitionControllerMixin(DashboardMixinBase):
    def face_controls_card(self):
        card = GlassCard()
        card.setMinimumHeight(245 if not self.compact_mode else 218)

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

        self.face_name_input = QLineEdit()
        self.face_name_input.setObjectName("NtidInput")
        self.face_name_input.setPlaceholderText("Enter employee name for registration")
        self.face_name_input.setClearButtonEnabled(True)
        self.face_name_input.setFixedHeight(34 if not self.compact_mode else 30)
        layout.addWidget(self.face_name_input)

        self.ntid_input = QLineEdit()
        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter employee ID / NTID")
        self.ntid_input.setClearButtonEnabled(True)
        self.ntid_input.setFixedHeight(34 if not self.compact_mode else 30)
        self.ntid_input.textChanged.connect(self.clear_ntid_input_error)
        layout.addWidget(self.ntid_input)

        # Compact action area.
        # Row 1: Capture full width
        # Row 2: Recognize full width
        # Row 3: Stop + Delete
        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(8)
        button_grid.setVerticalSpacing(8)

        capture = QPushButton("CAPTURE")
        capture.setObjectName("OutlineActionButton")

        train = QPushButton("TRAIN")
        train.setObjectName("OutlineActionButton")
        train.setVisible(False)

        recognize = QPushButton("⌁  RECOGNIZE")
        recognize.setObjectName("GreenActionButton")

        stop = QPushButton("STOP")
        stop.setObjectName("StopButton")

        delete = QPushButton("DELETE")
        delete.setObjectName("DeleteButton")

        self.face_capture_btn = capture
        self.face_train_btn = train
        self.face_recognize_btn = recognize
        self.face_stop_btn = stop
        self.face_delete_btn = delete

        for btn in (capture, train, recognize, stop, delete):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        small_h = 32 if not self.compact_mode else 28
        main_h = 34 if not self.compact_mode else 30

        capture.setFixedHeight(main_h)
        train.setFixedHeight(main_h)
        recognize.setFixedHeight(main_h)
        stop.setFixedHeight(small_h)
        delete.setFixedHeight(small_h)

        capture.clicked.connect(self._face_api_capture_user)
        recognize.clicked.connect(self._face_api_get_result)
        stop.clicked.connect(self._face_api_stop_recognition)
        delete.clicked.connect(self._face_api_delete_user)

        button_grid.addWidget(capture, 0, 0, 1, 2)
        button_grid.addWidget(recognize, 1, 0, 1, 2)
        button_grid.addWidget(stop, 2, 0)
        button_grid.addWidget(delete, 2, 1)

        layout.addLayout(button_grid)
        layout.addStretch(1)

        # Disabled until Pi API connection is confirmed.
        QTimer.singleShot(0, lambda: self.set_face_controls_connection_enabled(getattr(self, "pi_connected", False)))
        return card


    def system_log_card(self):
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
            "&gt; WAITING FOR PI CONNECTION"
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


    def face_users_card(self):
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
        sub = QLabel("CONNECT PI FIRST")
        sub.setObjectName("UsersStatus")
        title_box.addWidget(title)
        title_box.addWidget(sub)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setObjectName("SmallIconButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setFixedSize(30 if not self.compact_mode else 26, 30 if not self.compact_mode else 26)
        refresh_btn.clicked.connect(self._face_api_refresh_users)

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
        self.face_user_search_input.setPlaceholderText("Search name or NTID...")
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
        QTimer.singleShot(300, self._face_api_refresh_users)

        return card


    def face_user_row(self, user_id, frames, status, active=True, display_name=""):
        """Expandable authorised user card using the uploaded card UI concept.

        Click row to smoothly expand the card and reveal Capture/Delete actions.
        Expanding/collapsing does not write into System Log.
        """
        user_id = str(user_id or "").strip().upper()
        display_name = str(display_name or "").strip()

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

        ntid_label = QLabel(user_id if display_name else "NTID IDENTIFIER")
        ntid_label.setObjectName("FaceUserCardLabel")

        name = QLabel(display_name or user_id)
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

        capture_btn = QPushButton("+ CAPTURE")
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
            if user_id in ("CONNECT PI", "OFFLINE", ""):
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
            if hasattr(self, "face_name_input"):
                self.face_name_input.setText(display_name or user_id)
            if hasattr(self, "ntid_input"):
                self.ntid_input.setText(user_id)
                self.clear_ntid_input_error()
            self.face_action_feedback(f"QUICK_CAPTURE: {user_id}")
            self._face_api_capture_user()

        def delete_this_user():
            if hasattr(self, "face_name_input"):
                self.face_name_input.setText(display_name or user_id)
            if hasattr(self, "ntid_input"):
                self.ntid_input.setText(user_id)
                self.clear_ntid_input_error()
            self.face_action_feedback(f"QUICK_DELETE: {user_id}")
            self._face_api_delete_user()

        card.mousePressEvent = lambda event: toggle_card()
        capture_btn.clicked.connect(lambda checked=False: capture_this_user())
        delete_btn.clicked.connect(lambda checked=False: delete_this_user())

        # Prevent button clicks from toggling the parent card.
        capture_btn.mousePressEvent = lambda event, old=capture_btn.mousePressEvent: (event.accept(), old(event))[1]
        delete_btn.mousePressEvent = lambda event, old=delete_btn.mousePressEvent: (event.accept(), old(event))[1]

        card.setProperty("_actions_frame", actions)

        return card


    def capture_requested(self):
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

    def qt_after(self, ms: int, callback):
        """Run callback on Qt main thread safely.

        Worker threads may finish after the dashboard has been closed. In that
        case PySide can delete the signal source before the worker emits, causing
        ``RuntimeError: Signal source has been deleted``. This guard silently
        drops late callbacks during shutdown while keeping normal worker-to-UI
        updates unchanged.
        """
        def emit_callback():
            if getattr(self, "_closing", False):
                return
            bridge = getattr(self, "ui_bridge", None)
            if bridge is None:
                return
            try:
                bridge.run_callback.emit(callback)
            except RuntimeError:
                # The Qt object was already destroyed during application exit.
                return
            except Exception as e:
                print(f"[SAS] qt_after callback emit skipped: {e}")

        if ms <= 0:
            emit_callback()
        else:
            try:
                QTimer.singleShot(ms, emit_callback)
            except RuntimeError:
                return


    def append_system_log(self, message: str):
        """General internal log.

        The visible System Log card is reserved for Face Recognition system logs.
        Dashboard/settings/login messages are printed to terminal only.
        """
        print("[SAS]", message)


    def append_face_log(self, message: str):
        """Visible Face Recognition System Log.

        Shows all Face Recognition actions/status:
        connection, camera, capture, train, recognise, stop, delete,
        users refresh, import/export, SFTP, received data and errors.
        """
        now = datetime.now().strftime("%H:%M:%S")
        line = f"<span style='color:#1F7A45'>{now}</span> &gt; {html.escape(str(message))}"

        if not hasattr(self, "_system_log_lines"):
            self._system_log_lines = [
                "&gt; FACE RECOGNITION SYSTEM LOG READY",
                "&gt; WAITING FOR PI CONNECTION",
            ]

        self._system_log_lines.append(line)

        # Keep enough history for scrolling without making the UI too heavy.
        self._system_log_lines = self._system_log_lines[-120:]

        if not getattr(self, "_log_update_pending", False):
            self._log_update_pending = True
            self.qt_after(50, self.flush_face_log_label)

        print("[FACE]", message)


    def flush_face_log_label(self):
        self._log_update_pending = False
        if hasattr(self, "system_log_label") and hasattr(self, "_system_log_lines"):
            should_follow_bottom = True
            if hasattr(self, "system_log_scroll"):
                bar = self.system_log_scroll.verticalScrollBar()
                should_follow_bottom = bar.value() >= max(0, bar.maximum() - 24)

            self.system_log_label.setText("<br>".join(self._system_log_lines))
            self.system_log_label.adjustSize()

            if hasattr(self, "system_log_body"):
                self.system_log_body.adjustSize()
                self.system_log_body.setMinimumHeight(self.system_log_label.sizeHint().height() + 8)

            if hasattr(self, "system_log_scroll") and should_follow_bottom:
                # Follow latest status only when user was already near the bottom.
                # If user scrolls up to review older logs, do not force jump down.
                QTimer.singleShot(
                    0,
                    lambda: self.system_log_scroll.verticalScrollBar().setValue(
                        self.system_log_scroll.verticalScrollBar().maximum()
                    )
                )



    def set_status_message(self, message: str):
        self.append_system_log(message)
        if hasattr(self, "pi_status_label"):
            self.pi_status_label.setText("●  " + str(message))


    def _face_api_stop_recognition(self):
        """Handle the SAS STOP button without stopping Pi unlock recognition.

        Normal recognition:
        - STOP closes only the Windows SAS preview. The Pi camera continues face
          recognition in the background, so a locked workstation can still unlock.

        Capture:
        - STOP asks the Pi to end capture, waits for the Pi camera to be released,
          then asks the Pi to restart background recognition. The SAS preview stays
          closed and the user does not need to remember to press Recognize again.
        """
        self.face_action_feedback("STOP: Stop requested by user")
        if not getattr(self, "pi_connected", False):
            self.face_action_feedback("STOP_FAILED: Pi API is not connected")
            self.show_pi_disconnected_popup("Pi API is not connected. Please connect from Settings first.")
            return

        was_manual_capture = bool(getattr(self, "manual_capture_active", False))
        was_capture_active = bool(getattr(self, "face_capture_in_progress", False))
        manual_user = getattr(self, "manual_capture_user", None)

        # STOP in SAS always closes the local Windows preview immediately.
        # It must not stop Pi recognition unless an SAS capture is active.
        self._camera_user_stopped = True
        self.stop_camera_preview(show_prompt=True)

        if not was_capture_active:
            self.face_action_feedback(
                "STOP: SAS video preview stopped. Pi face recognition remains active for workstation unlock."
            )
            return

        self.face_action_feedback(
            "STOP: Ending Pi capture. Pi recognition will restart automatically; SAS preview stays closed."
        )

        def worker():
            try:
                # /stop-capture affects only the Pi capture process. It does not
                # call the Pi's full STOP action, so normal recognition can return.
                data = self._face_api_request("POST", "/stop-capture", timeout=20)
                message = str(data.get("message", "Capture stop requested.")).strip()

                capture_stopped, _ = self.wait_until_pi_capture_complete(timeout_seconds=18)
                if not capture_stopped:
                    raise RuntimeError("Pi capture did not stop in time. Please wait and try STOP again.")

                # PiCamera2 may take a moment to release the device after capture.
                # Retry the normal recognition request instead of treating a brief
                # camera-busy response as a Pi disconnection.
                recognition_ready = False
                last_start_error = ""
                for _attempt in range(6):
                    try:
                        self._face_api_request("POST", "/start-recognition", timeout=20)
                    except Exception as start_error:
                        last_start_error = str(start_error)

                    recognition_ready, _ = self.wait_until_pi_recognition_running(timeout_seconds=4)
                    if recognition_ready:
                        break

                    time.sleep(0.8)

                if not recognition_ready:
                    detail = f" Last Pi response: {last_start_error}" if last_start_error else ""
                    raise RuntimeError("Pi capture stopped, but Pi recognition did not restart in time." + detail)

                def done():
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_capture_in_progress(False)
                    self.set_capture_button_manual_mode(False)
                    self.manual_capture_user = None
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)

                    self.face_action_feedback(
                        f"STOP: {message} Pi recognition is running in the background; SAS preview remains stopped."
                    )

                    if was_manual_capture or was_capture_active:
                        frames = self.get_user_capture_frames_from_pi(manual_user) if manual_user else 0
                        if manual_user:
                            self.face_action_feedback(
                                f"MANUAL_CAPTURE_COMPLETE: {str(manual_user).upper()} | {frames} capture frames"
                            )
                            self.show_capture_complete_popup(manual_user, frames)
                        self._face_api_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.face_action_feedback(f"STOP_FAILED: {err}")
                    # Keep the preview closed. The status refresh restores the
                    # correct button state without falsely declaring Pi offline.
                    self.verify_pi_status_after_action("STOP")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()



    def _face_api_get_result(self):
        self.face_action_feedback("RECOGNITION: User pressed Recognize")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        # The button is greyed out during capture, but keep this guard as a
        # race-safe fallback in case a click was queued just before it disabled.
        if bool(getattr(self, "face_capture_in_progress", False)):
            self.face_action_feedback(
                "RECOGNITION_BLOCKED: Capture is still running. Press STOP, wait for Pi camera to stop, then press Recognize."
            )
            return

        """Recognize button starts recognition on the Pi."""
        def worker():
            try:
                data = self._face_api_request("POST", "/start-recognition", timeout=20)
                message = data.get("message", "Recognition start requested.")
                def done():
                    self._camera_user_stopped = False
                    self.face_action_feedback(f"RECOGNITION: {message}")
                    self.stop_camera_preview()

                    # Give Pi video-feed a short moment to warm up before OpenCV connects.
                    # This avoids false "feed lost" when recognition is already running.
                    QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))

                    # Do not call _face_api_test_connection() here.
                    # Recognition should not show the connection-success popup again.
                    self._face_api_refresh_users()

                self.qt_after(0, done)
            except Exception as e:
                err = str(e)
                def fail(err=err):
                    self.face_action_feedback(f"RECOGNITION_FAILED: {err}")
                    # A busy camera can reject /start-recognition while the Pi API
                    # is still healthy. Recheck /status instead of treating it as a
                    # network disconnect.
                    self.verify_pi_status_after_action("RECOGNITION")
                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()



    def parse_training_progress_details(self, data: dict):
        """Parse Pi /train response progress.

        Older Pi training APIs emitted messages such as:
        "Trained: /image_0.jpg"
        We extract NTID and image count so the popup can show who was trained.
        """
        progress = data.get("progress", []) or []
        trained = []

        for msg in progress:
            text = str(msg).strip()
            if text.lower().startswith("trained:"):
                file_key = text.split(":", 1)[1].strip()
                trained.append(file_key)

        users = {}
        for file_key in trained:
            parts = file_key.replace("\\", "/").split("/")
            ntid = parts[0].strip().upper() if parts and parts[0].strip() else "UNKNOWN"
            users.setdefault(ntid, 0)
            users[ntid] += 1

        # Some Pi APIs may return registered users directly instead of progress lines.
        for key in ("users", "trained_users", "trained_user_ids"):
            api_users = data.get(key, None)
            if isinstance(api_users, list):
                for uid in api_users:
                    uid = str(uid).strip().upper()
                    if uid:
                        users.setdefault(uid, 0)
            elif isinstance(api_users, dict):
                for uid, count in api_users.items():
                    uid = str(uid).strip().upper()
                    if uid:
                        try:
                            users[uid] = int(count)
                        except Exception:
                            users.setdefault(uid, 0)

        new_faces = int(data.get("new_faces", 0) or 0)

        if users:
            owner_text = ", ".join([f"{ntid} ({count} image{'s' if count != 1 else ''})" for ntid, count in users.items()])
            return f"Trained image owner: {owner_text}", users, trained

        if new_faces == 0:
            return "No new image was trained. Dataset is already up to date.", {}, []

        return f"Training completed. New faces trained: {new_faces}", {}, trained


    def wait_until_pi_camera_stopped(self, timeout_seconds: int = 14):
        """Wait until Pi API reports recognition/capture is stopped before training."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status

                rec = bool(status.get("recognition_running", False))
                cap = bool(status.get("capture_running", False))
                training = bool(status.get("training_running", False))

                if not rec and not cap and not training:
                    return True, status
            except Exception:
                pass

            time.sleep(0.25)

        return False, last_status or {}


    def wait_until_pi_training_finished(
        self,
        timeout_seconds: int = 300,
        training_id: str = "",
        progress_callback=None,
    ):
        """Wait for the specific asynchronous Pi /train operation to finish.

        New Pi builds expose ``last_training_id`` and ``training_state``.  The
        ID avoids a polling race where SAS sees an old idle status before the
        newly requested training thread reports itself as running.
        """
        import time
        start = time.time()
        last_status = None
        seen_training = False
        expected_id = str(training_id or "").strip()

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status

                if callable(progress_callback):
                    try:
                        progress_callback(status)
                    except Exception:
                        pass

                reported_id = str(status.get("last_training_id") or "").strip()
                if expected_id and reported_id and reported_id != expected_id:
                    time.sleep(0.35)
                    continue

                training = bool(status.get("training_running", False))
                state = str(status.get("training_state") or "").strip().lower()

                if state in ("completed", "failed"):
                    return True, status
                if training:
                    seen_training = True
                elif seen_training or (not expected_id and time.time() - start >= 1.0):
                    return True, status
            except Exception:
                pass

            time.sleep(0.35)

        return False, last_status or {}


    def update_training_dialog_progress_from_status(self, status: dict):
        """Forward real Pi train counters to the SAS modal on the Qt thread."""
        if not isinstance(status, dict):
            return

        try:
            processed = int(status.get("training_processed", 0) or 0)
            total = int(status.get("training_total", 0) or 0)
            percent = int(status.get("training_percent", 0) or 0)
            message = str(status.get("training_message", "") or "")
            phase = str(status.get("training_phase", "training") or "training")
            skipped = int(status.get("training_skipped_images", 0) or 0)
            already_trained = int(status.get("training_already_trained", 0) or 0)
            dataset_total = int(status.get("training_dataset_total", 0) or 0)
        except Exception:
            return

        def apply():
            dialog = getattr(self, "training_dialog", None)
            if dialog is None:
                return
            updater = getattr(dialog, "set_live_progress", None)
            if callable(updater):
                updater(
                    processed=processed,
                    total=total,
                    percent=percent,
                    message=message,
                    phase=phase,
                    skipped=skipped,
                    already_trained=already_trained,
                    dataset_total=dataset_total,
                )

        self.qt_after(0, apply)


    def ensure_pi_recognition_after_training(self, timeout_seconds: int = 35):
        """Confirm Pi recognition is running, requesting a safe restart if needed.

        The Pi normally restores recognition itself after training.  SAS also
        performs this controlled fallback so a workstation cannot be left
        unable to unlock when a short camera-release delay prevents the first
        Pi restart attempt.
        """
        import time
        start = time.time()
        last_error = ""

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                if (
                    bool(status.get("recognition_running", False))
                    and not bool(status.get("capture_running", False))
                    and not bool(status.get("training_running", False))
                ):
                    return True, status

                # Never start recognition while the Pi is still training or
                # releasing a capture session.  Retry after a short delay.
                if bool(status.get("training_running", False)) or bool(status.get("capture_running", False)):
                    time.sleep(0.7)
                    continue

                try:
                    self._face_api_request("POST", "/start-recognition", timeout=15)
                except Exception as e:
                    last_error = str(e)

            except Exception as e:
                last_error = str(e)

            time.sleep(1.0)

        status = {"last_start_error": last_error} if last_error else {}
        return False, status


    def wait_until_pi_recognition_running(self, timeout_seconds: int = 20):
        """Confirm that Pi recognition has resumed after a camera workflow."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status
                if (
                    bool(status.get("recognition_running", False))
                    and not bool(status.get("capture_running", False))
                    and not bool(status.get("training_running", False))
                ):
                    return True, status
            except Exception:
                pass

            time.sleep(0.35)

        return False, last_status or {}


    def set_face_controls_training_busy(self, busy: bool):
        """Grey out controls while training is running."""
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
        if hasattr(self, "face_name_input"):
            self.face_name_input.setEnabled(not busy)


    def _face_api_train(self):
        self.face_action_feedback("TRAIN_SKIPPED: InsightFace registration stores embeddings immediately.")
        return

        self.face_action_feedback("TRAIN: User pressed Train")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        ntid = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""
        actor = self.get_audit_actor()

        # Train works on the whole dataset.
        # NTID field is ignored for Train, because training does not depend on one user ID.
        if hasattr(self, "clear_ntid_input_error"):
            self.clear_ntid_input_error()

        self.set_face_controls_training_busy(True)

        self.training_dialog = TrainingProgressDialog(
            self,
            ntid="DATASET",
            compact_mode=self.compact_mode
        )

        geo = self.geometry()
        x = geo.x() + (geo.width() - self.training_dialog.width()) // 2
        y = geo.y() + (geo.height() - self.training_dialog.height()) // 2
        self.training_dialog.move(x, y)
        self.pause_camera_for_modal()
        self.training_dialog.finished.connect(lambda _: self.resume_camera_after_modal())
        self.training_dialog.show()

        # This flag lets an in-flight auto-capture worker finish cleanly without
        # opening a separate Capture Complete card while the user is moving
        # directly from Capture to Train.
        self._training_waiting_for_capture_stop = bool(
            getattr(self, "face_capture_in_progress", False)
        )
        self.face_action_feedback("TRAIN: preparing Pi dataset training while recognition remains active...")

        def worker():
            try:
                # A Train request is allowed during SAS capture. End the capture
                # first, wait until the Pi releases its camera, then start the
                # dataset-only training job. This works for both manual and
                # auto-capture without requiring the user to press STOP first.
                capture_active = bool(getattr(self, "face_capture_in_progress", False))
                try:
                    status_before_train = self._face_api_request("GET", "/status", timeout=10)
                    capture_active = capture_active or bool(
                        status_before_train.get("capture_running", False)
                    )
                except Exception:
                    # The /train request below still gives a clear API error if
                    # the Pi cannot be reached. Keep the local state as fallback.
                    pass

                if capture_active:
                    self._training_waiting_for_capture_stop = True
                    self.qt_after(0, lambda: self.training_dialog.status_label.setText(
                        "Ending active capture before training..."
                    ))
                    self.qt_after(0, lambda: self.stop_camera_preview(show_prompt=True))
                    self.face_action_feedback(
                        "TRAIN: Capture is active. Ending capture before starting training..."
                    )

                    stop_data = self._face_api_request("POST", "/stop-capture", timeout=20)
                    stop_message = str(stop_data.get("message", "Capture stop requested.")).strip()
                    capture_stopped, _capture_status = self.wait_until_pi_capture_complete(
                        timeout_seconds=25
                    )
                    if not capture_stopped:
                        raise RuntimeError(
                            "Pi capture did not stop in time. Training was not started."
                        )

                    def capture_ended_for_training():
                        self.set_face_capture_in_progress(False)
                        self.set_capture_button_manual_mode(False)
                        self.manual_capture_user = None
                        self.face_action_feedback(
                            f"TRAIN: {stop_message} Capture ended; starting training now."
                        )

                    self.qt_after(0, capture_ended_for_training)

                # Training works on stored dataset images, not Picamera2. Close
                # only the SAS preview modal; Pi recognition continues running
                # so the workstation can still be unlocked while training runs.
                self.qt_after(0, lambda: self.training_dialog.status_label.setText("Preparing dataset training on Pi..."))
                self.qt_after(0, lambda: self.stop_camera_preview(show_prompt=True))
                self.face_action_feedback("TRAIN: Pi recognition remains active while dataset training runs")

                self.qt_after(0, lambda: self.training_dialog.status_label.setText("Calling Pi /train API..."))
                self.face_action_feedback("TRAIN: Pi /train request submitted")

                # Pi /train starts an asynchronous task. Wait for the specific
                # operation to finish, then ensure recognition is available for
                # workstation unlock again.
                data = self._face_api_request("POST", "/train", timeout=30)
                ok = bool(data.get("ok", True))
                message = data.get("message", "Training started.")
                detail = ""
                users = {}
                trained_files = []
                new_faces = 0

                if ok:
                    training_id = str(data.get("training_id") or "").strip()
                    self.qt_after(0, lambda: self.training_dialog.status_label.setText("Training face data on Pi..."))
                    training_finished, final_status = self.wait_until_pi_training_finished(
                        timeout_seconds=300,
                        training_id=training_id,
                        progress_callback=self.update_training_dialog_progress_from_status,
                    )
                    if not training_finished:
                        raise RuntimeError("Pi training did not finish in time.")

                    training_error = str(final_status.get("last_training_error") or "").strip()
                    if training_error:
                        raise RuntimeError(f"Pi training failed: {training_error}")

                    # Normal path: recognition never stopped. If the camera was
                    # interrupted externally, recover it only as a safety net.
                    recognition_running = bool(final_status.get("recognition_running", False))
                    if not recognition_running:
                        self.qt_after(0, lambda: self.training_dialog.status_label.setText("Restoring interrupted Pi recognition..."))
                        recognition_resumed, resume_status = self.ensure_pi_recognition_after_training(timeout_seconds=35)
                        if not recognition_resumed:
                            last_start_error = str(resume_status.get("last_start_error") or "").strip()
                            suffix = f" Last Pi response: {last_start_error}" if last_start_error else ""
                            raise RuntimeError("Training finished, but Pi recognition could not be restored." + suffix)

                    new_faces = int(final_status.get("last_training_new_faces", 0) or 0)
                    checked_images = int(final_status.get("training_processed", 0) or 0)
                    new_image_total = int(final_status.get("training_total", 0) or 0)
                    skipped_images = int(final_status.get("training_skipped_images", 0) or 0)
                    already_trained = int(final_status.get("training_already_trained", 0) or 0)
                    dataset_total = int(final_status.get("training_dataset_total", 0) or 0)

                    if new_image_total == 0:
                        # The completion title and dataset summary already make
                        # this state clear. Keep the main result line empty so
                        # the popup does not show a redundant "No new images"
                        # sentence under "Training Complete".
                        message = ""
                    elif new_faces > 0:
                        message = f"{new_faces} valid face image(s) trained."
                    else:
                        message = "No new image produced a valid face encoding."

                    summary_parts = []
                    if dataset_total:
                        summary_parts.append(
                            f"Dataset scan: {dataset_total} image{'s' if dataset_total != 1 else ''}."
                        )
                    if new_image_total:
                        summary_parts.append(
                            f"New images checked: {checked_images}/{new_image_total}."
                        )
                    if skipped_images:
                        summary_parts.append(
                            f"Skipped: {skipped_images} image{'s' if skipped_images != 1 else ''} did not produce one usable face encoding."
                        )
                    if already_trained:
                        summary_parts.append(
                            f"Already trained: {already_trained} image{'s' if already_trained != 1 else ''} not reprocessed."
                        )
                    summary_parts.append(
                        "Pi recognition remained active and reloaded the updated face model without reopening the camera."
                    )
                    detail = " ".join(summary_parts)

                if ok:
                    def success_done():
                        self._training_waiting_for_capture_stop = False
                        self.face_action_feedback(f"TRAIN_COMPLETE: {message} | new_faces={new_faces}")
                        self.write_sas_log(
                            "FACE TRAINING COMPLETED",
                            actor=actor,
                            details={
                                "Scope": "Full face dataset",
                                "New face encodings": new_faces,
                            },
                        )
                        if trained_files:
                            for file_key in trained_files[-8:]:
                                self.face_action_feedback(f"TRAINED_IMAGE: {file_key}")
                        if hasattr(self, "training_dialog") and self.training_dialog is not None:
                            self.training_dialog.set_processing_users(users)
                            self.training_dialog.complete_success(message, detail=detail)
                        self.set_face_controls_training_busy(False)
                        self._face_api_refresh_users()
                        self._face_api_load_logs()

                    self.qt_after(0, success_done)
                else:
                    def fail_done():
                        self._training_waiting_for_capture_stop = False
                        self.face_action_feedback(f"TRAIN_FAILED: {message}")
                        self.write_sas_log(
                            "FACE TRAINING FAILED",
                            actor=actor,
                            details={"Scope": "Full face dataset", "Result": "Failed"},
                        )
                        if hasattr(self, "training_dialog") and self.training_dialog is not None:
                            self.training_dialog.complete_failed(message, detail=detail)
                        self.set_face_controls_training_busy(False)
                        self._face_api_load_logs()

                    self.qt_after(0, fail_done)

            except Exception as e:
                # Exception variables are cleared once an ``except`` block ends.
                # Capture the text now, otherwise the deferred Qt callback can
                # raise NameError and leave the progress dialog stuck forever.
                err = str(e)

                def error_done(err=err):
                    self._training_waiting_for_capture_stop = False
                    self.face_action_feedback(f"TRAIN_FAILED: {err}")
                    self.write_sas_log(
                        "FACE TRAINING FAILED",
                        actor=actor,
                        details={"Scope": "Full face dataset", "Result": "Failed"},
                    )
                    if hasattr(self, "training_dialog") and self.training_dialog is not None:
                        self.training_dialog.complete_failed(err, detail="Training did not complete on the Pi.")
                    self.set_face_controls_training_busy(False)
                    self._face_api_load_logs()

                self.qt_after(0, error_done)

        Thread(target=worker, daemon=True).start()



    def set_ntid_input_error(self, message: str = "Please enter NTID before capture"):
        """Highlight NTID field red and show a short prompt in the input."""
        if not hasattr(self, "ntid_input"):
            return

        self.ntid_input.setObjectName("NtidInputError")
        self.ntid_input.setPlaceholderText(message)
        self.ntid_input.style().unpolish(self.ntid_input)
        self.ntid_input.style().polish(self.ntid_input)
        self.ntid_input.update()
        self.ntid_input.setFocus()


    def clear_ntid_input_error(self):
        """Restore NTID field style when user starts typing again."""
        if not hasattr(self, "ntid_input"):
            return

        if self.ntid_input.objectName() != "NtidInputError":
            return

        self.ntid_input.setObjectName("NtidInput")
        self.ntid_input.setPlaceholderText("Enter employee ID / NTID")
        self.ntid_input.style().unpolish(self.ntid_input)
        self.ntid_input.style().polish(self.ntid_input)
        self.ntid_input.update()


    def validate_primary_ntid(self, action_name: str = "this action") -> str:
        """Validate NTID before Register / Delete.

        Only NTIDs that pass Active Directory validation can continue.
        """
        user_id = self.ntid_input.text().strip() if hasattr(self, "ntid_input") else ""

        if not user_id:
            self.append_face_log(f"{action_name.upper()}_FAILED: Please enter NTID first")
            self.set_ntid_input_error(f"Please enter NTID before {action_name.lower()}")
            return ""

        # Basic input guard before calling AD.
        if not user_id.isdigit():
            self.append_face_log(f"{action_name.upper()}_FAILED: Invalid NTID format {user_id}")
            self.set_ntid_input_error("Invalid NTID format")
            return ""

        self.face_action_feedback(f"{action_name.upper()}: Validating NTID {user_id.upper()}...")

        try:
            valid = self._validate_ntid_in_ad(user_id)
        except Exception as e:
            valid = False
            self.append_face_log(f"{action_name.upper()}_FAILED: NTID validation error: {e}")

        if not valid:
            self.append_face_log(f"{action_name.upper()}_FAILED: Invalid NTID {user_id.upper()}")
            self.set_ntid_input_error("Invalid NTID. Please enter a valid NTID.")
            return ""

        self.clear_ntid_input_error()
        return user_id



    def set_capture_button_manual_mode(self, active: bool):
        """Switch Capture button between capture and legacy manual-photo mode."""
        self.manual_capture_active = bool(active)

        btn = getattr(self, "face_capture_btn", None)
        if btn is None:
            return

        if active:
            btn.setText("◎  TAKE PHOTO")
            btn.setObjectName("GreenActionButton")
            btn.setToolTip("Manual capture mode: click once for each photo.")
        else:
            btn.setText("CAPTURE")
            btn.setObjectName("OutlineActionButton")
            btn.setToolTip("Start face capture.")

        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()


    def _face_api_take_photo(self):
        """Save one photo while manual capture mode is active."""
        if not getattr(self, "manual_capture_active", False):
            self.face_action_feedback("TAKE_PHOTO_FAILED: Manual capture is not active. Press Capture first.")
            return

        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        manual_user = getattr(self, "manual_capture_user", None)
        actor = self.get_audit_actor()

        def worker():
            try:
                data = self._face_api_request("POST", "/capture-photo", timeout=25)
                message = data.get("message", "Take Photo requested.")
                count = data.get("manual_capture_count", data.get("count", ""))
                suffix = f" | photo #{count}" if count != "" else ""

                def done():
                    self.pi_connected = True
                    self.pi_connection_checked = True
                    self.set_face_controls_connection_enabled(True)
                    self.set_pi_status_label(connected=True)
                    self.face_action_feedback(f"TAKE_PHOTO: {message}{suffix}")
                    self.write_sas_log(
                        "FACE PHOTO CAPTURED",
                        actor=actor,
                        details={
                            "Face ID": str(manual_user or "Unknown").upper(),
                            "Photo number": count if count != "" else "Recorded",
                            "Mode": "Manual",
                        },
                    )
                    self._face_api_refresh_users()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.face_action_feedback(f"TAKE_PHOTO_FAILED: {err}")
                    self.write_sas_log(
                        "FACE PHOTO CAPTURE FAILED",
                        actor=actor,
                        details={"Face ID": str(manual_user or "Unknown").upper(), "Mode": "Manual", "Result": "Failed"},
                    )
                    # Keep manual mode active; user can try again or press Stop.
                    if manual_user:
                        self.manual_capture_user = manual_user
                    self.set_capture_button_manual_mode(True)
                    self.verify_pi_status_after_action("TAKE_PHOTO")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()



    def _face_api_capture_user(self):
        self.face_action_feedback("CAPTURE: User pressed Capture")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        if bool(getattr(self, "face_capture_in_progress", False)):
            self.face_action_feedback("CAPTURE_BLOCKED: Capture is already running.")
            return

        display_name = self.face_name_input.text().strip() if hasattr(self, "face_name_input") else ""
        if not display_name:
            self.face_action_feedback("CAPTURE_FAILED: Please enter employee name first")
            if hasattr(self, "face_name_input"):
                self.face_name_input.setFocus()
                self.face_name_input.setPlaceholderText("Employee name is required")
            return

        user_id = self.validate_primary_ntid("register")
        if not user_id:
            return

        actor = self.get_audit_actor()
        self.set_face_capture_in_progress(True)
        if hasattr(self, "set_camera_guidance_message"):
            self.set_camera_guidance_message("Align full face inside the guide box.")

        def worker():
            try:
                data = self._face_api_request(
                    "POST",
                    "/capture-user",
                    {
                        "user_id": user_id,
                        "employee_id": user_id,
                        "display_name": display_name,
                        "name": display_name,
                        "mode": "add",
                        "auto_capture": False,
                    },
                    timeout=120,
                )
                message = data.get("message", "Registered successfully.")
                frames = int(data.get("photos", data.get("frames", data.get("captured", 1))) or 1)

                recognition_resumed, _resume_status = self.wait_until_pi_recognition_running(timeout_seconds=35)

                def complete():
                    if hasattr(self, "set_camera_guidance_message"):
                        self.set_camera_guidance_message("")
                    self.set_face_capture_in_progress(False)
                    self.set_capture_button_manual_mode(False)
                    self.manual_capture_user = None
                    self._camera_user_stopped = False
                    self.face_action_feedback(
                        f"CAPTURE_COMPLETE: {display_name} | {user_id.upper()} | {frames} embedding sample(s)"
                    )
                    if not recognition_resumed:
                        self.face_action_feedback("CAPTURE_WARNING: Pi registered the user, but recognition did not report running yet.")
                    self.write_sas_log(
                        "FACE USER REGISTERED",
                        actor=actor,
                        details={
                            "Name": display_name,
                            "Employee ID": user_id.upper(),
                            "Samples": frames,
                            "Model": "InsightFace buffalo_s",
                        },
                    )
                    self.show_capture_complete_popup(user_id, frames)
                    if hasattr(self, "face_name_input"):
                        self.face_name_input.clear()
                        self.face_name_input.setPlaceholderText("Enter employee name for registration")
                    if hasattr(self, "ntid_input"):
                        self.ntid_input.clear()
                    self._face_api_refresh_users()
                    self.stop_camera_preview()
                    QTimer.singleShot(500, lambda: self.start_camera_preview(force=True))

                self.qt_after(0, complete)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    if hasattr(self, "set_camera_guidance_message"):
                        self.set_camera_guidance_message(err)
                    self.start_camera_preview(force=True)
                    self.face_action_feedback(f"CAPTURE_FAILED: {err}")
                    self.write_sas_log(
                        "FACE USER REGISTRATION FAILED",
                        actor=actor,
                        details={
                            "Name": display_name,
                            "Employee ID": user_id.upper(),
                            "Result": "Failed",
                        },
                    )
                    self.set_face_capture_in_progress(False)
                    self.set_capture_button_manual_mode(False)
                    self.manual_capture_user = None
                    self.verify_pi_status_after_action("CAPTURE")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()



    def _face_api_delete_user(self):
        self.face_action_feedback("DELETE: User pressed Delete")
        if not getattr(self, "pi_connected", False):
            self.show_pi_disconnected_popup("Pi API is not connected.")
            self.auto_connect_pi_for_face_tab()
            return

        user_id = self.validate_primary_ntid("delete")
        if not user_id:
            return
        display_name = self.face_name_input.text().strip() if hasattr(self, "face_name_input") else ""
        if not display_name:
            self.face_action_feedback("DELETE_FAILED: Please enter or select employee name first")
            if hasattr(self, "face_name_input"):
                self.face_name_input.setFocus()
                self.face_name_input.setPlaceholderText("Employee name is required before delete")
            return
        actor = self.get_audit_actor()

        # Prevent repeated clicks while stopping/deleting.
        self.set_face_controls_training_busy(True)
        self.face_action_feedback(f"DELETE: Deleting {user_id.upper()}...")

        def worker():
            try:
                self.qt_after(0, lambda: self.face_action_feedback(
                    f"DELETE: Deleting {user_id.upper()}. Pi will pause and restore recognition automatically..."
                ))

                data = self._face_api_request(
                    "POST",
                    "/delete-user",
                    {
                        "user_id": user_id,
                        "employee_id": user_id,
                        "display_name": display_name,
                        "name": display_name,
                    },
                    timeout=60,
                )
                message = data.get("message", "Delete requested.")

                dataset_removed = bool(data.get("dataset_removed", False))
                encodings_removed = int(data.get("encodings_removed", 0) or 0)
                resume_requested = bool(data.get("recognition_resume_requested", False))
                recognition_resumed = True
                if resume_requested:
                    recognition_resumed, _resume_status = self.wait_until_pi_recognition_running(timeout_seconds=35)

                def done():
                    self.face_action_feedback(f"DELETE_COMPLETE: {user_id.upper()} | {message}")
                    if resume_requested and not recognition_resumed:
                        self.face_action_feedback("DELETE_WARNING: User deleted, but Pi recognition did not report running yet.")
                    self.write_sas_log(
                        "FACE USER DELETED",
                        actor=actor,
                        details={
                            "Face ID": user_id.upper(),
                            "Dataset removed": "Yes" if dataset_removed else "No",
                            "Embeddings removed": encodings_removed,
                        },
                    )
                    self.show_delete_complete_popup(
                        ntid=user_id,
                        dataset_removed=dataset_removed,
                        encodings_removed=encodings_removed,
                    )
                    self._face_api_refresh_users()
                    self._face_api_load_logs()
                    self.set_face_controls_training_busy(False)

                    if hasattr(self, "ntid_input"):
                        self.ntid_input.clear()

                self.qt_after(0, done)

            except Exception as e:
                err = str(e)

                def fail(err=err):
                    self.face_action_feedback(f"DELETE_FAILED: {err}")
                    self.write_sas_log(
                        "FACE USER DELETE FAILED",
                        actor=actor,
                        details={"Face ID": user_id.upper(), "Result": "Failed"},
                    )
                    self.set_face_controls_training_busy(False)

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()



    def _face_api_refresh_users(self, show_popup_after: bool = False):
        if not str(getattr(self, "pi_api_host", "") or "").strip():
            self.append_face_log("PI_SKIPPED: Pi hostname/IP is not configured.")
            return

        """Fetch authorised users from Pi API /users.

        Background refresh updates UI only. It never opens the View All popup,
        because that caused unstable popups appearing without user action.
        """
        def worker():
            try:
                data = self._face_api_request("GET", "/users")
                users = data.get("users", [])

                def done():
                    self.pi_connection_checked = True
                    self.pi_connected = True
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
                    self.pi_connected = False
                    self.set_face_controls_connection_enabled(False)
                    self.set_pi_status_label(connected=False)
                    self.clear_all_authorized_users_ui()
                    if hasattr(self, "face_users_subtitle"):
                        self.face_users_subtitle.setText("CONNECT PI FIRST")
                    self.append_face_log(f"USERS_REFRESH_FAILED: {err}")
                    if was_connected:
                        self.handle_pi_runtime_disconnect("Pi disconnected while refreshing users. Please check Pi.")

                self.qt_after(0, fail)

        Thread(target=worker, daemon=True).start()



    def get_user_capture_frames_from_pi(self, user_id: str) -> int:
        """Read /users and find how many capture frames belong to the NTID."""
        try:
            data = self._face_api_request("GET", "/users", timeout=20)
            users = data.get("users", [])
            for user in users:
                uid = str(user.get("id", "")).strip().lower()
                if uid == str(user_id).strip().lower():
                    return int(user.get("photos", 0) or 0)
        except Exception:
            pass
        return 0


    def wait_until_pi_capture_complete(self, timeout_seconds: int = 90):
        """Wait until the Pi API reports capture is no longer running."""
        import time
        start = time.time()
        last_status = None

        while time.time() - start < timeout_seconds:
            try:
                status = self._face_api_request("GET", "/status", timeout=5)
                last_status = status
                cap = bool(status.get("capture_running", False))
                if not cap:
                    return True, status
            except Exception:
                pass
            time.sleep(0.35)

        return False, last_status or {}


    def show_capture_complete_popup(self, ntid: str, frames: int = 0):
        dialog = CaptureCompleteDialog(
            self,
            ntid=ntid,
            frames=frames,
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


    def auto_open_recognize_after_capture(self):
        """Legacy compatibility helper kept for older call sites.

        Pi recognition is resumed by the Pi service after an SAS capture ends.
        SAS only opens the Windows preview when the user presses Recognize.
        """
        self.face_action_feedback(
            "CAPTURE_COMPLETE: Pi recognition is running in the background. "
            "Press Recognize only to open the SAS preview."
        )


    def show_delete_complete_popup(self, ntid: str, dataset_removed: bool = False, encodings_removed: int = 0):
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


    def render_face_users(self, users):
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

        def user_search_text(user):
            return " ".join(
                str(user.get(key, "") or "")
                for key in ("id", "user_id", "ntid", "employee_id", "name", "display_name")
            ).lower()

        filtered = [
            u for u in users
            if keyword in user_search_text(u)
        ] if keyword else list(users)

        pi_connected = bool(getattr(self, "pi_connected", False))

        if hasattr(self, "face_users_subtitle"):
            if users:
                if keyword:
                    self.face_users_subtitle.setText(f"{len(filtered)} / {len(users)} MATCHED")
                else:
                    self.face_users_subtitle.setText(f"{len(users)} ACTIVE RECORDS")
            elif pi_connected:
                self.face_users_subtitle.setText("NO USERS REGISTERED")
            else:
                self.face_users_subtitle.setText("CONNECT PI FIRST")

        self._open_face_user_expand_card = None

        if not users:
            if pi_connected:
                msg = QLabel("No face users registered yet.")
                msg.setObjectName("FaceUserEmptyMessage")
                msg.setWordWrap(True)
                self.face_users_list_layout.addWidget(msg)
            else:
                self.face_users_list_layout.addWidget(
                    self.face_user_row("CONNECT PI", "Please connect hostname/IP first", "OFFLINE", False)
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
            uid = str(user.get("id") or user.get("user_id") or user.get("ntid") or user.get("employee_id") or "")
            display_name = str(user.get("name") or user.get("display_name") or "").strip()
            photos = user.get("photos", 0)
            row = self.face_user_row(
                uid.upper(),
                f"{photos} Capture frames",
                "",
                True,
                display_name=display_name,
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


    def _grant_access(self, name=""):
        self.end_websocket_lock_session("unlocked")
        self.runtime_lock_service.grant_access(self, name)
        # Treat a successful unlock as a fresh activity anchor so the system
        # does not instantly re-lock when there has been no physical input yet.
        self.mark_user_activity(reset_countdown=True)


    def _do_logout(self):
        self.runtime_lock_service.lock_system(self)
        if getattr(self, "pi_connected", False):
            self.start_websocket_lock_session("manual_lock")
        else:
            self.append_face_log("LOCK_SESSION_SKIPPED: Pi is not connected to this SAS.")


    def face_action_feedback(self, message: str):
        self.append_face_log(message)


    # --------------------------------------------------------
    # Fixed footer
    # --------------------------------------------------------

