from __future__ import annotations

from dashboard_dependencies import *  # noqa: F401,F403
from dashboard_typing import DashboardMixinBase


class DashboardViewMixin(DashboardMixinBase):
    def build_unified_dashboard_card(self):
        """Unified one-card dashboard using the provided locked/unlocked concept."""
        card = QFrame()
        card.setObjectName("StatusCard")
        self.status_card_widget = card
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.setMinimumHeight(430 if not self.compact_mode else 360)
        card.setMaximumHeight(720 if not self.compact_mode else 560)
        card.setMinimumWidth(980 if not self.compact_mode else 820)
        card.setMaximumWidth(2200 if not self.compact_mode else 1500)

        self.status_watermark = QLabel("🔓", card)
        self.status_watermark.setObjectName("FadeLockBgWhite")
        self.status_watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_watermark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_watermark.lower()

        def move_watermark(event):
            size = 320 if not self.compact_mode else 230
            self.status_watermark.setFixedSize(size, size)
            self.status_watermark.move(card.width() - size + 26, -28)

            # Keep the Authorized Users action as a compact floating icon at
            # the bottom-left of the green/red status card. It stays outside
            # the main centered status composition, so it does not change the
            # timer/title alignment or existing animations.
            auth_btn = getattr(self, "dashboard_authorized_users_btn", None)
            if auth_btn is not None:
                btn_size = 48 if not self.compact_mode else 40
                pad = 34 if not self.compact_mode else 24
                auth_btn.setFixedSize(btn_size, btn_size)
                auth_btn.move(pad, max(pad, card.height() - btn_size - pad))
                auth_btn.raise_()

            QFrame.resizeEvent(card, event)

        card.resizeEvent = move_watermark

        root = QVBoxLayout(card)
        root.setContentsMargins(44 if not self.compact_mode else 30, 24 if not self.compact_mode else 18,
                                44 if not self.compact_mode else 30, 24 if not self.compact_mode else 18)
        root.setSpacing(10 if not self.compact_mode else 7)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Protocol Status label removed from the Dashboard card per latest UI
        # direction. Keep the attribute for compatibility with older resize
        # styling code, but do not add it to the card layout.
        self.dashboard_protocol_label = QLabel("")
        self.dashboard_protocol_label.setObjectName("CardEyebrowWhite")
        self.dashboard_protocol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dashboard_protocol_label.setVisible(False)

        self.status_title = QLabel("SYSTEM UNLOCKED")
        self.status_title.setObjectName("UnlockedTitleWhite")
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Hidden compatibility widgets used by apply_lock_state().
        self.status_lock_icon = QLabel("🔓")
        self.status_lock_icon.setObjectName("WhiteLockIcon")
        self.status_lock_icon.setVisible(False)

        self.status_pill = QLabel("●  UNLOCKED")
        self.status_pill.setObjectName("UnlockedPillGreen")
        self.status_pill.setVisible(False)

        self.circle_flip_container = QWidget()
        self.circle_flip_container.setObjectName("CircleFlipContainer")
        circle_size = 210 if not self.compact_mode else 150
        self.circle_flip_container.setFixedSize(circle_size, circle_size)

        self.circle_stack = QStackedWidget(self.circle_flip_container)
        self.circle_stack.setObjectName("CircleStack")
        self.circle_stack.setGeometry(0, 0, circle_size, circle_size)
        self.circle_stack.setFixedSize(circle_size, circle_size)

        self.timer_circle_front = self.build_timer_circle_front(circle_size)
        self.face_circle_back = self.build_face_circle_back(circle_size)
        self.circle_stack.addWidget(self.timer_circle_front)
        self.circle_stack.addWidget(self.face_circle_back)

        self.circle_flip_overlay = FlipCircleLabel(self.circle_flip_container)
        self.circle_flip_overlay.setGeometry(0, 0, circle_size, circle_size)
        self.circle_flip_overlay.hide()

        self.countdown_title_label = QLabel("AUTO-LOCK SEQUENCE")
        self.countdown_title_label.setObjectName("CountdownTitle")
        self.countdown_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_title_label.setVisible(False)

        self.face_state_label = QLabel("Active session expires soon")
        self.face_state_label.setObjectName("CountdownDesc")
        self.face_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        actions = QHBoxLayout()
        actions.setSpacing(18 if not self.compact_mode else 12)
        actions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.manual_lock_btn = QPushButton("MANUAL LOCK")
        self.manual_lock_btn.setObjectName("ManualLockButtonWhite")
        self.manual_lock_btn.setFixedHeight(50 if not self.compact_mode else 42)
        self.manual_lock_btn.setMinimumWidth(170 if not self.compact_mode else 140)
        self.manual_lock_btn.setMaximumWidth(220 if not self.compact_mode else 180)
        self.manual_lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_lock_btn.clicked.connect(self.toggle_lock_state)

        self.dashboard_authorized_users_btn = QPushButton("👥", card)
        self.dashboard_authorized_users_btn.setObjectName("AuthorizedUsersDashboardIconButton")
        self.dashboard_authorized_users_btn.setToolTip("Authorized Users")
        self.dashboard_authorized_users_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dashboard_authorized_users_btn.clicked.connect(self.open_authorized_users_popup)

        actions.addWidget(self.manual_lock_btn)

        root.addStretch(1)
        root.addWidget(self.status_title)
        root.addSpacing(2)
        root.addWidget(self.circle_flip_container, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.face_state_label)
        root.addSpacing(6)
        root.addLayout(actions)
        root.addStretch(1)

        # Old Dashboard authorised users card is removed, but the popup uses cache.
        self.dashboard_users_box = None
        self.dashboard_users_status = None
        self.dashboard_cards = [card]

        self.apply_lock_state()
        return card



    def build_bento_cards(self):
        grid = QGridLayout()
        grid.setHorizontalSpacing(20 if not self.compact_mode else 12)
        grid.setVerticalSpacing(20 if not self.compact_mode else 12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        status = self.status_card()
        countdown = self.countdown_card()
        users = self.users_card()

        self.dashboard_cards = [status, countdown, users]
        self.update_dashboard_card_sizes()

        grid.addWidget(status, 0, 0)
        grid.addWidget(countdown, 0, 1)
        grid.addWidget(users, 0, 2)
        return grid


    def card_padding(self):
        return (34, 30) if not self.compact_mode else (22, 18)


    def status_card(self):
        card = GlassCard(green_border=True)
        self.status_card_widget = card
        card.setObjectName("StatusCard")

        # Faded lock/unlock watermark inside the card
        self.status_watermark = QLabel("🔓", card)
        self.status_watermark.setObjectName("FadeLockBgWhite")
        self.status_watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_watermark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_watermark.lower()

        def move_watermark(event):
            size = 130 if not self.compact_mode else 95
            self.status_watermark.setFixedSize(size, size)
            y_pos = 105 if not self.compact_mode else 82
            x_pos = card.width() - size - 32
            self.status_watermark.move(x_pos, y_pos)
            QFrame.resizeEvent(card, event)

        card.resizeEvent = move_watermark

        layout = QVBoxLayout(card)
        px, py = self.card_padding()
        layout.setContentsMargins(px, py, px, py)
        layout.setSpacing(20 if not self.compact_mode else 12)

        label = QLabel("PROTOCOL STATUS")
        label.setObjectName("CardEyebrowWhite")

        self.status_title = QLabel("SYSTEM UNLOCKED")
        self.status_title.setObjectName("UnlockedTitleWhite")

        layout.addWidget(label)
        layout.addWidget(self.status_title)

        middle = QHBoxLayout()
        lock_box = QVBoxLayout()

        self.status_lock_icon = QLabel("🔓")
        self.status_lock_icon.setObjectName("WhiteLockIcon")
        self.status_lock_icon.setAlignment(Qt.AlignmentFlag.AlignLeft)

        encrypted = QLabel("ENCRYPTED")
        encrypted.setObjectName("EncryptedWhite")
        lock_box.addWidget(self.status_lock_icon)
        lock_box.addWidget(encrypted)

        self.status_pill = QLabel("●  UNLOCKED")
        self.status_pill.setObjectName("UnlockedPillGreen")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFixedSize(120 if not self.compact_mode else 104, 34 if not self.compact_mode else 28)

        middle.addLayout(lock_box)
        middle.addStretch()
        middle.addWidget(self.status_pill, alignment=Qt.AlignmentFlag.AlignBottom)

        line = QFrame()
        line.setObjectName("DividerWhite")
        line.setFixedHeight(1)

        self.manual_lock_btn = QPushButton("MANUAL LOCK")
        self.manual_lock_btn.setObjectName("ManualLockButtonWhite")
        self.manual_lock_btn.setFixedHeight(42 if not self.compact_mode else 34)
        self.manual_lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_lock_btn.clicked.connect(self.toggle_lock_state)

        layout.addStretch()
        layout.addLayout(middle)
        layout.addWidget(line)
        layout.addWidget(self.manual_lock_btn)

        self.apply_lock_state()
        return card


    def countdown_card(self):
        card = GlassCard()
        self.countdown_card_widget = card
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(card)
        px, py = self.card_padding()
        layout.setContentsMargins(px, py, px, py)
        layout.setSpacing(14 if not self.compact_mode else 10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Only this circle area flips. The outer card stays fixed.
        self.circle_flip_container = QWidget()
        self.circle_flip_container.setObjectName("CircleFlipContainer")
        circle_size = 168 if not self.compact_mode else 126
        self.circle_flip_container.setFixedSize(circle_size, circle_size)

        self.circle_stack = QStackedWidget(self.circle_flip_container)
        self.circle_stack.setObjectName("CircleStack")
        self.circle_stack.setGeometry(0, 0, circle_size, circle_size)
        self.circle_stack.setFixedSize(circle_size, circle_size)

        self.timer_circle_front = self.build_timer_circle_front(circle_size)
        self.face_circle_back = self.build_face_circle_back(circle_size)

        self.circle_stack.addWidget(self.timer_circle_front)
        self.circle_stack.addWidget(self.face_circle_back)

        # Overlay used only during flip animation.
        # It draws a compressed pixmap, so the circle is not cut/clipped.
        self.circle_flip_overlay = FlipCircleLabel(self.circle_flip_container)
        self.circle_flip_overlay.setGeometry(0, 0, circle_size, circle_size)
        self.circle_flip_overlay.hide()

        self.countdown_title_label = QLabel("Auto-Lock Sequence")
        self.countdown_title_label.setObjectName("CountdownTitle")
        self.countdown_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_state_label = QLabel("Active session expires soon")
        self.face_state_label.setObjectName("CountdownDesc")
        self.face_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(12)
        layout.addStretch(1)
        layout.addWidget(self.circle_flip_container, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.countdown_title_label)
        layout.addWidget(self.face_state_label)
        layout.addStretch(1)

        # Temporary testing: click the card to toggle face detected / not detected.
        # Runtime face unlock now arrives from Pi WebSocket events.
        card.mousePressEvent = lambda event: self.set_face_detected(not self.face_detected)

        return card


    def build_timer_circle_front(self, circle_size: int):
        front = QWidget()
        front.setObjectName("CircleFace")
        front.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(front)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ring = ProgressRing(self.total_seconds, self.time_left)
        self.ring.setFixedSize(circle_size, circle_size)

        self.countdown_label = QLabel("00:17")
        self.countdown_label.setObjectName("CountdownText")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        remaining = QLabel("REMAINING")
        remaining.setObjectName("RemainingText")
        remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)

        overlay = QVBoxLayout(self.ring)
        overlay.setContentsMargins(0, 0, 0, 0)
        overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay.addWidget(self.countdown_label)
        overlay.addWidget(remaining)

        layout.addWidget(self.ring)
        return front


    def build_face_circle_back(self, circle_size: int):
        back = QFrame()
        back.setObjectName("FaceDetectedCircle")
        back.setFixedSize(circle_size, circle_size)

        layout = QVBoxLayout(back)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_detected_icon = QLabel("☻")
        self.face_detected_icon.setObjectName("FaceDetectedIcon")
        self.face_detected_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_detected_circle_text = QLabel("FACE DETECTED")
        self.face_detected_circle_text.setObjectName("FaceDetectedCircleText")
        self.face_detected_circle_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Slightly move the face icon and text upward for better visual balance.
        layout.addStretch(2)
        layout.addWidget(self.face_detected_icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.face_detected_circle_text, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(3)

        return back


    def set_face_detected(self, detected: bool):
        """Update face state.

        detected=True:
            - authorised face is currently detected
            - countdown pauses
            - only the circle flips like a coin
            - label below changes to authorised user detected

        detected=False:
            - face not detected
            - countdown resumes
            - circle flips back to timer
        """
        if self.face_detected == detected and not self._circle_flip_animating:
            return

        # If user clicks very fast, do not start another animation in the middle.
        # Store the latest target and apply it when the current flip finishes.
        if self._circle_flip_animating:
            self._pending_face_detected_state = detected
            return

        self.face_detected = detected
        target_index = 1 if detected else 0

        self.flip_countdown_circle(target_index, detected)


    def update_face_detected_label(self, detected: bool):
        if not hasattr(self, "face_state_label"):
            return

        if detected:
            self.face_state_label.setText("●  AUTHORISED USER DETECTED")
            self.face_state_label.setObjectName("FaceDetectedState")
        else:
            self.face_state_label.setText("Active session expires soon")
            self.face_state_label.setObjectName("CountdownDesc")

        self.face_state_label.style().unpolish(self.face_state_label)
        self.face_state_label.style().polish(self.face_state_label)
        self.face_state_label.update()


    def grab_circle_face(self, widget: QWidget) -> QPixmap:
        """Grab a transparent pixmap of a circle face for the coin-flip overlay."""
        pixmap = QPixmap(widget.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        widget.render(pixmap)
        return pixmap


    def flip_countdown_circle(self, target_index: int, detected: bool):
        """Coin-style flip for only the circle.

        The old version animated the QWidget width directly. That caused the
        circle to look cut. This version takes a pixmap snapshot and compresses
        the image horizontally like a coin flip.
        """
        if not hasattr(self, "circle_flip_container") or not hasattr(self, "circle_stack"):
            return

        if not hasattr(self, "circle_flip_overlay"):
            self.circle_stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            return

        holder = self.circle_flip_container
        stack = self.circle_stack
        overlay = self.circle_flip_overlay

        full_w = max(1, holder.width())
        full_h = max(1, holder.height())

        if full_w <= 1 or full_h <= 1:
            stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            return

        self._circle_flip_animating = True

        # Keep overlay aligned and use snapshots for animation.
        overlay.setGeometry(0, 0, full_w, full_h)

        current_widget = stack.currentWidget()
        target_widget = stack.widget(target_index)

        if current_widget is None or target_widget is None:
            stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            self._circle_flip_animating = False
            return

        start_pixmap = self.grab_circle_face(current_widget)
        target_pixmap = self.grab_circle_face(target_widget)

        overlay.set_pixmap(start_pixmap)
        overlay.set_scale_x(1.0)
        overlay.show()
        overlay.raise_()
        stack.hide()

        if self._countdown_flip_anim_1 is not None:
            self._countdown_flip_anim_1.stop()

        if self._countdown_flip_anim_2 is not None:
            self._countdown_flip_anim_2.stop()

        self._countdown_flip_anim_1 = QPropertyAnimation(overlay, b"scaleX", self)
        self._countdown_flip_anim_1.setDuration(170)
        self._countdown_flip_anim_1.setStartValue(1.0)
        self._countdown_flip_anim_1.setEndValue(0.08)
        self._countdown_flip_anim_1.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._countdown_flip_anim_2 = QPropertyAnimation(overlay, b"scaleX", self)
        self._countdown_flip_anim_2.setDuration(210)
        self._countdown_flip_anim_2.setStartValue(0.08)
        self._countdown_flip_anim_2.setEndValue(1.0)
        self._countdown_flip_anim_2.setEasingCurve(QEasingCurve.Type.OutCubic)

        first_anim = self._countdown_flip_anim_1
        second_anim = self._countdown_flip_anim_2

        def switch_face():
            stack.setCurrentIndex(target_index)
            self.update_face_detected_label(detected)
            overlay.set_pixmap(target_pixmap)
            second_anim.start()

        def finish_flip():
            overlay.hide()
            stack.show()
            overlay.set_scale_x(1.0)

            self._circle_flip_animating = False

            # If user clicked again during animation, apply latest requested state now.
            pending = self._pending_face_detected_state
            self._pending_face_detected_state = None

            if pending is not None and pending != self.face_detected:
                self.set_face_detected(pending)

        first_anim.finished.connect(switch_face)
        second_anim.finished.connect(finish_flip)
        first_anim.start()


    def users_card(self):
        card = GlassCard()
        layout = QVBoxLayout(card)
        px, py = self.card_padding()
        layout.setContentsMargins(px, py, px, py)
        layout.setSpacing(20 if not self.compact_mode else 12)

        header = QHBoxLayout()
        title = QLabel("AUTHORIZED USERS")
        title.setObjectName("UsersTitle")
        self.dashboard_users_status = QLabel("STATUS     Connect Pi")
        self.dashboard_users_status.setObjectName("UsersStatus")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.dashboard_users_status)
        layout.addLayout(header)

        users_divider = QFrame()
        users_divider.setObjectName("UsersDivider")
        users_divider.setFixedHeight(1)
        layout.addWidget(users_divider)

        self.dashboard_users_box = QVBoxLayout()
        self.dashboard_users_box.setSpacing(18 if not self.compact_mode else 10)
        layout.addLayout(self.dashboard_users_box)
        layout.addStretch()

        view_all = QPushButton("VIEW ALL")
        view_all.setObjectName("ManageAccessButton")
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.setFixedHeight(42 if not self.compact_mode else 34)
        view_all.clicked.connect(self.open_authorized_users_popup)
        layout.addWidget(view_all)

        self.render_dashboard_users([])
        return card


    def clear_layout_widgets(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout_widgets(child_layout)


    def clear_all_authorized_users_ui(self):
        """Clear cached authorised users when Pi is offline/disconnected."""
        self.face_users_cache = []

        if hasattr(self, "dashboard_users_box"):
            self.render_dashboard_users([])

        if hasattr(self, "face_users_layout"):
            self.render_face_users([])



    def render_dashboard_users(self, users):
        """Render authorised users on Dashboard card.

        Show only the amount that can fit in the dashboard box.
        The full list is available through View All.
        """
        self.face_users_cache = users or []

        if not hasattr(self, "dashboard_users_box") or self.dashboard_users_box is None:
            self.face_users_cache = users or []
            return

        self.clear_layout_widgets(self.dashboard_users_box)

        if not users:
            status_label = getattr(self, "dashboard_users_status", None)
            if isinstance(status_label, QLabel):
                status_label.setText("STATUS     Connect Pi")

            hint = QLabel("Please connect Pi hostname/IP to fetch authorised users.")
            hint.setObjectName("UserDetail")
            hint.setWordWrap(True)
            self.dashboard_users_box.addWidget(hint)
            return

        active_count = len(users)
        status_label = getattr(self, "dashboard_users_status", None)
        if isinstance(status_label, QLabel):
            status_label.setText(f"STATUS     {active_count} active")

        # Show as many as the card can comfortably fit.
        # Normal desktop card fits around 6 rows; compact laptop layout fits fewer.
        max_visible = 6 if not self.compact_mode else 4

        for user in users[:max_visible]:
            uid = str(user.get("id", "")).upper()
            photos = int(user.get("photos", 0) or 0)
            self.dashboard_users_box.addWidget(self.user_row(uid, f"{photos} Photos", True))

        remaining = active_count - max_visible
        if remaining > 0:
            more = QLabel(f"+ {remaining} more users. Click View All.")
            more.setObjectName("UserDetail")
            self.dashboard_users_box.addWidget(more)



    def open_authorized_users_popup(self):
        """Show full authorised users list with search.

        Important: this should only open because the user clicked View All.
        It must not re-open later from a background refresh.
        """
        users = getattr(self, "face_users_cache", [])

        if not getattr(self, "pi_connected", False):
            self.show_authorized_users_dialog([], connected=False)
            return

        self.show_authorized_users_dialog(users, connected=True)



    def show_authorized_users_dialog(self, users, connected=True):
        """Stable Authorized Users popup.

        Shows up to 6 rows in the visible area. If more than 6 users exist,
        the list scrolls inside the popup instead of enlarging the popup.
        """
        dialog = QDialog(self)
        dialog.setObjectName("AuthorizedUsersDialog")
        dialog.setModal(True)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(650 if not self.compact_mode else 560, 640 if not self.compact_mode else 570)
        dialog.setWindowOpacity(0.0)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("AuthorizedUsersCard")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 58))
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(34 if not self.compact_mode else 26, 26 if not self.compact_mode else 22, 34 if not self.compact_mode else 26, 24 if not self.compact_mode else 20)
        root.setSpacing(14 if not self.compact_mode else 12)

        top = QHBoxLayout()
        top_left = QVBoxLayout()
        top_left.setSpacing(6)

        eyebrow = QLabel("▣  SYSTEM REGISTRY")
        eyebrow.setObjectName("AuthorizedUsersEyebrow")
        title = QLabel("Authorized Users")
        title.setObjectName("AuthorizedUsersTitle")

        top_left.addWidget(eyebrow)
        top_left.addWidget(title)

        count = QLabel(f"{len(users)} RECORDS" if connected else "DISCONNECTED")
        count.setObjectName("AuthorizedUsersCount")
        count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        close_top = QPushButton("×")
        close_top.setObjectName("AuthorizedRoundCloseButton")
        close_top.setCursor(Qt.CursorShape.PointingHandCursor)
        close_top.setFixedSize(44 if not self.compact_mode else 38, 44 if not self.compact_mode else 38)
        close_top.clicked.connect(dialog.accept)

        right_top = QVBoxLayout()
        right_top.setSpacing(12)
        right_top.addWidget(count, alignment=Qt.AlignmentFlag.AlignRight)
        right_top.addWidget(close_top, alignment=Qt.AlignmentFlag.AlignRight)

        top.addLayout(top_left, 1)
        top.addLayout(right_top)
        root.addLayout(top)

        search_box = QFrame()
        search_box.setObjectName("AuthorizedSearchBox")
        search_box.setFixedHeight(52 if not self.compact_mode else 46)
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(14, 0, 12, 0)
        search_layout.setSpacing(10)

        search_icon = QLabel("⌕")
        search_icon.setObjectName("AuthorizedSearchIcon")

        search = QLineEdit()
        search.setObjectName("AuthorizedSearchInput")
        search.setPlaceholderText("Search name or NTID...")
        search.setClearButtonEnabled(True)

        search_layout.addWidget(search_icon)
        search_layout.addWidget(search, 1)

        root.addWidget(search_box)

        scroll = QScrollArea()
        scroll.setObjectName("AuthorizedUsersScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.make_scrollbar_invisible(scroll)

        row_h = 64 if not self.compact_mode else 56
        max_visible_rows = 6
        scroll.setFixedHeight((row_h * max_visible_rows) + 22)

        body = QWidget()
        body.setObjectName("AuthorizedUsersBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 8, 0, 8)
        body_layout.setSpacing(0)
        scroll.setWidget(body)

        root.addWidget(scroll)

        def clear_rows():
            while body_layout.count():
                item = body_layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                child_layout = item.layout()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                elif child_layout is not None:
                    self.clear_layout_widgets(child_layout)

        def popup_row(user, display_no: int):
            uid = str(user.get("id") or user.get("user_id") or user.get("ntid") or user.get("employee_id") or "").upper()
            display_name = str(user.get("name") or user.get("display_name") or "").strip()
            photos = int(user.get("photos", 0) or 0)
            row = QFrame()
            row.setObjectName("AuthorizedPopupRow")
            row.setMinimumHeight(row_h)
            row.setMaximumHeight(row_h)

            lay = QHBoxLayout(row)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.setSpacing(12)

            avatar = QLabel(str(display_no))
            avatar.setObjectName("AuthorizedUserAvatar")
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFixedSize(38 if not self.compact_mode else 34, 38 if not self.compact_mode else 34)

            text = QVBoxLayout()
            text.setSpacing(4)

            name = QLabel(display_name or uid)
            name.setObjectName("AuthorizedPopupName")

            detail_text = f"{uid} | {photos} Capture frames stored" if display_name else f"{photos} Capture frames stored"
            detail = QLabel(detail_text)
            detail.setObjectName("AuthorizedPopupDetail")

            text.addWidget(name)
            text.addWidget(detail)

            lay.addWidget(avatar)
            lay.addLayout(text, 1)

            return row

        def render_list():
            clear_rows()
            keyword = search.text().strip().lower()

            if not connected:
                count.setText("DISCONNECTED")
                msg = QLabel("Please connect Pi hostname/IP first to fetch authorised users.")
                msg.setObjectName("AuthorizedPopupEmpty")
                msg.setWordWrap(True)
                body_layout.addWidget(msg)
                body_layout.addStretch()
                return

            def user_search_text(user):
                return " ".join(
                    str(user.get(key, "") or "")
                    for key in ("id", "user_id", "ntid", "employee_id", "name", "display_name")
                ).lower()

            filtered = [
                u for u in users
                if keyword in user_search_text(u)
            ] if keyword else list(users)

            if keyword:
                count.setText(f"{len(filtered)} / {len(users)} MATCHED")
            else:
                count.setText(f"{len(users)} RECORDS")

            if not filtered:
                msg = QLabel("No matching user found.")
                msg.setObjectName("AuthorizedPopupEmpty")
                body_layout.addWidget(msg)
            else:
                for index, user in enumerate(filtered, start=1):
                    body_layout.addWidget(popup_row(user, index))

            body_layout.addStretch()
            body.updateGeometry()
            scroll.viewport().update()
            QTimer.singleShot(0, lambda: scroll.verticalScrollBar().setValue(0))

        search.textChanged.connect(render_list)
        render_list()

        close_btn = QPushButton("CLOSE")
        close_btn.setObjectName("AuthorizedCloseButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(44 if not self.compact_mode else 38)
        close_btn.clicked.connect(dialog.accept)
        root.addWidget(close_btn)

        geo = self.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)

        popup_opacity_anim = QPropertyAnimation(dialog, b"windowOpacity", dialog)
        popup_opacity_anim.setDuration(150)
        popup_opacity_anim.setStartValue(0.0)
        popup_opacity_anim.setEndValue(1.0)
        popup_opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.pause_camera_for_modal()
        try:
            QTimer.singleShot(0, popup_opacity_anim.start)
            dialog.exec()
        finally:
            self.resume_camera_after_modal()



    def user_row(self, user_id, detail, active=True):
        row = QFrame()
        row.setObjectName("UserRow")
        row.setFixedHeight(44 if not self.compact_mode else 34)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        text = QVBoxLayout()
        name = QLabel(user_id)
        name.setObjectName("UserName")
        sub = QLabel(detail)
        sub.setObjectName("UserDetail")
        text.addWidget(name)
        text.addWidget(sub)

        right = QLabel("●") if active else QLabel("Idle")
        right.setObjectName("GreenDot" if active else "IdleText")

        layout.addLayout(text)
        layout.addStretch()
        layout.addWidget(right)
        return row

    # --------------------------------------------------------
    # Face recognition page parts
    # --------------------------------------------------------

