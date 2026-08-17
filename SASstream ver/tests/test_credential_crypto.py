from __future__ import annotations

import os
import unittest

from services.credential_crypto import DPAPI_PREFIX, protect_secret, unprotect_secret


@unittest.skipUnless(os.name == "nt", "Windows DPAPI is required")
class CredentialCryptoTests(unittest.TestCase):
    def test_dpapi_round_trip(self):
        protected = protect_secret("SecretPassword123!")
        self.assertTrue(protected.startswith(DPAPI_PREFIX))
        self.assertNotIn("SecretPassword123!", protected)
        self.assertEqual(unprotect_secret(protected), "SecretPassword123!")


if __name__ == "__main__":
    unittest.main()
