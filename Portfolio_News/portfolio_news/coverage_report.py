"""CLI/helpers: news coverage matrix (ticker × source) for holdings scope."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_news.db import NewsItem, Ticker
from portfolio_news.sources import default_sources

_TOAST_TZ = timezone(timedelta(hours=5))  # Asia/Yekaterinburg


@dataclass
class CoverageRow:
    ticker_id: str
    kind: str
    name: str
    total: int
    by_source: dict[str, int] = field(default_factory=dict)


@dataclass
class CoverageReport:
    window: str
    since: datetime
    sources_active: list[str]
    source_totals: dict[str, int]
    rows: list[CoverageRow]
    zero: list[CoverageRow]
    low: list[CoverageRow]
    fat: list[CoverageRow]
    scope: str
    scope_error: str = ""


def _aware(dt: Optional[datetime], *, assume_tz: timezone = _TOAST_TZ) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=assume_tz)
    return dt.astimezone(assume_tz)


def window_start(window: str, *, now: Optional[datetime] = None) -> datetime:
    ref = now or datetime.now(_TOAST_TZ)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=_TOAST_TZ)
    else:
        ref = ref.astimezone(_TOAST_TZ)
    day0 = datetime.combine(ref.date(), time.min, tzinfo=_TOAST_TZ)
    w = (window or "7d").strip().lower()
    if w in ("today", "1d", "day"):
        return day0
    if w in ("7d", "week"):
        return day0 - timedelta(days=7)
    if w in ("30d", "month"):
        return day0 - timedelta(days=30)
    if w in ("all", "*"):
        return datetime(2000, 1, 1, tzinfo=_TOAST_TZ)
    raise ValueError(f"unknown window: {window!r} (today|7d|30d|all)")


def resolve_scope_tickers(
    session: Session,
    *,
    bcs_only: bool = True,
    ids: Optional[Sequence[str]] = None,
) -> tuple[list[Ticker], str, str]:
    """Return (tickers, scope_label, error)."""
    if ids is not None:
        clean = [str(x).strip().upper() for x in ids if x and str(x).strip()]
        rows = list(session.scalars(select(Ticker).where(Ticker.id.in_(clean))))
        by_id = {t.id.upper(): t for t in rows}
        ordered = [by_id[i] for i in clean if i in by_id]
        return ordered, "ids", ""
    if bcs_only:
        from portfolio_news.bcs_scope import resolve_bcs_scope

        scope_ids, err = resolve_bcs_scope(session)
        if err and not scope_ids:
            # Fallback: report on whatever is in tickers DB (offline audit).
            all_rows = list(session.scalars(select(Ticker).order_by(Ticker.id)))
            return all_rows, "tickers_db_fallback", err
        rows = list(
            session.scalars(select(Ticker).where(Ticker.id.in_(scope_ids)).order_by(Ticker.id))
        )
        return rows, "bcs", err or ""
    all_rows = list(session.scalars(select(Ticker).order_by(Ticker.id)))
    return all_rows, "all_tickers", ""


def build_coverage_report(
    session: Session,
    *,
    window: str = "7d",
    bcs_only: bool = True,
    ids: Optional[Sequence[str]] = None,
    low_max: int = 2,
    fat_min: int = 25,
    now: Optional[datetime] = None,
) -> CoverageReport:
    since = window_start(window, now=now)
    tickers, scope, scope_error = resolve_scope_tickers(session, bcs_only=bcs_only, ids=ids)
    active = [s.name for s in default_sources()]

    if not tickers:
        return CoverageReport(
            window=window,
            since=since,
            sources_active=active,
            source_totals={},
            rows=[],
            zero=[],
            low=[],
            fat=[],
            scope=scope,
            scope_error=scope_error or "no_tickers",
        )

    news_rows = list(
        session.scalars(
            select(NewsItem).where(NewsItem.ticker_id.in_([t.id for t in tickers]))
        )
    )
    # Filter by published_at (fallback created_at) in local TZ.
    filtered: list[NewsItem] = []
    for n in news_rows:
        dt = _aware(n.published_at) or _aware(n.created_at)
        if dt is not None and dt >= since:
            filtered.append(n)

    by_tick_src: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    source_totals: dict[str, int] = defaultdict(int)
    for n in filtered:
        src = (n.source or "?").strip() or "?"
        by_tick_src[n.ticker_id][src] += 1
        source_totals[src] += 1

    rows: list[CoverageRow] = []
    for t in tickers:
        srcs = dict(by_tick_src.get(t.id, {}))
        total = sum(srcs.values())
        rows.append(
            CoverageRow(
                ticker_id=t.id,
                kind=t.kind or "?",
                name=t.name or "",
                total=total,
                by_source=srcs,
            )
        )

    zero = [r for r in rows if r.total == 0]
    low = [r for r in rows if 0 < r.total <= low_max]
    fat = [r for r in rows if r.total >= fat_min]

    return CoverageReport(
        window=window,
        since=since,
        sources_active=active,
        source_totals=dict(sorted(source_totals.items(), key=lambda x: -x[1])),
        rows=rows,
        zero=sorted(zero, key=lambda r: (r.kind, r.ticker_id)),
        low=sorted(low, key=lambda r: (r.total, r.kind, r.ticker_id)),
        fat=sorted(fat, key=lambda r: (-r.total, r.ticker_id)),
        scope=scope,
        scope_error=scope_error,
    )


def format_coverage_report(
    rep: CoverageReport,
    *,
    top: int = 15,
    low_max: int = 2,
    fat_min: int = 25,
) -> str:
    lines: list[str] = []
    lines.append(
        f"coverage window={rep.window} since={rep.since.isoformat()} "
        f"scope={rep.scope} tickers={len(rep.rows)}"
    )
    if rep.scope_error:
        lines.append(f"scope_note: {rep.scope_error} (fallback used if tickers listed)")
    lines.append(f"active_sources ({len(rep.sources_active)}): {', '.join(rep.sources_active)}")
    tot = sum(rep.source_totals.values())
    lines.append(f"items_in_window={tot} by_source={rep.source_totals}")
    lines.append(
        f"holes: zero={len(rep.zero)} low(1-{low_max})={len(rep.low)} "
        f"fat>={fat_min}={len(rep.fat)}"
    )
    if rep.zero:
        lines.append("--- ZERO ---")
        for r in rep.zero[:40]:
            lines.append(f"  {r.ticker_id:12} kind={r.kind:7} {r.name[:40]}")
        if len(rep.zero) > 40:
            lines.append(f"  … +{len(rep.zero) - 40} more")
    if rep.low:
        lines.append("--- LOW ---")
        for r in rep.low[:30]:
            lines.append(
                f"  n={r.total:2} {r.ticker_id:12} kind={r.kind:7} "
                f"srcs={r.by_source} {r.name[:30]}"
            )
    if rep.fat:
        lines.append("--- FAT ---")
        for r in rep.fat[:top]:
            lines.append(
                f"  n={r.total:3} {r.ticker_id:12} kind={r.kind:7} srcs={r.by_source}"
            )
    # top covered
    top_rows = sorted(rep.rows, key=lambda r: -r.total)[:top]
    if top_rows and top_rows[0].total > 0:
        lines.append("--- TOP ---")
        for r in top_rows:
            if r.total <= 0:
                break
            lines.append(
                f"  n={r.total:3} {r.ticker_id:12} kind={r.kind:7} "
                f"srcs={r.by_source} {r.name[:30]}"
            )
    # missing source tags in DB vs active
    missing_tags = [s for s in rep.sources_active if s not in rep.source_totals]
    if missing_tags:
        lines.append(f"sources_with_0_rows_in_window: {', '.join(missing_tags)}")
    return "\n".join(lines)


def iter_equity_holes(rep: CoverageReport) -> Iterable[CoverageRow]:
    for r in rep.zero:
        if (r.kind or "").lower() in ("equity", "stock", "share", "shares"):
            yield r
