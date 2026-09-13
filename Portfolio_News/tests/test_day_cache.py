"""SQLite day snapshot roundtrip (no live MOEX)."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.day_attribution import DayAttribution, DayContributor
from portfolio_news.day_cache import load_day_snapshot, save_day_snapshot
from portfolio_news.db import Base


class DayCacheTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, future=True)

    def test_save_load(self):
        attr = DayAttribution(
            ok=True,
            day_rub=12.5,
            day_pct=0.1,
            missing=2,
            top=[
                DayContributor(ticker="SBER", day_rub=10.0, day_pct=1.0),
                DayContributor(ticker="LKOH", day_rub=2.5, day_pct=0.2),
            ],
            fetched_at=1000.0,
        )
        with self.Session() as db:
            save_day_snapshot(db, attr)
            loaded = load_day_snapshot(db)
        self.assertIsNotNone(loaded)
        got, ts = loaded
        self.assertTrue(got.ok)
        self.assertEqual(got.day_rub, 12.5)
        self.assertEqual(len(got.top), 2)
        self.assertEqual(got.top[0].ticker, "SBER")
        self.assertGreater(ts, 0)


if __name__ == "__main__":
    unittest.main()
