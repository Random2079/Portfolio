"""Unit tests for C2 catalog card helpers (no GUI / no ffmpeg network)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import overlay_player as op


class CatalogEntryMetaTests(unittest.TestCase):
    def test_pair_mp4_mp3_same_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "Song [dQw4w9WgXcQ].mp4"
            mp3 = root / "Song [dQw4w9WgXcQ].mp3"
            mp4.write_bytes(b"v")
            mp3.write_bytes(b"a")
            title, has_v, has_a, vpath = op.catalog_entry_meta(mp4)
            self.assertEqual(title, "Song")
            self.assertTrue(has_v)
            self.assertTrue(has_a)
            self.assertEqual(vpath, mp4)

    def test_audio_only_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp3 = root / "OnlyAudio [abcdefghijk].mp3"
            mp3.write_bytes(b"a")
            title, has_v, has_a, vpath = op.catalog_entry_meta(mp3)
            self.assertEqual(title, "OnlyAudio")
            self.assertFalse(has_v)
            self.assertTrue(has_a)
            self.assertIsNone(vpath)

    def test_video_finds_audio_by_id_different_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "Clip Title [xyzXYZabc12].mp4"
            mp3 = root / "other name [xyzXYZabc12].mp3"
            mp4.write_bytes(b"v")
            mp3.write_bytes(b"a")
            _title, has_v, has_a, _v = op.catalog_entry_meta(mp4)
            self.assertTrue(has_v)
            self.assertTrue(has_a)


class CatalogThumbPathTests(unittest.TestCase):
    def test_cache_uses_youtube_id(self) -> None:
        p = Path(r"C:\Music\Foo [dQw4w9WgXcQ].mp4")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
            out = op.catalog_thumb_cache_path(p)
        self.assertEqual(out.name, "dQw4w9WgXcQ.jpg")
        self.assertTrue(str(out).endswith(os.path.join(".subtitle_ripper", "thumbs", "dQw4w9WgXcQ.jpg")))


if __name__ == "__main__":
    unittest.main()
