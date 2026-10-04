"""Pure helpers for SR single-instance gate (titles / process match)."""
from __future__ import annotations

import unittest

from Subtitle_App import (
    _is_fond_window_title,
    _is_main_sr_window_title,
    _process_looks_like_main_sr,
)


class TestMainSrWindowTitle(unittest.TestCase):
    def test_main_titles(self) -> None:
        self.assertTrue(_is_main_sr_window_title("Subtitle Ripper Pro"))
        self.assertTrue(_is_main_sr_window_title("Subtitle Ripper Pro — video"))
        self.assertTrue(_is_main_sr_window_title("Subtitle Ripper"))

    def test_fond_not_main(self) -> None:
        self.assertFalse(_is_main_sr_window_title("Фон — overlay (IDEA-022)"))
        self.assertFalse(_is_main_sr_window_title("Фон — overlay"))
        self.assertFalse(_is_main_sr_window_title(""))
        self.assertFalse(_is_main_sr_window_title("Chrome"))


class TestFondWindowTitle(unittest.TestCase):
    def test_fond(self) -> None:
        self.assertTrue(_is_fond_window_title("Фон — overlay (IDEA-022)"))
        self.assertTrue(_is_fond_window_title("Фон - overlay"))
        self.assertFalse(_is_fond_window_title("Subtitle Ripper Pro"))


class TestProcessLooksLikeMainSr(unittest.TestCase):
    def test_dev_python(self) -> None:
        self.assertTrue(
            _process_looks_like_main_sr(
                "pythonw.exe",
                [r"C:\Python\pythonw.exe", r"C:\proj\Subtitle_App.py"],
            )
        )
        self.assertFalse(
            _process_looks_like_main_sr(
                "python.exe",
                [r"C:\Python\python.exe", r"C:\proj\overlay_player.py"],
            )
        )

    def test_packed_exe(self) -> None:
        self.assertTrue(
            _process_looks_like_main_sr("Subtitle Ripper Pro.exe", None)
        )
        self.assertTrue(
            _process_looks_like_main_sr(
                "something.exe",
                r"C:\dist\Subtitle Ripper Pro\Subtitle Ripper Pro.exe",
            )
        )
        self.assertFalse(_process_looks_like_main_sr("notepad.exe", None))


if __name__ == "__main__":
    unittest.main()
