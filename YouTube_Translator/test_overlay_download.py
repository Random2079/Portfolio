"""Unit tests for overlay wallpaper yt-dlp cmd builders (no network)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

import Subtitle_App as app


class OverlayDownloadCmdTests(unittest.TestCase):
    def test_out_tmpl_shared_stem(self) -> None:
        tmpl = app._overlay_media_out_tmpl(r"C:\Music\YouTube_DL")
        self.assertIn("%(title).200B [%(id)s].%(ext)s", tmpl)
        self.assertTrue(tmpl.endswith("%(title).200B [%(id)s].%(ext)s"))

    def test_video_cmd_has_merge_and_impersonate(self) -> None:
        with mock.patch.dict(os.environ, {"SUBTITLE_RIPPER_IMPERSONATE": "Chrome-136"}):
            cmd = app.build_overlay_video_ytdlp_cmd(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                r"C:\out",
            )
        joined = " ".join(cmd)
        self.assertIn("--impersonate", cmd)
        self.assertIn("Chrome-136", cmd)
        self.assertIn("--merge-output-format", cmd)
        self.assertIn("mp4", cmd)
        self.assertIn(app._OVERLAY_FMT_DEFAULT, cmd)
        self.assertIn("-S", cmd)
        self.assertIn(app._OVERLAY_FMT_SORT, cmd)
        self.assertIn("dQw4w9WgXcQ", joined)

    def test_video_cmd_dash_fmt(self) -> None:
        cmd = app.build_overlay_video_ytdlp_cmd(
            "https://youtu.be/abcdefghijk",
            r"C:\out",
            fmt=app._OVERLAY_FMT_DASH,
        )
        self.assertIn(app._OVERLAY_FMT_DASH, cmd)

    def test_impersonate_off(self) -> None:
        with mock.patch.dict(os.environ, {"SUBTITLE_RIPPER_IMPERSONATE": "0"}):
            self.assertEqual(app._ytdlp_impersonate_args(), [])

    def test_audio_overlay_cmd_extracts_mp3(self) -> None:
        cmd = app.build_overlay_audio_ytdlp_cmd(
            "https://www.youtube.com/watch?v=abcdefghijk",
            r"C:\out",
        )
        self.assertIn("-x", cmd)
        self.assertIn("--audio-format", cmd)
        self.assertIn("mp3", cmd)
        self.assertIn("--audio-quality", cmd)
        aq = cmd.index("--audio-quality")
        self.assertEqual(cmd[aq + 1], "0")

    def test_default_fmt_prefers_max_res(self) -> None:
        self.assertIn("bestvideo", app._OVERLAY_FMT_DEFAULT)
        self.assertIn("height<=2160", app._OVERLAY_FMT_DEFAULT)
        self.assertEqual(app._OVERLAY_FMT_SORT, "res,fps,vbr,abr")

    def test_dash_retry_heuristic(self) -> None:
        self.assertTrue(app._ytdlp_stderr_suggests_dash_retry("Only images available"))
        self.assertFalse(app._ytdlp_stderr_suggests_dash_retry("HTTP Error 403"))


if __name__ == "__main__":
    unittest.main()
