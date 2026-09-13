"""Weekly capital replay from deals (no live MOEX)."""

from __future__ import annotations

import unittest
from datetime import date

from portfolio_news.bcs_client import Operation
from portfolio_news.capital_replay import (
    build_weekly_points,
    last_close_on_or_before,
    op_local_day,
    qty_as_of,
    unit_rub,
    week_fridays,
)


class CapitalReplayTests(unittest.TestCase):
    def test_op_day_utc_to_yekat(self):
        self.assertEqual(op_local_day("2026-09-03T16:25:43Z"), date(2026, 9, 3))
        self.assertEqual(op_local_day("2026-01-27T08:00:00Z"), date(2026, 1, 27))

    def test_qty_walk(self):
        ops = [
            Operation(ticker="SBER", side="buy", quantity=10, executed_at="2026-02-01T10:00:00Z"),
            Operation(ticker="SBER", side="sell", quantity=3, executed_at="2026-03-01T10:00:00Z"),
            Operation(ticker="SBER", side="buy", quantity=1, executed_at="2026-06-01T10:00:00Z"),
        ]
        self.assertEqual(qty_as_of(ops, date(2026, 1, 31)), {})
        self.assertEqual(qty_as_of(ops, date(2026, 2, 6))["SBER"], 10)
        self.assertEqual(qty_as_of(ops, date(2026, 3, 6))["SBER"], 7)
        self.assertEqual(qty_as_of(ops, date(2026, 6, 6))["SBER"], 8)

    def test_sell_without_prior_buy_ignored(self):
        ops = [
            Operation(ticker="UGLD", side="sell", quantity=4000, executed_at="2026-01-28T10:00:00Z"),
            Operation(ticker="SBER", side="buy", quantity=1, executed_at="2026-01-28T11:00:00Z"),
        ]
        q = qty_as_of(ops, date(2026, 1, 30))
        self.assertNotIn("UGLD", q)
        self.assertEqual(q["SBER"], 1)

    def test_week_fridays(self):
        fr = week_fridays(date(2026, 1, 26), date(2026, 2, 13))
        self.assertEqual(fr, [date(2026, 1, 30), date(2026, 2, 6), date(2026, 2, 13)])

    def test_bond_percent_to_rub(self):
        self.assertAlmostEqual(unit_rub(98.08, "bond"), 980.8)
        self.assertAlmostEqual(unit_rub(250.0, "equity"), 250.0)

    def test_weekly_points_from_closes(self):
        ops = [
            Operation(ticker="SBER", side="buy", quantity=2, executed_at="2026-01-27T10:00:00Z"),
        ]
        closes = {
            "SBER": [
                (date(2026, 1, 27), 300.0),
                (date(2026, 1, 30), 310.0),
                (date(2026, 2, 6), 320.0),
            ]
        }
        pts = build_weekly_points(
            ops,
            closes,
            {"SBER": "equity"},
            start=date(2026, 1, 26),
            end=date(2026, 2, 8),
        )
        days = [d for d, _ in pts]
        self.assertIn("2026-01-30", days)
        self.assertIn("2026-02-06", days)
        by = dict(pts)
        self.assertAlmostEqual(by["2026-01-30"], 620.0)
        self.assertAlmostEqual(by["2026-02-06"], 640.0)

    def test_last_close(self):
        series = [(date(2026, 1, 29), 10.0), (date(2026, 1, 30), 11.0)]
        self.assertEqual(last_close_on_or_before(series, date(2026, 1, 29)), 10.0)
        self.assertEqual(last_close_on_or_before(series, date(2026, 1, 31)), 11.0)
        self.assertIsNone(last_close_on_or_before(series, date(2026, 1, 20)))


if __name__ == "__main__":
    unittest.main()
