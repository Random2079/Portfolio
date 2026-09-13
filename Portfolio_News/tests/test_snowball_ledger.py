"""Snowball portfolio CSV ledger (no live MOEX)."""

from __future__ import annotations

import unittest
from datetime import date

from portfolio_news.snowball_ledger import (
    Book,
    apply_event,
    book_as_of,
    calendar_rows_from_journal,
    parse_num,
)


class SnowballLedgerTests(unittest.TestCase):
    def test_parse_num_comma(self):
        self.assertAlmostEqual(parse_num("208750,77290712"), 208750.77290712)
        self.assertAlmostEqual(parse_num("10,01"), 10.01)

    def test_cash_in_and_buy(self):
        book = Book()
        apply_event(
            book,
            {"Event": "CASH_IN", "Symbol": "RUB", "Price": "1", "Quantity": "1000", "FeeTax": "0", "NKD": ""},
        )
        apply_event(
            book,
            {
                "Event": "BUY",
                "Symbol": "SBER",
                "Price": "250",
                "Quantity": "2",
                "FeeTax": "0",
                "NKD": "0",
                "DoNotAdjustCash": "False",
            },
        )
        self.assertEqual(book.qty["SBER"], 2)
        self.assertAlmostEqual(book.cash, 500.0)

    def test_dividend_quantity_is_rubles(self):
        book = Book(cash=0)
        apply_event(
            book,
            {"Event": "DIVIDEND", "Symbol": "SBER", "Price": "33,3", "Quantity": "333", "FeeTax": "43"},
        )
        self.assertAlmostEqual(book.cash, 290.0)

    def test_book_as_of_cuts_future(self):
        events = [
            {"Event": "CASH_IN", "Date": "2026-01-01 00:00:00", "Symbol": "RUB", "Price": "1", "Quantity": "100", "FeeTax": "0", "NKD": ""},
            {"Event": "CASH_IN", "Date": "2026-02-01 00:00:00", "Symbol": "RUB", "Price": "1", "Quantity": "50", "FeeTax": "0", "NKD": ""},
        ]
        self.assertAlmostEqual(book_as_of(events, date(2026, 1, 15)).cash, 100.0)
        self.assertAlmostEqual(book_as_of(events, date(2026, 2, 1)).cash, 150.0)

    def test_journal_rows_div_and_repay(self):
        rows = calendar_rows_from_journal(
            [
                {
                    "Event": "DIVIDEND",
                    "Date": "2025-07-18 00:00:00",
                    "Symbol": "SBER",
                    "Price": "34,84",
                    "Quantity": "696,8",
                    "FeeTax": "91",
                    "Currency": "RUB",
                },
                {
                    "Event": "REPAYMENT",
                    "Date": "2025-04-18 00:00:00",
                    "Symbol": "RU000A1074Q1",
                    "Price": "1000",
                    "Quantity": "2",
                    "FeeTax": "0",
                    "Currency": "RUB",
                },
                {
                    "Event": "DIVIDEND",
                    "Date": "2023-12-04 00:00:00",
                    "Symbol": "WUSH",
                    "Price": "10",
                    "Quantity": "41",
                    "FeeTax": "5",
                    "Currency": "RUB",
                },
            ],
            start=date(2024, 1, 1),
            end=date(2026, 9, 13),
        )
        kinds = {r["kind"] for r in rows}
        self.assertEqual(kinds, {"dividend", "redemption"})
        sber = next(r for r in rows if r["ticker"] == "SBER")
        self.assertAlmostEqual(sber["amount"], 605.8)
        repay = next(r for r in rows if r["kind"] == "redemption")
        self.assertAlmostEqual(repay["amount"], 2000.0)
        self.assertFalse(any(r["ticker"] == "WUSH" for r in rows))


if __name__ == "__main__":
    unittest.main()
