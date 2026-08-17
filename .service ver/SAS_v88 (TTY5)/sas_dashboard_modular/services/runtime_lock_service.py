import time
import ctypes
from threading import Thread

try:
    import keyboard
except Exception:
    keyboard = None

try:
    import pyautogui
except Exception:
    pyautogui = None


class RuntimeLockService:
    """Runtime lock state coordinator.

    Migrated/adapted from lockapp.py:
    - lock/unlock state control
    - keyboard disable/enable
    - mouse disable/enable
    - emergency hotkey
    - optional USB flag placeholder
    - system idle polling hook

    Emergency unlock hotkey:
        Ctrl + Shift + Alt
    """

    def __init__(self):
        self._mouse_lock_running = False
        self._mouse_hook_handle = None
        self._mouse_hook_proc = None
        self._mouse_anchor = None
        self._keyboard_disabled = False
        self._hotkey_registered = False
        self._usb_disabled = False
        self._last_runtime_state = None

        # Backup emergency unlock monitor.
        # keyboard.add_hotkey can stop working after Windows lock screen /
        # secure desktop transitions, so we also poll physical key state using
        # Win32 GetAsyncKeyState. This keeps Ctrl+Shift+Alt usable after resume.
        self._emergency_watchdog_running = False
        self._emergency_last_fire = 0
        self._hotkey_last_registered = 0

    # --------------------------------------------------------
    # Main state control
    # --------------------------------------------------------
    def grant_access(self, dashboard, name=""):
        dashboard.is_logged_in = True
        dashboard.is_locked = False
        dashboard.apply_lock_state()
        self.apply_lock_controls(dashboard)
        dashboard.hide_locked_alert_overlay()
        dashboard.append_system_log("Access granted" + (f": {name}" if name else ""))

    def lock_system(self, dashboard):
        dashboard.is_logged_in = False
        dashboard.is_locked = True
        dashboard.apply_lock_state()
        dashboard.set_face_detected(False)
        self.apply_lock_controls(dashboard)
        dashboard.append_system_log("System locked. Waiting for face match.")

    def emergency_unlock(self, dashboard):
        """Emergency unlock. Always keeps keyboard/mouse enabled afterwards.

        Important fix:
        A previous countdown may have already scheduled a delayed auto-lock when
        the timer reached 00:00. Emergency unlock must cancel that pending lock
        and reset the countdown back to the user's configured timeout.
        """
        try:
            dashboard.append_system_log("Emergency unlock activated using Ctrl + Shift + Alt.")
            if hasattr(dashboard, "write_sas_log"):
                dashboard.write_sas_log("UNLOCKED | USER=EMERGENCY | METHOD=EMERGENCY_HOTKEY | CONFIDENCE=N/A")

            # Release input first. This is important after Windows desktop
            # lock/unlock because a stale keyboard hook can keep blocking input.
            self.enable_keyboard(dashboard)
            self.enable_mouse(dashboard)
            self.enable_usb(dashboard)

            # Cancel any delayed lock that was scheduled from a previous 00:00 state.
            dashboard._pending_auto_lock = False

            dashboard.is_locked = False
            dashboard.is_logged_in = True

            # Emergency unlock is a temporary override session.
            # Always show it clearly in the account button/menu.
            dashboard.current_user = "EMERGENCY"
            dashboard.current_user_role = "Override"
            dashboard.is_admin = False

            # Reset countdown to the user-configured lock timeout.
            dashboard.total_seconds = max(1, int(getattr(dashboard, "lock_timeout_seconds", 300)))
            dashboard.time_left = dashboard.total_seconds

            if hasattr(dashboard, "ring"):
                dashboard.ring.set_total_seconds(dashboard.total_seconds)
                dashboard.ring.set_time_left(dashboard.time_left, animate=False)

            if hasattr(dashboard, "countdown_label"):
                mins = dashboard.time_left // 60
                secs = dashboard.time_left % 60
                dashboard.countdown_label.setText(f"{mins:02d}:{secs:02d}")

            # Keep the face state true briefly so update_countdown will not
            # instantly reduce from 00:00 on the same event cycle.
            dashboard.set_face_detected(True)

            dashboard.apply_lock_state()

            # Force the header Login button and account dropdown text to refresh.
            if hasattr(dashboard, "update_account_ui"):
                dashboard.update_account_ui()
                dashboard.append_system_log("Account button updated to Admin")

            if hasattr(dashboard, "open_pending_restricted_tab_if_allowed"):
                dashboard.open_pending_restricted_tab_if_allowed()

            if hasattr(dashboard, "account_menu_user"):
                dashboard.account_menu_user.setText("ADMIN")

            dashboard.hide_locked_alert_overlay()

            # After a short buffer, allow normal no-face countdown to resume.
            # If recognition_result.json becomes valid, poll_recognition_result()
            # will keep it in face-detected state anyway.
            dashboard.qt_after(1200, lambda: dashboard.set_face_detected(False))

        except Exception as e:
            dashboard.append_system_log(f"Emergency unlock error: {e}")

    def update_face_detected_from_result(self, dashboard, result_tuple):
        state, ntid, detected_time, confidence = result_tuple
        if state == "valid":
            dashboard.set_face_detected(True)
            return True
        dashboard.set_face_detected(False)
        return False

    # --------------------------------------------------------
    # Apply saved security options
    # --------------------------------------------------------
    def apply_security_options(self, dashboard):
        if getattr(dashboard, "enable_hotkey", True):
            self.register_emergency_hotkey(dashboard)
        else:
            self.clear_hotkeys(dashboard)

        self.apply_lock_controls(dashboard)

    def apply_lock_controls(self, dashboard):
        """Same logic as lockapp.py: only block input while locked."""
        if getattr(dashboard, "enable_hotkey", True):
            self.register_emergency_hotkey(dashboard)
            self.refresh_emergency_hotkey_if_needed(dashboard)

        if getattr(dashboard, "is_locked", False):
            if getattr(dashboard, "disable_keyboard_when_locked", False):
                self.disable_keyboard(dashboard)
            else:
                self.enable_keyboard(dashboard)

            if getattr(dashboard, "disable_mouse_when_locked", False):
                self.disable_mouse(dashboard)
            else:
                self.enable_mouse(dashboard)

            if getattr(dashboard, "disable_usb_when_locked", False):
                self.disable_usb(dashboard)
            else:
                self.enable_usb(dashboard)
        else:
            self.enable_keyboard(dashboard)
            self.enable_mouse(dashboard)
            self.enable_usb(dashboard)

    # --------------------------------------------------------
    # Keyboard lock
    # --------------------------------------------------------
    def start_emergency_hotkey_watchdog(self, dashboard):
        """Start backup emergency hotkey polling.

        Why needed:
        After Windows lock screen / unlock, the keyboard module hook may stop
        receiving the hotkey. This watchdog uses ctypes GetAsyncKeyState, so
        the emergency unlock still works after the desktop is opened again.
        """
        if self._emergency_watchdog_running:
            return

        self._emergency_watchdog_running = True

        def watchdog_loop():
            while self._emergency_watchdog_running:
                try:
                    if getattr(dashboard, "enable_hotkey", True):
                        self.poll_emergency_hotkey_state(dashboard)
                except Exception:
                    pass

                time.sleep(0.12)

        Thread(target=watchdog_loop, daemon=True).start()

    def poll_emergency_hotkey_state(self, dashboard):
        """Physical-state emergency unlock fallback.

        Hotkey:
            Ctrl + Shift + Alt

        Uses VK codes:
            Ctrl  = 0x11
            Shift = 0x10
            Alt   = 0x12
        """
        if not getattr(dashboard, "is_locked", False):
            return

        # Windows only. On non-Windows, ctypes.windll does not exist.
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return

        def pressed(vk):
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)

        ctrl = pressed(0x11)
        shift = pressed(0x10)
        alt = pressed(0x12)

        if ctrl and shift and alt:
            now = time.time()

            # Debounce so one key hold does not trigger repeatedly.
            if now - self._emergency_last_fire < 1.2:
                return

            self._emergency_last_fire = now
            dashboard.qt_after(0, lambda: self.emergency_unlock(dashboard))

    def refresh_emergency_hotkey_if_needed(self, dashboard):
        """Occasionally re-register keyboard hook while locked.

        This helps after Windows secure desktop transitions without constantly
        clearing hooks on every UI tick.
        """
        if keyboard is None:
            return

        if not getattr(dashboard, "enable_hotkey", True):
            return

        if not getattr(dashboard, "is_locked", False):
            return

        now = time.time()
        if now - self._hotkey_last_registered < 6:
            return

        self._hotkey_last_registered = now

        try:
            keyboard.clear_all_hotkeys()
            keyboard.add_hotkey(
                "ctrl+shift+alt",
                lambda: dashboard.qt_after(0, lambda: self.emergency_unlock(dashboard)),
                suppress=False,
            )
            self._hotkey_registered = True
        except Exception:
            pass

    def register_emergency_hotkey(self, dashboard):
        # Always start backup watchdog, even if keyboard module is unavailable.
        self.start_emergency_hotkey_watchdog(dashboard)

        if keyboard is None:
            dashboard.append_system_log("Emergency hotkey fallback active: keyboard module is not installed.")
            return

        try:
            keyboard.clear_all_hotkeys()
            keyboard.add_hotkey(
                "ctrl+shift+alt",
                lambda: dashboard.qt_after(0, lambda: self.emergency_unlock(dashboard)),
                suppress=False,
            )
            self._hotkey_registered = True
            self._hotkey_last_registered = time.time()
            print("[EMERGENCY HOTKEY REGISTERED + WATCHDOG ACTIVE]")
        except Exception as e:
            dashboard.append_system_log(f"Emergency hotkey fallback active. keyboard module error: {e}")


    def clear_hotkeys(self, dashboard):
        self._emergency_watchdog_running = False

        if keyboard is None:
            return
        try:
            keyboard.clear_all_hotkeys()
            self._hotkey_registered = False
        except Exception as e:
            dashboard.append_system_log(f"Clear hotkey error: {e}")


    def disable_keyboard(self, dashboard):
        if keyboard is None:
            dashboard.append_system_log("Keyboard disable unavailable: keyboard module is not installed.")
            return

        try:
            keyboard.unhook_all()

            # Important: re-register emergency hotkey after unhooking.
            if getattr(dashboard, "enable_hotkey", True):
                self.register_emergency_hotkey(dashboard)

            blocked_keys = [
                "a","b","c","d","e","f","g","h","i","j","k","l","m",
                "n","o","p","q","r","s","t","u","v","w","x","y","z",
                "0","1","2","3","4","5","6","7","8","9",
                "`","~","-","_","=","+","[","{","]","}","\\\\","|",
                ";",":","'",'"',",","<",".",">","/","?","*",
                "space","enter","tab","esc","backspace","delete",
                "insert","home","end","page up","page down",
                "up","down","left","right",
                "windows","cmd","menu",
                "f1","f2","f3","f4","f5","f6",
                "f7","f8","f9","f10","f11","f12",
                "print screen","scroll lock","pause","caps lock","num lock",
            ]

            for key in blocked_keys:
                try:
                    keyboard.block_key(key)
                except Exception:
                    pass

            self._keyboard_disabled = True
            print("[KEYBOARD DISABLED] Emergency hotkey still active")

        except Exception as e:
            dashboard.append_system_log(f"Keyboard disable error: {e}")

    def enable_keyboard(self, dashboard):
        if keyboard is None:
            return

        try:
            keyboard.unhook_all()
            self._keyboard_disabled = False

            # Keep emergency hotkey active even after keyboard is restored.
            if getattr(dashboard, "enable_hotkey", True):
                self.register_emergency_hotkey(dashboard)

            print("[KEYBOARD ENABLED]")

        except Exception as e:
            dashboard.append_system_log(f"Keyboard enable error: {e}")

    # --------------------------------------------------------
    # Mouse lock
    # --------------------------------------------------------
    def _get_cursor_pos(self):
        """Return current Windows cursor position without requiring pyautogui."""
        try:
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            point = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return int(point.x), int(point.y)
        except Exception:
            if pyautogui is not None:
                try:
                    return pyautogui.position()
                except Exception:
                    pass
            return 0, 0

    def _clip_cursor_to_point(self, x, y):
        """Confine Windows cursor to a 1x1 rectangle at x,y."""
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT(int(x), int(y), int(x) + 1, int(y) + 1)
            ctypes.windll.user32.ClipCursor(ctypes.byref(rect))
        except Exception:
            pass

    def _release_cursor_clip(self):
        try:
            ctypes.windll.user32.ClipCursor(None)
        except Exception:
            pass

    def _install_mouse_click_block_hook(self, dashboard):
        """Install a low-level Windows mouse hook to swallow mouse clicks/move.

        This makes the mouse feel disabled, not just pulled back. It blocks:
        movement, left/right/middle/X clicks, wheel, and horizontal wheel while
        SAS is locked and Disable Mouse When Locked is enabled.
        """
        if self._mouse_hook_handle is not None:
            return

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except Exception:
            return

        try:
            WH_MOUSE_LL = 14
            WM_MOUSEMOVE = 0x0200
            WM_LBUTTONDOWN = 0x0201
            WM_LBUTTONUP = 0x0202
            WM_LBUTTONDBLCLK = 0x0203
            WM_RBUTTONDOWN = 0x0204
            WM_RBUTTONUP = 0x0205
            WM_RBUTTONDBLCLK = 0x0206
            WM_MBUTTONDOWN = 0x0207
            WM_MBUTTONUP = 0x0208
            WM_MBUTTONDBLCLK = 0x0209
            WM_MOUSEWHEEL = 0x020A
            WM_XBUTTONDOWN = 0x020B
            WM_XBUTTONUP = 0x020C
            WM_XBUTTONDBLCLK = 0x020D
            WM_MOUSEHWHEEL = 0x020E

            blocked_messages = {
                WM_MOUSEMOVE,
                WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK,
                WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK,
                WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK,
                WM_MOUSEWHEEL, WM_MOUSEHWHEEL,
                WM_XBUTTONDOWN, WM_XBUTTONUP, WM_XBUTTONDBLCLK,
            }

            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p)

            def low_level_mouse_proc(nCode, wParam, lParam):
                try:
                    if (
                        nCode >= 0
                        and int(wParam) in blocked_messages
                        and getattr(dashboard, "is_locked", False)
                        and getattr(dashboard, "disable_mouse_when_locked", False)
                        and self._mouse_lock_running
                    ):
                        # Swallow the event so clicking is not passed to any app.
                        return 1
                except Exception:
                    pass

                try:
                    return user32.CallNextHookEx(self._mouse_hook_handle, nCode, wParam, lParam)
                except Exception:
                    return 0

            self._mouse_hook_proc = HOOKPROC(low_level_mouse_proc)
            hmod = kernel32.GetModuleHandleW(None)
            self._mouse_hook_handle = user32.SetWindowsHookExW(
                WH_MOUSE_LL,
                self._mouse_hook_proc,
                hmod,
                0,
            )

            if not self._mouse_hook_handle:
                self._mouse_hook_handle = None
                self._mouse_hook_proc = None
                dashboard.append_system_log("Mouse click block hook could not be installed.")
                return

            def message_pump():
                try:
                    class MSG(ctypes.Structure):
                        _fields_ = [
                            ("hwnd", ctypes.c_void_p),
                            ("message", ctypes.c_uint),
                            ("wParam", ctypes.c_void_p),
                            ("lParam", ctypes.c_void_p),
                            ("time", ctypes.c_uint),
                            ("pt_x", ctypes.c_long),
                            ("pt_y", ctypes.c_long),
                        ]

                    msg = MSG()
                    while self._mouse_lock_running and self._mouse_hook_handle is not None:
                        # Non-blocking pump with short sleep keeps callback active.
                        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            user32.TranslateMessage(ctypes.byref(msg))
                            user32.DispatchMessageW(ctypes.byref(msg))
                        time.sleep(0.01)
                except Exception:
                    pass

            Thread(target=message_pump, daemon=True).start()
            dashboard.append_system_log("Mouse click block hook installed.")

        except Exception as e:
            try:
                dashboard.append_system_log(f"Mouse click block hook error: {e}")
            except Exception:
                pass
            self._mouse_hook_handle = None
            self._mouse_hook_proc = None

    def _uninstall_mouse_click_block_hook(self):
        try:
            if self._mouse_hook_handle is not None:
                ctypes.windll.user32.UnhookWindowsHookEx(self._mouse_hook_handle)
        except Exception:
            pass
        self._mouse_hook_handle = None
        self._mouse_hook_proc = None

    def disable_mouse(self, dashboard):
        try:
            if self._mouse_lock_running:
                return

            self._mouse_lock_running = True

            x, y = self._get_cursor_pos()
            self._mouse_anchor = (x, y)

            # Strong Windows-level confinement makes the cursor feel disabled.
            self._clip_cursor_to_point(x, y)
            try:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
            except Exception:
                pass

            # Block clicks/wheel/move events so user cannot click while locked.
            self._install_mouse_click_block_hook(dashboard)

            def lock_mouse_loop():
                try:
                    anchor_x, anchor_y = self._mouse_anchor or (x, y)

                    while (
                        self._mouse_lock_running
                        and getattr(dashboard, "is_locked", False)
                        and getattr(dashboard, "disable_mouse_when_locked", False)
                    ):
                        try:
                            self._clip_cursor_to_point(anchor_x, anchor_y)
                            ctypes.windll.user32.SetCursorPos(int(anchor_x), int(anchor_y))
                        except Exception:
                            pass

                        # Fast loop: user should not see pull-back movement.
                        time.sleep(0.002)

                except Exception as e:
                    try:
                        dashboard.qt_after(0, lambda: dashboard.append_system_log(f"Mouse lock error: {e}"))
                    except Exception:
                        pass

            Thread(target=lock_mouse_loop, daemon=True).start()
            dashboard.append_system_log("Mouse strongly disabled while locked.")

        except Exception as e:
            dashboard.append_system_log(f"Mouse disable error: {e}")

    def enable_mouse(self, dashboard):
        self._mouse_lock_running = False
        self._uninstall_mouse_click_block_hook()
        self._release_cursor_clip()
        self._mouse_anchor = None

    # --------------------------------------------------------
    # USB option
    # --------------------------------------------------------
    def disable_usb(self, dashboard):
        """Placeholder for USB blocking.

        lockapp.py had the disable_usb flag but no actual USB implementation.
        We keep the setting and log that it is configured, but do not disable
        ports unless a company-approved method is added later.
        """
        if not self._usb_disabled:
            self._usb_disabled = True
            dashboard.append_system_log("USB disable option is enabled, but USB blocking is not implemented yet.")

    def enable_usb(self, dashboard):
        self._usb_disabled = False

    # --------------------------------------------------------
    # Optional Windows idle helper
    # --------------------------------------------------------
    def get_idle_secs(self):
        """Returns how many seconds the whole PC has been idle."""
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            elapsed = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return elapsed / 1000.0
        except Exception:
            return 0.0

    def shutdown(self, dashboard=None):
        self._emergency_watchdog_running = False

        if dashboard is not None:
            self.enable_keyboard(dashboard)
            self.enable_mouse(dashboard)
            self.enable_usb(dashboard)
        elif keyboard is not None:
            try:
                keyboard.unhook_all()
                keyboard.clear_all_hotkeys()
            except Exception:
                pass
        self._mouse_lock_running = False
