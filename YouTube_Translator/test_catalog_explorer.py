"""Unit tests for C2c explorer-row helpers (no GUI / no ffmpeg)."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import overlay_player as op


class CatalogRowMetaTests(unittest.TestCase):
    def test_pair_badges_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "Track [dQw4w9WgXcQ].mp4"
            mp3 = root / "Track [dQw4w9WgXcQ].mp3"
            mp4.write_bytes(b"v")
            mp3.write_bytes(b"a")
            now = time.time()
            os.utime(mp4, (now - 10, now - 10))
            os.utime(mp3, (now - 5, now - 5))
            title, hv, ha, vp, date_str = op.catalog_row_meta(mp4)
            self.assertEqual(title, "Track")
            self.assertTrue(hv)
            self.assertTrue(ha)
            self.assertEqual(vp, mp4)
            self.assertRegex(date_str, r"\d{2}\.\d{2}\.\d{4}")

    def test_audio_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp3 = root / "Only [abcdefghijk].mp3"
            mp3.write_bytes(b"a")
            title, hv, ha, vp, _d = op.catalog_row_meta(mp3)
            self.assertEqual(title, "Only")
            self.assertFalse(hv)
            self.assertTrue(ha)
            self.assertIsNone(vp)


class CatalogThumbPathTests(unittest.TestCase):
    def test_id_in_cache_name(self) -> None:
        p = Path(r"C:\Music\Foo [dQw4w9WgXcQ].mp4")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
            out = op.catalog_thumb_cache_path(p)
        self.assertEqual(out.name, "dQw4w9WgXcQ.jpg")


if __name__ == "__main__":
    unittest.main()
