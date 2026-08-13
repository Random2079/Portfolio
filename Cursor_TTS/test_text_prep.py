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


class TestMissingEnModel(unittest.TestCase):
    def test_hybrid_falls_back_without_en_file(self) -> None:
        import tts_daemon as daemon

        cfg = {
            "engine": "piper",
            "hybrid_mode": "dict_and_en",
            "piper_model_en": "models/en_US-ryan-medium.onnx",
        }
        with patch("speak_piper.model_exists", return_value=False):
            self.assertEqual(daemon._effective_hybrid(cfg), "dict_only")


if __name__ == "__main__":
    unittest.main()
