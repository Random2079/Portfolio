"""Tests for bond → issuer news query mapping."""

from __future__ import annotations

import unittest

from portfolio_news.bond_issuer import (
    news_query_for_ticker,
    resolve_bond_issuer,
    _guess_issuer_from_name,
)


class BondIssuerTests(unittest.TestCase):
    def test_sber_bond_mapped(self):
        bi = resolve_bond_issuer("RU000A10EF52", name="Сбербанк 001Р-SBER52")
        self.assertIsNotNone(bi)
        assert bi is not None
        self.assertEqual(bi.equity_ticker, "SBER")
        self.assertIn("Сбербанк", bi.search_query())

    def test_x5_finance_mapped(self):
        bi = resolve_bond_issuer("RU000A10AHA3")
        self.assertIsNotNone(bi)
        assert bi is not None
        self.assertEqual(bi.equity_ticker, "X5")

    def test_news_query_bond_uses_issuer(self):
        q = news_query_for_ticker(
            "RU000A10C618",
            kind="bond",
            name="Магнит БО-004Р-08",
            search_query="Магнит БО-004Р-08",
        )
        self.assertIn("Магнит", q)
        self.assertNotIn("004Р", q)

    def test_news_query_equity_unchanged(self):
        q = news_query_for_ticker(
            "SBER", kind="equity", name="Сбербанк", search_query="Сбербанк"
        )
        self.assertEqual(q, "Сбербанк")

    def test_guess_strips_series(self):
        self.assertEqual(_guess_issuer_from_name("Магнит БО-004Р-08"), "Магнит")


if __name__ == "__main__":
    unittest.main()
