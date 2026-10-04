"""Pure helpers for SR single-instance gate (titles / process match / open_request)."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from Subtitle_App import (
    _ACTIVATE_REQUEST,
    _is_fond_window_title,
    _is_main_sr_window_title,
    _process_looks_like_main_sr,
    read_open_request,
    second_instance_may_bring_main,
    write_open_request,
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


class TestSecondInstanceBringPolicy(unittest.TestCase):
    def test_pending_url_never_bring(self) -> None:
        # overlay-live / hidden shell: URL only via open_request
        self.assertFalse(
            second_instance_may_bring_main(
                pending_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                activate_ok=False,
                main_visible=False,
            )
        )
        self.assertFalse(
            second_instance_may_bring_main(
                pending_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                activate_ok=False,
                main_visible=True,
            )
        )

    def test_activate_ok_skips_bring(self) -> None:
        self.assertFalse(
            second_instance_may_bring_main(
                pending_url=None,
                activate_ok=True,
                main_visible=True,
            )
        )

    def test_activate_fail_bring_only_if_visible(self) -> None:
        self.assertTrue(
            second_instance_may_bring_main(
                pending_url=None,
                activate_ok=False,
                main_visible=True,
            )
        )
        self.assertFalse(
            second_instance_may_bring_main(
                pending_url=None,
                activate_ok=False,
                main_visible=False,
            )
        )


class TestReadOpenRequestActivate(unittest.TestCase):
    def test_activate_token_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "open_request.txt")
            with mock.patch(
                "Subtitle_App.open_request_path", return_value=path
            ):
                write_open_request(_ACTIVATE_REQUEST)
                self.assertEqual(
                    read_open_request(consume=True), _ACTIVATE_REQUEST
                )
                self.assertFalse(os.path.isfile(path))

    def test_youtube_url_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "open_request.txt")
            with mock.patch(
                "Subtitle_App.open_request_path", return_value=path
            ):
                write_open_request("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                got = read_open_request(consume=True)
                self.assertEqual(
                    got, "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                )


if __name__ == "__main__":
    unittest.main()
