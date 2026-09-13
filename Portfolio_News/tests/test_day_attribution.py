"""Unit tests for KA day attribution (no live BCS/MOEX)."""

from __future__ import annotations

import unittest

from portfolio_news.bcs_client import Holding
from portfolio_news.day_attribution import (
    DayQuote,
    compute_day_attribution,
    day_delta_rub,
    is_cash_holding,
)


class DayDeltaTests(unittest.TestCase):
    def test_qty_last_prev(self):
        self.assertAlmostEqual(
            day_delta_rub(quantity=10, market_value=2800, last=280, prevprice=250) or 0,
            300.0,
        )

    def test_flat_day(self):
        self.assertEqual(
            day_delta_rub(quantity=5, market_value=500, last=100, prevprice=100),
            0.0,
        )

    def test_from_changepct_and_mv(self):
        # mv at last; pct vs prev → Δ = mv * pct/(100+pct)
        # last=110, prev=100 → pct=10; mv=1100 → Δ=100
        rub = day_delta_rub(quantity=None, market_value=1100.0, changepct=10.0)
        self.assertAlmostEqual(rub or 0, 100.0, places=6)


class ComputeAttributionTests(unittest.TestCase):
    def test_top_contributors_and_totals(self):
        holdings = [
            Holding(ticker="SBER", quantity=10, market_value=2800, market_price=280),
            Holding(ticker="GAZP", quantity=20, market_value=2000, market_price=100),
            Holding(ticker="RUB", quantity=5000, market_value=5000),  # cash skip
            Holding(ticker="LKOH", quantity=1, market_value=7000, market_price=7000),
        ]
        quotes = {
            "SBER": DayQuote(ticker="SBER", last=280, prevprice=250, changepct=12.0),
            "GAZP": DayQuote(ticker="GAZP", last=100, prevprice=110, changepct=-9.0909),
            "LKOH": DayQuote(ticker="LKOH", last=7000, prevprice=6900, changepct=1.449),
        }
        attr = compute_day_attribution(holdings, quotes, top_n=2)
        self.assertTrue(attr.ok)
        self.assertAlmostEqual(attr.total_value or 0, 11800.0)  # no cash
        # SBER +300, GAZP -200, LKOH +100 → +200
        self.assertAlmostEqual(attr.day_rub or 0, 200.0, places=4)
        self.assertEqual(len(attr.top), 2)
        self.assertEqual(attr.top[0].ticker, "SBER")
        self.assertAlmostEqual(attr.top[0].day_rub or 0, 300.0)
        self.assertEqual(attr.top[1].ticker, "GAZP")
        self.assertEqual(attr.missing, 0)

    def test_missing_quotes_counted(self):
        holdings = [
            Holding(ticker="SBER", quantity=1, market_value=100, market_price=100),
            Holding(ticker="NOPE", quantity=1, market_value=50, market_price=50),
        ]
        quotes = {"SBER": DayQuote(ticker="SBER", last=100, prevprice=90, changepct=11.11)}
        attr = compute_day_attribution(holdings, quotes, top_n=5)
        self.assertEqual(attr.missing, 1)
        self.assertAlmostEqual(attr.day_rub or 0, 10.0)

    def test_cash_helper(self):
        self.assertTrue(is_cash_holding(Holding(ticker="USD")))
        self.assertFalse(is_cash_holding(Holding(ticker="SBER")))


if __name__ == "__main__":
    unittest.main()
