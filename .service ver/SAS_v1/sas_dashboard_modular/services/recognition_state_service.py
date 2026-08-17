import os
import json
from datetime import datetime


class RecognitionStateService:
    """recognition_result.json reader migrated from lockapp.py."""

    def __init__(self, result_filename: str, valid_seconds: int):
        self.result_filename = result_filename
        self.valid_seconds = valid_seconds

    def read_result(self, server_path: str):
        json_file = os.path.join(server_path, self.result_filename)

        if not os.path.exists(json_file):
            return ("no_file", None, None, None)

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            detected = data.get("detected", False)
            ntid = data.get("user_id")
            confidence = data.get("confidence", 0)
            timestamp = data.get("timestamp")

            if not detected or not ntid or not timestamp:
                return ("no_face", None, None, None)

            detected_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            diff = (datetime.now() - detected_time).total_seconds()

            if diff > self.valid_seconds:
                return ("expired", ntid.lower(), detected_time, confidence)

            return ("valid", ntid.lower(), detected_time, confidence)

        except Exception as e:
            print("[JSON READ ERROR]", e)
            return ("error", None, None, None)
