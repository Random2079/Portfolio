"""Layer 1: poller-level diagnostics (empty vs error, one outcome per item)."""

from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_news.db import Base, NewsItem, Ticker
from portfolio_news.poll_stats import (
    IS_NOISE_TITLE,
    NEAR_DUPLICATE,
    URL_DUPLICATE,
)
from portfolio_news.poller import poll_once
from portfolio_news.sources.base import RawNews


class _FakeSource:
    def __init__(self, name: str, items=None, *, exc: Exception | None = None):
        self.name = name
        self._items = list(items or [])
        self._exc = exc
        self.calls = 0

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        del search_query, kind
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        # Stamp source name on copies
        out = []
        for it in self._items:
            out.append(
                RawNews(
                    title=it.title,
                    url=it.url,
                    source=self.name,
                    published_at=it.published_at,
                )
            )
        return out


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _add_ticker(session, tid: str = "OZON") -> None:
    session.add(
        Ticker(id=tid, name=tid, kind="equity", search_query=tid)
    )
    session.commit()


class PollDiagnosticsLayer1Tests(unittest.TestCase):
    def test_empty_ok_vs_source_exception(self) -> None:
        session = _session()
        _add_ticker(session)
        empty = _FakeSource("empty_src", [])
        boom = _FakeSource("boom_src", [], exc=RuntimeError("http 503"))
        result = poll_once(
            session,
            sources=[empty, boom],
            ticker_id="OZON",
            notify="off",
            bcs_only=False,
            notify_focus_only=False,
        )
        diag = result["diagnostics"]
        summary = diag["summary"]
        self.assertEqual(summary["source_errors"], 1)
        self.assertEqual(summary["empty_ok_calls"], 1)
        self.assertEqual(summary["ok_calls"], 1)
        self.assertEqual(summary["returned"], 0)
        self.assertEqual(summary["inserted"], 0)

        by = {c["source"]: c for c in diag["by_source"]}
        self.assertEqual(by["empty_src"]["empty_ok_calls"], 1)
        self.assertEqual(by["empty_src"]["errors"], 0)
        self.assertEqual(by["boom_src"]["errors"], 1)
        self.assertEqual(by["boom_src"]["empty_ok_calls"], 0)

        oz = diag["by_ticker"]["OZON"]
        boom_call = next(s for s in oz["sources"] if s["source"] == "boom_src")
        self.assertFalse(boom_call["ok"])
        self.assertEqual(boom_call["error_kind"], "exception")
        empty_call = next(s for s in oz["sources"] if s["source"] == "empty_src")
        self.assertTrue(empty_call["ok"])
        self.assertTrue(empty_call["empty_ok"])

    def test_one_outcome_per_returned_item(self) -> None:
        session = _session()
        _add_ticker(session)
        # Pre-existing URL + near-dup title already in DB
        session.add(
            NewsItem(
                ticker_id="OZON",
                title="Ozon opens new warehouse - Интерфакс",
                url="https://example.test/dup-url",
                source="seed",
                published_at=datetime(2026, 10, 10, 12, 0, 0),
                notified=0,
            )
        )
        session.commit()

        items = [
            RawNews(
                title="Brand new corporate fact",
                url="https://example.test/new",
                source="fake",
                published_at=datetime(2026, 10, 11, 10, 0, 0),
            ),
            RawNews(
                title="Идея в Профите: лонг OZON",  # hard noise
                url="https://example.test/noise",
                source="fake",
                published_at=datetime(2026, 10, 11, 11, 0, 0),
            ),
            RawNews(
                title="Other headline",
                url="https://example.test/dup-url",  # URL duplicate
                source="fake",
                published_at=datetime(2026, 10, 11, 12, 0, 0),
            ),
            RawNews(
                title="Ozon opens new warehouse - РБК",  # near-dup fingerprint
                url="https://example.test/near",
                source="fake",
                published_at=datetime(2026, 10, 11, 13, 0, 0),
            ),
        ]
        src = _FakeSource("fake", items)
        result = poll_once(
            session,
            sources=[src],
            ticker_id="OZON",
            notify="off",
            bcs_only=False,
            notify_focus_only=False,
        )
        diag = result["diagnostics"]
        summary = diag["summary"]
        self.assertEqual(summary["returned"], 4)
        self.assertEqual(summary["inserted"], 1)
        drops = summary["drops_by_reason"]
        self.assertEqual(drops.get(IS_NOISE_TITLE), 1)
        self.assertEqual(drops.get(URL_DUPLICATE), 1)
        self.assertEqual(drops.get(NEAR_DUPLICATE), 1)
        # No double-count: each returned item → exactly one terminal bucket
        self.assertEqual(
            summary["inserted"] + sum(drops.values()),
            summary["returned"],
        )
        call = diag["by_ticker"]["OZON"]["sources"][0]
        self.assertEqual(call["returned"], 4)
        poller_drop = sum(
            call["drops"].get(r, 0)
            for r in (
                IS_NOISE_TITLE,
                URL_DUPLICATE,
                NEAR_DUPLICATE,
                "integrity_error",
            )
        )
        self.assertEqual(call["inserted"] + poller_drop, 4)

        n_news = session.scalar(
            select(NewsItem).where(NewsItem.url == "https://example.test/new")
        )
        self.assertIsNotNone(n_news)
        # Only one new insert beyond seed
        total = len(list(session.scalars(select(NewsItem)).all()))
        self.assertEqual(total, 2)

    def test_url_and_near_duplicate_reasons(self) -> None:
        session = _session()
        _add_ticker(session)
        session.add(
            NewsItem(
                ticker_id="OZON",
                title="Same story about Ozon - Интерфакс",
                url="https://example.test/a",
                source="seed",
                published_at=datetime(2026, 10, 1, 8, 0, 0),
                notified=0,
            )
        )
        session.commit()
        src = _FakeSource(
            "fake",
            [
                RawNews(
                    title="Unrelated insert",
                    url="https://example.test/a",
                    source="fake",
                ),
                RawNews(
                    title="Same story about Ozon - РБК",
                    url="https://example.test/b",
                    source="fake",
                ),
            ],
        )
        result = poll_once(
            session,
            sources=[src],
            ticker_id="OZON",
            notify="off",
            bcs_only=False,
            notify_focus_only=False,
        )
        drops = result["diagnostics"]["summary"]["drops_by_reason"]
        self.assertEqual(drops.get(URL_DUPLICATE), 1)
        self.assertEqual(drops.get(NEAR_DUPLICATE), 1)
        self.assertEqual(result["inserted"], 0)

    def test_diagnostics_present_when_no_news(self) -> None:
        session = _session()
        _add_ticker(session)
        result = poll_once(
            session,
            sources=[_FakeSource("empty", [])],
            ticker_id="OZON",
            notify="off",
            bcs_only=False,
            notify_focus_only=False,
        )
        self.assertIn("diagnostics", result)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["diagnostics"]["summary"]["empty_ok_calls"], 1)
        # Legacy poll result keys still present
        self.assertIn("tickers", result)
        self.assertIn("sources", result)
        self.assertEqual(result["tickers"], 1)


if __name__ == "__main__":
    unittest.main()
