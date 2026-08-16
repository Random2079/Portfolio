from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_news.db import NewsItem, Ticker
from portfolio_news.notify_toast import notify_toast
from portfolio_news.sources import default_sources
from portfolio_news.sources.base import NewsSource, RawNews

log = logging.getLogger(__name__)

NotifyMode = Literal["off", "each", "digest"]
ProgressCallback = Callable[["PollProgress"], None]


@dataclass
class PollProgress:
    running: bool = False
    current: int = 0
    total: int = 0
    ticker_id: str = ""
    inserted: int = 0
    notified: int = 0
    error: str = ""
    done: bool = False


@dataclass
class PollResult:
    tickers: int = 0
    inserted: int = 0
    notified: int = 0
    sources: list[str] = field(default_factory=list)
    new_titles: list[str] = field(default_factory=list)


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


def select_tickers(
    session: Session,
    *,
    ticker_id: Optional[str] = None,
    kind: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 0,
) -> list[Ticker]:
    q = select(Ticker).order_by(Ticker.id)
    if ticker_id:
        q = q.where(Ticker.id == ticker_id)
    else:
        if kind:
            q = q.where(Ticker.kind == kind)
        if category:
            q = q.where(Ticker.category == category)
    tickers = list(session.scalars(q))
    if limit and limit > 0:
        tickers = tickers[:limit]
    return tickers


def poll_once(
    session: Session,
    *,
    sources: Sequence[NewsSource] | None = None,
    limit: int = 0,
    notify: bool | NotifyMode = "digest",
    ticker_id: Optional[str] = None,
    kind: Optional[str] = None,
    category: Optional[str] = None,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """Fetch news for scoped tickers; insert new URLs; notify per mode."""
    if isinstance(notify, bool):
        mode: NotifyMode = "each" if notify else "off"
    else:
        mode = notify

    sources = list(sources or default_sources())
    tickers = select_tickers(
        session,
        ticker_id=ticker_id,
        kind=kind,
        category=category,
        limit=limit,
    )

    result = PollResult(sources=[s.name for s in sources])
    digest_titles: list[str] = []

    def emit(progress: PollProgress) -> None:
        if on_progress:
            on_progress(progress)

    total = len(tickers)
    emit(PollProgress(running=True, current=0, total=total, ticker_id="", inserted=0))

    for idx, t in enumerate(tickers, start=1):
        emit(
            PollProgress(
                running=True,
                current=idx,
                total=total,
                ticker_id=t.id,
                inserted=result.inserted,
            )
        )
        result.tickers += 1
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
                result.inserted += 1
                digest_titles.append(f"{t.id}: {raw.title}")
                if mode == "each":
                    notify_toast(
                        title=f"{t.id} · {raw.source}",
                        message=raw.title,
                        url=raw.url,
                    )
                    row.notified = 1
                    session.commit()
                    result.notified += 1
                elif mode == "digest":
                    row.notified = 1
                    session.commit()

    if mode == "digest" and result.inserted > 0:
        preview = " · ".join(digest_titles[:2])
        body = f"+{result.inserted} новостей"
        if preview:
            body = f"{body}\n{preview}"
        notify_toast(title="Portfolio News", message=body, url="http://127.0.0.1:8765/")
        result.notified = 1

    result.new_titles = digest_titles[:5]
    emit(
        PollProgress(
            running=False,
            current=total,
            total=total,
            ticker_id="",
            inserted=result.inserted,
            notified=result.notified,
            done=True,
        )
    )
    return {
        "tickers": result.tickers,
        "inserted": result.inserted,
        "notified": result.notified,
        "sources": result.sources,
        "titles": result.new_titles,
    }
