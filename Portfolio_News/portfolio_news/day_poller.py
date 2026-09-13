"""Background MOEX → SQLite day snapshot (default every 60s). No UI button required."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from portfolio_news.bcs_client import get_bcs_client
from portfolio_news.config import get_settings
from portfolio_news.day_attribution import build_day_attribution, clear_day_cache
from portfolio_news.day_cache import save_day_snapshot
from portfolio_news.db import Ticker

log = logging.getLogger(__name__)

_lock = threading.Lock()
_running = False
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_last_ok_at = 0.0
_last_error = ""


def _bcs():
    cfg = get_settings()
    return get_bcs_client(
        refresh_token=cfg.bcs_trade_refresh_token,
        client_id=cfg.bcs_trade_client_id or "trade-api-read",
    )


def day_poll_status() -> dict:
    return {
        "running": _running or (_thread is not None and _thread.is_alive()),
        "last_ok_at": _last_ok_at,
        "last_error": _last_error,
    }


def refresh_day_snapshot(SessionLocal: sessionmaker, *, force_moex: bool = True) -> bool:
    """One MOEX pass → SQLite. Skip if another refresh is in progress."""
    global _running, _last_ok_at, _last_error
    if not _lock.acquire(blocking=False):
        log.info("day refresh skipped — already running")
        return False
    _running = True
    try:
        client = _bcs()
        snap = client.fetch_holdings(force=False)
        if not snap.configured or (not snap.ok and not snap.holdings):
            _last_error = snap.error or "holdings unavailable"
            log.warning("day refresh: %s", _last_error)
            return False

        db = SessionLocal()
        try:
            kind_by: dict[str, str] = {}
            for t in db.scalars(select(Ticker)).all():
                kind_by[str(t.id).upper()] = t.kind or "equity"
            if force_moex:
                clear_day_cache()
            attr = build_day_attribution(
                list(snap.holdings),
                kind_by_ticker=kind_by,
                top_n=8,
                force=force_moex,
            )
            if snap.total_value is not None:
                attr.total_value = snap.total_value
            save_day_snapshot(db, attr)
            from portfolio_news.capital_cache import maybe_record_from_holdings

            # Prefer live BCS total; else whatever day attribution kept
            maybe_record_from_holdings(
                db,
                total_value=snap.total_value
                if snap.total_value is not None
                else attr.total_value,
                cash=snap.cash,
                currency=snap.currency or "RUB",
                ok=bool(snap.ok or snap.holdings or attr.total_value),
            )
            if attr.ok:
                _last_ok_at = time.time()
                _last_error = ""
            else:
                _last_error = attr.error or "day not ok"
            log.info(
                "day snapshot saved ok=%s missing=%s day_rub=%s",
                attr.ok,
                attr.missing,
                attr.day_rub,
            )
            return bool(attr.ok)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        _last_error = str(exc)
        log.warning("day refresh failed: %s", exc)
        return False
    finally:
        _running = False
        _lock.release()


def start_day_poller(
    SessionLocal: sessionmaker,
    *,
    interval_sec: int = 60,
) -> None:
    """Daemon loop: refresh every interval_sec. Idempotent."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    interval = max(30, int(interval_sec or 60))

    def _loop() -> None:
        # first fill soon after startup (don't block uvicorn boot)
        time.sleep(1.0)
        while not _stop.is_set():
            t0 = time.time()
            refresh_day_snapshot(SessionLocal, force_moex=True)
            elapsed = time.time() - t0
            wait = max(1.0, interval - elapsed)
            _stop.wait(wait)

    _thread = threading.Thread(target=_loop, name="day-snapshot-poller", daemon=True)
    _thread.start()
    log.info("day snapshot poller started every %ss", interval)


def stop_day_poller() -> None:
    _stop.set()
