"""Тесты merge/дедупа субтитров (YouTube rolling captions)."""
from __future__ import annotations

import os
import tempfile
import unittest

from Subtitle_App import (
    build_texts_from_srt,
    extend_caption_text,
    merge_segments,
    segments_to_plain_text,
)


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


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

    def test_rerun_overwrite_not_append(self) -> None:
        """5) повторная запись в тот же файл не удваивает результат (mode w)."""
        srt = """1
00:00:00,000 --> 00:00:02,000
Одна фраза здесь

2
00:00:00,500 --> 00:00:02,500
Одна фраза здесь
"""
        plain, _, _ = build_texts_from_srt(srt)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "0_весь_текст_для_буфера.txt")
            for _ in range(3):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(plain)
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()
            self.assertEqual(body, plain)
            self.assertEqual(body.count("Одна фраза здесь"), 1)


if __name__ == "__main__":
    unittest.main()
