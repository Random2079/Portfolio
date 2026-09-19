"""F-A: ai_noise parser — no network."""

from __future__ import annotations

import unittest

from portfolio_news.ai_noise import (
    extract_json_object,
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


if __name__ == "__main__":
    unittest.main()
