"""Unit tests for overlay catalog scan_media sort (C1)."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from overlay_player import scan_media


class ScanMediaSortTests(unittest.TestCase):
    def test_date_asc_oldest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "older_track.mp3"
            newer = root / "newer_track.mp3"
            older.write_bytes(b"aaa")
            time.sleep(0.05)
            newer.write_bytes(b"bbb")
            # Force mtime order even on fast FS
            now = time.time()
            os.utime(older, (now - 100, now - 100))
            os.utime(newer, (now - 10, now - 10))

            asc = scan_media(str(root), sort="date_asc")
            self.assertEqual([p.name for p in asc], ["older_track.mp3", "newer_track.mp3"])

            desc = scan_media(str(root), sort="date_desc")
            self.assertEqual([p.name for p in desc], ["newer_track.mp3", "older_track.mp3"])

            by_name = scan_media(str(root), sort="name")
            self.assertEqual([p.name for p in by_name], ["newer_track.mp3", "older_track.mp3"])

    def test_default_is_date_asc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "zzz.mp3"
            b = root / "aaa.mp3"
            a.write_bytes(b"a")
            b.write_bytes(b"b")
            now = time.time()
            os.utime(a, (now - 50, now - 50))
            os.utime(b, (now - 5, now - 5))
            files = scan_media(str(root))
            self.assertEqual([p.name for p in files], ["zzz.mp3", "aaa.mp3"])

    def test_dedupe_prefers_video_keeps_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp3 = root / "Song [dQw4w9WgXcQ].mp3"
            mp4 = root / "Song [dQw4w9WgXcQ].mp4"
            mp3.write_bytes(b"audio")
            mp4.write_bytes(b"video-bytes-longer")
            now = time.time()
            os.utime(mp3, (now - 20, now - 20))
            os.utime(mp4, (now - 20, now - 20))
            other = root / "Other.mp3"
            other.write_bytes(b"x")
            os.utime(other, (now - 5, now - 5))

            files = scan_media(str(root), sort="date_asc")
            names = [p.name for p in files]
            self.assertEqual(len(names), 2)
            self.assertTrue(names[0].endswith(".mp4"))
            self.assertEqual(names[1], "Other.mp3")


if __name__ == "__main__":
    unittest.main()
