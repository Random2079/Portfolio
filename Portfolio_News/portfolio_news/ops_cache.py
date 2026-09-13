"""K2: SQLite cache for BCS executed deals (dedupe by deal_id)."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_news.bcs_client import Operation, OperationsSnapshot
from portfolio_news.db import BcsOperation

log = logging.getLogger(__name__)


def stable_deal_id(op: Operation) -> str:
    """Prefer broker id; else fingerprint so empty-id rows still dedupe."""
    raw = (op.deal_id or "").strip()
    if raw:
        return raw[:128]
    blob = "|".join(
        [
            (op.ticker or "").upper(),
            (op.side or "").lower(),
            op.executed_at or "",
            str(op.quantity or ""),
            str(op.price or ""),
            str(op.volume or ""),
            (op.class_code or "").upper(),
        ]
    )
    return "fp_" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:40]


def upsert_operations(session: Session, ops: list[Operation]) -> int:
    """Insert/update rows; return number of new inserts."""
    inserted = 0
    for op in ops:
        did = stable_deal_id(op)
        row = session.get(BcsOperation, did)
        if row is None:
            row = BcsOperation(deal_id=did)
            session.add(row)
            inserted += 1
        row.ticker = (op.ticker or "")[:64]
        row.class_code = (op.class_code or "")[:32]
        row.side = (op.side or "")[:16]
        row.quantity = op.quantity
        row.price = op.price
        row.volume = op.volume
        row.commission = op.commission
        row.currency = (op.currency or "RUB")[:16]
        row.executed_at = (op.executed_at or "")[:64]
        row.updated_at = time.time()
    session.commit()
    return inserted


def list_cached_operations(
    session: Session,
    *,
    ticker: str = "",
    limit: int = 100,
) -> list[Operation]:
    q = select(BcsOperation).order_by(
        BcsOperation.executed_at.desc(), BcsOperation.deal_id.desc()
    )
    tid = (ticker or "").strip().upper()
    if tid:
        q = q.where(BcsOperation.ticker == tid)
    if limit and limit > 0:
        q = q.limit(limit)
    rows = session.scalars(q).all()
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


def cache_count(session: Session) -> int:
    return len(session.scalars(select(BcsOperation.deal_id)).all())


def merge_live_into_cache(
    session: Session,
    snap: OperationsSnapshot,
) -> OperationsSnapshot:
    """If live snap ok — upsert; always attach cache metadata."""
    if snap.ok and snap.operations:
        n = upsert_operations(session, snap.operations)
        log.info("BCS ops cache upsert: +%s new (batch %s)", n, len(snap.operations))
    return snap


def snapshot_from_cache(
    session: Session,
    *,
    configured: bool,
    ticker: str = "",
    limit: int = 100,
    error: str = "",
    live_ok: Optional[bool] = None,
) -> OperationsSnapshot:
    ops = list_cached_operations(session, ticker=ticker, limit=limit)
    # ok if we have rows OR live succeeded with empty
    ok = bool(ops) or (live_ok is True)
    err = error
    if not ops and error:
        ok = False
    elif ops and error:
        # stale-ish: show cache + note
        ok = True
    return OperationsSnapshot(
        configured=configured,
        ok=ok,
        error=err,
        fetched_at=time.time(),
        operations=ops,
        raw_keys=["sqlite_cache"],
    )
