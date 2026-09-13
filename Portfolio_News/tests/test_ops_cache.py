"""Tests for K2 SQLite operations cache."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from portfolio_news.bcs_client import Operation
from portfolio_news.db import Base
from portfolio_news.ops_cache import (
    list_cached_operations,
    stable_deal_id,
    upsert_operations,
)


class OpsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, future=True)

    def test_upsert_dedupes_by_deal_id(self):
        op = Operation(
            deal_id="d1",
            ticker="SBER",
            side="buy",
            quantity=10,
            price=250,
            volume=2500,
            executed_at="2026-09-01T10:00:00",
        )
        with self.Session() as s:
            self.assertEqual(upsert_operations(s, [op, op]), 1)
            # second call updates, no new insert
            op.price = 251
            self.assertEqual(upsert_operations(s, [op]), 0)
            rows = list_cached_operations(s)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].price, 251)

    def test_fingerprint_when_no_deal_id(self):
        a = Operation(ticker="SBER", side="buy", quantity=1, price=100, executed_at="t1")
        b = Operation(ticker="SBER", side="buy", quantity=1, price=100, executed_at="t1")
        c = Operation(ticker="SBER", side="sell", quantity=1, price=100, executed_at="t1")
        self.assertEqual(stable_deal_id(a), stable_deal_id(b))
        self.assertNotEqual(stable_deal_id(a), stable_deal_id(c))
        with self.Session() as s:
            upsert_operations(s, [a, b, c])
            self.assertEqual(len(list_cached_operations(s)), 2)

    def test_filter_ticker(self):
        with self.Session() as s:
            upsert_operations(
                s,
                [
                    Operation(deal_id="1", ticker="SBER", side="buy", executed_at="2026-01-02"),
                    Operation(deal_id="2", ticker="LKOH", side="buy", executed_at="2026-01-03"),
                ],
            )
            only = list_cached_operations(s, ticker="sber", limit=10)
            self.assertEqual(len(only), 1)
            self.assertEqual(only[0].ticker, "SBER")


if __name__ == "__main__":
    unittest.main()
