"""Fair /api/news selection: round-robin across tickers (no created_at monopoly)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.api import app, fair_round_robin_news, get_db
from portfolio_news.db import Base, NewsItem, Ticker


def _add_ticker(session, tid: str) -> None:
    session.add(
        Ticker(
            id=tid,
            name=tid,
            kind="equity",
            search_query=tid,
        )
    )


def _add_news(
    session,
    *,
    tid: str,
    title: str,
    url: str,
    published_at: datetime | None,
    created_at: datetime,
    source: str = "test",
) -> NewsItem:
    row = NewsItem(
        ticker_id=tid,
        title=title,
        url=url,
        source=source,
        published_at=published_at,
        created_at=created_at,
        notified=0,
    )
    session.add(row)
    return row


class FairRoundRobinUnitTests(unittest.TestCase):
    def test_round_robin_covers_all_tickers(self) -> None:
        base = datetime(2026, 10, 11, 12, 0, 0)
        rows: list[NewsItem] = []
        # 10 tickers; A/B each have many fresh created_at inserts
        for i in range(10):
            tid = f"T{i:02d}"
            n = 20 if i < 2 else 2
            for j in range(n):
                rows.append(
                    NewsItem(
                        id=i * 100 + j + 1,
                        ticker_id=tid,
                        title=f"{tid} story {j}",
                        url=f"https://example.test/{tid}/{j}",
                        source="test",
                        published_at=base - timedelta(hours=j),
                        created_at=base + timedelta(seconds=i * 100 + j),
                    )
                )
        picked = fair_round_robin_news(rows, limit=20)
        self.assertEqual(len(picked), 20)
        tickers = {r.ticker_id for r in picked}
        self.assertEqual(tickers, {f"T{i:02d}" for i in range(10)})
        # First 10 picks: one per ticker (a full round)
        first_round = [r.ticker_id for r in picked[:10]]
        self.assertEqual(len(set(first_round)), 10)

    def test_published_at_preferred_over_created_at(self) -> None:
        older_pub = NewsItem(
            id=1,
            ticker_id="AAA",
            title="old pub new insert",
            url="https://example.test/a1",
            source="test",
            published_at=datetime(2026, 10, 1, 10, 0, 0),
            created_at=datetime(2026, 10, 11, 18, 0, 0),
        )
        newer_pub = NewsItem(
            id=2,
            ticker_id="AAA",
            title="new pub old insert",
            url="https://example.test/a2",
            source="test",
            published_at=datetime(2026, 10, 10, 10, 0, 0),
            created_at=datetime(2026, 10, 5, 18, 0, 0),
        )
        null_pub = NewsItem(
            id=3,
            ticker_id="BBB",
            title="null pub",
            url="https://example.test/b1",
            source="test",
            published_at=None,
            created_at=datetime(2026, 10, 11, 19, 0, 0),
        )
        picked = fair_round_robin_news([older_pub, newer_pub, null_pub], limit=3)
        aaa = [r for r in picked if r.ticker_id == "AAA"]
        self.assertEqual(len(aaa), 2)
        self.assertEqual(aaa[0].id, 2)  # newer published_at before older
        self.assertEqual(aaa[1].id, 1)
        # BBB uses created_at fallback and still gets a slot
        self.assertIn("BBB", {r.ticker_id for r in picked})

    def test_limit_caps_output(self) -> None:
        rows = [
            NewsItem(
                id=i,
                ticker_id=f"T{i}",
                title=f"t{i}",
                url=f"https://example.test/{i}",
                source="test",
                published_at=datetime(2026, 10, 11, 0, 0, 0),
                created_at=datetime(2026, 10, 11, 0, 0, 0),
            )
            for i in range(5)
        ]
        self.assertEqual(len(fair_round_robin_news(rows, 3)), 3)
        self.assertEqual(fair_round_robin_news(rows, 0), [])


class NewsApiFairFeedTests(unittest.TestCase):
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

        base_pub = datetime(2026, 10, 10, 12, 0, 0)
        # Late bulk insert for leaders (simulates last poll crowding created_at)
        late = datetime(2026, 10, 11, 16, 33, 0)
        early = datetime(2026, 10, 1, 8, 0, 0)

        tickers = [f"T{i:02d}" for i in range(10)]
        for tid in tickers:
            _add_ticker(self.session, tid)

        # Leaders T00/T01: many rows with late created_at
        for j in range(25):
            _add_news(
                self.session,
                tid="T00",
                title=f"Leader0 {j}",
                url=f"https://example.test/t00/{j}",
                published_at=base_pub - timedelta(hours=j),
                created_at=late + timedelta(seconds=j),
            )
            _add_news(
                self.session,
                tid="T01",
                title=f"Leader1 {j}",
                url=f"https://example.test/t01/{j}",
                published_at=base_pub - timedelta(hours=j),
                created_at=late + timedelta(seconds=100 + j),
            )
        # Quiet tickers: older created_at but valid published_at
        for i in range(2, 10):
            tid = f"T{i:02d}"
            _add_news(
                self.session,
                tid=tid,
                title=f"{tid} only",
                url=f"https://example.test/{tid}/0",
                published_at=base_pub - timedelta(days=i),
                created_at=early + timedelta(days=i),
            )
        self.session.commit()
        self.scope = tickers

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        try:
            self.session.close()
        except Exception:  # noqa: BLE001
            pass

    def test_api_fair_feed_represents_all_scope_tickers(self) -> None:
        with patch(
            "portfolio_news.bcs_scope.resolve_bcs_scope",
            return_value=(self.scope, ""),
        ):
            r = self.client.get("/api/news?limit=20")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 20)
        ids = {row["ticker_id"] for row in data}
        self.assertEqual(ids, set(self.scope))

    def test_api_respects_bcs_scope(self) -> None:
        partial = self.scope[:3]
        with patch(
            "portfolio_news.bcs_scope.resolve_bcs_scope",
            return_value=(partial, ""),
        ):
            r = self.client.get("/api/news?limit=50")
        self.assertEqual(r.status_code, 200)
        ids = {row["ticker_id"] for row in r.json()}
        self.assertTrue(ids)
        self.assertTrue(ids.issubset(set(partial)))
        self.assertNotIn("T09", ids)

    def test_api_noise_filter_still_drops(self) -> None:
        _add_news(
            self.session,
            tid="T02",
            title="Идея в Профите по T02 — спам",
            url="https://example.test/noise/1",
            published_at=datetime(2026, 10, 11, 20, 0, 0),
            created_at=datetime(2026, 10, 11, 20, 0, 0),
        )
        self.session.commit()
        with patch(
            "portfolio_news.bcs_scope.resolve_bcs_scope",
            return_value=(["T02"], ""),
        ):
            r = self.client.get("/api/news?limit=20")
        titles = [x["title"] for x in r.json()]
        self.assertTrue(any("only" in t for t in titles))
        self.assertFalse(any("Профите" in t for t in titles))

    def test_api_limit_bound(self) -> None:
        with patch(
            "portfolio_news.bcs_scope.resolve_bcs_scope",
            return_value=(self.scope, ""),
        ):
            r = self.client.get("/api/news?limit=7")
        self.assertEqual(len(r.json()), 7)


if __name__ == "__main__":
    unittest.main()
