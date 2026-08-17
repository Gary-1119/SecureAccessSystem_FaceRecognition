from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from services.log_retention import cleanup_expired_daily_app_logs, cleanup_expired_daily_logs


class LogRetentionTests(unittest.TestCase):
    def test_cleanup_deletes_only_expired_dated_audit_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expired = root / "2026-07-03.txt"
            boundary = root / "2026-07-04.txt"
            current = root / "2026-07-18.txt"
            app_log = root / "sas_app.log"
            invalid = root / "notes.txt"

            for path in (expired, boundary, current, app_log, invalid):
                path.write_text("x", encoding="utf-8")

            result = cleanup_expired_daily_logs(root, retention_days=14, today=date(2026, 7, 18))

            self.assertEqual(result["deleted_count"], 1)
            self.assertFalse(expired.exists())
            self.assertTrue(boundary.exists())
            self.assertTrue(current.exists())
            self.assertTrue(app_log.exists())
            self.assertTrue(invalid.exists())


    def test_cleanup_deletes_only_expired_dated_app_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expired = root / "2026-07-03_app.log"
            boundary = root / "2026-07-04_app.log"
            current = root / "2026-07-18_app.log"
            legacy = root / "sas_app.log"
            audit = root / "2026-07-03.txt"

            for path in (expired, boundary, current, legacy, audit):
                path.write_text("x", encoding="utf-8")

            result = cleanup_expired_daily_app_logs(root, retention_days=14, today=date(2026, 7, 18))

            self.assertEqual(result["deleted_count"], 1)
            self.assertFalse(expired.exists())
            self.assertTrue(boundary.exists())
            self.assertTrue(current.exists())
            self.assertTrue(legacy.exists())
            self.assertTrue(audit.exists())



if __name__ == "__main__":
    unittest.main()
