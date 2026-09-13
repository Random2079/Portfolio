"""K6 capital day upsert / list (no live BCS)."""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from portfolio_news.capital_cache import (
    list_capital_days,
    maybe_record_from_holdings,
    upsert_capital_day,
)
from portfolio_news.db import Base


class CapitalCacheTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def test_upsert_same_day_overwrites(self):
        with self.Session() as db:
            upsert_capital_day(db, total_value=100.0, day="2026-09-10")
            upsert_capital_day(db, total_value=110.0, day="2026-09-10")
            rows = list_capital_days(db, days=900)
            hit = [r for r in rows if r["day"] == "2026-09-10"]
            self.assertEqual(len(hit), 1)
            self.assertEqual(hit[0]["total_value"], 110.0)

    def test_list_ordered(self):
        with self.Session() as db:
            upsert_capital_day(db, total_value=1.0, day="2026-09-01")
            upsert_capital_day(db, total_value=2.0, day="2026-09-03")
            upsert_capital_day(db, total_value=3.0, day="2026-09-02")
            rows = list_capital_days(db, days=900)
            days = [r["day"] for r in rows if r["day"].startswith("2026-09-0")]
            self.assertEqual(days, ["2026-09-01", "2026-09-02", "2026-09-03"])

    def test_maybe_skips_bad(self):
        with self.Session() as db:
            self.assertIsNone(maybe_record_from_holdings(db, total_value=None, ok=True))
            self.assertIsNone(maybe_record_from_holdings(db, total_value=100.0, ok=False))
            self.assertIsNone(maybe_record_from_holdings(db, total_value=0.0, ok=True))
            row = maybe_record_from_holdings(db, total_value=50.0, ok=True)
            self.assertIsNotNone(row)
            self.assertEqual(row.total_value, 50.0)

    def test_bootstrap_from_day_snapshot(self):
        import json
        import time

        from portfolio_news.db import DaySnapshot

        with self.Session() as db:
            db.add(
                DaySnapshot(
                    id=1,
                    payload_json=json.dumps(
                        {"ok": True, "total_value": 180110.84, "top": []}
                    ),
                    updated_at=time.time(),
                    ok=1,
                )
            )
            db.commit()
            rows = list_capital_days(db, days=90)
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0]["total_value"], 180110.84, places=1)


if __name__ == "__main__":
    unittest.main()
