"""Unit tests for ops filter buckets."""

from __future__ import annotations

import unittest

from portfolio_news.ops_buckets import (
    bond_type,
    fund_bucket,
    rating_bucket,
)


class OpsBucketsTest(unittest.TestCase):
    def test_bond_ofz(self):
        self.assertEqual(bond_type(ticker="SU26238", name="ОФЗ 26238"), "ofz")
        self.assertEqual(bond_type(ticker="SU26238", name="", isin="SU26238RMFS0"), "ofz")

    def test_bond_corp(self):
        self.assertEqual(
            bond_type(ticker="RU000A105A12", name="Бо-001Р", isin="RU000A105A12"),
            "corp",
        )

    def test_fund_buckets(self):
        self.assertEqual(fund_bucket("GOLD"), "gold")
        self.assertEqual(fund_bucket("TMOS"), "equity_rf")
        self.assertEqual(fund_bucket("BCSR"), "mixed")
        self.assertEqual(fund_bucket("XXXX"), "other")

    def test_rating_bucket(self):
        self.assertEqual(rating_bucket("AA+(RU)"), "aa")
        self.assertEqual(rating_bucket("A-"), "a")
        self.assertEqual(rating_bucket("BBB+"), "bbb")
        self.assertEqual(rating_bucket(""), "nr")


if __name__ == "__main__":
    unittest.main()
