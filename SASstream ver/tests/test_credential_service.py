from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from services.credential_crypto import DPAPI_PREFIX
from services.credential_service import CredentialService


@unittest.skipUnless(os.name == "nt", "Windows DPAPI is required")
class CredentialServiceTests(unittest.TestCase):
    def test_save_credentials_encrypts_password_and_reads_plain_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential.txt"
            service = CredentialService(str(path))
            service.save_credentials("1234567", "SecretPassword123!", r"\\server\\share", "300")

            raw = path.read_text(encoding="utf-8")
            self.assertIn(f"password={DPAPI_PREFIX}", raw)
            self.assertNotIn("SecretPassword123!", raw)
            self.assertFalse(path.with_suffix(".txt.bak").exists())

            creds = service.read_credentials()
            self.assertEqual(creds["password"], "SecretPassword123!")
            self.assertEqual(creds["ntid"], "1234567")

    def test_migrate_plaintext_password_encrypts_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential.txt"
            path.write_text(
                "ntid=1234567\n"
                "password=PlainPassword!\n"
                "server=\\\\server\\\\share\n"
                "timeout=300\n",
                encoding="utf-8",
            )
            path.with_suffix(".txt.bak").write_text("password=PlainPassword!\n", encoding="utf-8")

            service = CredentialService(str(path))
            self.assertTrue(service.migrate_plaintext_password_if_needed())

            raw = path.read_text(encoding="utf-8")
            self.assertIn(f"password={DPAPI_PREFIX}", raw)
            self.assertNotIn("PlainPassword!", raw)
            self.assertFalse(path.with_suffix(".txt.bak").exists())
            self.assertEqual(service.read_credentials()["password"], "PlainPassword!")


if __name__ == "__main__":
    unittest.main()
