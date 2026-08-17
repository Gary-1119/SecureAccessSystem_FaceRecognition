from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path


class AppLoggingTests(unittest.TestCase):
    def test_daily_app_log_handler_writes_dated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            from services.app_logging import DailyAppLogHandler

            log_dir = Path(tmp)
            handler = DailyAppLogHandler(log_dir, retention_days=14)
            handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
            logger = logging.getLogger("sas_test_daily_handler")
            logger.handlers.clear()
            logger.setLevel(logging.INFO)
            logger.propagate = False
            logger.addHandler(handler)

            try:
                logger.warning("rtsp disconnected")
            finally:
                handler.close()
                logger.handlers.clear()

            files = list(Path(tmp).glob("*_app.log"))
            self.assertEqual(len(files), 1)
            self.assertIn("WARNING | sas_test_daily_handler | rtsp disconnected", files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
