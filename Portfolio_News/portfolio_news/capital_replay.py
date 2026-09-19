"""Weekly capital: Snowball journal (qty+cash) × MOEX Friday close.

Bond ISS close is usually % of par → qty × close/100 × 1000.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_news.bcs_client import Operation, classify_asset_class
from portfolio_news.capital_cache import today_local, upsert_capital_day
from portfolio_news.db import BcsOperation, CapitalDay, MoexClose, Ticker

log = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=5))
_OPS_START = date(2026, 1, 26)
_SNOWBALL_START = date(2024, 1, 5)
_BOND_FACE = 1000.0


def op_local_day(executed_at: str) -> Optional[date]:
    s = (executed_at or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z") or "+" in s[10:]:
            raw = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_TZ).date()
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def signed_qty(op: Operation) -> float:
    q = float(op.quantity or 0.0)
    side = (op.side or "").strip().lower()
    if side in ("sell", "sale", "s"):
        return -q
    return q


def qty_as_of(ops: Sequence[Operation], as_of: date) -> dict[str, float]:
    qty: dict[str, float] = {}
    for op in ops:
        d = op_local_day(op.executed_at)
        if d is None or d > as_of:
            continue
        tid = (op.ticker or "").strip().upper()
        if not tid:
            continue
        qty[tid] = qty.get(tid, 0.0) + signed_qty(op)
    # Sells of papers bought before BCS history must not go short.
    return {k: v for k, v in qty.items() if v > 1e-9}


def week_fridays(start: date, end: date) -> list[date]:
    """Fridays in [start, end], inclusive."""
    if end < start:
        return []
    d = start + timedelta(days=(4 - start.weekday()) % 7)
    out: list[date] = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def moex_kind(ticker: str, class_code: str = "", db_kind: str = "") -> str:
    ac = classify_asset_class(
        ticker=ticker,
        class_code=class_code,
        db_kind=db_kind,
    )
    if ac == "bond":
        return "bond"
    if ac == "fund":
        return "fund"
    return "equity"


def unit_rub(close: float, kind: str) -> float:
    """One piece in ₽. Bond ISS close is usually percent of 1000 face."""
    if kind == "bond" and 0 < close < 300:
        return close / 100.0 * _BOND_FACE
    return close


def candles_unit_rub(points: Sequence[Any], kind: str) -> list[Any]:
    """Scale bond OHLC from % of par → ₽/шт (same as markers/avg). Equity unchanged."""
    if (kind or "").strip().lower() != "bond" or not points:
        return list(points)
    out: list[Any] = []
    for p in points:
        o = getattr(p, "open", None)
        c = getattr(p, "close", None)
        h = getattr(p, "high", None)
        lo = getattr(p, "low", None)
        out.append(
            type(p)(
                begin=getattr(p, "begin", "") or "",
                end=getattr(p, "end", "") or "",
                open=unit_rub(float(o), "bond") if o is not None else None,
                close=unit_rub(float(c), "bond") if c is not None else None,
                high=unit_rub(float(h), "bond") if h is not None else None,
                low=unit_rub(float(lo), "bond") if lo is not None else None,
                volume=getattr(p, "volume", None),
                value=getattr(p, "value", None),
            )
        )
    return out


def last_close_on_or_before(
    closes: Sequence[tuple[date, float]], as_of: date
) -> Optional[float]:
    best: Optional[float] = None
    for d, px in closes:
        if d <= as_of:
            best = px
        else:
            break
    return best


def value_positions(
    qty: dict[str, float],
    as_of: date,
    closes_by: dict[str, list[tuple[date, float]]],
    kind_by: dict[str, str],
) -> Optional[float]:
    total = 0.0
    known = 0
    for tid, q in qty.items():
        series = closes_by.get(tid) or []
        px = last_close_on_or_before(series, as_of)
        if px is None:
            continue
        total += q * unit_rub(px, kind_by.get(tid, "equity"))
        known += 1
    if not known:
        return None
    return total


def _ops_from_db(session: Session) -> list[Operation]:
    rows = list(session.scalars(select(BcsOperation)))
    return [
        Operation(
            deal_id=r.deal_id,
            ticker=r.ticker,
            class_code=r.class_code,
            side=r.side,
            quantity=r.quantity,
            price=r.price,
            volume=r.volume,
            commission=r.commission,
            currency=r.currency,
            executed_at=r.executed_at,
        )
        for r in rows
    ]


def _kind_maps(
    session: Session, ops: Sequence[Operation]
) -> tuple[dict[str, str], dict[str, str]]:
    db_kind = {str(t.id).upper(): (t.kind or "equity") for t in session.scalars(select(Ticker))}
    kind_by: dict[str, str] = {}
    class_by: dict[str, str] = {}
    for op in ops:
        tid = (op.ticker or "").strip().upper()
        if not tid:
            continue
        if op.class_code:
            class_by[tid] = op.class_code
        kind_by[tid] = moex_kind(tid, op.class_code or class_by.get(tid, ""), db_kind.get(tid, ""))
    for tid, k in db_kind.items():
        kind_by.setdefault(tid, moex_kind(tid, "", k))
    return kind_by, class_by


def _series_from_points(points: Sequence) -> list[tuple[date, float]]:
    series: list[tuple[date, float]] = []
    for p in points:
        raw = (p.begin or p.end or "")[:10]
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        if p.close is None:
            continue
        series.append((d, float(p.close)))
    series.sort(key=lambda x: x[0])
    return series


def _fetch_one_close(
    tid: str,
    kind: str,
    *,
    from_date: str,
    till_date: str,
    interval: int,
    timeout: float,
) -> list[tuple[date, float]]:
    from portfolio_news.metrics_moex import fetch_candles

    last_err = ""
    for _attempt in range(2):
        try:
            points, _secid, _board, err = fetch_candles(
                tid,
                kind,
                interval=interval,
                from_date=from_date,
                till_date=till_date,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue
        if points:
            series = _series_from_points(points)
            if series:
                return series
        last_err = err or "empty"
    log.warning("capital replay no candles %s: %s", tid, last_err or "empty")
    return []


def _fetch_closes(
    tickers: Iterable[str],
    kind_by: dict[str, str],
    *,
    from_date: str,
    till_date: str,
    interval: int = 24,
    timeout: float = 16.0,
) -> dict[str, list[tuple[date, float]]]:
    ids = [t for t in tickers if t]
    out: dict[str, list[tuple[date, float]]] = {}
    if not ids:
        return out
    workers = min(8, len(ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                _fetch_one_close,
                tid,
                kind_by.get(tid, "equity"),
                from_date=from_date,
                till_date=till_date,
                interval=interval,
                timeout=timeout,
            ): tid
            for tid in ids
        }
        done = 0
        for fut in as_completed(futs):
            tid = futs[fut]
            done += 1
            try:
                series = fut.result()
            except Exception as exc:  # noqa: BLE001
                log.warning("capital replay %s: %s", tid, exc)
                continue
            if series:
                out[tid] = series
            if done % 10 == 0 or done == len(ids):
                log.info("capital closes %s/%s ok=%s", done, len(ids), len(out))
    return out


def journal_unit_prices(events: Sequence[dict]) -> dict[str, list[tuple[date, float]]]:
    """Per-ticker BUY prices from Snowball journal (already ₽ per unit, incl. bonds).

    Used as a fallback close when MOEX ISS has no candle for a held paper,
    so NAV isn't understated (fake dips) and no week is dropped (holes).
    """
    from portfolio_news.snowball_ledger import parse_day, parse_num

    out: dict[str, list[tuple[date, float]]] = {}
    for row in events:
        if (row.get("Event") or "").strip().upper() != "BUY":
            continue
        tid = (row.get("Symbol") or "").strip().upper()
        if not tid or tid == "RUB":
            continue
        d = parse_day(row.get("Date") or "")
        px = parse_num(row.get("Price") or "")
        if d is None or px <= 0:
            continue
        out.setdefault(tid, []).append((d, px))
    for tid in out:
        out[tid].sort(key=lambda x: x[0])
    return out


def value_positions_fallback(
    qty: dict[str, float],
    as_of: date,
    closes_by: dict[str, list[tuple[date, float]]],
    kind_by: dict[str, str],
    cost_by: dict[str, list[tuple[date, float]]],
) -> Optional[float]:
    """MOEX close if known, else last journal buy price (absolute ₽/unit)."""
    total = 0.0
    known = 0
    for tid, q in qty.items():
        px = last_close_on_or_before(closes_by.get(tid) or [], as_of)
        if px is not None:
            total += q * unit_rub(px, kind_by.get(tid, "equity"))
            known += 1
            continue
        cost = last_close_on_or_before(cost_by.get(tid) or [], as_of)
        if cost is not None:
            total += q * cost  # journal price already in ₽ per unit
            known += 1
    if not known:
        return None
    return total


def load_cached_closes(
    session: Session, tickers: Iterable[str]
) -> dict[str, list[tuple[date, float]]]:
    """Read persisted MOEX closes so a single ISS timeout can't wipe a ticker."""
    ids = [t for t in tickers if t]
    out: dict[str, list[tuple[date, float]]] = {}
    if not ids:
        return out
    rows = session.scalars(select(MoexClose).where(MoexClose.ticker.in_(ids)))
    for r in rows:
        try:
            d = date.fromisoformat(r.day)
        except ValueError:
            continue
        out.setdefault(r.ticker, []).append((d, float(r.close)))
    for tid in out:
        out[tid].sort(key=lambda x: x[0])
    return out


def save_closes(
    session: Session, closes_by: dict[str, list[tuple[date, float]]]
) -> int:
    """Persist freshly fetched closes (merge on composite PK)."""
    now = time.time()
    n = 0
    for tid, series in closes_by.items():
        for d, px in series:
            session.merge(
                MoexClose(ticker=tid, day=d.isoformat(), close=float(px), updated_at=now)
            )
            n += 1
    if n:
        session.commit()
    return n


def _closes_with_cache(
    session: Session,
    tickers: Iterable[str],
    kind_by: dict[str, str],
    *,
    from_date: str,
    till_date: str,
    last_needed: date,
    held_now: Optional[Iterable[str]] = None,
    interval: int = 7,
    timeout: float = 20.0,
) -> dict[str, list[tuple[date, float]]]:
    """Cached closes + fetch only missing/stale tickers; persist new ones.

    Staleness (cache ends before last needed week) only forces a refetch for
    tickers still held today — a sold paper legitimately has no recent closes,
    so we don't re-hammer ISS for it every rebuild.
    """
    ids = sorted({t for t in tickers if t})
    held = {t.strip().upper() for t in (held_now or ids) if t}
    cached = load_cached_closes(session, ids)
    stale_before = last_needed - timedelta(days=8)
    need = [
        t
        for t in ids
        if not cached.get(t) or (t in held and cached[t][-1][0] < stale_before)
    ]
    if need:
        log.info("capital closes: %s cached, refetch %s", len(ids) - len(need), len(need))
        fetched = _fetch_closes(
            need,
            kind_by,
            from_date=from_date,
            till_date=till_date,
            interval=interval,
            timeout=timeout,
        )
        save_closes(session, fetched)
        for tid, series in fetched.items():
            cached[tid] = series
    still_missing = [t for t in ids if not cached.get(t)]
    if still_missing:
        log.warning("capital closes still missing (ISS timeout?): %s", still_missing)
    return cached


def build_weekly_points(
    ops: Sequence[Operation],
    closes_by: dict[str, list[tuple[date, float]]],
    kind_by: dict[str, str],
    *,
    start: date = _OPS_START,
    end: Optional[date] = None,
) -> list[tuple[str, float]]:
    end_d = end or date.fromisoformat(today_local())
    # Last Friday on or before end (if end is Friday — include it).
    last_friday = end_d - timedelta(days=(end_d.weekday() - 4) % 7)
    points: list[tuple[str, float]] = []
    for friday in week_fridays(start, last_friday):
        qty = qty_as_of(ops, friday)
        if not qty:
            continue
        val = value_positions(qty, friday, closes_by, kind_by)
        if val is None or val <= 0:
            continue
        points.append((friday.isoformat(), val))
    return points


def _write_weekly_points(session: Session, points: list[tuple[str, float]]) -> list[dict]:
    today = today_local()
    today_row = session.get(CapitalDay, today)
    today_keep = None
    if today_row is not None and today_row.total_value:
        today_keep = (today_row.day, today_row.total_value, today_row.cash, today_row.currency)
    old = list(session.scalars(select(CapitalDay).where(CapitalDay.day < today)))
    for row in old:
        session.delete(row)
    session.commit()
    for day, val in points:
        upsert_capital_day(session, total_value=val, day=day)
    if today_keep:
        upsert_capital_day(
            session,
            total_value=today_keep[1],
            cash=today_keep[2],
            currency=today_keep[3] or "RUB",
            day=today_keep[0],
        )
    log.info("capital weekly replay: %s Fridays", len(points))
    return [{"day": d, "total_value": v} for d, v in points]


def rebuild_weekly_from_snowball(session: Session, csv_path: Optional[Path] = None) -> list[dict]:
    """Weekly NAV = Snowball book (qty+cash) × MOEX Friday close, from 2024-01."""
    from portfolio_news.snowball_ledger import book_as_of, find_snowball_csv, load_events

    path = find_snowball_csv(csv_path)
    if path is None:
        return []
    events = load_events(path)
    if not events:
        return []
    kind_by, _cc = _kind_maps(session, [])
    tickers: set[str] = set()
    for row in events:
        ev = (row.get("Event") or "").upper()
        if ev in ("BUY", "SELL", "REPAYMENT", "SPLIT"):
            tid = (row.get("Symbol") or "").strip().upper()
            if tid and tid != "RUB":
                tickers.add(tid)
                if tid not in kind_by:
                    kind_by[tid] = moex_kind(tid, "", "")
    today = today_local()
    start = _SNOWBALL_START
    end_d = date.fromisoformat(today)
    last_friday = end_d - timedelta(days=(end_d.weekday() - 4) % 7)
    held_now = set(book_as_of(events, last_friday).papers().keys())
    closes_by = _closes_with_cache(
        session,
        tickers,
        kind_by,
        from_date=start.isoformat(),
        till_date=today,
        last_needed=last_friday,
        held_now=held_now,
        interval=7,
        timeout=20.0,
    )
    cost_by = journal_unit_prices(events)
    points: list[tuple[str, float]] = []
    for friday in week_fridays(start, last_friday):
        book = book_as_of(events, friday)
        papers = book.papers()
        mtm = value_positions_fallback(papers, friday, closes_by, kind_by, cost_by)
        if mtm is None and not papers:
            val = book.cash
        elif mtm is None:
            continue
        else:
            val = mtm + book.cash
        if val <= 0:
            continue
        points.append((friday.isoformat(), val))
    return _write_weekly_points(session, points)


def rebuild_weekly_capital(session: Session) -> list[dict]:
    """Prefer Snowball journal; else BCS deals. Keep today's live point."""
    from portfolio_news.snowball_ledger import find_snowball_csv

    if find_snowball_csv() is not None:
        return rebuild_weekly_from_snowball(session)
    ops = _ops_from_db(session)
    if not ops:
        return []
    kind_by, _cc = _kind_maps(session, ops)
    tickers = sorted({(o.ticker or "").upper() for o in ops if o.ticker})
    today = today_local()
    closes_by = _fetch_closes(
        tickers,
        kind_by,
        from_date=_OPS_START.isoformat(),
        till_date=today,
    )
    points = build_weekly_points(ops, closes_by, kind_by)
    return _write_weekly_points(session, points)
