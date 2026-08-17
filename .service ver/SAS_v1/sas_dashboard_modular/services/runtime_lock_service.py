class RuntimeLockService:
    """Runtime lock state coordinator.

    This keeps lock/unlock rules separate from the PySide UI. The actual UI still
    calls dashboard.apply_lock_state() to draw the state.
    """

    def grant_access(self, dashboard, name=""):
        dashboard.is_logged_in = True
        dashboard.is_locked = False
        dashboard.apply_lock_state()
        dashboard.append_system_log("Access granted" + (f": {name}" if name else ""))

    def lock_system(self, dashboard):
        dashboard.is_logged_in = False
        dashboard.is_locked = True
        dashboard.apply_lock_state()
        dashboard.set_face_detected(False)
        dashboard.append_system_log("System locked. Waiting for face match.")

    def update_face_detected_from_result(self, dashboard, result_tuple):
        state, ntid, detected_time, confidence = result_tuple
        if state == "valid":
            dashboard.set_face_detected(True)
            return True
        dashboard.set_face_detected(False)
        return False
