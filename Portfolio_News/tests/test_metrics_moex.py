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

    def test_parse_candles(self):
        from portfolio_news.metrics_moex import candle_to_dict, parse_candle_rows

        rows = parse_candle_rows(
            [
                {
                    "begin": "2026-01-10 00:00:00",
                    "end": "2026-01-10 23:59:59",
                    "open": 100,
                    "close": 105.5,
                    "high": 106,
                    "low": 99,
                    "volume": 1000,
                },
                {"begin": "", "close": None},
                {"TRADEDATE": "2026-01-11", "CLOSE": 107},
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].close, 105.5)
        self.assertEqual(rows[0].begin, "2026-01-10 00:00:00")
        self.assertEqual(rows[1].close, 107.0)
        self.assertEqual(rows[1].begin, "2026-01-11")
        d = candle_to_dict(rows[0])
        self.assertEqual(d["close"], 105.5)
        self.assertIn("begin", d)

    def test_parse_candles_limit(self):
        from portfolio_news.metrics_moex import parse_candle_rows

        raw = [{"begin": f"2026-01-{i:02d}", "close": float(i)} for i in range(1, 20)]
        rows = parse_candle_rows(raw, limit=5)
        self.assertEqual(len(rows), 5)


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


class SecidPickTests(unittest.TestCase):
    """Board/SECID pick for ETF vs iNAV twins — no live ISS."""

    def test_bcsr_skips_inav_twin(self):
        from portfolio_news.metrics_moex import _pick_secid_board

        secs = [
            {
                "secid": "BCSRA",
                "primary_boardid": "INAV",
                "type": "stock_index_ie",
                "group": "stock_index",
                "isin": None,
            },
            {
                "secid": "BCSR",
                "primary_boardid": "TQBR",
                "type": "exchange_ppif",
                "group": "stock_ppif",
                "isin": "RU000A10A0N6",
            },
        ]
        self.assertEqual(
            _pick_secid_board(secs, ticker_id="BCSR", kind="fund"),
            ("BCSR", "TQBR"),
        )
        self.assertEqual(
            _pick_secid_board(secs, ticker_id="BCSR", kind="equity"),
            ("BCSR", "TQBR"),
        )

    def test_gold_isin_beats_index_noise(self):
        from portfolio_news.metrics_moex import _pick_secid_board

        by_ticker = [
            {
                "secid": "GZGOLD",
                "primary_boardid": "INPF",
                "type": "stock_index_pf",
                "group": "stock_index",
                "isin": None,
            },
            {
                "secid": "GOLDO",
                "primary_boardid": "INAV",
                "type": "stock_index_ie",
                "group": "stock_index",
                "isin": None,
            },
        ]
        self.assertIsNone(
            _pick_secid_board(by_ticker, ticker_id="GOLD", kind="fund")
        )
        by_isin = [
            {
                "secid": "GOLD",
                "primary_boardid": "TQBR",
                "type": "exchange_ppif",
                "group": "stock_ppif",
                "isin": "RU000A101NZ2",
            },
            {
                "secid": "VTBG",
                "primary_boardid": "TQTF",
                "type": "exchange_ppif",
                "group": "stock_ppif",
                "isin": "RU000A101NZ2",
            },
        ]
        self.assertEqual(
            _pick_secid_board(
                by_isin,
                ticker_id="GOLD",
                kind="fund",
                isin="RU000A101NZ2",
            ),
            ("GOLD", "TQBR"),
        )

    def test_lookup_falls_back_to_isin_query(self):
        from portfolio_news.metrics_moex import _lookup_secid, clear_secid_cache

        clear_secid_cache()
        noise = {
            "securities": {
                "columns": ["secid", "primary_boardid", "type", "group", "isin"],
                "data": [
                    ["GZGOLD", "INPF", "stock_index_pf", "stock_index", None],
                ],
            }
        }
        hit = {
            "securities": {
                "columns": ["secid", "primary_boardid", "type", "group", "isin"],
                "data": [
                    ["GOLD", "TQBR", "exchange_ppif", "stock_ppif", "RU000A101NZ2"],
                ],
            }
        }

        def fake_iss(path, params=None):
            q = (params or {}).get("q", "")
            if q == "GOLD":
                return noise
            if q == "RU000A101NZ2":
                return hit
            return {"securities": {"columns": [], "data": []}}

        with patch("portfolio_news.metrics_moex._iss_get", side_effect=fake_iss):
            self.assertEqual(
                _lookup_secid("GOLD", "fund", isin="RU000A101NZ2"),
                ("GOLD", "TQBR"),
            )

    def test_candle_board_candidates_skip_inav(self):
        from portfolio_news.metrics_moex import _candle_board_candidates

        c = _candle_board_candidates("INAV", "fund")
        self.assertNotIn("INAV", c)
        self.assertEqual(c[0], "TQTF")
        self.assertIn("", c)


if __name__ == "__main__":
    unittest.main()
