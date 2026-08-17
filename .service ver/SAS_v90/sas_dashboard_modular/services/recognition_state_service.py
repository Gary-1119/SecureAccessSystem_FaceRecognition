import os
import json
from datetime import datetime


class RecognitionStateService:
    """Read recognition_result.json from the configured server path.

    Important:
    result_filename must be treated as a file name, not a local app path.
    The SAS unlock decision should always read:
        <server_path>/recognition_result.json
    """

    def __init__(self, result_filename: str, valid_seconds: int):
        self.result_filename = os.path.basename(str(result_filename or "recognition_result.json"))
        self.valid_seconds = valid_seconds

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "y", "detected", "recognized", "recognised")
        return bool(value)

    def _parse_confidence(self, value):
        try:
            if isinstance(value, str):
                value = value.strip().replace("%", "")
            return float(value)
        except Exception:
            return 0.0

    def _parse_timestamp(self, value):
        if not value:
            return None

        text = str(value).strip()
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ]

        # Accept ISO strings with Z suffix.
        text_no_z = text[:-1] if text.endswith("Z") else text

        for fmt in formats:
            try:
                return datetime.strptime(text_no_z, fmt)
            except Exception:
                pass

        try:
            return datetime.fromisoformat(text_no_z)
        except Exception:
            return None

    def read_result(self, server_path: str):
        server_path = str(server_path or "").strip()

        if not server_path:
            return ("no_server_path", None, None, None)

        json_file = os.path.join(server_path, self.result_filename)

        if not os.path.exists(json_file):
            return ("no_file", None, None, None)

        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            # Support several possible Pi JSON keys, but preserve the original keys:
            # detected, user_id, confidence, timestamp.
            detected = self._parse_bool(
                data.get("detected", data.get("recognized", data.get("recognised", False)))
            )

            ntid = (
                data.get("user_id")
                or data.get("ntid")
                or data.get("user")
                or data.get("name")
                or data.get("recognized_user")
            )

            confidence = self._parse_confidence(data.get("confidence", data.get("score", 0)))
            timestamp = (
                data.get("timestamp")
                or data.get("time")
                or data.get("last_seen")
                or data.get("updated_at")
            )

            if not detected or not ntid or not timestamp:
                return ("no_face", None, None, None)

            detected_time = self._parse_timestamp(timestamp)

            if detected_time is None:
                return ("error", None, None, None)

            diff = (datetime.now() - detected_time).total_seconds()

            if diff > self.valid_seconds:
                return ("expired", str(ntid).lower(), detected_time, confidence)

            return ("valid", str(ntid).lower(), detected_time, confidence)

        except Exception as e:
            print("[JSON READ ERROR]", e)
            return ("error", None, None, None)
