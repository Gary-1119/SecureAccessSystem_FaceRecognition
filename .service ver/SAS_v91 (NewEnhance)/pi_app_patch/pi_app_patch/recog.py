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
from threading import Thread

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
LOGIN_INTERVAL = 1  # minutes
last_sent_times = {}

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
        local_file = USER_JSON_FILE
        server_file = os.path.join(SERVER_PATH, USER_JSON_FILE)

        if not os.path.exists(SERVER_PATH):
            return

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

    # server log
    # Keep Pi recognition logs inside Pi_LOG folder on the shared server path.
    # This avoids mixing daily Pi logs with SAS files such as recognition_result.json.
    if os.path.exists(SERVER_PATH) and os.access(SERVER_PATH, os.W_OK):
        try:
            server_log_folder = os.path.join(SERVER_PATH, SERVER_LOG_FOLDER)
            os.makedirs(server_log_folder, exist_ok=True)

            server_log = os.path.join(server_log_folder, f"{date_str}.log")
            with open(server_log, "a") as f:
                f.write(line)
        except Exception as e:
            print(f"[WARN] Server log failed: {e}")


def save_recognition_result(detected, user_id=None, confidence=0):

    data = {
        "detected": detected,
        "user_id": user_id,
        "confidence": round(confidence * 100, 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Save local copy
    try:
        with open(RECOGNITION_RESULT_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[WARN] Local recognition_result.json failed: {e}")

    # Save to server path
    if os.path.exists(SERVER_PATH) and os.access(SERVER_PATH, os.W_OK):
        try:
            server_file = os.path.join(SERVER_PATH, RECOGNITION_RESULT_FILE)

            with open(server_file, "w") as f:
                json.dump(data, f, indent=4)

        except Exception as e:
            print(f"[WARN] Server recognition_result.json failed: {e}")

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

    # 🔥 Sync across devices
    sync_user_json()

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

    # sync at startup
    sync_user_json()

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
