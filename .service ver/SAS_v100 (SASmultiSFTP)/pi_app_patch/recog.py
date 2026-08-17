import encodings

from picamera2 import Picamera2
import face_recognition
import pickle
import cv2
import time
import os
import numpy as np
from datetime import datetime, timedelta
import json
import shutil
import socket
import threading
from threading import Thread, Lock, Event

from camera_rotation import rotate_camera_frame

ENCODINGS_FILE = "encodings.pickle"
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
# Offline-safe SMB recognition-result delivery
# ---------------------------------------------------------------------------
# Local recognition_result.json is always written immediately. The SMB copy is
# delivered only by this background publisher, so a disconnected/stale CIFS
# mount can never block the camera or Tkinter recognition loop.
SERVER_RESULT_TTL_SECONDS = 3.0
SERVER_PROBE_TIMEOUT_SECONDS = 0.60
SERVER_PUBLISH_COALESCE_SECONDS = 0.25

_server_result_lock = Lock()
_server_result_wakeup = Event()
_server_result_pending = None
_server_result_worker_running = False
_server_result_reset_required = True
_server_delivery_state = None

# One local result file is the Pi source of truth. The previous v104/v105
# implementation used a unique temporary name per thread, which could leave
# multiple ``recognition_result.json.tmp-*`` files after an interrupted write.
# A fixed temporary name plus a local lock guarantees one active result file
# and at most one short-lived temp file during a write.
_LOCAL_RESULT_TEMP_NAME = f"{RECOGNITION_RESULT_FILE}.tmp"
_LOCAL_RESULT_TEMP_PREFIX = f"{RECOGNITION_RESULT_FILE}.tmp"
_local_result_write_lock = Lock()
_server_result_temp_cleanup_required = True


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
    """Print connection-state changes once instead of flooding the GUI log."""
    global _server_delivery_state
    if _server_delivery_state == state:
        return
    _server_delivery_state = state
    print(message)


def _mark_server_delivery_offline(reason):
    """Drop queued authorization delivery until a fresh post-reconnect scan."""
    global _server_result_reset_required
    global _server_result_temp_cleanup_required
    with _server_result_lock:
        _server_result_reset_required = True
        _server_result_temp_cleanup_required = True
    _set_server_delivery_state(
        "offline",
        f"[SMB RESULT] Offline; keeping recognition local only. ({reason})",
    )


def _cleanup_recognition_result_temp_files(directory, *, announce=False):
    """Remove only leftover temp files; never remove the live JSON result."""
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
            "[RESULT CLEANUP] Removed stale recognition-result temp file(s): "
            + ", ".join(removed)
        )
    return removed


def _cleanup_local_recognition_result_temp_files():
    """Clean Pi-local temp files left by earlier/aborted result writes."""
    directory = os.path.dirname(os.path.abspath(RECOGNITION_RESULT_FILE)) or "."
    return _cleanup_recognition_result_temp_files(directory, announce=True)


def _cleanup_server_recognition_result_temp_files():
    """Clean SMB temp files only after the SMB availability probe succeeds."""
    return _cleanup_recognition_result_temp_files(SERVER_PATH, announce=True)


def _write_json_atomic(path, data):
    """Write one local JSON result atomically using a fixed temporary filename."""
    temp_path = f"{path}.tmp"
    with _local_result_write_lock:
        try:
            # A prior power loss can leave the fixed temp file behind. It is never
            # the active result, so remove it before beginning the next write.
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
    """Persist the Pi's current recognition state without any LAN dependency."""
    try:
        _write_json_atomic(RECOGNITION_RESULT_FILE, data)
        return True
    except Exception as exc:
        print(f"[WARN] Local recognition_result.json failed: {exc}")
        return False


def _write_server_result_if_fresh(data, created_monotonic):
    """Write through one temporary SMB file, then atomically replace the live file."""
    global _server_result_temp_cleanup_required
    server_file = os.path.join(SERVER_PATH, RECOGNITION_RESULT_FILE)
    temp_file = f"{server_file}.tmp"

    try:
        # Clean temp files left by previous network interruptions once after a
        # successful reconnect. This never touches the live JSON file.
        if _server_result_temp_cleanup_required:
            _cleanup_server_recognition_result_temp_files()
            _server_result_temp_cleanup_required = False

        # The live SAS file is replaced only after freshness is checked again.
        # The publisher is single-threaded, so one fixed SMB temp filename is safe.
        if os.path.exists(temp_file):
            os.remove(temp_file)
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())

        age = time.monotonic() - created_monotonic
        if age > SERVER_RESULT_TTL_SECONDS:
            return False, "stale result dropped before server replace"

        if not _server_delivery_available():
            return False, "server became unavailable before server replace"

        os.replace(temp_file, server_file)
        return True, ""
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass


def _server_result_publisher_loop():
    """Publish only the newest local result; never block recognition/UI work."""
    global _server_result_pending
    global _server_result_worker_running
    global _server_result_reset_required

    while True:
        # Coalesce fast camera-frame updates into one latest payload.
        _server_result_wakeup.wait(timeout=SERVER_PUBLISH_COALESCE_SECONDS)
        _server_result_wakeup.clear()
        time.sleep(SERVER_PUBLISH_COALESCE_SECONDS)

        with _server_result_lock:
            item = _server_result_pending
            _server_result_pending = None

        if item is not None:
            data = item["data"]
            created = item["created_monotonic"]

            if time.monotonic() - created > SERVER_RESULT_TTL_SECONDS:
                # Do not replay an old authorization after a network delay.
                pass
            elif not _server_delivery_available():
                _mark_server_delivery_offline("SMB host or mount is unavailable")
            else:
                with _server_result_lock:
                    reset_required = _server_result_reset_required

                if reset_required:
                    # A previously disconnected server may still contain an old
                    # authorized result. Reset it first, then require a new live
                    # recognition event before forwarding authorization again.
                    neutral = {
                        "detected": False,
                        "user_id": None,
                        "confidence": 0,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "server_reconnected",
                    }
                    ok, reason = _write_server_result_if_fresh(neutral, time.monotonic())
                    if ok:
                        with _server_result_lock:
                            _server_result_reset_required = False
                        _set_server_delivery_state(
                            "online",
                            "[SMB RESULT] Server connection restored; reset remote result to safe state.",
                        )
                    else:
                        _mark_server_delivery_offline(reason)
                    # Intentionally drop the current item. A subsequent camera
                    # frame is required to provide a fresh post-reconnect result.
                else:
                    ok, reason = _write_server_result_if_fresh(data, created)
                    if ok:
                        _set_server_delivery_state("online", "[SMB RESULT] Server delivery active.")
                    else:
                        _mark_server_delivery_offline(reason)

        with _server_result_lock:
            if _server_result_pending is None:
                _server_result_worker_running = False
                return


def queue_server_recognition_result(data):
    """Queue the newest SMB delivery without retaining offline/stale results."""
    global _server_result_pending
    global _server_result_worker_running

    item = {
        "data": dict(data),
        "created_monotonic": time.monotonic(),
    }

    with _server_result_lock:
        _server_result_pending = item
        if not _server_result_worker_running:
            _server_result_worker_running = True
            Thread(
                target=_server_result_publisher_loop,
                daemon=True,
                name="SmbRecognitionResultPublisher",
            ).start()

    _server_result_wakeup.set()

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


def save_recognition_result(detected, user_id=None, confidence=0):
    """Save Pi-local state immediately and deliver SMB state asynchronously."""
    data = {
        "detected": detected,
        "user_id": user_id,
        "confidence": round(confidence * 100, 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Local state is the Pi's source of truth and never depends on Ethernet.
    write_local_recognition_result(data)

    # SMB is delivery-only. A stale/offline mount never runs in this thread.
    queue_server_recognition_result(data)


# ----------------------------
# Handle recognition event
# ----------------------------
def handle_recognition(name, confidence):
    if name.lower() == "unknown":
        return

    # Do not write login history or log file if confidence is below 70%
    if confidence < 0.70:
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
            "last_login": now.strftime("%Y-%m-%d %H:%M:%S")
        }
    else:
        users[name]["last_login"] = now.strftime("%Y-%m-%d %H:%M:%S")

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
            except:
                pass

    def read(self):
        return self.frame

    def stop(self):
        self.running = False
        self._thread.join(timeout=2)

# ----------------------------
# Live encoding reload
# ----------------------------
def load_encodings_snapshot():
    """Load one complete encoding snapshot and its modification time.

    ``train.py`` replaces the pickle atomically, so recognition either keeps
    the old in-memory model or loads a complete new one; it never reads a
    partially written training file.
    """
    with open(ENCODINGS_FILE, "rb") as f:
        data = pickle.load(f)

    if not isinstance(data, dict):
        raise ValueError("encodings.pickle has an invalid format")

    encodings_list = data.get("encodings", [])
    names_list = data.get("names", [])
    if not isinstance(encodings_list, list) or not isinstance(names_list, list):
        raise ValueError("encodings.pickle is missing face encoding lists")

    data["encodings"] = encodings_list
    data["names"] = names_list
    return data, os.path.getmtime(ENCODINGS_FILE)


# ----------------------------
# Main recognition
# ----------------------------
def start_recognition(frame_callback=None, stop_flag=None):

    currentname = "unknown"

    # --- Recognition tuning ---
    # Raised tolerance (0.27→0.45): allows spectacles/lighting variation to still match
    # Lowered confidence floor (0.70→0.55): accepts slightly weaker matches caused by glasses
    # Vote buffer: require VOTE_THRESHOLD consistent hits before emitting a name,
    #              so the looser tolerance doesn't cause false-positive flicker
    TOLERANCE        = 0.45
    CONFIDENCE_FLOOR = 0.70
    VOTE_NEEDED      = 3          # frames a name must appear consecutively to be accepted
    vote_buffer: dict = {}        # name → consecutive hit count

    if not os.path.exists(ENCODINGS_FILE):
        print("[ERROR] encodings.pickle not found.")
        return

    print("[INFO] Loading encodings + detector...")

    if os.path.exists(SERVER_PATH):
        print("[INFO] Server connected.")
    else:
        print("[WARN] Server not mounted.")

    # Sync user history outside the camera/recognition thread. Offline SMB must
    # never delay camera startup or TTY5 rendering.
    Thread(target=sync_user_json, daemon=True, name="SmbStartupUserJsonSync").start()

    try:
        data, encodings_mtime = load_encodings_snapshot()
    except Exception as e:
        print(f"[ERROR] Could not load encodings.pickle: {e}")
        return

    detector = cv2.CascadeClassifier(CASCADE_PATH)

    picam2 = Picamera2()
    picam2.configure(
        picam2.create_preview_configuration(
            main={"format": "XRGB8888", "size": (640, 480)}
        )
    )
    picam2.start()
    time.sleep(1.5)

    reader = FrameReader(picam2)

    try:
        frame_count = 0
        last_reload_check = 0.0

        while True:
            if stop_flag and stop_flag():
                break

            # Training does not use the camera. Keep recognition running and
            # reload the completed model only after train.py atomically replaces
            # encodings.pickle. This makes newly trained users available without
            # closing and reopening the Pi camera.
            now = time.monotonic()
            if now - last_reload_check >= 1.0:
                last_reload_check = now
                try:
                    current_mtime = os.path.getmtime(ENCODINGS_FILE)
                    if current_mtime != encodings_mtime:
                        data, encodings_mtime = load_encodings_snapshot()
                        vote_buffer.clear()
                        currentname = "unknown"
                        print("[INFO] Reloaded trained encodings without restarting camera.")
                except Exception as e:
                    # Keep the last known-good in-memory model if a reload ever
                    # fails. The next loop will retry safely.
                    print(f"[WARN] Encoding reload deferred: {e}")

            frame = reader.read()
            if frame is None:
                continue

            # Apply the persisted Pi camera rotation before drawing, detection,
            # encoding, API streaming, or GUI preview.  This keeps the entire
            # system (Pi UI + SAS video feed + saved capture orientation) aligned.
            frame = rotate_camera_frame(frame)

            frame_count += 1

            if frame_count % 3 != 0:
                if frame_callback:
                    frame_callback(frame, [])
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            rects = detector.detectMultiScale(gray, 1.2, 5, minSize=(30, 30))
            boxes = [(y, x + w, y + h, x) for (x, y, w, h) in rects]

            encodings = face_recognition.face_encodings(rgb, boxes)
            names = []

            if len(encodings) == 0:
                save_recognition_result(False, None, 0)

            known_encodings = data.get("encodings", [])
            known_names = data.get("names", [])

            for encoding in encodings:
                if not known_encodings or not known_names:
                    confidence = 0
                    candidate = "Unknown"
                else:
                    distances = face_recognition.face_distance(known_encodings, encoding)
                    best_match_index = int(np.argmin(distances))
                    confidence = max(0, 1 - distances[best_match_index])

                    matches = face_recognition.compare_faces(
                        known_encodings, encoding, tolerance=TOLERANCE
                    )

                    if True in matches and confidence >= CONFIDENCE_FLOOR:
                        candidate = known_names[best_match_index]
                    else:
                        candidate = "Unknown"

                # --- Vote buffer: only promote a name after VOTE_NEEDED hits ---
                if candidate != "Unknown":
                    vote_buffer[candidate] = vote_buffer.get(candidate, 0) + 1
                    # Reset all other candidates
                    for k in list(vote_buffer):
                        if k != candidate:
                            vote_buffer[k] = 0
                    name = candidate if vote_buffer[candidate] >= VOTE_NEEDED else currentname
                else:
                    # Unknown resets the buffer immediately
                    vote_buffer.clear()
                    name = "Unknown"

                if currentname != name:
                    currentname = name

                # Only accept recognition if confidence is 70% or above
                if currentname.lower() != "unknown" and confidence >= CONFIDENCE_FLOOR:
                    handle_recognition(currentname, confidence)
                    save_recognition_result(True, currentname, confidence)
                else:
                    save_recognition_result(False, None, confidence)
                    name = "Unknown"
                    currentname = "unknown"

                names.append((name, confidence))

            for ((top, right, bottom, left), (name, confidence)) in zip(boxes, names):
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 200, 100), 2)
                label = f"{name} ({confidence * 100:.1f}%)"
                cv2.putText(frame, label, (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 100), 2)

            if frame_callback:
                frame_callback(frame, names)
            else:
                cv2.imshow("Face Recognition", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        reader.stop()
        picam2.stop()
        picam2.close()
        cv2.destroyAllWindows()
        print("[INFO] Recognition stopped cleanly.")
