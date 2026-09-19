"""Unit tests for BCS portfolio parsing (no live BCS)."""

from __future__ import annotations

import unittest

from portfolio_news.bcs_client import (
    Holding,
    HoldingsSnapshot,
    match_holding,
    friendly_bcs_error,
    holdings_snapshot_from_dict,
    _parse_portfolio,
    _parse_summary,
    _parse_deals,
    _merge_limits,
    _parse_money_limits_cash_rub,
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

    def test_money_limits_cash_rub(self):
        limits = {
            "moneyLimits": [
                {
                    "currencyCode": "RUB",
                    "instrumentType": "MONEY",
                    "quantity": {"type": "T365", "value": 791.27},
                },
                {
                    "currencyCode": "USD",
                    "instrumentType": "MONEY",
                    "quantity": {"type": "T365", "value": 10.0},
                },
            ]
        }
        self.assertAlmostEqual(_parse_money_limits_cash_rub(limits) or 0, 791.27)

    def test_currency_row_is_cash(self):
        raw = [
            {
                "ticker": "RUB",
                "displayName": "RUB",
                "instrumentType": "CURRENCY",
                "quantity": 791.27,
                "currentValue": 791.27,
                "currentValueRub": 791.27,
                "currency": "RUB",
                "type": "depoLimit",
            }
        ]
        rows = _parse_portfolio(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].asset_class, "cash")
        self.assertAlmostEqual(rows[0].market_value or 0, 791.27)

    def test_match_holding(self):
        hs = [
            Holding(ticker="SBER", isin="RU0009029540", quantity=1),
            Holding(ticker="", isin="RU000A10EF52", sec_code="RU000A10EF52", quantity=2),
        ]
        self.assertEqual(match_holding(hs, ticker_id="SBER").isin, "RU0009029540")
        self.assertEqual(match_holding(hs, isin="RU000A10EF52").quantity, 2)
        self.assertIsNone(match_holding(hs, ticker_id="NOPE"))

    def test_friendly_dns_and_timeout(self):
        dns = friendly_bcs_error(
            Exception("Failed to resolve 'be.broker.ru' ([Errno 11001] getaddrinfo failed)")
        )
        self.assertIn("DNS", dns)
        to = friendly_bcs_error(Exception("Connection to be.broker.ru timed out. (connect timeout=30)"))
        self.assertIn("таймаут", to.lower())


class ParseDealsTests(unittest.TestCase):
    def test_canonical_deals(self):
        raw = {
            "deals": [
                {
                    "dealId": "d1",
                    "ticker": "SBER",
                    "classCode": "TQBR",
                    "side": "buy",
                    "quantity": 10,
                    "price": 250.5,
                    "volume": 2505.0,
                    "commission": 1.2,
                    "currency": "RUB",
                    "executedAt": "2026-09-01T10:15:00Z",
                },
                {
                    "dealId": "d0",
                    "ticker": "GAZP",
                    "side": "sell",
                    "quantity": 5,
                    "price": 100,
                    "executedAt": "2026-08-01T09:00:00Z",
                },
            ]
        }
        ops = _parse_deals(raw)
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0].ticker, "SBER")
        self.assertEqual(ops[0].side, "buy")
        self.assertEqual(ops[0].quantity, 10)
        self.assertEqual(ops[0].price, 250.5)
        self.assertEqual(ops[0].volume, 2505.0)
        self.assertEqual(ops[1].side, "sell")
        self.assertAlmostEqual(ops[1].volume or 0, 500.0)

    def test_nested_aliases_and_side(self):
        raw = {
            "data": {
                "items": [
                    {
                        "id": "x",
                        "secCode": "LKOH",
                        "buySell": "S",
                        "qty": 2,
                        "price": 7000,
                        "dateTime": "2026-07-15T12:00:00",
                    }
                ]
            }
        }
        ops = _parse_deals(raw)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].ticker, "LKOH")
        self.assertEqual(ops[0].side, "sell")
        self.assertAlmostEqual(ops[0].volume or 0, 14000.0)


    def test_trades_records_shape(self):
        raw = {
            "records": [
                {
                    "tradeId": "t9",
                    "ticker": "SBER",
                    "side": 1,
                    "quantity": 3,
                    "price": 280,
                    "tradeDateTime": "2026-02-01T11:00:00+03:00",
                }
            ],
            "totalRecords": 1,
        }
        ops = _parse_deals(raw)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].ticker, "SBER")
        self.assertEqual(ops[0].side, "buy")
        self.assertEqual(ops[0].deal_id, "t9")
        self.assertIn("2026-02-01", ops[0].executed_at)

    def test_bcs_trade_details_live_shape(self):
        """Shape from trade-api-bff-trade-details /trades/search."""
        raw = {
            "records": [
                {
                    "classCode": "TQCB",
                    "dealType": 1,
                    "orderNum": 84003390478,
                    "price": 98.08,
                    "priceCurrency": "RUB",
                    "settlementCurrency": "RUB",
                    "side": "1",
                    "ticker": "RU000A10C8C0",
                    "tradeDateTime": "2026-09-03T16:25:43Z",
                    "tradeNum": 17622906858,
                    "tradeQuantity": 1.0,
                    "tradeQuantityLots": 1.0,
                    "volume": 984.62,
                }
            ],
            "totalPages": 1,
            "totalRecords": 1,
        }
        ops = _parse_deals(raw)
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op.deal_id, "17622906858")
        self.assertEqual(op.ticker, "RU000A10C8C0")
        self.assertEqual(op.class_code, "TQCB")
        self.assertEqual(op.side, "buy")
        self.assertEqual(op.quantity, 1.0)
        self.assertEqual(op.price, 98.08)
        self.assertEqual(op.volume, 984.62)
        self.assertEqual(op.currency, "RUB")
        self.assertIn("2026-09-03", op.executed_at)


    def test_bcs_native_list_dedupes(self):
        """Live BCS shape: flat moneyLimit/depoLimit list, often 4× duplicates."""
        row = {
            "type": "depoLimit",
            "ticker": "SBER",
            "board": "TQBR",
            "displayName": "Сбербанк",
            "quantity": 23,
            "currentPrice": 280,
            "currentValue": 6440,
            "balancePrice": 250,
            "balanceValue": 5750,
            "currency": "RUB",
        }
        bond = {
            "type": "depoLimit",
            "ticker": "RU000A107RZ0",
            "board": "TQCB",
            "displayName": "Самолет БО-П13",
            "quantity": 3,
            "currentPrice": 955,
            "currentValue": 2865,
            "currency": "RUB",
        }
        cash = {
            "type": "moneyLimit",
            "ticker": "RUB",
            "displayName": "RUB",
            "quantity": 791.27,
            "currentValue": 791.27,
            "currency": "RUB",
        }
        raw = [cash, row, bond] * 4
        rows = _parse_portfolio(raw)
        self.assertEqual(len(rows), 3)
        by = {h.ticker: h for h in rows}
        self.assertEqual(by["RUB"].quantity, 791.27)
        self.assertEqual(by["SBER"].class_code, "TQBR")
        self.assertEqual(by["SBER"].name, "Сбербанк")
        self.assertEqual(by["RU000A107RZ0"].class_code, "TQCB")
        self.assertEqual(by["RU000A107RZ0"].isin, "RU000A107RZ0")
        self.assertAlmostEqual(by["SBER"].market_value or 0, 6440)

    def test_holdings_last_good_roundtrip(self):
        snap = HoldingsSnapshot(
            configured=True,
            ok=True,
            total_value=1000.0,
            holdings=[Holding(ticker="SBER", quantity=2, market_value=500.0)],
        )
        restored = holdings_snapshot_from_dict(snap.to_dict())
        self.assertTrue(restored.stale)
        self.assertEqual(restored.total_value, 1000.0)
        self.assertEqual(restored.holdings[0].ticker, "SBER")
        self.assertEqual(restored.holdings[0].quantity, 2)


if __name__ == "__main__":
    unittest.main()