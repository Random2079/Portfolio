"""K7: payout calendar (dividends + coupons) for BCS holdings only.

MOEX is slow for 30+ papers, so the whole calendar lives in SQLite and is
rebuilt in a background thread (same idea as the day snapshot).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_news.db import CalendarCache, Ticker

log = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=5))  # Yekaterinburg, no DST
_CACHE_ID = 1
_MAX_EVENTS = 2500
_DEFAULT_AHEAD = 365
_HISTORY_START = date(2024, 1, 1)  # Snowball / user: from 2024 through today
_LAST_GOOD = Path(__file__).resolve().parent.parent / "data" / "calendar_last_good.json"
_lock = threading.Lock()
_running = False


@dataclass
class PayoutEvent:
    ticker: str
    name: str
    kind: str  # dividend | coupon | redemption
    pay_date: str  # YYYY-MM-DD
    per_unit: Optional[float] = None
    quantity: Optional[float] = None
    amount: Optional[float] = None  # per_unit * quantity when both known
    currency: str = "RUB"
    note: str = ""
    status: str = "upcoming"  # paid | upcoming | announced


@dataclass
class MonthTotal:
    month: str  # YYYY-MM
    amount: float = 0.0
    known: int = 0  # events with money
    unknown: int = 0  # events without value/qty
    coupon: float = 0.0
    dividend: float = 0.0
    redemption: float = 0.0


@dataclass
class CalendarPayload:
    ok: bool = False
    error: str = ""
    ahead_days: int = _DEFAULT_AHEAD
    today: str = ""
    built_at: float = 0.0
    total_amount: Optional[float] = None
    missing: int = 0  # papers without any known future payout
    events: list[PayoutEvent] = field(default_factory=list)
    months: list[MonthTotal] = field(default_factory=list)
    per_month: Optional[float] = None
    per_day: Optional[float] = None
    years: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def today_local() -> str:
    return datetime.now(_TZ).date().isoformat()


def _as_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def event_status(kind: str, pay: date, today: date, amount: Optional[float]) -> str:
    """paid = already passed; announced = future dividend or no sum; upcoming = scheduled money."""
    if pay < today:
        return "paid"
    if kind == "dividend" or amount is None:
        return "announced"
    return "upcoming"


def _window_start(today_d: date, back_days: Optional[int] = None) -> date:
    if back_days is not None and int(back_days) > 0:
        return today_d - timedelta(days=int(back_days))
    return _HISTORY_START


def _recompute_calendar_totals(
    events: list[dict[str, Any]],
    *,
    today: str,
    ahead_days: int,
    back_days: Optional[int] = None,
) -> dict[str, Any]:
    """Rebuild months / total_amount / per_* from event dicts (after qty patch)."""
    today_d = _as_date(today) or datetime.now(_TZ).date()
    start = _window_start(today_d, back_days)
    end = today_d + timedelta(days=max(1, int(ahead_days or _DEFAULT_AHEAD)))

    known = [float(e["amount"]) for e in events if e.get("amount") is not None]
    total = sum(known) if known else None

    by_month: dict[str, MonthTotal] = {}
    for e in events:
        key = str(e.get("pay_date") or "")[:7]
        if not key:
            continue
        row = by_month.get(key)
        if row is None:
            row = MonthTotal(month=key)
            by_month[key] = row
        if e.get("amount") is None:
            row.unknown += 1
        else:
            val = float(e["amount"])
            row.amount += val
            row.known += 1
            kind = str(e.get("kind") or "")
            if kind == "coupon":
                row.coupon += val
            elif kind == "dividend":
                row.dividend += val
            else:
                row.redemption += val
    months = [by_month[k] for k in sorted(by_month)]

    span_days = max(1, (end - start).days)
    per_day = (total / span_days) if total else None
    per_month = (per_day * 30.4) if per_day else None
    years = sorted({str(e.get("pay_date") or "")[:4] for e in events if e.get("pay_date")})

    return {
        "events": events,
        "months": [asdict(m) for m in months],
        "total_amount": total,
        "per_month": per_month,
        "per_day": per_day,
        "years": years,
        "today": today_d.isoformat(),
        "ahead_days": int(ahead_days or _DEFAULT_AHEAD),
    }


def apply_quantities(
    data: dict[str, Any],
    qty_by_ticker: dict[str, float],
    *,
    only_own: bool = True,
) -> dict[str, Any]:
    """Patch cached calendar with live BCS quantities → amount = per_unit × qty.

    When ``only_own`` and qty map is non-empty, drop events for tickers not in holdings
    (fallback rebuilds sometimes dump the whole bond universe from tickers DB).
    """
    if not isinstance(data, dict):
        return data
    qty_by = {
        str(k).strip().upper(): float(v)
        for k, v in (qty_by_ticker or {}).items()
        if k and v is not None and float(v)
    }
    today_s = str(data.get("today") or "") or today_local()
    today_d = _as_date(today_s) or datetime.now(_TZ).date()
    ahead = int(data.get("ahead_days") or _DEFAULT_AHEAD)

    events_out: list[dict[str, Any]] = []
    for raw in data.get("events") or []:
        if not isinstance(raw, dict):
            continue
        tid = str(raw.get("ticker") or "").strip().upper()
        e = dict(raw)
        e["ticker"] = tid
        if only_own and qty_by and tid not in qty_by:
            # keep journal history (already has ₽); drop leftover universe rows
            if e.get("amount") is None:
                continue
        qty = qty_by.get(tid)
        if qty is not None:
            e["quantity"] = qty
            per = e.get("per_unit")
            # Journal rows already have ₽ — do not rebuild from today's qty.
            if e.get("amount") is None and per is not None:
                try:
                    e["amount"] = float(per) * qty
                except (TypeError, ValueError):
                    pass
        pay = _as_date(str(e.get("pay_date") or ""))
        if pay is not None:
            e["status"] = event_status(str(e.get("kind") or ""), pay, today_d, e.get("amount"))
        events_out.append(e)

    events_out.sort(key=lambda x: (str(x.get("pay_date") or ""), str(x.get("ticker") or "")))
    patched = dict(data)
    patched.update(
        _recompute_calendar_totals(
            events_out,
            today=today_d.isoformat(),
            ahead_days=ahead,
        )
    )
    patched["ok"] = True
    return patched


def build_events(
    *,
    dividends: Sequence[Any],
    coupons: Sequence[Any],
    qty_by_ticker: dict[str, float],
    today: str,
    ahead_days: int = _DEFAULT_AHEAD,
    back_days: Optional[int] = None,
    redemptions: Sequence[Any] = (),
) -> CalendarPayload:
    """Merge dividends / coupons / redemptions in [2024-01-01 .. today+ahead]."""
    today_d = _as_date(today) or datetime.now(_TZ).date()
    start = _window_start(today_d, back_days)
    end = today_d + timedelta(days=max(1, int(ahead_days or _DEFAULT_AHEAD)))
    events: list[PayoutEvent] = []
    seen_tickers: set[str] = set()

    def qty_for(tid: str) -> Optional[float]:
        return qty_by_ticker.get((tid or "").strip().upper())

    def add(
        *,
        tid: str,
        name: str,
        kind: str,
        d: date,
        per: Optional[float],
        currency: str,
        note: str,
    ) -> None:
        if d < start or d > end:
            return
        qty = qty_for(tid)
        amount = None
        if per is not None and qty:
            amount = float(per) * float(qty)
        seen_tickers.add(tid)
        events.append(
            PayoutEvent(
                ticker=tid,
                name=name or tid,
                kind=kind,
                pay_date=d.isoformat(),
                per_unit=per,
                quantity=qty,
                amount=amount,
                currency=currency or "RUB",
                note=note,
                status=event_status(kind, d, today_d, amount),
            )
        )

    for row in dividends:
        if getattr(row, "error", ""):
            continue
        d = _as_date(getattr(row, "registryclosedate", ""))
        if d is None:
            continue
        tid = (getattr(row, "ticker_id", "") or "").strip().upper()
        add(
            tid=tid,
            name=getattr(row, "name", "") or tid,
            kind="dividend",
            d=d,
            per=getattr(row, "value", None),
            currency=(getattr(row, "currencyid", "") or "RUB") or "RUB",
            note="дата закрытия реестра",
        )

    for row in coupons:
        if getattr(row, "error", ""):
            continue
        d = _as_date(getattr(row, "coupondate", ""))
        if d is None:
            continue
        tid = (getattr(row, "ticker_id", "") or "").strip().upper()
        add(
            tid=tid,
            name=getattr(row, "name", "") or tid,
            kind="coupon",
            d=d,
            per=getattr(row, "value", None),
            currency=(getattr(row, "currencyid", "") or "RUB") or "RUB",
            note="купон",
        )

    for row in redemptions:
        if getattr(row, "error", ""):
            continue
        d = _as_date(getattr(row, "amortdate", ""))
        if d is None:
            continue
        tid = (getattr(row, "ticker_id", "") or "").strip().upper()
        add(
            tid=tid,
            name=getattr(row, "name", "") or tid,
            kind="redemption",
            d=d,
            per=getattr(row, "value", None),
            currency=(getattr(row, "currencyid", "") or "RUB") or "RUB",
            note="погашение",
        )

    events.sort(key=lambda e: (e.pay_date, e.ticker))
    events = events[:_MAX_EVENTS]

    known = [e.amount for e in events if e.amount is not None]
    total = sum(known) if known else None
    missing = len([t for t in qty_by_ticker if t not in seen_tickers])

    by_month: dict[str, MonthTotal] = {}
    for e in events:
        key = e.pay_date[:7]
        row = by_month.get(key)
        if row is None:
            row = MonthTotal(month=key)
            by_month[key] = row
        if e.amount is None:
            row.unknown += 1
        else:
            val = float(e.amount)
            row.amount += val
            row.known += 1
            if e.kind == "coupon":
                row.coupon += val
            elif e.kind == "dividend":
                row.dividend += val
            else:
                row.redemption += val
    months = [by_month[k] for k in sorted(by_month)]

    span_days = max(1, (end - start).days)
    per_day = (total / span_days) if total else None
    per_month = (per_day * 30.4) if per_day else None

    years = sorted({e.pay_date[:4] for e in events if e.pay_date})

    return CalendarPayload(
        ok=True,
        ahead_days=int(ahead_days or _DEFAULT_AHEAD),
        today=today_d.isoformat(),
        built_at=time.time(),
        total_amount=total,
        missing=missing,
        events=events,
        months=months,
        per_month=per_month,
        per_day=per_day,
        years=years,
    )


def _bond_event_count(data: Optional[dict[str, Any]]) -> int:
    if not data:
        return 0
    n = 0
    for e in data.get("events") or []:
        if isinstance(e, dict) and e.get("kind") in ("coupon", "redemption"):
            n += 1
    return n


def would_wipe_bonds(old: Optional[dict[str, Any]], new: dict[str, Any]) -> bool:
    """True if new payload drops all coupons/redemptions that we already had."""
    return _bond_event_count(old) > 0 and _bond_event_count(new) == 0


def _write_last_good(data: dict[str, Any]) -> None:
    if _bond_event_count(data) == 0:
        return
    try:
        _LAST_GOOD.parent.mkdir(parents=True, exist_ok=True)
        _LAST_GOOD.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("calendar last-good write failed: %s", exc)


def load_last_good_file() -> Optional[dict[str, Any]]:
    if not _LAST_GOOD.is_file():
        return None
    try:
        data = json.loads(_LAST_GOOD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and _bond_event_count(data) > 0:
        return data
    return None


def save_calendar(session: Session, payload: CalendarPayload) -> bool:
    """Write SQLite cache. Refuses to replace a coupon-rich list with empty/divs-only."""
    incoming = payload.to_dict()
    loaded = load_calendar(session)
    old = loaded[0] if loaded else None
    if would_wipe_bonds(old, incoming):
        log.warning(
            "calendar save skipped — would wipe %s coupon/redemption events",
            _bond_event_count(old),
        )
        return False
    row = session.get(CalendarCache, _CACHE_ID)
    if row is None:
        row = CalendarCache(id=_CACHE_ID)
        session.add(row)
    row.payload_json = json.dumps(incoming, ensure_ascii=False)
    row.updated_at = time.time()
    row.ok = 1 if payload.ok else 0
    session.commit()
    _write_last_good(incoming)
    return True


def load_calendar(session: Session) -> Optional[tuple[dict[str, Any], float]]:
    row = session.get(CalendarCache, _CACHE_ID)
    if row is None or not (row.payload_json or "").strip():
        return None
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        log.warning("calendar cache JSON broken")
        return None
    if not isinstance(data, dict):
        return None
    return data, float(row.updated_at or 0.0)


def _dividends_from_cached_events(events: list[Any]) -> list[Any]:
    from portfolio_news.metrics_moex import DividendRow

    out = []
    for e in events:
        if not isinstance(e, dict) or e.get("kind") != "dividend":
            continue
        out.append(
            DividendRow(
                ticker_id=str(e.get("ticker") or ""),
                name=str(e.get("name") or ""),
                registryclosedate=str(e.get("pay_date") or ""),
                value=e.get("per_unit"),
                currencyid=str(e.get("currency") or "RUB"),
            )
        )
    return out


def _dividends_only_from_tickers(db: Session, *, ahead_days: int) -> bool:
    """When coupon cache was wiped and BCS is down — still show stock dividends."""
    from portfolio_news.dividends_smartlab import fetch_smartlab_dividends

    eq_ids = {
        str(t.id).upper()
        for t in db.scalars(select(Ticker)).all()
        if (t.kind or "equity") in ("equity", "fund")
    }
    if not eq_ids:
        return False
    sl = [r for r in fetch_smartlab_dividends() if (r.ticker_id or "").upper() in eq_ids]
    if not sl:
        return False
    payload = build_events(
        dividends=sl,
        coupons=[],
        qty_by_ticker={},
        today=today_local(),
        ahead_days=ahead_days,
        back_days=None,
    )
    if not save_calendar(db, payload):
        return False
    log.info("calendar dividends-only: %s events", len(payload.events))
    return True


def _coupons_from_bond_tickers(db: Session, *, ahead_days: int) -> bool:
    """Rebuild coupons/redemptions from tickers.kind=bond — no BCS qty needed."""
    from portfolio_news.metrics_moex import fetch_bondization_for

    items = [
        (str(t.id), "bond", t.name or str(t.id))
        for t in db.scalars(select(Ticker)).all()
        if (t.kind or "") == "bond"
    ]
    if not items:
        return False
    coupons, amorts = fetch_bondization_for(items)
    ok_coupons = [r for r in coupons if not getattr(r, "error", "")]
    if not ok_coupons and not amorts:
        return False

    cached = load_calendar(db)
    events = (cached[0].get("events") or []) if cached else []
    divs = _dividends_from_cached_events(events)
    if not divs:
        from portfolio_news.dividends_smartlab import fetch_smartlab_dividends

        eq_ids = {
            str(t.id).upper()
            for t in db.scalars(select(Ticker)).all()
            if (t.kind or "equity") in ("equity", "fund")
        }
        divs = [r for r in fetch_smartlab_dividends() if (r.ticker_id or "").upper() in eq_ids]

    payload = build_events(
        dividends=divs,
        coupons=ok_coupons,
        redemptions=amorts,
        qty_by_ticker={},
        today=today_local(),
        ahead_days=ahead_days,
        back_days=None,
    )
    if not save_calendar(db, payload):
        return False
    log.info(
        "calendar coupons-from-tickers: %s coupons, %s amorts, %s events",
        len(ok_coupons),
        len(amorts),
        len(payload.events),
    )
    return True


def _restore_last_good(db: Session) -> bool:
    data = load_last_good_file()
    if not data:
        return False
    loaded = load_calendar(db)
    old = loaded[0] if loaded else None
    if _bond_event_count(old) >= _bond_event_count(data):
        return False
    row = db.get(CalendarCache, _CACHE_ID)
    if row is None:
        row = CalendarCache(id=_CACHE_ID)
        db.add(row)
    row.payload_json = json.dumps(data, ensure_ascii=False)
    row.updated_at = time.time()
    row.ok = 1
    db.commit()
    log.info("calendar restored from last-good file (%s bond events)", _bond_event_count(data))
    return True


def _refresh_dividends_on_cache(db: Session, *, ahead_days: int) -> bool:
    """Add Smart-Lab dividends onto last coupon/redemption list. No BCS needed."""
    from portfolio_news.dividends_smartlab import fetch_smartlab_dividends
    from portfolio_news.metrics_moex import AmortRow, CouponRow

    cached = load_calendar(db)
    if not cached:
        return False
    data, _upd = cached
    events = data.get("events") or []
    if not any(isinstance(e, dict) and e.get("kind") in ("coupon", "redemption") for e in events):
        return False

    qty_by: dict[str, float] = {}
    own: set[str] = set()
    for e in events:
        if not isinstance(e, dict):
            continue
        tid = str(e.get("ticker") or "").upper()
        if tid:
            own.add(tid)
        q = e.get("quantity")
        if tid and q:
            qty_by[tid] = float(q)

    eq_ids = {
        str(t.id).upper()
        for t in db.scalars(select(Ticker)).all()
        if (t.kind or "equity") in ("equity", "fund")
    }
    own |= eq_ids
    sl = [r for r in fetch_smartlab_dividends() if (r.ticker_id or "").upper() in own]
    # also keep tickers that only appear on Smart-Lab if already in qty_by
    coupons = [
        CouponRow(
            ticker_id=str(e.get("ticker") or ""),
            name=str(e.get("name") or ""),
            coupondate=str(e.get("pay_date") or ""),
            value=e.get("per_unit"),
            currencyid=str(e.get("currency") or "RUB"),
        )
        for e in events
        if e.get("kind") == "coupon"
    ]
    amorts = [
        AmortRow(
            ticker_id=str(e.get("ticker") or ""),
            name=str(e.get("name") or ""),
            amortdate=str(e.get("pay_date") or ""),
            value=e.get("per_unit"),
            currencyid=str(e.get("currency") or "RUB"),
        )
        for e in events
        if e.get("kind") == "redemption"
    ]
    payload = build_events(
        dividends=sl,
        coupons=coupons,
        redemptions=amorts,
        qty_by_ticker=qty_by,
        today=today_local(),
        ahead_days=ahead_days,
        back_days=None,
    )
    save_calendar(db, payload)
    log.info("calendar dividends patched: %s divs, total events %s", len(sl), len(payload.events))
    return True


def refresh_calendar(
    SessionLocal: sessionmaker,
    *,
    ahead_days: int = _DEFAULT_AHEAD,
) -> bool:
    """One MOEX pass over own papers → SQLite. Skipped if already running."""
    global _running
    if not _lock.acquire(blocking=False):
        log.info("calendar refresh skipped — already running")
        return False
    _running = True
    try:
        from portfolio_news.bcs_client import get_bcs_client
        from portfolio_news.bcs_scope import ensure_tickers_from_holdings
        from portfolio_news.config import get_settings
        from portfolio_news.metrics_moex import fetch_bondization_for, fetch_dividends_for

        cfg = get_settings()
        client = get_bcs_client(
            refresh_token=cfg.bcs_trade_refresh_token,
            client_id=cfg.bcs_trade_client_id or "trade-api-read",
        )
        snap = client.fetch_holdings(force=False)
        db = SessionLocal()
        try:
            if not snap.configured or (not snap.ok and not snap.holdings):
                # Keep last good calendar; never write an empty/divs-only over coupons.
                if _refresh_dividends_on_cache(db, ahead_days=ahead_days):
                    return True
                cached = load_calendar(db)
                has_bonds = bool(cached and _bond_event_count(cached[0]) > 0)
                if not has_bonds and _restore_last_good(db):
                    return True
                if not has_bonds and _coupons_from_bond_tickers(db, ahead_days=ahead_days):
                    return True
                if _dividends_only_from_tickers(db, ahead_days=ahead_days):
                    return True
                log.warning("calendar refresh: holdings down, cache kept")
                return False

            ensure_tickers_from_holdings(db, snap.holdings)

            qty_by: dict[str, float] = {}
            div_items: list[tuple[str, str, str]] = []
            coupon_items: list[tuple[str, str, str]] = []
            for h in snap.holdings:
                ac = (h.asset_class or "").strip().lower()
                if ac == "cash":
                    continue
                tid = (h.ticker or h.sec_code or "").strip().upper()
                if not tid:
                    continue
                if h.quantity:
                    qty_by[tid] = float(h.quantity)
                name = (h.name or tid).strip()
                if ac == "bond" or tid.startswith("RU000"):
                    coupon_items.append((tid, "bond", name))
                else:
                    div_items.append((tid, "fund" if ac == "fund" else "equity", name))

            from portfolio_news.dividends_smartlab import fetch_smartlab_dividends

            own_eq = {tid for tid, _k, _n in div_items}
            sl_divs = [
                r
                for r in fetch_smartlab_dividends()
                if (r.ticker_id or "").upper() in own_eq
            ]
            dividends = sl_divs
            # ISS /securities/.../dividends.json now returns empty description — skip unless SmartLab failed
            if not dividends:
                iss_divs = fetch_dividends_for(div_items)
                dividends = [r for r in iss_divs if not getattr(r, "error", "")]

            from portfolio_news.metrics_moex import AmortRow, CouponRow

            cached = load_calendar(db)
            cache_events = (cached[0].get("events") or []) if cached else []
            reuse = any(
                isinstance(e, dict) and e.get("kind") == "coupon" for e in cache_events
            )
            if reuse:
                coupons = [
                    CouponRow(
                        ticker_id=str(e.get("ticker") or ""),
                        name=str(e.get("name") or ""),
                        coupondate=str(e.get("pay_date") or ""),
                        value=e.get("per_unit"),
                        currencyid=str(e.get("currency") or "RUB"),
                    )
                    for e in cache_events
                    if e.get("kind") == "coupon"
                ]
                amorts = [
                    AmortRow(
                        ticker_id=str(e.get("ticker") or ""),
                        name=str(e.get("name") or ""),
                        amortdate=str(e.get("pay_date") or ""),
                        value=e.get("per_unit"),
                        currencyid=str(e.get("currency") or "RUB"),
                    )
                    for e in cache_events
                    if e.get("kind") == "redemption"
                ]
            else:
                coupons, amorts = fetch_bondization_for(coupon_items)
            payload = build_events(
                dividends=dividends,
                coupons=coupons,
                redemptions=amorts,
                qty_by_ticker=qty_by,
                today=today_local(),
                ahead_days=ahead_days,
                back_days=None,
            )
            save_calendar(db, payload)
            merge_journal_history(db, ahead_days=ahead_days)
            log.info(
                "calendar built: %s events, total=%s, missing=%s",
                len(payload.events),
                payload.total_amount,
                payload.missing,
            )
            return True
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar refresh failed: %s", exc)
        return False
    finally:
        _running = False
        _lock.release()


def _event_key(e: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(e.get("pay_date") or "")[:10],
        str(e.get("ticker") or "").upper(),
        str(e.get("kind") or ""),
    )


def merge_journal_history(session: Session, *, ahead_days: int = _DEFAULT_AHEAD) -> bool:
    """Past payouts from Snowball journal (2024 → today) + keep future from cache."""
    from portfolio_news.snowball_ledger import (
        calendar_rows_from_journal,
        find_snowball_csv,
        load_events,
    )

    path = find_snowball_csv()
    if path is None:
        return False
    today_d = _as_date(today_local()) or datetime.now(_TZ).date()
    names = {str(t.id).upper(): (t.name or t.id) for t in session.scalars(select(Ticker))}
    hist = calendar_rows_from_journal(
        load_events(path),
        start=_HISTORY_START,
        end=today_d,
        names=names,
    )
    if not hist:
        return False

    cached = load_calendar(session)
    future: list[dict[str, Any]] = []
    if cached:
        for e in cached[0].get("events") or []:
            if not isinstance(e, dict):
                continue
            d = str(e.get("pay_date") or "")[:10]
            if d > today_d.isoformat():
                future.append(e)

    by: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in hist:
        by[_event_key(e)] = e
    for e in future:
        k = _event_key(e)
        if k not in by:
            by[k] = dict(e)

    merged = sorted(by.values(), key=lambda x: (str(x.get("pay_date") or ""), str(x.get("ticker") or "")))
    merged = merged[:_MAX_EVENTS]
    for e in merged:
        pay = _as_date(str(e.get("pay_date") or ""))
        if pay is not None:
            e["status"] = event_status(str(e.get("kind") or ""), pay, today_d, e.get("amount"))

    totals = _recompute_calendar_totals(
        merged,
        today=today_d.isoformat(),
        ahead_days=ahead_days,
    )
    row = session.get(CalendarCache, _CACHE_ID)
    if row is None:
        row = CalendarCache(id=_CACHE_ID)
        session.add(row)
    payload = {"ok": True, "error": "", **totals}
    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.updated_at = time.time()
    row.ok = 1
    session.commit()
    _write_last_good(payload)
    log.info(
        "calendar journal merge: %s hist + %s future → %s events, years=%s",
        len(hist),
        len(future),
        len(merged),
        totals.get("years"),
    )
    return True


def calendar_running() -> bool:
    return _running
