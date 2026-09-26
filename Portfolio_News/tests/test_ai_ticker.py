"""F-B: ai_ticker parser — no network."""

from __future__ import annotations

import unittest

from portfolio_news.ai_ticker import parse_ticker_review


class ParseTickerReviewTests(unittest.TestCase):
    def test_ok(self):
        raw = """{
          "ticker": "sber",
          "summary": "Отчёт и дивиденды.",
          "hits": ["дивидендная политика", "капитал"],
          "urgency": "mid",
          "checklist": ["держим ли под див.?", "есть ли кэш на добор?"],
          "caveats": ["цифр в заголовках нет"]
        }"""
        p = parse_ticker_review(raw, default_ticker="SBER")
        self.assertEqual(p["ticker"], "SBER")
        self.assertEqual(p["urgency"], "mid")
        self.assertEqual(len(p["hits"]), 2)
        self.assertGreaterEqual(len(p["checklist"]), 2)

    def test_bad_urgency_defaults(self):
        p = parse_ticker_review(
            {"ticker": "OZON", "summary": "x", "urgency": " ASAP", "hits": [], "checklist": ["a"]},
            default_ticker="OZON",
        )
        self.assertEqual(p["urgency"], "mid")

    def test_markdown_fence(self):
        raw = '```json\n{"ticker":"TATNP","summary":"нефть","urgency":"low","hits":["цена нефти"],"checklist":["сектор ok?"]}\n```'
        p = parse_ticker_review(raw)
        self.assertEqual(p["ticker"], "TATNP")
        self.assertEqual(p["urgency"], "low")

    def test_forbids_empty_root(self):
        with self.assertRaises(ValueError):
            parse_ticker_review([])


if __name__ == "__main__":
    unittest.main()
