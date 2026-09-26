"""Chart cache lookback: slice on read, never shrink stored history."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.chart_cache import (
    cache_covers_from,
    load_chart_cache,
    merge_candle_points,
    resolve_chart_candles,
    save_chart_cache,
    slice_candles_since,
)
from portfolio_news.db import Base
from portfolio_news.metrics_moex import CandlePoint


def _pts(*begins: str) -> list[CandlePoint]:
    return [CandlePoint(begin=b + " 00:00:00", close=100.0) for b in begins]


class SliceHelpersTests(unittest.TestCase):
    def test_slice_since(self):
        pts = _pts("2026-01-01", "2026-02-01", "2026-03-01")
        out = slice_candles_since(pts, "2026-02-01")
        self.assertEqual([p.begin[:10] for p in out], ["2026-02-01", "2026-03-01"])

    def test_covers_lookback(self):
        pts = _pts("2020-01-01", "2026-09-01")
        self.assertTrue(cache_covers_from(pts, "2026-08-01", complete=True))
        self.assertFalse(cache_covers_from(pts, "2019-01-01", complete=True))

    def test_days0_rejects_truncated_legacy(self):
        # ~30 recent days, no complete flag → not enough for full history
        pts = _pts("2026-08-27", "2026-09-26")
        self.assertFalse(cache_covers_from(pts, "", complete=None))
        self.assertTrue(cache_covers_from(pts, "", complete=True))


class ResolveChartCacheTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.session.close()

    def test_fresh_cache_slices_days_without_refetch(self):
        full = _pts("2020-01-01", "2026-08-01", "2026-09-01", "2026-09-20")
        save_chart_cache(
            self.session,
            ticker="BELU",
            candles=full,
            secid="BELU",
            board="TQBR",
            complete=True,
        )
        with patch("portfolio_news.chart_cache.fetch_candles") as fc:
            pts, *_rest = resolve_chart_candles(
                self.session, "BELU", "equity", days=30
            )
            fc.assert_not_called()
        self.assertEqual(len(pts), 2)  # Aug+Sep within ~30d of "today" may vary
        # At least all returned are >= from_date
        from datetime import date, timedelta

        fd = (date.today() - timedelta(days=30)).isoformat()
        self.assertTrue(all(p.begin[:10] >= fd for p in pts))

    def test_short_lookback_does_not_shrink_cache(self):
        full = _pts("2018-01-01", "2020-01-01", "2026-09-01")
        save_chart_cache(
            self.session,
            ticker="BELU",
            candles=full,
            complete=True,
        )
        short = _pts("2026-09-01")
        with patch(
            "portfolio_news.chart_cache.fetch_candles",
            return_value=(short, "BELU", "TQBR", ""),
        ), patch(
            "portfolio_news.chart_cache.cache_is_fresh",
            return_value=False,
        ):
            # Force cold path by making cache not cover? Actually covers=True and
            # not fresh → incremental. Make covers fail so full refetch runs.
            with patch(
                "portfolio_news.chart_cache.cache_covers_from",
                return_value=False,
            ):
                resolve_chart_candles(
                    self.session, "BELU", "equity", days=30, force=False
                )
        cached = load_chart_cache(self.session, "BELU")
        n = len((cached or {}).get("candles") or [])
        self.assertGreaterEqual(n, 3)  # merged, not replaced by 1
        self.assertTrue((cached or {}).get("complete"))


class MergeTests(unittest.TestCase):
    def test_merge_keeps_union(self):
        a = _pts("2020-01-01", "2026-01-01")
        b = _pts("2026-01-01", "2026-09-01")
        m = merge_candle_points(a, b)
        self.assertEqual([p.begin[:10] for p in m], ["2020-01-01", "2026-01-01", "2026-09-01"])


if __name__ == "__main__":
    unittest.main()
