try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None
import cv2
import time
import os
import numpy as np
from datetime import datetime, timedelta
import json
import shutil
import socket
import threading
from threading import Thread, Lock

from camera_rotation import rotate_camera_frame
try:
    from websocket_service import publish_recognition_result
except Exception:
    def publish_recognition_result(data):
        return 0

CASCADE_PATH = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"

# ----------------------------
# Server path (fixed mount point)
# ----------------------------
SERVER_PATH = "/mnt/pcshare"

USER_JSON_FILE = "user.json"
LOG_FOLDER = "LOG"
SERVER_LOG_FOLDER = "Pi_LOG"
RECOGNITION_RESULT_FILE = "recognition_result.json"
SETTINGS_FILE = "settings.json"
LOGIN_INTERVAL = 1  # minutes
last_sent_times = {}

# ---------------------------------------------------------------------------
# Recognition-result delivery
# ---------------------------------------------------------------------------
# Workstation unlock no longer writes recognition_result.json to SMB.  SAS now
# receives valid recognition events through the WebSocket API (/ws/sas).  SMB is
# still used by the rest of this file for optional user.json sync and Pi_LOG
# delivery, so the SMB availability helpers remain.
SERVER_PROBE_TIMEOUT_SECONDS = 0.60
_server_delivery_state = None

# A small Pi-local JSON state is kept only for local diagnostics and the legacy
# /recognition-result HTTP endpoint.  It is not copied to the server path and
# Windows SAS does not use it for unlock.
_LOCAL_RESULT_TEMP_NAME = f"{RECOGNITION_RESULT_FILE}.tmp"
_LOCAL_RESULT_TEMP_PREFIX = f"{RECOGNITION_RESULT_FILE}.tmp"
_local_result_write_lock = Lock()


def _read_server_host():
    """Read the Windows/SMB host from settings.json without touching the mount."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        unc_path = str(settings.get("pc_save_path", "") or "").strip()
    except Exception:
        return None

    if not unc_path:
        return None

    normalized = unc_path.replace("\\", "/").lstrip("/")
    host = normalized.split("/", 1)[0].strip()
    return host or None


def _is_cifs_mount_present():
    """Check mount metadata only; do not access a potentially stale SMB path."""
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as f:
            for line in f:
                fields = line.split()
                if len(fields) >= 3 and fields[1] == SERVER_PATH and fields[2] == "cifs":
                    return True
    except Exception:
        pass
    return False


def _server_delivery_available():
    """Return True only when the CIFS mount exists and SMB port 445 responds."""
    if not _is_cifs_mount_present():
        return False

    host = _read_server_host()
    if not host:
        return False

    try:
        with socket.create_connection((host, 445), timeout=SERVER_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _set_server_delivery_state(state, message):
    """Print SMB connection-state changes once instead of flooding the GUI log."""
    global _server_delivery_state
    if _server_delivery_state == state:
        return
    _server_delivery_state = state
    print(message)


def _mark_server_delivery_offline(reason):
    """Record that optional SMB delivery is offline. Recognition unlock is unaffected."""
    _set_server_delivery_state(
        "offline",
        f"[SMB OPTIONAL] Offline; logs/user sync deferred. ({reason})",
    )


def _cleanup_recognition_result_temp_files(directory, *, announce=False):
    """Remove only leftover local temp files; never remove the live JSON result."""
    removed = []
    try:
        for name in os.listdir(directory):
            if not name.startswith(_LOCAL_RESULT_TEMP_PREFIX):
                continue
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            try:
                os.remove(path)
                removed.append(name)
            except Exception:
                pass
    except Exception:
        return removed

    if announce and removed:
        print(
            "[RESULT CLEANUP] Removed stale local recognition-result temp file(s): "
            + ", ".join(removed)
        )
    return removed


def _cleanup_local_recognition_result_temp_files():
    """Clean Pi-local temp files left by earlier/aborted result writes."""
    directory = os.path.dirname(os.path.abspath(RECOGNITION_RESULT_FILE)) or "."
    return _cleanup_recognition_result_temp_files(directory, announce=True)


def _write_json_atomic(path, data):
    """Write one local JSON result atomically using a fixed temporary filename."""
    temp_path = f"{path}.tmp"
    with _local_result_write_lock:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)

            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
            return True
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


def write_local_recognition_result(data):
    """Persist local diagnostic state without any LAN/SMB dependency."""
    try:
        _write_json_atomic(RECOGNITION_RESULT_FILE, data)
        return True
    except Exception as exc:
        print(f"[WARN] Local recognition_result.json failed: {exc}")
        return False


# Remove stale local ``recognition_result.json.tmp*`` files left by a
# previous crash/version before recognition begins. The live JSON file is kept.
_cleanup_local_recognition_result_temp_files()

# ----------------------------
# Load / save local JSON
# ----------------------------
def load_users():
    if not os.path.exists(USER_JSON_FILE):
        return {}
    try:
        with open(USER_JSON_FILE, "r") as f:
            content = f.read().strip()
        if not content:
            print("[WARN] user.json is empty, resetting.")
            save_users({})
            return {}
        return json.loads(content)
    except json.JSONDecodeError:
        print("[WARN] user.json is corrupted, resetting.")
        save_users({})
        return {}


def save_users(data):
    with open(USER_JSON_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ----------------------------
# Sync user.json bi-directionally
# ----------------------------
def sync_user_json():
    try:
        # Never touch the mounted path unless SMB is confirmed reachable. This
        # function runs in a background worker so offline LAN cannot slow frames.
        if not _server_delivery_available():
            _mark_server_delivery_offline("user.json sync skipped while SMB is unavailable")
            return

        local_file = USER_JSON_FILE
        server_file = os.path.join(SERVER_PATH, USER_JSON_FILE)

        # Ensure local file exists
        if not os.path.exists(local_file):
            save_users({})

        def is_valid_json_file(path):
            try:
                with open(path, "r") as f:
                    content = f.read().strip()
                if not content:
                    return False
                json.loads(content)
                return True
            except Exception:
                return False

        if os.path.exists(server_file):
            local_valid  = is_valid_json_file(local_file)
            server_valid = is_valid_json_file(server_file)

            # If server file is corrupted/empty, don't pull it
            if not server_valid and local_valid:
                print("[SYNC] Server user.json invalid, skipping pull.")
                return

            # If local is corrupted, pull from server if server is valid
            if not local_valid and server_valid:
                shutil.copy2(server_file, local_file)
                print("[SYNC] Local user.json invalid, restored from PC.")
                return

            # Both valid — compare timestamps
            local_time  = os.path.getmtime(local_file)
            server_time = os.path.getmtime(server_file)

            if server_time > local_time:
                shutil.copy2(server_file, local_file)
                print("[SYNC] Pulled user.json from PC")
            elif local_time > server_time:
                shutil.copy2(local_file, server_file)
                print("[SYNC] Pushed user.json to PC")

        else:
            # Server file doesn't exist yet — push local if valid
            if is_valid_json_file(local_file):
                shutil.copy2(local_file, server_file)
                print("[SYNC] Created user.json on PC")

    except Exception as e:
        print(f"[SYNC ERROR] {e}")

# ----------------------------
# Write log file (sync to PC)
# ----------------------------
def write_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(LOG_FOLDER, exist_ok=True)
    local_log = os.path.join(LOG_FOLDER, f"{date_str}.log")

    line = f"[{timestamp}] {message}\n"

    # local log
    with open(local_log, "a") as f:
        f.write(line)

    # Server logs are optional delivery copies. Write them in the background
    # so a stale SMB mount cannot block recognition or the camera preview.
    Thread(
        target=_append_server_log,
        args=(date_str, line),
        daemon=True,
        name="SmbRecognitionLog",
    ).start()


def _append_server_log(date_str, line):
    try:
        if not _server_delivery_available():
            return

        server_log_folder = os.path.join(SERVER_PATH, SERVER_LOG_FOLDER)
        os.makedirs(server_log_folder, exist_ok=True)
        server_log = os.path.join(server_log_folder, f"{date_str}.log")
        with open(server_log, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        _mark_server_delivery_offline(f"server log write failed: {exc}")


def save_recognition_result(detected, user_id=None, confidence=0, name=None):
    """Save Pi-local diagnostics and publish successful unlock events by WebSocket."""
    data = {
        "detected": bool(detected),
        "user_id": user_id,
        "ntid": user_id,
        "name": name or user_id,
        "display_name": name or user_id,
        "confidence": round(confidence * 100, 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Local file is diagnostic only. It is no longer copied to SMB and SAS no
    # longer polls it for unlock.
    write_local_recognition_result(data)

    # Real-time workstation unlock delivery. This sends only valid recognition
    # events to SAS clients that have started an active lock session.
    try:
        publish_recognition_result(data)
    except Exception as exc:
        print(f"[WEBSOCKET RESULT] Publish skipped: {exc}")

    return data


# ----------------------------
# Handle recognition event
# ----------------------------
def handle_recognition(name, confidence, display_name=None):
    if name.lower() == "unknown":
        return

    # Keep login history aligned with the active InsightFace match threshold.
    if confidence < 0.38:
        return
    
    now = datetime.now()

    if name in last_sent_times:
        if now - last_sent_times[name] < timedelta(minutes=LOGIN_INTERVAL):
            return

    last_sent_times[name] = now

    users = load_users()

    if name not in users:
        users[name] = {
            "first_registered": now.strftime("%Y-%m-%d %H:%M:%S"),
            "last_login": now.strftime("%Y-%m-%d %H:%M:%S"),
            "display_name": display_name or name,
        }
    else:
        users[name]["last_login"] = now.strftime("%Y-%m-%d %H:%M:%S")
        if display_name:
            users[name]["display_name"] = display_name

    save_users(users)

    # User-history sync is network work. Keep it away from the recognition loop.
    Thread(target=sync_user_json, daemon=True, name="SmbUserJsonSync").start()

    log_msg = f"Recognized: {name} | Confidence: {round(confidence * 100, 1)}%"
    write_log(log_msg)
    print(f"[INFO] {log_msg}")

# ----------------------------
# Frame reader (keeps latest frame)
# ----------------------------
class FrameReader:
    def __init__(self, picam2):
        self.picam2 = picam2
        self.frame = None
        self.running = True
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self.running:
            try:
                self.frame = self.picam2.capture_array()
                time.sleep(0.01)
            except Exception:
                time.sleep(0.02)

    def read(self):
        return self.frame

    def stop(self):
        self.running = False
        self._thread.join(timeout=2)


def _draw_match_overlay(frame, match):
    """Draw largest-face state, name, ID and confidence on the Pi preview."""
    try:
        bbox = getattr(match, "bbox", None)
        if not bbox:
            return frame
        left, top, right, bottom = bbox
        color = (0, 200, 100) if getattr(match, "matched", False) else (0, 0, 255)
        confidence = float(getattr(match, "confidence", 0.0) or 0.0) * 100.0
        if getattr(match, "matched", False):
            label = f"{getattr(match, 'name', '')} | {getattr(match, 'employee_id', '')} | {confidence:.1f}%"
        else:
            label = f"UNKNOWN | {confidence:.1f}%"

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.62
        thickness = 2
        (text_w, text_h), baseline = cv2.getTextSize(label, font, scale, thickness)
        label_top = max(0, top - text_h - baseline - 10)
        cv2.rectangle(frame, (left, label_top), (min(frame.shape[1] - 1, left + text_w + 12), label_top + text_h + baseline + 8), color, -1)
        cv2.putText(frame, label, (left + 6, label_top + text_h + 2), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
    except Exception as exc:
        print(f"[WARN] Overlay failed: {exc}")
    return frame


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


# ----------------------------
# Main recognition
# ----------------------------
def start_recognition(frame_callback=None, stop_flag=None):
    """Start Pi-camera InsightFace recognition.

    Registration already creates embeddings, so this loop only loads the
    buffalo_s model, reads the latest camera frame, recognises the largest face,
    and publishes valid matches to SAS through WebSocket.
    """
    from insightface_engine import get_engine

    CONFIDENCE_FLOOR = 0.38
    VOTE_NEEDED = 2
    vote_buffer: dict[str, int] = {}
    currentname = "unknown"

    if Picamera2 is None:
        raise RuntimeError("Picamera2 is not installed. Install python3-picamera2 on the Raspberry Pi.")

    print("[INFO] Loading InsightFace buffalo_s model...")
    engine = get_engine()
    engine.ensure_model()
    engine.reload()

    if os.path.exists(SERVER_PATH):
        print("[INFO] Server connected.")
    else:
        print("[WARN] Server not mounted.")

    Thread(target=sync_user_json, daemon=True, name="SmbStartupUserJsonSync").start()

    picam2 = Picamera2()
    picam2.configure(
        picam2.create_preview_configuration(
            main={"format": "XRGB8888", "size": (640, 480)}
        )
    )
    picam2.start()
    time.sleep(1.2)

    reader = FrameReader(picam2)

    try:
        frame_count = 0
        last_overlay_match = None
        last_overlay_at = 0.0

        while True:
            if stop_flag and stop_flag():
                break

            frame = reader.read()
            if frame is None:
                time.sleep(0.02)
                continue

            frame = rotate_camera_frame(frame)
            if len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = frame[:, :, :3].copy()

            frame_count += 1
            if frame_count % 3 != 0:
                raw_frame = frame.copy()
                if last_overlay_match is not None and (time.time() - last_overlay_at) <= 0.45:
                    frame = _draw_match_overlay(frame, last_overlay_match)
                if frame_callback:
                    try:
                        frame_callback(frame, [], raw_frame)
                    except TypeError:
                        frame_callback(frame, [])
                continue

            try:
                match = engine.recognize_frame(frame)
            except Exception as exc:
                print(f"[ERROR] InsightFace recognition failed: {exc}")
                save_recognition_result(False, None, 0)
                if frame_callback:
                    try:
                        frame_callback(frame, [], frame.copy())
                    except TypeError:
                        frame_callback(frame, [])
                time.sleep(0.08)
                continue

            confidence = float(getattr(match, "confidence", 0.0) or 0.0)
            candidate = str(getattr(match, "employee_id", "") or "").strip().lower() if getattr(match, "matched", False) else "unknown"

            if candidate != "unknown" and confidence >= CONFIDENCE_FLOOR:
                vote_buffer[candidate] = vote_buffer.get(candidate, 0) + 1
                for key in list(vote_buffer):
                    if key != candidate:
                        vote_buffer[key] = 0
                promoted = candidate if vote_buffer[candidate] >= VOTE_NEEDED else currentname
            else:
                vote_buffer.clear()
                promoted = "unknown"

            currentname = promoted
            if currentname != "unknown" and confidence >= CONFIDENCE_FLOOR:
                handle_recognition(currentname, confidence, display_name=getattr(match, "name", ""))
                save_recognition_result(
                    True,
                    currentname,
                    confidence,
                    name=getattr(match, "name", ""),
                )
            else:
                save_recognition_result(False, None, confidence)

            raw_frame = frame.copy()
            last_overlay_match = match
            last_overlay_at = time.time()
            frame = _draw_match_overlay(frame, match)

            if frame_callback:
                try:
                    frame_callback(frame, [], raw_frame)
                except TypeError:
                    frame_callback(frame, [])
            else:
                if _safe_cv2_show("Face Recognition", frame) == ord("q"):
                    break

            time.sleep(0.03)

    finally:
        reader.stop()
        picam2.stop()
        picam2.close()
        _safe_cv2_destroy_windows()
        print("[INFO] Recognition stopped cleanly.")
