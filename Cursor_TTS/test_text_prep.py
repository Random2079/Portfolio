"""Тесты словаря, RU/EN-сегментации и таблиц (без Piper/pygame)."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import text_prep
from text_prep import (
    apply_pronunciations,
    finalize_speech_segments,
    finalize_speech_text,
    load_pronunciations,
    segment_languages,
    tables_to_speech,
)


class TestPronunciations(unittest.TestCase):
    def test_whole_word_case_insensitive(self) -> None:
        vocab = {"fallback": "фэлбэк", "python": "питон"}
        self.assertIn("фэлбэк", apply_pronunciations("Use FALLBACK here", vocab))
        self.assertIn("питон", apply_pronunciations("Python rocks", vocab))

    def test_does_not_eat_substring(self) -> None:
        vocab = {"cache": "кэш"}
        out = apply_pronunciations("cacheable", vocab)
        self.assertEqual(out, "cacheable")

    def test_json_file_loads(self) -> None:
        vocab = load_pronunciations()
        self.assertIn("fallback", vocab)
        self.assertEqual(vocab["fallback"], "фэлбэк")
        self.assertTrue((Path(text_prep.PRONUNCIATIONS_FILE)).is_file())


class TestLanguageRouting(unittest.TestCase):
    def test_ru_plus_one_term_stays_ru(self) -> None:
        vocab = {"fallback": "фэлбэк"}
        segs = segment_languages("Если fallback не работает", vocab)
        self.assertTrue(segs)
        self.assertTrue(all(s.lang == "ru" for s in segs))

    def test_english_phrase_is_en(self) -> None:
        segs = segment_languages(
            "Check the network connection and restart the daemon.",
            vocab={},
        )
        self.assertTrue(segs)
        self.assertTrue(any(s.lang == "en" for s in segs))
        self.assertTrue(all(s.lang == "en" for s in segs))

    def test_mixed_keeps_punctuation(self) -> None:
        vocab = {"fallback": "фэлбэк"}
        segs = segment_languages(
            "Если fallback не работает, check the network connection, потом демон.",
            vocab,
        )
        langs = [s.lang for s in segs]
        self.assertIn("ru", langs)
        self.assertIn("en", langs)
        joined = " ".join(s.text for s in segs)
        self.assertIn(",", joined)

    def test_finalize_replaces_fallback_on_ru(self) -> None:
        segs = finalize_speech_segments("Если fallback не сработал.")
        ru = " ".join(s.text for s in segs if s.lang == "ru")
        self.assertIn("фэлбэк", ru.lower().replace("э", "э"))
        self.assertNotIn("fallback", ru.lower())

    def test_finalize_en_skips_normalizer_words(self) -> None:
        segs = finalize_speech_segments(
            "Check the network connection and restart the daemon."
        )
        en = " ".join(s.text for s in segs if s.lang == "en")
        self.assertIn("network", en.lower())


class TestTablesStillWork(unittest.TestCase):
    def test_markdown_table_header(self) -> None:
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        out = tables_to_speech(md)
        self.assertIn("Столбцы:", out)
        joined = finalize_speech_text(md, apply_dict=False)
        self.assertIn("Столбцы", joined)


class TestStageDirections(unittest.TestCase):
    def test_strips_short_stage_cues(self) -> None:
        source = "Я иду домой. *вздох* Потом (pause) [смеётся] продолжаю."
        out = finalize_speech_text(source, apply_dict=False).lower()
        self.assertIn("я иду домой", out)
        self.assertIn("потом", out)
        self.assertNotIn("вздох", out)
        self.assertNotIn("pause", out)
        self.assertNotIn("смеётся", out)


class TestQwenChunkIntegrity(unittest.TestCase):
    def test_decimal_date_example_survives_preparation_and_chunking(self) -> None:
        import tts_daemon as daemon

        source = (
            "Цифра ~2,7 трлн на 13.08.2026 совпадает с данными ЦБ "
            "(Коммерсант / РБК). Максимум с марта 2022, "
            "но ЦБ сам это не считает аварией."
        )
        cfg = {"engine": "qwen", "hybrid_mode": "dict_only"}
        with patch("text_prep.normalize_tts", side_effect=lambda text: text):
            prepared = finalize_speech_text(source)
            units = daemon._speech_units(source, cfg)

        self.assertEqual(units, [(prepared, "ru")])
        self.assertIn("2,7 трлн на 13.08.2026", prepared)
        self.assertIn("Максимум с марта 2022", prepared)
        self.assertTrue(prepared.endswith("не считает аварией."))


class TestPathAndChunkPrep(unittest.TestCase):
    def test_path_slash_not_or(self) -> None:
        out = finalize_speech_text("docs/parts/MAP.md", apply_dict=True)
        self.assertNotIn("или", out)
        self.assertNotIn(".md", out.lower())
        self.assertIn("мэп", out.lower())

    def test_spaced_slash_is_or(self) -> None:
        out = finalize_speech_text("take / pass", apply_dict=False)
        self.assertIn("или", out)

    def test_file_ext_not_sentence_break(self) -> None:
        import tts_daemon as daemon

        source = "Открыл Portfolio_News/MAP.md — короткий."
        with patch("text_prep.normalize_tts", side_effect=lambda text: text):
            units = daemon._speech_units(
                source, {"engine": "tera", "hybrid_mode": "dict_only"}
            )
        joined = " ".join(t for t, _ in units)
        self.assertNotRegex(joined, r"(?i)\bмд\b")
        self.assertFalse(any(t.strip().lower().startswith("мд") for t, _ in units))


class TestListChunking(unittest.TestCase):
    def test_short_numbered_list_is_one_tera_unit(self) -> None:
        import tts_daemon as daemon

        source = (
            "1. После слоя — explain.\n"
            "2. Запомнить цепочку из 5–8 блоков.\n"
            "3. Самому ответить на три вопроса:\n"
            "   ◦ зачем этот блок;\n"
            "   ◦ что сломается без него;\n"
            "4. На следующий день — exam.\n"
            "Это 10–15 минут, не вторая работа."
        )
        with patch("text_prep.normalize_tts", side_effect=lambda text: text):
            units = daemon._speech_units(
                source, {"engine": "tera", "hybrid_mode": "dict_only"}
            )
        self.assertEqual(len(units), 1, units)

    def test_slash_command_and_range(self) -> None:
        out = finalize_speech_text(
            "После слоя — `/explain-my-project`. Цепочка 5–8 блоков.",
            apply_dict=False,
        )
        low = out.lower()
        self.assertIn("команда", low)
        self.assertTrue("до" in low and ("5" in out or "пят" in low))
        self.assertNotIn("пяти, восемь", low)


class TestRuOnlyHybrid(unittest.TestCase):
    def test_dict_and_en_collapses_to_dict_only(self) -> None:
        import tts_daemon as daemon

        for engine in ("tera", "edge", "local"):
            cfg = {"engine": engine, "hybrid_mode": "dict_and_en"}
            self.assertEqual(daemon._effective_hybrid(cfg), "dict_only")

    def test_english_phrase_stays_ru_units(self) -> None:
        import tts_daemon as daemon

        source = "Check the network connection and restart."
        with patch("text_prep.normalize_tts", side_effect=lambda text: text):
            units = daemon._speech_units(
                source, {"engine": "tera", "hybrid_mode": "dict_and_en"}
            )
        self.assertTrue(units)
        self.assertTrue(all(lang == "ru" for _, lang in units))
        joined = " ".join(t for t, _ in units).lower()
        self.assertIn("нэтворк", joined)
        self.assertIn("рестарт", joined)


class TestMissingEnModel(unittest.TestCase):
    def test_hybrid_collapses_without_tera(self) -> None:
        import tts_daemon as daemon

        cfg = {"engine": "local", "hybrid_mode": "dict_and_en"}
        self.assertEqual(daemon._effective_hybrid(cfg), "dict_only")


if __name__ == "__main__":
    unittest.main()
