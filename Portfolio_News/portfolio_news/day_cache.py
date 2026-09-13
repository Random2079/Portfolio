"""SQLite persistence for KA day attribution (UI reads DB, MOEX only in background)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from portfolio_news.day_attribution import DayAttribution, DayContributor
from portfolio_news.db import DaySnapshot

log = logging.getLogger(__name__)

_SNAPSHOT_ID = 1


def _attr_from_payload(data: dict[str, Any], *, updated_at: float) -> DayAttribution:
    top_raw = data.get("top") or []
    top: list[DayContributor] = []
    for row in top_raw:
        if not isinstance(row, dict):
            continue
        top.append(
            DayContributor(
                ticker=str(row.get("ticker") or ""),
                name=str(row.get("name") or ""),
                day_rub=row.get("day_rub"),
                day_pct=row.get("day_pct"),
                weight_pct=row.get("weight_pct"),
                market_value=row.get("market_value"),
            )
        )
    return DayAttribution(
        ok=bool(data.get("ok")),
        error=str(data.get("error") or ""),
        total_value=data.get("total_value"),
        day_rub=data.get("day_rub"),
        day_pct=data.get("day_pct"),
        covered_value=data.get("covered_value"),
        missing=int(data.get("missing") or 0),
        top=top,
        fetched_at=float(data.get("fetched_at") or updated_at or 0.0),
        source=str(data.get("source") or "moex"),
        stale=bool(data.get("stale")),
    )


def save_day_snapshot(session: Session, attr: DayAttribution) -> None:
    payload = attr.to_dict()
    payload["stale"] = False
    now = time.time()
    row = session.get(DaySnapshot, _SNAPSHOT_ID)
    if row is None:
        row = DaySnapshot(id=_SNAPSHOT_ID)
        session.add(row)
    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.updated_at = now
    row.ok = 1 if attr.ok else 0
    session.commit()


def load_day_snapshot(session: Session) -> Optional[tuple[DayAttribution, float]]:
    """Return (attribution, updated_at) or None."""
    row = session.get(DaySnapshot, _SNAPSHOT_ID)
    if row is None or not (row.payload_json or "").strip():
        return None
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        log.warning("day snapshot JSON broken")
        return None
    if not isinstance(data, dict):
        return None
    attr = _attr_from_payload(data, updated_at=float(row.updated_at or 0.0))
    return attr, float(row.updated_at or 0.0)
