"""Coverage report helpers (ticker × source matrix)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from portfolio_news.coverage_report import (
    build_coverage_report,
    format_coverage_report,
    window_start,
)
from portfolio_news.db import Base, NewsItem, Ticker

_TZ = timezone(timedelta(hours=5))


class CoverageReportTests(unittest.TestCase):
    def setUp(self) -> None:
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        self.Session = sessionmaker(bind=eng)
        with self.Session() as s:
            s.add_all(
                [
                    Ticker(id="SBER", name="Сбер", kind="equity", search_query="Сбербанк"),
                    Ticker(id="X5", name="X5", kind="equity", search_query="ИКС 5"),
                    Ticker(id="BOND1", name="Облиг", kind="bond", search_query="Облиг"),
                ]
            )
            now = datetime(2026, 10, 3, 12, 0, tzinfo=_TZ).replace(tzinfo=None)
            s.add_all(
                [
                    NewsItem(
                        ticker_id="SBER",
                        title="Сбер дивиденды",
                        url="https://example.com/1",
                        source="google_news_ru",
                        published_at=now,
                        created_at=now,
                    ),
                    NewsItem(
                        ticker_id="SBER",
                        title="Сбер ещё",
                        url="https://example.com/2",
                        source="pulse_news_ticker",
                        published_at=now - timedelta(days=2),
                        created_at=now,
                    ),
                    NewsItem(
                        ticker_id="X5",
                        title="старое",
                        url="https://example.com/3",
                        source="smartlab",
                        published_at=now - timedelta(days=40),
                        created_at=now - timedelta(days=40),
                    ),
                ]
            )
            s.commit()

    def test_window_start_today(self):
        now = datetime(2026, 10, 3, 20, 0, tzinfo=_TZ)
        self.assertEqual(window_start("today", now=now).date().isoformat(), "2026-10-03")
        self.assertEqual(window_start("7d", now=now).date().isoformat(), "2026-09-26")

    def test_7d_holes(self):
        now = datetime(2026, 10, 3, 20, 0, tzinfo=_TZ)
        with self.Session() as s:
            rep = build_coverage_report(
                s, window="7d", bcs_only=False, now=now
            )
        self.assertEqual(rep.scope, "all_tickers")
        self.assertEqual(rep.source_totals.get("google_news_ru"), 1)
        self.assertEqual(rep.source_totals.get("pulse_news_ticker"), 1)
        zero_ids = {r.ticker_id for r in rep.zero}
        self.assertIn("X5", zero_ids)
        self.assertIn("BOND1", zero_ids)
        sber = next(r for r in rep.rows if r.ticker_id == "SBER")
        self.assertEqual(sber.total, 2)
        text = format_coverage_report(rep)
        self.assertIn("pulse_news_ticker", text)
        self.assertIn("ZERO", text)


if __name__ == "__main__":
    unittest.main()
