from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Literal, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_news.db import NewsItem, Ticker
from portfolio_news.focus import list_focus_tickers, notify_allowed
from portfolio_news.notify_toast import notify_toast
from portfolio_news.sources import default_sources
from portfolio_news.sources.base import NewsSource, RawNews

log = logging.getLogger(__name__)

NotifyMode = Literal["off", "each", "digest"]
ProgressCallback = Callable[["PollProgress"], None]
_TOAST_TZ = timezone(timedelta(hours=5))  # Asia/Yekaterinburg, no DST / no tzdata


def news_is_today_for_toast(
    published_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """K9: toast only if published_at is today in Asia/Yekaterinburg (UTC+5).

    No published_at → no toast (still OK to store in DB). Avoids undated RSS
    catch-up spam on first poll.
    """
    if published_at is None:
        return False
    ref = now or datetime.now(_TOAST_TZ)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=_TOAST_TZ)
    else:
        ref = ref.astimezone(_TOAST_TZ)
    start = datetime.combine(ref.date(), time.min, tzinfo=_TOAST_TZ)
    pub = published_at
    if pub.tzinfo is None:
        # Naive timestamps from feeds: treat as local wall clock (Yekaterinburg).
        pub = pub.replace(tzinfo=_TOAST_TZ)
    else:
        pub = pub.astimezone(_TOAST_TZ)
    return pub >= start


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
    ids: Optional[Sequence[str]] = None,
) -> list[Ticker]:
    q = select(Ticker).order_by(Ticker.id)
    if ticker_id:
        q = q.where(Ticker.id == ticker_id)
    elif ids is not None:
        clean = [str(x).strip().upper() for x in ids if x and str(x).strip()]
        if not clean:
            return []
        q = q.where(Ticker.id.in_(clean))
        if kind:
            q = q.where(Ticker.kind == kind)
        if category:
            q = q.where(Ticker.category == category)
        rows = list(session.scalars(q))
        by_id = {t.id.upper(): t for t in rows}
        ordered = [by_id[i] for i in clean if i in by_id]
        if limit and limit > 0:
            ordered = ordered[:limit]
        return ordered
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
    should_cancel: Callable[[], bool] | None = None,
    notify_focus_only: bool = True,
    bcs_only: bool = True,
    ids: Optional[Sequence[str]] = None,
) -> dict:
    """Fetch news for scoped tickers; insert new URLs; notify per mode.

    K5: default bcs_only=True → poll only current BCS holdings (not full Snowball DB).
    Pass bcs_only=False for legacy full-table / unit tests.
    KB: when Focus set is non-empty and notify_focus_only, toast only for Focus
    (news still stored for all polled tickers).
    """
    if isinstance(notify, bool):
        mode: NotifyMode = "each" if notify else "off"
    else:
        mode = notify

    sources = list(sources or default_sources())
    scope_ids: Optional[list[str]] = list(ids) if ids is not None else None
    scope_error = ""
    if scope_ids is None and bcs_only:
        from portfolio_news.bcs_scope import filter_ticker_id_to_scope, resolve_bcs_scope

        scope_ids, scope_error = resolve_bcs_scope(session)
        if scope_error and not scope_ids:
            emit0 = PollProgress(
                running=False,
                current=0,
                total=0,
                ticker_id="",
                inserted=0,
                error=scope_error,
                done=True,
            )
            if on_progress:
                on_progress(emit0)
            return {
                "tickers": 0,
                "inserted": 0,
                "notified": 0,
                "sources": [s.name for s in sources],
                "new_titles": [],
                "cancelled": False,
                "scope": "bcs",
                "scope_error": scope_error,
                "scope_ids": [],
            }
        if ticker_id:
            eff, terr = filter_ticker_id_to_scope(ticker_id, scope_ids)
            if terr:
                if on_progress:
                    on_progress(
                        PollProgress(
                            running=False,
                            done=True,
                            error=terr,
                        )
                    )
                return {
                    "tickers": 0,
                    "inserted": 0,
                    "notified": 0,
                    "sources": [s.name for s in sources],
                    "new_titles": [],
                    "cancelled": False,
                    "scope": "bcs",
                    "scope_error": terr,
                    "scope_ids": scope_ids,
                }
            ticker_id = eff

    tickers = select_tickers(
        session,
        ticker_id=ticker_id,
        kind=kind,
        category=category,
        limit=limit,
        ids=None if ticker_id else scope_ids,
    )

    focus_ids: set[str] | None = None
    if notify_focus_only:
        focus_list = list_focus_tickers(session)
        focus_ids = set(focus_list) if focus_list else None

    result = PollResult(sources=[s.name for s in sources])
    digest_titles: list[str] = []
    cancelled = False

    def emit(progress: PollProgress) -> None:
        if on_progress:
            on_progress(progress)

    total = len(tickers)
    emit(PollProgress(running=True, current=0, total=total, ticker_id="", inserted=0))

    for idx, t in enumerate(tickers, start=1):
        if should_cancel and should_cancel():
            cancelled = True
            break
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
            if should_cancel and should_cancel():
                cancelled = True
                break
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
                # K9: today-only toast; KB: optional Focus filter. DB insert always ok.
                focus_ok = (not notify_focus_only) or notify_allowed(t.id, focus_ids)
                today_ok = news_is_today_for_toast(raw.published_at)
                toast_ok = bool(focus_ok and today_ok and mode != "off")
                if toast_ok:
                    digest_titles.append(f"{t.id}: {raw.title}")
                if mode == "each" and toast_ok:
                    notify_toast(
                        title=f"{t.id} · {raw.source}",
                        message=raw.title,
                        url=raw.url,
                    )
                    row.notified = 1
                    session.commit()
                    result.notified += 1
                elif mode == "digest" and toast_ok:
                    row.notified = 1
                    session.commit()
                else:
                    # Hold / not today / off: keep in DB, no toast
                    session.commit()
        if cancelled:
            break

    if not cancelled and mode == "digest" and digest_titles:
        preview = " · ".join(digest_titles[:2])
        body = f"+{len(digest_titles)} новостей"
        if focus_ids:
            body = f"{body} (Focus)"
        if preview:
            body = f"{body}\n{preview}"
        notify_toast(title="Portfolio News", message=body, url="http://127.0.0.1:8765/")
        result.notified = 1

    result.new_titles = digest_titles[:5]
    emit(
        PollProgress(
            running=False,
            current=result.tickers if cancelled else total,
            total=total,
            ticker_id="",
            inserted=result.inserted,
            notified=result.notified,
            done=True,
            error="cancelled" if cancelled else "",
        )
    )
    return {
        "tickers": result.tickers,
        "inserted": result.inserted,
        "notified": result.notified,
        "sources": result.sources,
        "titles": result.new_titles,
        "cancelled": cancelled,
        "scope": "bcs" if bcs_only or scope_ids is not None else "all",
        "scope_error": scope_error,
        "scope_ids": list(scope_ids) if scope_ids is not None else [],
    }
