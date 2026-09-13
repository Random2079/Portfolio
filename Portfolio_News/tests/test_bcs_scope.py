"""Unit tests for K5 BCS news/MOEX scope (no live BCS)."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from portfolio_news.bcs_client import Holding
from portfolio_news.bcs_scope import (
    ensure_tickers_from_holdings,
    filter_ticker_id_to_scope,
    holdings_to_ticker_items,
    ticker_ids_from_holdings,
)
from portfolio_news.db import Base, Ticker
from portfolio_news.poller import select_tickers


class BcsScopeTests(unittest.TestCase):
    def test_ticker_ids_skips_cash_and_dupes(self):
        holdings = [
            Holding(ticker="SBER", asset_class="stock", name="Сбер"),
            Holding(ticker="SBER", asset_class="stock"),
            Holding(ticker="", asset_class="cash", name="RUB"),
            Holding(ticker="BCSR", asset_class="fund", name="БКС Рубль"),
            Holding(sec_code="LKOH", asset_class="stock"),
        ]
        self.assertEqual(ticker_ids_from_holdings(holdings), ["SBER", "BCSR", "LKOH"])

    def test_holdings_to_ticker_items_kinds(self):
        holdings = [
            Holding(ticker="SBER", asset_class="stock", name="Сбер", isin="RU0009029540"),
            Holding(ticker="BCSR", asset_class="fund", name="Фонд"),
            Holding(ticker="RU000A0JX0J2", asset_class="bond", name="Облиг"),
        ]
        items = holdings_to_ticker_items(holdings)
        by_id = {i["id"]: i for i in items}
        self.assertEqual(by_id["SBER"]["kind"], "equity")
        self.assertEqual(by_id["BCSR"]["kind"], "fund")
        self.assertEqual(by_id["RU000A0JX0J2"]["kind"], "bond")

    def test_ensure_and_select_ordered(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        with Session() as session:
            # noise ticker not in portfolio
            session.add(
                Ticker(id="NOISE", name="Noise", kind="equity", search_query="Noise")
            )
            session.commit()
            holdings = [
                Holding(ticker="BCSR", asset_class="fund", name="Фонд"),
                Holding(ticker="SBER", asset_class="stock", name="Сбер"),
            ]
            ids = ensure_tickers_from_holdings(session, holdings)
            self.assertEqual(ids, ["BCSR", "SBER"])
            rows = select_tickers(session, ids=ids)
            self.assertEqual([t.id for t in rows], ["BCSR", "SBER"])
            self.assertNotIn("NOISE", [t.id for t in rows])

    def test_filter_ticker_not_in_scope(self):
        tid, err = filter_ticker_id_to_scope("GAZP", ["SBER", "LKOH"])
        self.assertIsNone(tid)
        self.assertIn("ticker_not_in_bcs", err)
        tid2, err2 = filter_ticker_id_to_scope("SBER", ["SBER", "LKOH"])
        self.assertEqual(tid2, "SBER")
        self.assertEqual(err2, "")


if __name__ == "__main__":
    unittest.main()
