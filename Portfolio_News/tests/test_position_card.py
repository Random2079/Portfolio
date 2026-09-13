"""K4 position card: pure facts + API wiring (no live BCS/MOEX in unit tests)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.api import app, get_db
from portfolio_news.bcs_client import Holding, HoldingsSnapshot, Operation
from portfolio_news.db import Base
from portfolio_news.ops_cache import upsert_operations
from portfolio_news.position_card import (
    build_position_card,
    buy_date_bounds,
    portfolio_paper_value,
)


class PositionCardPureTests(unittest.TestCase):
    def test_buy_date_bounds(self):
        ops = [
            Operation(deal_id="1", ticker="SBER", side="sell", executed_at="2026-02-01"),
            Operation(deal_id="2", ticker="SBER", side="buy", executed_at="2026-01-20T12:00:00"),
            Operation(deal_id="3", ticker="SBER", side="buy", executed_at="2025-06-01"),
            Operation(deal_id="4", ticker="SBER", side="BUY", executed_at="2026-03-01T09:00:00"),
        ]
        first, last, n = buy_date_bounds(ops)
        self.assertEqual(first, "2025-06-01")
        self.assertEqual(last, "2026-03-01T09:00:00")
        self.assertEqual(n, 3)

    def test_portfolio_value_prefers_total(self):
        holdings = [
            Holding(ticker="SBER", market_value=1000),
            Holding(ticker="RUB", market_value=500),
        ]
        self.assertEqual(portfolio_paper_value(holdings, total_value=9000), 9000.0)
        self.assertEqual(portfolio_paper_value(holdings, total_value=None), 1000.0)

    def test_build_card_facts(self):
        h = Holding(
            ticker="SBER",
            name="Сбер",
            quantity=10,
            avg_price=250.0,
            market_price=280.0,
            market_value=2800.0,
            cost_value=2500.0,
            pnl=300.0,
            pnl_pct=12.0,
        )
        other = Holding(ticker="LKOH", market_value=7200.0)
        ops = [
            Operation(
                deal_id="b1",
                ticker="SBER",
                side="buy",
                price=240,
                quantity=5,
                executed_at="2024-01-10T10:00:00",
            ),
            Operation(
                deal_id="b2",
                ticker="SBER",
                side="buy",
                price=260,
                quantity=5,
                executed_at="2025-08-01T11:00:00",
            ),
        ]
        card = build_position_card(
            ticker="SBER",
            holding=h,
            operations=ops,
            holdings=[h, other],
            total_value=10000.0,
        )
        self.assertTrue(card.ok)
        self.assertEqual(card.avg_price, 250.0)
        self.assertEqual(card.current_price, 280.0)
        self.assertEqual(card.current_price_source, "bcs")
        self.assertAlmostEqual(card.avg_vs_price.diff or 0, 30.0)
        self.assertAlmostEqual(card.avg_vs_price.diff_pct or 0, 12.0)
        self.assertEqual(card.unrealized_pnl, 300.0)
        self.assertEqual(card.first_buy, "2024-01-10T10:00:00")
        self.assertEqual(card.last_buy, "2025-08-01T11:00:00")
        self.assertEqual(card.n_buys, 2)
        self.assertAlmostEqual(card.weight_pct or 0, 28.0)

    def test_moex_fallback_price(self):
        h = Holding(
            ticker="SBER",
            quantity=2,
            avg_price=100.0,
            market_price=None,
            market_value=220.0,
            cost_value=200.0,
        )
        card = build_position_card(
            ticker="SBER",
            holding=h,
            operations=[],
            holdings=[h],
            total_value=1000.0,
            moex_last=110.0,
        )
        self.assertEqual(card.current_price, 110.0)
        self.assertEqual(card.current_price_source, "moex")
        self.assertAlmostEqual(card.avg_vs_price.diff or 0, 10.0)

    def test_missing_holding(self):
        card = build_position_card(
            ticker="XXX",
            holding=None,
            operations=[],
            holdings=[],
            total_value=None,
        )
        self.assertFalse(card.ok)
        self.assertIn("XXX", card.error)


class PositionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, future=True)
        self.session = Session()

        def _override():
            try:
                yield self.session
            finally:
                pass

        app.dependency_overrides[get_db] = _override
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        try:
            self.session.close()
        except Exception:  # noqa: BLE001
            pass

    def test_api_position_from_holdings_and_ops(self):
        upsert_operations(
            self.session,
            [
                Operation(
                    deal_id="pb1",
                    ticker="SBER",
                    side="buy",
                    price=200,
                    quantity=10,
                    executed_at="2023-05-01T10:00:00",
                ),
                Operation(
                    deal_id="pb2",
                    ticker="SBER",
                    side="buy",
                    price=220,
                    quantity=5,
                    executed_at="2024-11-15T12:00:00",
                ),
            ],
        )
        h = Holding(
            ticker="SBER",
            name="Сбербанк",
            quantity=15,
            avg_price=210.0,
            market_price=250.0,
            market_value=3750.0,
            cost_value=3150.0,
            pnl=600.0,
            pnl_pct=19.0476,
        )
        snap = HoldingsSnapshot(
            configured=True,
            ok=True,
            total_value=20000.0,
            holdings=[h, Holding(ticker="LKOH", market_value=16250.0)],
        )
        mock_client = MagicMock()
        mock_client.fetch_holdings.return_value = snap
        with patch("portfolio_news.api._bcs", return_value=mock_client):
            r = self.client.get("/api/position/SBER")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["ticker"], "SBER")
        self.assertEqual(data["avg_price"], 210.0)
        self.assertEqual(data["current_price"], 250.0)
        self.assertEqual(data["first_buy"], "2023-05-01T10:00:00")
        self.assertEqual(data["last_buy"], "2024-11-15T12:00:00")
        self.assertEqual(data["n_buys"], 2)
        self.assertAlmostEqual(data["weight_pct"], 18.75)
        self.assertAlmostEqual(data["avg_vs_price"]["diff"], 40.0)
        self.assertNotIn("покупай", str(data).lower())
        self.assertNotIn("продавай", str(data).lower())

    def test_api_not_in_portfolio(self):
        snap = HoldingsSnapshot(configured=True, ok=True, holdings=[])
        mock_client = MagicMock()
        mock_client.fetch_holdings.return_value = snap
        with patch("portfolio_news.api._bcs", return_value=mock_client):
            r = self.client.get("/api/position/ZZZZ")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["ok"])
        self.assertTrue(data["error"])


if __name__ == "__main__":
    unittest.main()
