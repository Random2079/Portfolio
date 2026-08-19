"""Тесты IDEA-016: парсинг таймкодов, прореживание, player.html."""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from timecode_player import (
    build_player_html,
    parse_highlights,
    parse_timed_lines,
    thin_marks,
    video_id_from_folder_name,
    write_player_html,
)


class TestParseTimed(unittest.TestCase):
    def test_lines(self) -> None:
        text = "[00:00] привет\n[0:25] дальше\nмусор\n[1:05] минута\n"
        marks = parse_timed_lines(text)
        self.assertEqual([m["seconds"] for m in marks], [0, 25, 65])
        self.assertEqual(marks[0]["label"], "привет")

    def test_thin_25s(self) -> None:
        marks = [
            {"seconds": 0, "label": "a"},
            {"seconds": 10, "label": "skip"},
            {"seconds": 25, "label": "b"},
            {"seconds": 40, "label": "skip2"},
            {"seconds": 50, "label": "c"},
        ]
        thin = thin_marks(marks, min_gap=25)
        self.assertEqual([m["seconds"] for m in thin], [0, 25, 50])
        self.assertEqual(thin[0]["label"], "a")

    def test_folder_id(self) -> None:
        self.assertEqual(
            video_id_from_folder_name("субтитры_Title [PgKGax4kknY]"),
            "PgKGax4kknY",
        )
        self.assertIsNone(video_id_from_folder_name("no-id-here"))


class TestHighlightsAndHtml(unittest.TestCase):
    def test_highlights_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "метки.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("01:30 | Вступление\n")
            hi = parse_highlights(tmp)
            self.assertEqual(hi[0]["seconds"], 90)
            self.assertEqual(hi[0]["label"], "Вступление")

    def test_broken_json_falls_back_to_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "highlights.json"), "w", encoding="utf-8") as f:
                f.write("{not-json")
            with open(os.path.join(tmp, "метки.txt"), "w", encoding="utf-8") as f:
                f.write("00:45 | Из txt\n")
            hi = parse_highlights(tmp)
            self.assertEqual(len(hi), 1)
            self.assertEqual(hi[0]["seconds"], 45)
            self.assertEqual(hi[0]["label"], "Из txt")

    def test_valid_empty_json_skips_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "highlights.json"), "w", encoding="utf-8") as f:
                f.write("[]")
            with open(os.path.join(tmp, "метки.txt"), "w", encoding="utf-8") as f:
                f.write("00:10 | Не должны взять\n")
            self.assertEqual(parse_highlights(tmp), [])

    def test_highlights_json_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "highlights.json"), "w", encoding="utf-8") as f:
                f.write('[{"t": "02:00", "title": "Середина"}]')
            hi = parse_highlights(tmp)
            self.assertEqual(hi[0]["seconds"], 120)
            self.assertEqual(hi[0]["label"], "Середина")

    def test_html_has_id_and_seek(self) -> None:
        html_text = build_player_html(
            "PgKGax4kknY",
            [{"seconds": 0, "label": "start <x>"}],
            [{"seconds": 90, "label": "hi"}],
        )
        self.assertIn("PgKGax4kknY", html_text)
        self.assertIn("seekTo", html_text)
        self.assertIn("data-t=\"0\"", html_text)
        self.assertIn("&lt;x&gt;", html_text)
        self.assertIn("Полезные", html_text)

    def test_write_player(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            timed = os.path.join(tmp, "1_текст_с_таймкодами.txt")
            with open(timed, "w", encoding="utf-8") as f:
                f.write("[00:00] раз\n[00:10] два\n[00:30] три\n")
            out = write_player_html(tmp, "abcdefghijk")
            self.assertTrue(os.path.isfile(out))
            with open(out, encoding="utf-8") as f:
                body = f.read()
            self.assertIn("abcdefghijk", body)
            self.assertIn("data-t=\"0\"", body)
            self.assertIn("data-t=\"30\"", body)
            self.assertNotIn("data-t=\"10\"", body)


class TestResolvePlayerTarget(unittest.TestCase):
    def test_foreign_url_falls_back_latest_id_none(self) -> None:
        from Subtitle_App import resolve_player_target

        with tempfile.TemporaryDirectory() as root:
            a = os.path.join(root, "субтитры_A [aaaaaaaaaaa]")
            b = os.path.join(root, "субтитры_B [bbbbbbbbbbb]")
            os.makedirs(a)
            time.sleep(0.02)
            os.makedirs(b)
            folder, idw = resolve_player_target(
                "https://youtu.be/ccccccccccc", base_dir=root
            )
            self.assertEqual(folder, b)
            self.assertIsNone(idw)

    def test_matching_url_keeps_id(self) -> None:
        from Subtitle_App import resolve_player_target

        with tempfile.TemporaryDirectory() as root:
            a = os.path.join(root, "субтитры_A [aaaaaaaaaaa]")
            os.makedirs(a)
            folder, idw = resolve_player_target(
                "https://youtu.be/aaaaaaaaaaa", base_dir=root
            )
            self.assertEqual(folder, a)
            self.assertEqual(idw, "aaaaaaaaaaa")

    def test_find_latest_in_given_dist(self) -> None:
        from Subtitle_App import find_latest_subtitle_folder

        with tempfile.TemporaryDirectory() as root:
            dist = os.path.join(root, "dist")
            os.makedirs(os.path.join(dist, "субтитры_InDist [ddddddddddd]"))
            found = find_latest_subtitle_folder(base_dir=dist)
            self.assertIsNotNone(found)
            self.assertIn("ddddddddddd", found or "")

    def test_multi_root_prefers_dist_when_cwd_empty(self) -> None:
        """Эмуляция бага: cwd без папок, артефакт только в dist/ рядом со скриптом."""
        import Subtitle_App as sa

        with tempfile.TemporaryDirectory() as root:
            app_dir = os.path.join(root, "app")
            dist = os.path.join(app_dir, "dist")
            cwd = os.path.join(root, "empty_cwd")
            os.makedirs(cwd)
            os.makedirs(
                os.path.join(dist, "субтитры_OnlyDist [eeeeeeeeeee]")
            )
            fake_file = os.path.join(app_dir, "Subtitle_App.py")
            os.makedirs(app_dir, exist_ok=True)
            with open(fake_file, "w", encoding="utf-8") as f:
                f.write("# stub\n")

            old_cwd = os.getcwd()
            old_file = sa.__file__
            try:
                sa.__file__ = fake_file
                os.chdir(cwd)
                found = sa.find_latest_subtitle_folder()
                self.assertIsNotNone(found)
                self.assertIn("eeeeeeeeeee", found or "")
                self.assertEqual(os.path.basename(os.path.dirname(found or "")), "dist")
            finally:
                os.chdir(old_cwd)
                sa.__file__ = old_file

    def test_app_install_dir_not_temp_when_unfrozen(self) -> None:
        from Subtitle_App import app_install_dir

        d = app_install_dir()
        self.assertTrue(os.path.isdir(d))
        self.assertTrue(
            os.path.isfile(os.path.join(d, "Subtitle_App.py"))
            or os.path.isfile(os.path.join(d, "timecode_player.py"))
        )


if __name__ == "__main__":
    unittest.main()
