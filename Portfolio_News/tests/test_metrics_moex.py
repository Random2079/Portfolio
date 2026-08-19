"""Unit tests for MOEX helpers (no live ISS)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from portfolio_news.metrics_moex import (
    MOEX_DEFAULT_TICKER_LIMIT,
    MetricRow,
    clear_secid_cache,
    effective_moex_limit,
    metric_to_dict,
    parse_coupon_rows,
    parse_dividend_rows,
    resolve_secid,
)


class EffectiveLimitTests(unittest.TestCase):
    def test_single_ticker_no_default_slice(self):
        self.assertEqual(effective_moex_limit(ticker_id="SBER", limit=0), 0)

    def test_broad_scope_defaults_to_15(self):
        self.assertEqual(effective_moex_limit(ticker_id=None, limit=0), MOEX_DEFAULT_TICKER_LIMIT)

    def test_explicit_limit_wins(self):
        self.assertEqual(effective_moex_limit(ticker_id=None, limit=7), 7)
        self.assertEqual(effective_moex_limit(ticker_id="SBER", limit=3), 3)


class MetricToDictTests(unittest.TestCase):
    def test_yield_alias(self):
        m = MetricRow(ticker_id="X", kind="bond", name="X", yield_=12.5)
        d = metric_to_dict(m)
        self.assertNotIn("yield_", d)
        self.assertEqual(d["yield"], 12.5)
        self.assertEqual(d["ticker_id"], "X")


class ParseTablesTests(unittest.TestCase):
    def test_parse_dividends(self):
        rows = parse_dividend_rows(
            "SBER",
            "Сбер",
            "SBER",
            [
                {
                    "isin": "RU0009029540",
                    "registryclosedate": "2024-07-11",
                    "value": 33.3,
                    "currencyid": "RUB",
                    "funny": 1,
                }
            ],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, 33.3)
        self.assertEqual(rows[0].registryclosedate, "2024-07-11")
        self.assertEqual(rows[0].extra.get("funny"), 1)

    def test_parse_coupons_cap(self):
        raw = [
            {
                "coupondate": f"2026-01-{i:02d}",
                "value": float(i),
                "valueprc": 10.0,
            }
            for i in range(1, 50)
        ]
        rows = parse_coupon_rows("BOND", "Bond", "BOND", raw)
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows[0].coupondate, "2026-01-01")


class SecidCacheTests(unittest.TestCase):
    def setUp(self):
        clear_secid_cache()

    def tearDown(self):
        clear_secid_cache()

    def test_resolve_secid_cached(self):
        with patch(
            "portfolio_news.metrics_moex._lookup_secid",
            return_value=("SBER", "TQBR"),
        ) as lookup:
            a = resolve_secid("sber", "equity")
            b = resolve_secid("SBER", "equity")
            self.assertEqual(a, ("SBER", "TQBR"))
            self.assertEqual(b, ("SBER", "TQBR"))
            self.assertEqual(lookup.call_count, 1)


if __name__ == "__main__":
    unittest.main()
