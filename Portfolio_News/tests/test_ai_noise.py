"""F-A: ai_noise parser — no network."""

from __future__ import annotations

import unittest

from portfolio_news.ai_noise import (
    PROMPT_BATCH,
    calibrate_urgency,
    extract_json_object,
    high_allowed_from_title,
    parse_classify_item,
    parse_classify_response,
)


class ParseItemTests(unittest.TestCase):
    def test_relevant_mid(self):
        r = parse_classify_item(
            {"id": 7, "label": "relevant", "urgency": "high", "reason": "отчёт по выручке"}
        )
        self.assertEqual(r["id"], 7)
        self.assertEqual(r["label"], "relevant")
        self.assertEqual(r["urgency"], "high")
        self.assertIn("выручке", r["reason"])

    def test_noise_drops_urgency(self):
        r = parse_classify_item({"label": "noise", "urgency": "high", "reason": "кликбейт"})
        self.assertEqual(r["label"], "noise")
        self.assertIsNone(r["urgency"])

    def test_bad_label(self):
        with self.assertRaises(ValueError):
            parse_classify_item({"label": "buy"})

    def test_reason_trimmed(self):
        long = "x" * 200
        r = parse_classify_item({"label": "dup", "reason": long})
        self.assertLessEqual(len(r["reason"]), 120)


class ParseResponseTests(unittest.TestCase):
    def test_items_array(self):
        raw = '{"items":[{"id":1,"label":"noise","reason":"спам"},{"id":2,"label":"relevant","urgency":"low","reason":"дивиденд"}]}'
        rows = parse_classify_response(raw)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["label"], "noise")
        self.assertEqual(rows[1]["urgency"], "low")

    def test_markdown_fence(self):
        raw = '```json\n{"items":[{"id":3,"label":"dup","reason":"повтор"}]}\n```'
        rows = parse_classify_response(raw)
        self.assertEqual(rows[0]["id"], 3)

    def test_single_object(self):
        rows = parse_classify_response('{"label":"relevant","urgency":"mid","reason":"оферта"}')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "relevant")

    def test_extract_embedded(self):
        data = extract_json_object('blah {"label":"noise","reason":"x"} tail')
        self.assertEqual(data["label"], "noise")


class PromptGeoTests(unittest.TestCase):
    def test_prompt_keeps_ru_geopolitics_relevant(self):
        # Light guard: do not auto-noise «макро без бумаги»; prefer market geo.
        self.assertNotIn("макро-страшилка без бумаги", PROMPT_BATCH)
        self.assertIn("геополитик", PROMPT_BATCH.lower())
        self.assertIn("MOEX", PROMPT_BATCH)
        self.assertIn("Слова «срочно»", PROMPT_BATCH)


class UrgencyCalibrationTests(unittest.TestCase):
    def test_clickbait_high_demoted_to_mid(self):
        row = {"label": "relevant", "urgency": "high", "reason": "срочно"}
        out = calibrate_urgency(row, {"title": "Срочно: акция может вырасти"})
        self.assertEqual(out["urgency"], "mid")
        self.assertIn("high снят", out["reason"])

    def test_hard_event_keeps_high(self):
        row = {"label": "relevant", "urgency": "high", "reason": "суд"}
        out = calibrate_urgency(row, {"title": "Суд взыскал с эмитента крупный долг"})
        self.assertEqual(out["urgency"], "high")

    def test_high_guard_patterns(self):
        self.assertTrue(high_allowed_from_title("Облигации допустили технический дефолт"))
        self.assertFalse(high_allowed_from_title("Важная идея аналитика по акциям"))


if __name__ == "__main__":
    unittest.main()
