"""K3 chart helpers: candles parser wiring + markers from ops cache (no live MOEX)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.api import app, get_db
from portfolio_news.bcs_client import Operation
from portfolio_news.db import Base
from portfolio_news.metrics_moex import CandlePoint
from portfolio_news.ops_cache import upsert_operations


class ChartApiTests(unittest.TestCase):
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

    def test_chart_combines_candles_and_markers(self):
        upsert_operations(
            self.session,
            [
                Operation(
                    deal_id="b1",
                    ticker="SBER",
                    side="buy",
                    price=250.0,
                    quantity=10,
                    executed_at="2026-01-15T10:00:00",
                ),
                Operation(
                    deal_id="s1",
                    ticker="SBER",
                    side="sell",
                    price=260.0,
                    quantity=2,
                    executed_at="2026-01-20T12:00:00",
                ),
                Operation(
                    deal_id="other",
                    ticker="LKOH",
                    side="buy",
                    price=7000,
                    executed_at="2026-01-15T10:00:00",
                ),
            ],
        )
        fake = [
            CandlePoint(begin="2026-08-15 00:00:00", close=251.0),
            CandlePoint(begin="2026-09-20 00:00:00", close=259.0),
        ]
        with patch(
            "portfolio_news.ops_history.journal_rows",
            return_value=[],
        ), patch(
            "portfolio_news.chart_cache.fetch_candles",
            return_value=(fake, "SBER", "TQBR", ""),
        ):
            r = self.client.get("/api/chart/SBER?days=90&kind=equity")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["ticker"], "SBER")
        self.assertEqual(data["n_candles"], 2)
        self.assertEqual(data["n_markers"], 2)
        sides = {m["side"] for m in data["markers"]}
        self.assertEqual(sides, {"buy", "sell"})
        self.assertEqual(data["board"], "TQBR")

    def test_chart_empty_candles_not_ok(self):
        with patch(
            "portfolio_news.chart_cache.fetch_candles",
            return_value=([], "XXX", "", "boom"),
        ):
            r = self.client.get("/api/chart/XXX?kind=equity")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["ok"])
        self.assertTrue(data["error"])

    def test_chart_fund_kind_passes_isin_to_moex(self):
        from portfolio_news.db import Ticker

        self.session.add(
            Ticker(
                id="BCSR",
                name="БПИФ БКС Индекс Росс рынка",
                isin="RU000A10A0N6",
                kind="fund",
            )
        )
        self.session.commit()
        fake = [CandlePoint(begin="2026-08-15 00:00:00", close=10.0)]
        with patch(
            "portfolio_news.chart_cache.fetch_candles",
            return_value=(fake, "BCSR", "TQBR", ""),
        ) as fc:
            r = self.client.get("/api/chart/BCSR?days=90")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["kind"], "fund")
        self.assertEqual(fc.call_args.kwargs.get("isin"), "RU000A10A0N6")
        self.assertEqual(fc.call_args.args[1], "fund")

    def test_chart_fund_kind_from_holdings_over_equity_db(self):
        """tickers row may say equity; BCS asset_class=fund wins."""
        from portfolio_news.bcs_client import Holding, HoldingsSnapshot
        from portfolio_news.db import Ticker

        self.session.add(
            Ticker(id="BCSR", name="Индекс Мосбиржи", isin="", kind="equity")
        )
        self.session.commit()
        snap = HoldingsSnapshot(
            configured=True,
            ok=True,
            holdings=[
                Holding(
                    ticker="BCSR",
                    name="БПИФ",
                    isin="RU000A10A0N6",
                    asset_class="fund",
                    quantity=1,
                    market_value=100,
                )
            ],
        )
        fake = [CandlePoint(begin="2026-08-15 00:00:00", close=10.0)]
        with patch(
            "portfolio_news.bcs_client.load_holdings_last_good",
            return_value=snap,
        ), patch(
            "portfolio_news.chart_cache.fetch_candles",
            return_value=(fake, "BCSR", "TQBR", ""),
        ) as fc:
            r = self.client.get("/api/chart/BCSR?days=90")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["kind"], "fund")
        self.assertEqual(fc.call_args.args[1], "fund")
        self.assertEqual(fc.call_args.kwargs.get("isin"), "RU000A10A0N6")

    def test_chart_bond_candles_scaled_to_rub(self):
        """MOEX % of par → ₽/шт so LWC scale matches avg/markers."""
        fake = [
            CandlePoint(
                begin="2026-08-15 00:00:00",
                open=87.0,
                high=89.0,
                low=86.5,
                close=88.0,
                volume=100,
            )
        ]
        with patch(
            "portfolio_news.ops_history.journal_rows",
            return_value=[],
        ), patch(
            "portfolio_news.chart_cache.fetch_candles",
            return_value=(fake, "RU000A107RZ0", "TQCB", ""),
        ):
            r = self.client.get("/api/chart/RU000A107RZ0?kind=bond&days=90")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["kind"], "bond")
        self.assertEqual(data["price_unit"], "rub_per_bond")
        c0 = data["candles"][0]
        self.assertAlmostEqual(c0["close"], 880.0)
        self.assertAlmostEqual(c0["open"], 870.0)
        self.assertAlmostEqual(c0["high"], 890.0)
        self.assertEqual(c0["volume"], 100)


if __name__ == "__main__":
    unittest.main()
