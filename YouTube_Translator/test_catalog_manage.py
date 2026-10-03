"""Unit tests for C2b catalog delete/rename (temp dir, no GUI)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overlay_player import (
    catalog_pair_files,
    delete_catalog_pair,
    rename_catalog_pair,
    sanitize_media_title,
)


class CatalogManageTests(unittest.TestCase):
    def test_sanitize_strips_invalid(self) -> None:
        self.assertEqual(sanitize_media_title('  Foo<>:"/\\|?*Bar  '), "FooBar")
        self.assertEqual(sanitize_media_title("   "), "")

    def test_pair_by_youtube_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "Song A [dQw4w9WgXcQ].mp4"
            mp3 = root / "Song A [dQw4w9WgXcQ].mp3"
            other = root / "Other [xxxxxxxxxx1].mp3"
            mp4.write_bytes(b"v")
            mp3.write_bytes(b"a")
            other.write_bytes(b"x")
            names = {p.name for p in catalog_pair_files(mp4)}
            self.assertEqual(names, {mp4.name, mp3.name})

    def test_rename_keeps_id_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "Old Name [dQw4w9WgXcQ].mp4"
            mp3 = root / "Old Name [dQw4w9WgXcQ].mp3"
            mp4.write_bytes(b"v")
            mp3.write_bytes(b"a")
            ok, msg, primary = rename_catalog_pair(mp4, "New Title")
            self.assertTrue(ok, msg)
            self.assertIsNotNone(primary)
            assert primary is not None
            self.assertTrue(primary.name.startswith("New Title [dQw4w9WgXcQ]"))
            self.assertTrue((root / "New Title [dQw4w9WgXcQ].mp4").is_file())
            self.assertTrue((root / "New Title [dQw4w9WgXcQ].mp3").is_file())
            self.assertFalse(mp4.exists())
            self.assertFalse(mp3.exists())

    def test_delete_removes_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "Kill Me [abcdefghijk].mp4"
            mp3 = root / "Kill Me [abcdefghijk].mp3"
            mp4.write_bytes(b"v")
            mp3.write_bytes(b"a")
            ok, msg, deleted = delete_catalog_pair(mp4)
            self.assertTrue(ok, msg)
            self.assertEqual(len(deleted), 2)
            self.assertFalse(mp4.exists())
            self.assertFalse(mp3.exists())

    def test_rename_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "A [dQw4w9WgXcQ].mp3"
            b = root / "Taken [xxxxxxxxxx1].mp3"
            a.write_bytes(b"1")
            b.write_bytes(b"2")
            # rename A to Taken but different id → Taken [dQw4w9WgXcQ].mp3 ok
            ok, _msg, _p = rename_catalog_pair(a, "Taken")
            self.assertTrue(ok)
            # second file same target name
            c = root / "C [yyyyyyyyyy1].mp3"
            c.write_bytes(b"3")
            (root / "Taken [dQw4w9WgXcQ].mp3").write_bytes(b"block")  # already from rename
            # create conflict: rename c to name that exists with same id pattern
            exist = root / "Exist [zzzzzzzzzz1].mp3"
            exist.write_bytes(b"e")
            d = root / "D [zzzzzzzzzz1].mp4"
            d.write_bytes(b"v")
            # renaming D to Exist would collide with Exist [id].mp3? 
            # build_renamed for D → Exist [zzzzzzzzzz1].mp4 — no collision with .mp3
            ok2, msg2, _ = rename_catalog_pair(d, "Exist")
            self.assertTrue(ok2, msg2)


if __name__ == "__main__":
    unittest.main()
