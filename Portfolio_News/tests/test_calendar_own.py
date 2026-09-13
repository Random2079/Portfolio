"""K7 payout calendar merge (no live MOEX / BCS)."""

from __future__ import annotations

import unittest

from portfolio_news.calendar_own import apply_quantities, build_events, would_wipe_bonds
from portfolio_news.metrics_moex import AmortRow, CouponRow, DividendRow


class CalendarBuildTests(unittest.TestCase):
    def test_future_only_and_sorted(self):
        divs = [
            DividendRow(ticker_id="SBER", name="Сбер", registryclosedate="2026-10-05", value=35.0),
            DividendRow(ticker_id="SBER", name="Сбер", registryclosedate="2025-05-05", value=33.0),
        ]
        coupons = [
            CouponRow(ticker_id="RU000A0JX0J2", name="Облиг", coupondate="2026-09-20", value=12.5),
        ]
        payload = build_events(
            dividends=divs,
            coupons=coupons,
            qty_by_ticker={"SBER": 10, "RU000A0JX0J2": 4},
            today="2026-09-12",
            ahead_days=180,
        )
        self.assertTrue(payload.ok)
        self.assertEqual(
            [e.pay_date for e in payload.events],
            ["2025-05-05", "2026-09-20", "2026-10-05"],
        )
        self.assertEqual([e.kind for e in payload.events], ["dividend", "coupon", "dividend"])

    def test_amount_uses_quantity(self):
        payload = build_events(
            dividends=[DividendRow(ticker_id="LKOH", name="Лук", registryclosedate="2026-11-01", value=500.0)],
            coupons=[],
            qty_by_ticker={"LKOH": 3},
            today="2026-09-12",
            ahead_days=365,
        )
        self.assertEqual(payload.events[0].amount, 1500.0)
        self.assertEqual(payload.total_amount, 1500.0)

    def test_unknown_quantity_keeps_event(self):
        payload = build_events(
            dividends=[DividendRow(ticker_id="MOEX", name="Биржа", registryclosedate="2026-10-01", value=20.0)],
            coupons=[],
            qty_by_ticker={},
            today="2026-09-12",
            ahead_days=180,
        )
        self.assertEqual(len(payload.events), 1)
        self.assertIsNone(payload.events[0].amount)
        self.assertIsNone(payload.total_amount)

    def test_error_rows_and_out_of_window_skipped(self):
        payload = build_events(
            dividends=[DividendRow(ticker_id="X", name="X", error="boom")],
            coupons=[CouponRow(ticker_id="Y", name="Y", coupondate="2030-01-01", value=1.0)],
            qty_by_ticker={"X": 1, "Y": 1},
            today="2026-09-12",
            ahead_days=90,
        )
        self.assertEqual(payload.events, [])
        self.assertEqual(payload.missing, 2)

    def test_status_and_redemption(self):
        payload = build_events(
            dividends=[
                DividendRow(ticker_id="SBER", name="Сбер", registryclosedate="2026-10-05", value=35.0),
                DividendRow(ticker_id="SBER", name="Сбер", registryclosedate="2026-08-01", value=30.0),
            ],
            coupons=[
                CouponRow(ticker_id="BOND", name="Облиг", coupondate="2026-09-20", value=10.0),
            ],
            redemptions=[
                AmortRow(ticker_id="BOND", name="Облиг", amortdate="2026-12-01", value=1000.0),
            ],
            qty_by_ticker={"SBER": 2, "BOND": 1},
            today="2026-09-12",
            ahead_days=180,
            back_days=60,
        )
        by = {(e.kind, e.pay_date): e for e in payload.events}
        self.assertEqual(by[("dividend", "2026-08-01")].status, "paid")
        self.assertEqual(by[("dividend", "2026-10-05")].status, "announced")
        self.assertEqual(by[("coupon", "2026-09-20")].status, "upcoming")
        self.assertEqual(by[("redemption", "2026-12-01")].status, "upcoming")
        self.assertEqual(by[("redemption", "2026-12-01")].amount, 1000.0)

    def test_refuse_wipe_coupons(self):
        rich = {
            "events": [
                {"kind": "coupon", "ticker": "OFZ"},
                {"kind": "redemption", "ticker": "OFZ"},
                {"kind": "dividend", "ticker": "SBER"},
            ]
        }
        thin = {"events": [{"kind": "dividend", "ticker": "SBER"}]}
        self.assertTrue(would_wipe_bonds(rich, thin))
        self.assertFalse(would_wipe_bonds(thin, rich))
        self.assertFalse(would_wipe_bonds(None, thin))
        self.assertFalse(would_wipe_bonds(rich, rich))

    def test_apply_quantities_fills_amount_and_filters(self):
        raw = {
            "ok": True,
            "today": "2026-09-12",
            "ahead_days": 365,
            "events": [
                {
                    "ticker": "RU000A107UU5",
                    "kind": "coupon",
                    "pay_date": "2026-10-01",
                    "per_unit": 13.8,
                    "quantity": None,
                    "amount": None,
                },
                {
                    "ticker": "ALIEN",
                    "kind": "coupon",
                    "pay_date": "2026-10-02",
                    "per_unit": 10.0,
                    "quantity": None,
                    "amount": None,
                },
            ],
        }
        out = apply_quantities(raw, {"RU000A107UU5": 2.0}, only_own=True)
        self.assertEqual(len(out["events"]), 1)
        ev = out["events"][0]
        self.assertEqual(ev["quantity"], 2.0)
        self.assertEqual(ev["amount"], 27.6)  # was None, filled from per×qty
        self.assertEqual(out["total_amount"], 27.6)
        self.assertIsNotNone(out["per_month"])
        self.assertIsNotNone(out["per_day"])
        self.assertEqual(out["months"][0]["coupon"], 27.6)

    def test_apply_keeps_sold_ticker_if_journal_amount(self):
        raw = {
            "ok": True,
            "today": "2026-09-12",
            "ahead_days": 365,
            "events": [
                {
                    "ticker": "WUSH",
                    "kind": "dividend",
                    "pay_date": "2024-12-06",
                    "amount": 27.65,
                }
            ],
        }
        out = apply_quantities(raw, {"SBER": 23.0}, only_own=True)
        self.assertEqual(len(out["events"]), 1)
        self.assertAlmostEqual(out["events"][0]["amount"], 27.65)

    def test_apply_keeps_journal_amount_without_per_unit(self):
        raw = {
            "ok": True,
            "today": "2026-09-12",
            "ahead_days": 365,
            "events": [
                {
                    "ticker": "SBER",
                    "kind": "dividend",
                    "pay_date": "2026-02-01",
                    "per_unit": None,
                    "quantity": None,
                    "amount": 605.8,
                }
            ],
        }
        out = apply_quantities(raw, {"SBER": 23.0}, only_own=True)
        self.assertAlmostEqual(out["events"][0]["amount"], 605.8)
        self.assertEqual(out["events"][0]["quantity"], 23.0)


if __name__ == "__main__":
    unittest.main()
