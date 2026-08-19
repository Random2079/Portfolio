"""Unit tests for BCS portfolio parsing (no live BCS)."""

from __future__ import annotations

import unittest

from portfolio_news.bcs_client import (
    Holding,
    match_holding,
    _parse_portfolio,
    _parse_summary,
    _merge_limits,
)


class ParsePortfolioTests(unittest.TestCase):
    def test_canonical_shape(self):
        raw = {
            "positions": [
                {
                    "ticker": "SBER",
                    "isin": "RU0009029540",
                    "secCode": "SBER",
                    "classCode": "TQBR",
                    "quantity": 10,
                    "openPrice": 250.0,
                    "marketPrice": 280.0,
                    "marketValue": 2800.0,
                    "profitLoss": 300.0,
                    "profitLossPct": 12.0,
                    "currency": "RUB",
                }
            ],
            "summary": {
                "totalValue": 2800.0,
                "cash": 100.0,
                "profitLoss": 300.0,
                "currency": "RUB",
            },
        }
        rows = _parse_portfolio(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ticker, "SBER")
        self.assertEqual(rows[0].quantity, 10)
        self.assertEqual(rows[0].avg_price, 250.0)
        s = _parse_summary(raw)
        self.assertEqual(s["total_value"], 2800.0)

    def test_nested_and_aliases(self):
        raw = {
            "data": {
                "assets": [
                    {
                        "symbol": "HEAD",
                        "ISIN": "RU000A106XF0",
                        "qty": 5,
                        "avgPrice": 100,
                        "last": 110,
                    }
                ]
            }
        }
        rows = _parse_portfolio(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ticker, "HEAD")
        self.assertEqual(rows[0].quantity, 5)
        self.assertAlmostEqual(rows[0].market_value or 0, 550.0)

    def test_merge_limits_fills_qty(self):
        holdings = [Holding(ticker="SBER", sec_code="SBER", quantity=None)]
        limits = {
            "depoLimit": [
                {"secCode": "SBER", "currentBalance": 42},
            ]
        }
        out = _merge_limits(holdings, limits)
        self.assertEqual(out[0].quantity, 42)

    def test_match_holding(self):
        hs = [
            Holding(ticker="SBER", isin="RU0009029540", quantity=1),
            Holding(ticker="", isin="RU000A10EF52", sec_code="RU000A10EF52", quantity=2),
        ]
        self.assertEqual(match_holding(hs, ticker_id="SBER").isin, "RU0009029540")
        self.assertEqual(match_holding(hs, isin="RU000A10EF52").quantity, 2)
        self.assertIsNone(match_holding(hs, ticker_id="NOPE"))


if __name__ == "__main__":
    unittest.main()
