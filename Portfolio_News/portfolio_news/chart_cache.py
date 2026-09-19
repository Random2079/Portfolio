"""K3: SQLite cache for MOEX daily candles (разбор бумаги).

Full ISS history is slow; serve from cache and only refresh the tail.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from portfolio_news.db import ChartCandleCache
from portfolio_news.metrics_moex import CandlePoint, candle_to_dict, fetch_candles

log = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=5))  # Yekaterinburg
_FRESH_SEC = 6 * 3600  # same-session reuse


def today_local() -> str:
    return datetime.now(_TZ).date().isoformat()


def _day_key(begin: str) -> str:
    t = (begin or "").strip()
    return t[:10] if t else ""


def points_from_dicts(rows: list[dict[str, Any]]) -> list[CandlePoint]:
    out: list[CandlePoint] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        begin = str(r.get("begin") or r.get("time") or "").strip()
        close = r.get("close")
        if not begin and close is None:
            continue
        try:
            c_close = float(close) if close is not None else None
        except (TypeError, ValueError):
            c_close = None
        out.append(
            CandlePoint(
                begin=begin,
                end=str(r.get("end") or ""),
                open=_opt_f(r.get("open")),
                close=c_close,
                high=_opt_f(r.get("high")),
                low=_opt_f(r.get("low")),
                volume=_opt_f(r.get("volume")),
                value=_opt_f(r.get("value")),
            )
        )
    out.sort(key=lambda p: _day_key(p.begin))
    return out


def _opt_f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def merge_candle_points(
    older: list[CandlePoint], newer: list[CandlePoint]
) -> list[CandlePoint]:
    by_day: dict[str, CandlePoint] = {}
    for p in older + newer:
        dk = _day_key(p.begin)
        if not dk:
            continue
        by_day[dk] = p
    return [by_day[k] for k in sorted(by_day.keys())]


def load_chart_cache(session: Session, ticker: str) -> Optional[dict[str, Any]]:
    tid = (ticker or "").strip().upper()
    if not tid:
        return None
    row = session.get(ChartCandleCache, tid)
    if row is None or not (row.payload_json or "").strip():
        return None
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    data["_updated_at"] = float(row.updated_at or 0.0)
    data["_ok"] = bool(row.ok)
    return data


def save_chart_cache(
    session: Session,
    *,
    ticker: str,
    candles: list[CandlePoint],
    secid: str = "",
    board: str = "",
    kind: str = "equity",
    interval: int = 24,
) -> None:
    tid = (ticker or "").strip().upper()
    if not tid or not candles:
        return
    payload = {
        "ticker": tid,
        "kind": kind,
        "secid": secid or "",
        "board": board or "",
        "interval": int(interval) or 24,
        "candles": [candle_to_dict(p) for p in candles],
        "n_candles": len(candles),
        "last_day": _day_key(candles[-1].begin) if candles else "",
    }
    row = session.get(ChartCandleCache, tid)
    if row is None:
        row = ChartCandleCache(ticker=tid)
        session.add(row)
    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.updated_at = time.time()
    row.ok = 1
    session.commit()


def cache_is_fresh(updated_at: float, last_day: str) -> bool:
    """Fresh if written recently, or last candle is today/yesterday (weekend gap)."""
    now = time.time()
    if updated_at and (now - float(updated_at)) <= _FRESH_SEC:
        return True
    today = today_local()
    ld = (last_day or "")[:10]
    if not ld:
        return False
    if ld >= today:
        return True
    # Fri candle on Sat/Sun still ok
    try:
        d_today = datetime.now(_TZ).date()
        d_last = datetime.strptime(ld, "%Y-%m-%d").date()
        if (d_today - d_last).days <= 3:
            return True
    except ValueError:
        pass
    return False


def resolve_chart_candles(
    session: Session,
    ticker: str,
    kind: str = "equity",
    *,
    isin: str = "",
    days: int = 0,
    interval: int = 24,
    force: bool = False,
) -> tuple[list[CandlePoint], str, str, str, bool, bool]:
    """Returns (points, secid, board, error, from_cache, stale)."""
    from datetime import date, timedelta

    tid = (ticker or "").strip().upper()
    resolved_kind = (kind or "equity").strip().lower() or "equity"
    from_date = ""
    if int(days) > 0:
        from_date = (date.today() - timedelta(days=int(days))).isoformat()
    candle_limit = 0 if int(days) == 0 else min(4000, max(int(days) + 50, 100))
    full_timeout = 45.0 if int(days) == 0 else 12.0

    cached = load_chart_cache(session, tid)
    cached_pts = points_from_dicts((cached or {}).get("candles") or [])
    cached_secid = str((cached or {}).get("secid") or "")
    cached_board = str((cached or {}).get("board") or "")
    last_day = str((cached or {}).get("last_day") or "")
    if not last_day and cached_pts:
        last_day = _day_key(cached_pts[-1].begin)
    updated_at = float((cached or {}).get("_updated_at") or 0.0)

    if cached_pts and not force and cache_is_fresh(updated_at, last_day):
        return cached_pts, cached_secid, cached_board, "", True, False

    # Stale cache → incremental tail (cheap) instead of full history.
    if cached_pts and not force and last_day:
        new_pts, secid, board, err = fetch_candles(
            tid,
            resolved_kind,
            interval=int(interval) or 24,
            from_date=last_day,
            limit=80,
            isin=isin,
            timeout=15.0,
        )
        if new_pts:
            merged = merge_candle_points(cached_pts, new_pts)
            try:
                save_chart_cache(
                    session,
                    ticker=tid,
                    candles=merged,
                    secid=secid or cached_secid,
                    board=board or cached_board,
                    kind=resolved_kind,
                    interval=int(interval) or 24,
                )
            except Exception:  # noqa: BLE001
                log.warning("chart cache save failed for %s", tid, exc_info=True)
            return merged, secid or cached_secid, board or cached_board, "", False, False
        # MOEX down → stale cache better than empty
        if cached_pts:
            return (
                cached_pts,
                cached_secid,
                cached_board,
                err or "",
                True,
                True,
            )

    points, secid, board, err = fetch_candles(
        tid,
        resolved_kind,
        interval=int(interval) or 24,
        from_date=from_date,
        limit=candle_limit,
        isin=isin,
        timeout=full_timeout,
    )
    if points:
        try:
            save_chart_cache(
                session,
                ticker=tid,
                candles=points,
                secid=secid,
                board=board,
                kind=resolved_kind,
                interval=int(interval) or 24,
            )
        except Exception:  # noqa: BLE001
            log.warning("chart cache save failed for %s", tid, exc_info=True)
        return points, secid, board, err or "", False, False

    if cached_pts:
        return cached_pts, cached_secid, cached_board, err or "", True, True
    return [], secid, board, err or "", False, False
