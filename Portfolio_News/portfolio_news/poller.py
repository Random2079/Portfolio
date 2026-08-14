from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_news.db import NewsItem, Ticker
from portfolio_news.notify_toast import notify_toast
from portfolio_news.sources import default_sources
from portfolio_news.sources.base import NewsSource, RawNews

log = logging.getLogger(__name__)


def _insert_if_new(session: Session, ticker_id: str, item: RawNews) -> NewsItem | None:
    exists = session.scalar(select(NewsItem.id).where(NewsItem.url == item.url).limit(1))
    if exists is not None:
        return None
    row = NewsItem(
        ticker_id=ticker_id,
        title=item.title,
        url=item.url,
        source=item.source,
        published_at=item.published_at,
        notified=0,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    session.refresh(row)
    return row


def poll_once(
    session: Session,
    *,
    sources: Sequence[NewsSource] | None = None,
    limit: int = 0,
    notify: bool = True,
) -> dict:
    """Fetch news for all tickers; insert new URLs; toast on first sight."""
    sources = list(sources or default_sources())
    q = select(Ticker).order_by(Ticker.id)
    tickers = list(session.scalars(q))
    if limit and limit > 0:
        tickers = tickers[:limit]

    scanned = 0
    inserted = 0
    notified = 0

    for t in tickers:
        scanned += 1
        query = t.search_query or t.name or t.id
        for src in sources:
            try:
                items = src.fetch(t.id, query, t.kind)
            except Exception as exc:  # noqa: BLE001
                log.warning("source %s failed for %s: %s", src.name, t.id, exc)
                continue
            for raw in items:
                row = _insert_if_new(session, t.id, raw)
                if row is None:
                    continue
                inserted += 1
                if notify:
                    notify_toast(
                        title=f"{t.id} · {raw.source}",
                        message=raw.title,
                        url=raw.url,
                    )
                    row.notified = 1
                    session.commit()
                    notified += 1

    return {
        "tickers": scanned,
        "inserted": inserted,
        "notified": notified,
        "sources": [s.name for s in sources],
    }
