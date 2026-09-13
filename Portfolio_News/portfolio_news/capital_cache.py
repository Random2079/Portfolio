"""K6: daily portfolio total → capital curve (local date Asia/Yekaterinburg)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_news.db import CapitalDay

# Yekaterinburg = UTC+5 year-round (no DST). Avoid ZoneInfo/tzdata on Windows.
_TZ = timezone(timedelta(hours=5))


def today_local() -> str:
    return datetime.now(_TZ).date().isoformat()


def upsert_capital_day(
    session: Session,
    *,
    total_value: float,
    cash: Optional[float] = None,
    currency: str = "RUB",
    day: Optional[str] = None,
) -> CapitalDay:
    """One row per calendar day; later writes same day overwrite the total."""
    d = (day or today_local()).strip()
    row = session.get(CapitalDay, d)
    if row is None:
        row = CapitalDay(day=d)
        session.add(row)
    row.total_value = float(total_value)
    row.cash = cash
    row.currency = (currency or "RUB").strip() or "RUB"
    row.updated_at = time.time()
    session.commit()
    return row


def maybe_record_from_holdings(
    session: Session,
    *,
    total_value: Optional[float],
    cash: Optional[float] = None,
    currency: str = "RUB",
    ok: bool = True,
) -> Optional[CapitalDay]:
    """Record only when we have a real total (BCS answered)."""
    if not ok or total_value is None:
        return None
    try:
        tv = float(total_value)
    except (TypeError, ValueError):
        return None
    if tv <= 0:
        return None
    return upsert_capital_day(
        session,
        total_value=tv,
        cash=cash,
        currency=currency or "RUB",
    )


def bootstrap_today_from_day_snapshot(session: Session) -> Optional[CapitalDay]:
    """If capital empty for today but KA day_snapshot has total — copy it.

    Covers: BCS down now, but day block already shows a portfolio sum.
    """
    import json

    from portfolio_news.db import DaySnapshot

    today = today_local()
    if session.get(CapitalDay, today) is not None:
        return None
    row = session.get(DaySnapshot, 1)
    if row is None or not (row.payload_json or "").strip():
        return None
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    tv = data.get("total_value")
    return maybe_record_from_holdings(session, total_value=tv, ok=True)


def list_capital_days(
    session: Session,
    *,
    days: int = 90,
    bootstrap: bool = True,
) -> list[dict[str, Any]]:
    """Points from (today - days + 1) .. today, ascending."""
    if bootstrap:
        bootstrap_today_from_day_snapshot(session)
    n = max(1, min(int(days or 90), 1200))
    end = datetime.now(_TZ).date()
    start = end - timedelta(days=n - 1)
    start_s = start.isoformat()
    end_s = end.isoformat()
    rows = list(
        session.scalars(
            select(CapitalDay)
            .where(CapitalDay.day >= start_s, CapitalDay.day <= end_s)
            .order_by(CapitalDay.day)
        )
    )
    return [
        {
            "day": r.day,
            "total_value": r.total_value,
            "cash": r.cash,
            "currency": r.currency or "RUB",
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


def seed_days_for_tests(session: Session, points: Sequence[tuple[str, float]]) -> None:
    for day, total in points:
        upsert_capital_day(session, total_value=total, day=day)
