from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import BinaryIO

from services.atomic_file import atomic_write_bytes_from_writer, atomic_write_text


class AtomicFileTests(unittest.TestCase):
    def test_atomic_text_write_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            atomic_write_text(path, "first", keep_backup=True)
            atomic_write_text(path, "second", keep_backup=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "second")
            self.assertEqual(path.with_suffix(".txt.bak").read_text(encoding="utf-8"), "first")

    def test_atomic_binary_writer(self):
        def write_sample(handle: BinaryIO) -> None:
            handle.write(b"abc")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.bin"
            atomic_write_bytes_from_writer(path, write_sample, keep_backup=True)
            self.assertEqual(path.read_bytes(), b"abc")


if __name__ == "__main__":
    unittest.main()
