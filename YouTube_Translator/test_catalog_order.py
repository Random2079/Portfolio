"""Tests for catalog drag-order helpers."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from overlay_player import apply_catalog_order, catalog_track_key, scan_media


class CatalogOrderTests(unittest.TestCase):
    def test_apply_manual_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "A [aaaaaaaaaaa].mp3"
            b = root / "B [bbbbbbbbbbb].mp3"
            c = root / "C [ccccccccccc].mp3"
            for p in (a, b, c):
                p.write_bytes(b"x")
            now = time.time()
            os.utime(a, (now - 30, now - 30))
            os.utime(b, (now - 20, now - 20))
            os.utime(c, (now - 10, now - 10))
            files = scan_media(str(root), sort="date_asc")
            self.assertEqual([p.name[0] for p in files], ["A", "B", "C"])
            order = [catalog_track_key(c), catalog_track_key(a)]
            ordered = apply_catalog_order(files, order)
            self.assertEqual([p.name[0] for p in ordered], ["C", "A", "B"])


if __name__ == "__main__":
    unittest.main()
