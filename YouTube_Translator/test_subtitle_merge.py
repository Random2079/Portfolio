"""Тесты merge/дедупа субтитров + хелперы Translator."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from Subtitle_App import (
    build_meta_yt_dlp_cmd,
    build_texts_from_srt,
    extend_caption_text,
    fetch_video_meta,
    get_video_id,
    merge_segments,
    resolve_subtitle_track,
    segments_to_plain_text,
    write_output_texts,
)


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


class TestVideoId(unittest.TestCase):
    def test_watch_url(self) -> None:
        self.assertEqual(
            get_video_id("https://www.youtube.com/watch?v=PgKGax4kknY"),
            "PgKGax4kknY",
        )

    def test_short_url(self) -> None:
        self.assertEqual(get_video_id("https://youtu.be/PgKGax4kknY"), "PgKGax4kknY")

    def test_rejects_garbage(self) -> None:
        self.assertIsNone(get_video_id("https://youtu.be/short"))
        self.assertIsNone(get_video_id("https://example.com/not-youtube"))
        self.assertIsNone(get_video_id("https://www.youtube.com/watch?v=too_short"))


class TestResolveLang(unittest.TestCase):
    def test_ru_ru_from_auto(self) -> None:
        meta = {"automatic_captions": {"ru-RU": []}, "subtitles": {}}
        self.assertEqual(resolve_subtitle_track(meta, "ru"), ("auto", "ru-RU"))

    def test_prefers_auto_over_manual(self) -> None:
        meta = {
            "automatic_captions": {"en": []},
            "subtitles": {"en": []},
        }
        self.assertEqual(resolve_subtitle_track(meta, "en"), ("auto", "en"))

    def test_manual_fallback(self) -> None:
        meta = {"automatic_captions": {}, "subtitles": {"ru": []}}
        self.assertEqual(resolve_subtitle_track(meta, "ru"), ("manual", "ru"))

    def test_missing(self) -> None:
        self.assertIsNone(resolve_subtitle_track({}, "ru"))


class TestMetaCmd(unittest.TestCase):
    def test_url_after_double_dash(self) -> None:
        url = "https://www.youtube.com/watch?v=PgKGax4kknY"
        cmd = build_meta_yt_dlp_cmd(url, ["--socket-timeout", "20"])
        self.assertEqual(cmd[-2], "--")
        self.assertEqual(cmd[-1], url)
        self.assertIn("--socket-timeout", cmd)

    def test_timeout_stops_retries(self) -> None:
        import subprocess

        calls: list[list[str]] = []

        def boom(cmd, **kwargs):
            calls.append(list(cmd))
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)

        with mock.patch("Subtitle_App.subprocess.run", side_effect=boom):
            with self.assertRaises(subprocess.TimeoutExpired):
                fetch_video_meta("https://www.youtube.com/watch?v=PgKGax4kknY", 0)
        self.assertEqual(len(calls), 1)


class TestExtendCaption(unittest.TestCase):
    def test_exact_duplicate(self) -> None:
        t = "Каждый из нас хоть раз в жизни"
        self.assertEqual(extend_caption_text(t, t), t)

    def test_rolling_extension(self) -> None:
        a = "Каждый из нас хоть раз"
        b = "Каждый из нас хоть раз в жизни сталкивался"
        self.assertEqual(extend_caption_text(a, b), b)

    def test_partial_word_overlap(self) -> None:
        a = "Каждый из нас хоть раз"
        b = "хоть раз в жизни сталкивался"
        self.assertEqual(
            extend_caption_text(a, b),
            "Каждый из нас хоть раз в жизни сталкивался",
        )

    def test_independent_returns_none(self) -> None:
        self.assertIsNone(
            extend_caption_text("Привет друзья", "Сегодня поговорим о рынке")
        )

    def test_single_stopword_overlap_not_merged(self) -> None:
        """Одно общее слово («в») не должно склеивать разные фразы."""
        self.assertIsNone(extend_caption_text("в конце", "в начале"))
        self.assertIsNone(extend_caption_text("сказал и", "и потом ушёл"))

    def test_two_word_overlap_still_merges(self) -> None:
        self.assertEqual(
            extend_caption_text("мы идём дальше", "идём дальше вместе"),
            "мы идём дальше вместе",
        )

    def test_punct_tolerant_prefix(self) -> None:
        self.assertEqual(
            extend_caption_text("Каждый из нас хоть раз,", "Каждый из нас хоть раз в жизни"),
            "Каждый из нас хоть раз в жизни",
        )


class TestMergePipeline(unittest.TestCase):
    def test_exact_triple_duplicate(self) -> None:
        """1) точный тройной дубль → одна строка."""
        phrase = "Каждый из нас хоть раз в жизни"
        segs = [
            _seg(0.0, 2.0, phrase),
            _seg(0.5, 2.5, phrase),
            _seg(1.0, 3.0, phrase),
        ]
        plain = segments_to_plain_text(merge_segments(segs))
        self.assertEqual(plain, phrase)

    def test_partial_overlapping_segments(self) -> None:
        """2) частично перекрывающиеся сегменты → одна склеенная фраза."""
        segs = [
            _seg(0.0, 2.0, "Каждый из нас хоть раз"),
            _seg(1.0, 3.0, "хоть раз в жизни сталкивался"),
        ]
        plain = segments_to_plain_text(merge_segments(segs))
        self.assertEqual(plain, "Каждый из нас хоть раз в жизни сталкивался")

    def test_nearby_unrelated_not_glued(self) -> None:
        """Близкие по времени, но без overlap — не склеиваем в кашу."""
        segs = [
            _seg(0.0, 1.0, "воняет мусор надо"),
            _seg(1.1, 2.0, "озеро шашлык"),
            _seg(2.1, 3.0, "ненавижу насекомых"),
        ]
        plain = segments_to_plain_text(merge_segments(segs))
        self.assertEqual(
            plain.splitlines(),
            ["воняет мусор надо", "озеро шашлык", "ненавижу насекомых"],
        )

    def test_nearby_single_word_overlap_not_glued(self) -> None:
        """Близко по времени + одно общее слово — всё равно две фразы."""
        segs = [
            _seg(0.0, 1.0, "был в конце"),
            _seg(1.1, 2.0, "в начале пути"),
        ]
        plain = segments_to_plain_text(merge_segments(segs))
        self.assertEqual(plain.splitlines(), ["был в конце", "в начале пути"])
        self.assertNotIn("конце начале", plain)

    def test_normal_neighbor_phrases(self) -> None:
        """3) нормальные соседние фразы остаются двумя строками."""
        segs = [
            _seg(0.0, 2.0, "Первая мысль про рынок."),
            _seg(5.0, 7.0, "Вторая мысль про акции."),
        ]
        plain = segments_to_plain_text(merge_segments(segs))
        self.assertEqual(
            plain.splitlines(),
            ["Первая мысль про рынок.", "Вторая мысль про акции."],
        )

    def test_intentional_repeat_inside_phrase(self) -> None:
        """4) «нет, нет, нет» внутри одной фразы не вычищается."""
        segs = [_seg(0.0, 1.5, "нет, нет, нет")]
        plain = segments_to_plain_text(merge_segments(segs))
        self.assertEqual(plain, "нет, нет, нет")

    def test_youtube_rolling_srt_fragment(self) -> None:
        """Реалистичный фрагмент auto-SRT: rolling window без «A A B»."""
        srt = """1
00:00:00,000 --> 00:00:02,500
Каждый из нас хоть раз

2
00:00:01,200 --> 00:00:03,800
Каждый из нас хоть раз в жизни

3
00:00:02,500 --> 00:00:05,000
Каждый из нас хоть раз в жизни сталкивался

4
00:00:08,000 --> 00:00:10,000
А теперь другая тема.
"""
        plain, _timed, phrases = build_texts_from_srt(srt)
        lines = plain.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "Каждый из нас хоть раз в жизни сталкивался")
        self.assertEqual(lines[1], "А теперь другая тема.")
        self.assertNotIn("Каждый из нас хоть раз Каждый", plain)
        self.assertEqual(len(phrases), 2)

    def test_long_monologue_without_periods_splits(self) -> None:
        """Длинный rolling без точек режется по словам, не одной простынёй."""
        words = " ".join(f"слово{i}" for i in range(80))
        segs = [_seg(0.0, 40.0, words)]
        phrases = merge_segments(segs, max_chars=60)
        self.assertGreater(len(phrases), 1)
        self.assertTrue(all(len(p["text"]) <= 60 for p in phrases))

    def test_write_output_texts_overwrite_not_append(self) -> None:
        """Повторный write_output_texts не удваивает файлы (mode w)."""
        with tempfile.TemporaryDirectory() as tmp:
            write_output_texts(tmp, "один\n", "[00:00] один\n", "ru", max_chars=100)
            write_output_texts(tmp, "два\n", "[00:00] два\n", "ru", max_chars=100)
            with open(
                os.path.join(tmp, "0_весь_текст_для_буфера.txt"),
                encoding="utf-8",
            ) as f:
                body = f.read()
            self.assertEqual(body, "два\n")
            self.assertNotIn("один", body)
            with open(
                os.path.join(tmp, "1_текст_с_таймкодами.txt"),
                encoding="utf-8",
            ) as f:
                timed = f.read()
            self.assertEqual(timed, "[00:00] два\n")


if __name__ == "__main__":
    unittest.main()
