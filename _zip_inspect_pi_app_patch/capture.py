import os
import time

import cv2
from picamera2 import Picamera2

from camera_rotation import rotate_camera_frame
from insightface_engine import get_engine


AUTO_LIMIT = 10
AUTO_COOLDOWN = 2.0


def _open_camera_with_retry(retries=5, delay=1.0):
    last_error = None
    for attempt in range(retries):
        try:
            return Picamera2()
        except RuntimeError as exc:
            last_error = exc
            print(f"[WARN] Camera busy, retrying ({attempt + 1}/{retries})...")
            time.sleep(delay)
    raise RuntimeError(f"Camera is busy. Please close other apps and retry. Detail: {last_error}")


def _count_samples(employee_id):
    try:
        for user in get_engine().list_users():
            if str(user.get("employee_id") or user.get("id") or "").strip().upper() == employee_id:
                return int(user.get("samples") or user.get("photos") or 0)
    except Exception:
        pass
    return 0


def _normalise_id(value):
    return str(value or "").strip().upper()


def _safe_cv2_show(window_name, frame):
    try:
        cv2.imshow(window_name, frame)
        return cv2.waitKey(1) & 0xFF
    except cv2.error as exc:
        print(f"[WARN] OpenCV window preview unavailable: {exc}")
        return -1


def _safe_cv2_destroy_windows():
    try:
        cv2.destroyAllWindows()
    except cv2.error as exc:
        print(f"[WARN] OpenCV window cleanup skipped: {exc}")


def capture_faces(person_name, mode="add", save_base=None,
                  frame_callback=None, stop_flag=None, auto_capture=False,
                  display_name=None, max_captures=None):
    """v106-compatible capture entry point backed by InsightFace.

    ``save_base`` is accepted only for old callers. InsightFace registers each
    accepted frame immediately into ``face_data/users.json``,
    ``face_data/embeddings.npz``, and ``face_data/photos``. The return value
    stays ``(captured, total)`` so the v106 GUI/API flow remains compatible.
    """
    employee_id = _normalise_id(person_name)
    if not employee_id:
        raise RuntimeError("Employee ID / NTID is required.")

    display_name = str(display_name or employee_id).strip() or employee_id
    engine = get_engine()
    engine.ensure_model()

    if str(mode or "").strip().lower() == "replace":
        try:
            engine.delete_user(employee_id)
        except Exception:
            pass

    captured = 0
    target_captures = int(max_captures) if max_captures else AUTO_LIMIT
    target_captures = max(1, target_captures)
    capture_cooldown = 0.25 if max_captures else AUTO_COOLDOWN
    auto_count = 0
    last_auto_time = 0.0
    picam2 = None

    try:
        picam2 = _open_camera_with_retry()
        picam2.configure(
            picam2.create_preview_configuration(
                main={"format": "XRGB8888", "size": (640, 480)}
            )
        )
        picam2.start()
        time.sleep(0.7)

        while True:
            if stop_flag and stop_flag():
                break

            frame = rotate_camera_frame(picam2.capture_array())
            if len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = frame[:, :, :3].copy()

            action = None
            if frame_callback:
                action = frame_callback(frame)
                if action == "stop":
                    break

            if auto_capture:
                now = time.time()
                if auto_count < target_captures and (now - last_auto_time) >= capture_cooldown:
                    action = "capture"
                    last_auto_time = now

            if action == "capture":
                try:
                    user = engine.register_frame(display_name, employee_id, frame)
                    captured += 1
                    auto_count += 1
                    print(f"[INFO] InsightFace sample saved for {user.employee_id}: {user.sample_count}")
                except Exception as exc:
                    print(f"[WARN] InsightFace sample not saved: {exc}")
                if auto_capture and auto_count >= target_captures:
                    break

            if not frame_callback:
                key = _safe_cv2_show("Capture Faces", frame)
                if key == 27:
                    break
                if key == 32:
                    try:
                        user = engine.register_frame(display_name, employee_id, frame)
                        captured += 1
                        print(f"[INFO] InsightFace sample saved for {user.employee_id}: {user.sample_count}")
                    except Exception as exc:
                        print(f"[WARN] InsightFace sample not saved: {exc}")

    finally:
        if not frame_callback:
            _safe_cv2_destroy_windows()
        if picam2 is not None:
            try:
                picam2.stop()
            except Exception:
                pass
            try:
                picam2.close()
            except Exception:
                pass
            time.sleep(0.8)

    return captured, _count_samples(employee_id)


if __name__ == "__main__":
    import sys

    capture_faces(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "add")
