"""Chart cache lookback: slice on read, never shrink stored history."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.chart_cache import (
    cache_is_fresh,
    cache_covers_from,
    load_chart_cache,
    merge_candle_points,
    resolve_chart_candles,
    save_chart_cache,
    slice_candles_since,
    today_local,
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

    def test_today_candle_expires_quickly(self):
        now = 10_000.0
        with patch("portfolio_news.chart_cache.time.time", return_value=now):
            self.assertTrue(cache_is_fresh(now - 60, today_local()))
            self.assertFalse(cache_is_fresh(now - 600, today_local()))


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
        from datetime import date, timedelta

        def ago(n: int) -> str:
            return (date.today() - timedelta(days=n)).isoformat()

        full = _pts("2020-01-01", ago(60), ago(20), ago(5))
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
        self.assertEqual(len(pts), 2)
        fd = ago(30)
        self.assertTrue(all(p.begin[:10] >= fd for p in pts))

    def test_stale_cache_returns_immediately_without_blocking_iss(self):
        """Intraday TTL expiry must not block the click on ISS."""
        full = _pts("2020-01-01", "2026-09-01", "2026-09-20")
        save_chart_cache(
            self.session,
            ticker="BELU",
            candles=full,
            complete=True,
        )

        def _boom(*_a, **_k):
            raise AssertionError("fetch_candles must not run in-request")

        with patch(
            "portfolio_news.chart_cache.cache_is_fresh",
            return_value=False,
        ), patch(
            "portfolio_news.chart_cache._schedule_chart_refresh"
        ) as sched, patch(
            "portfolio_news.chart_cache.fetch_candles",
            side_effect=_boom,
        ):
            pts, _secid, _board, err, from_cache, stale = resolve_chart_candles(
                self.session, "BELU", "equity", days=0, force=False
            )
        self.assertEqual(len(pts), 3)
        self.assertTrue(from_cache)
        self.assertTrue(stale)
        self.assertEqual(err, "")
        sched.assert_called_once()
        self.assertEqual(sched.call_args.kwargs.get("mode"), "tail")

    def test_truncated_cache_served_stale_schedules_full_refresh(self):
        short = _pts("2026-08-27", "2026-09-01", "2026-09-20")
        save_chart_cache(
            self.session,
            ticker="BELU",
            candles=short,
            complete=False,
        )
        with patch(
            "portfolio_news.chart_cache.cache_is_fresh",
            return_value=False,
        ), patch(
            "portfolio_news.chart_cache._schedule_chart_refresh"
        ) as sched, patch(
            "portfolio_news.chart_cache.fetch_candles"
        ) as fc:
            pts, _s, _b, _e, from_cache, stale = resolve_chart_candles(
                self.session, "BELU", "equity", days=0, force=False
            )
        self.assertEqual(len(pts), 3)
        self.assertTrue(from_cache and stale)
        fc.assert_not_called()
        self.assertEqual(sched.call_args.kwargs.get("mode"), "full")

    def test_bg_tail_refresh_does_not_promote_complete_flag(self):
        """Legacy truncated cache must stay incomplete after tail merge."""
        from portfolio_news import chart_cache as cc

        short = _pts("2026-08-27", "2026-09-01", "2026-09-20")
        save_chart_cache(
            self.session,
            ticker="BELU",
            candles=short,
            complete=False,
        )
        tail = _pts("2026-09-20", "2026-09-26")

        class _SessCtx:
            def __enter__(self_inner):
                return self.session

            def __exit__(self_inner, *exc):
                return False

        with patch.object(cc, "fetch_candles", return_value=(tail, "BELU", "TQBR", "")), patch(
            "portfolio_news.config.get_settings"
        ) as gs, patch(
            "portfolio_news.db.make_session_factory",
            return_value=lambda: _SessCtx(),
        ):
            gs.return_value.database_url = "sqlite://"
            with cc._bg_lock:
                cc._bg_inflight.discard("BELU")
            cc._run_chart_refresh(
                ticker="BELU",
                kind="equity",
                isin="",
                interval=24,
                mode="tail",
                last_day="2026-09-20",
                cached_pts=short,
                cached_secid="BELU",
                cached_board="TQBR",
                cached_complete=False,
            )
        cached = load_chart_cache(self.session, "BELU")
        self.assertIs(cached.get("complete"), False)
        self.assertGreaterEqual(len((cached or {}).get("candles") or []), 3)

    def test_cold_miss_fetches_recent_window_schedules_full(self):
        """Cold path must not block on full ISS history."""
        recent = _pts("2025-08-01", "2026-09-01", "2026-09-20")

        def _fake_fetch(_tid, _kind, **kwargs):
            self.assertTrue(kwargs.get("from_date"))
            self.assertEqual(kwargs.get("limit"), 500)
            return recent, "NEWX", "TQBR", ""

        with patch(
            "portfolio_news.chart_cache.fetch_candles",
            side_effect=_fake_fetch,
        ), patch(
            "portfolio_news.chart_cache._schedule_chart_refresh"
        ) as sched:
            pts, secid, board, err, from_cache, stale = resolve_chart_candles(
                self.session, "NEWX", "equity", days=0, force=False
            )
        self.assertEqual(len(pts), 3)
        self.assertFalse(from_cache)
        self.assertTrue(stale)
        self.assertEqual(secid, "NEWX")
        self.assertEqual(err, "")
        sched.assert_called_once()
        self.assertEqual(sched.call_args.kwargs.get("mode"), "full")
        cached = load_chart_cache(self.session, "NEWX")
        self.assertIs(cached.get("complete"), False)


class MergeTests(unittest.TestCase):
    def test_merge_keeps_union(self):
        a = _pts("2020-01-01", "2026-01-01")
        b = _pts("2026-01-01", "2026-09-01")
        m = merge_candle_points(a, b)
        self.assertEqual([p.begin[:10] for p in m], ["2020-01-01", "2026-01-01", "2026-09-01"])


if __name__ == "__main__":
    unittest.main()
