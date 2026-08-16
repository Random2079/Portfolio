from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from portfolio_news.config import get_settings
from portfolio_news.db import make_session_factory
from portfolio_news.poller import PollProgress, poll_once


@dataclass
class PollJobStatus:
    running: bool = False
    current: int = 0
    total: int = 0
    ticker_id: str = ""
    inserted: int = 0
    notified: int = 0
    error: str = ""
    done: bool = False
    result: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


_lock = threading.Lock()
_status = PollJobStatus()
_thread: threading.Thread | None = None


def get_poll_status() -> dict[str, Any]:
    with _lock:
        return _status.to_dict()


def _set_status(**kwargs: Any) -> None:
    with _lock:
        for k, v in kwargs.items():
            setattr(_status, k, v)


def _on_progress(p: PollProgress) -> None:
    _set_status(
        running=p.running,
        current=p.current,
        total=p.total,
        ticker_id=p.ticker_id,
        inserted=p.inserted,
        notified=p.notified,
        error=p.error,
        done=p.done,
    )


def start_poll_job(
    *,
    ticker_id: Optional[str] = None,
    kind: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 0,
    notify: str = "digest",
) -> dict[str, Any]:
    """Start background poll; returns immediately. Rejects if already running."""
    global _thread
    with _lock:
        if _status.running:
            return {"ok": False, "error": "poll_already_running", "status": _status.to_dict()}
        _status.running = True
        _status.current = 0
        _status.total = 0
        _status.ticker_id = ""
        _status.inserted = 0
        _status.notified = 0
        _status.error = ""
        _status.done = False
        _status.result = None

    def worker() -> None:
        settings = get_settings()
        Session = make_session_factory(settings.database_url)
        try:
            with Session() as session:
                result = poll_once(
                    session,
                    limit=limit or settings.poll_limit,
                    notify=notify,  # type: ignore[arg-type]
                    ticker_id=ticker_id,
                    kind=kind,
                    category=category,
                    on_progress=_on_progress,
                )
            _set_status(running=False, done=True, result=result, error="")
        except Exception as exc:  # noqa: BLE001
            _set_status(running=False, done=True, error=str(exc), result=None)

    _thread = threading.Thread(target=worker, name="portfolio-news-poll", daemon=True)
    _thread.start()
    return {"ok": True, "status": get_poll_status()}
