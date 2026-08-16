from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from portfolio_news.config import Settings, get_settings
from portfolio_news.db import NewsItem, Ticker, make_session_factory
from portfolio_news.import_tickers import load_tickers_from_json, upsert_tickers
from portfolio_news.metrics_moex import fetch_metrics_for
from portfolio_news.poll_job import get_poll_status, start_poll_job

_settings = get_settings()
_SessionLocal = make_session_factory(_settings.database_url)
_STATIC = Path(__file__).resolve().parent / "static"


def get_db():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_cfg() -> Settings:
    return _settings


app = FastAPI(title="Portfolio News", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TickerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    isin: str
    kind: str
    category: str
    search_query: str


class NewsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker_id: str
    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    created_at: datetime
    notified: int


class MetricOut(BaseModel):
    ticker_id: str
    kind: str
    name: str
    last: Optional[float] = None
    changepct: Optional[float] = None
    div_yield: Optional[float] = None
    coupon_percent: Optional[float] = None
    currency: str = "RUB"
    board: str = ""
    error: str = ""


@app.on_event("startup")
def _ensure_tickers():
    settings = get_settings()
    db = _SessionLocal()
    try:
        if settings.tickers_json.exists():
            upsert_tickers(db, load_tickers_from_json(settings.tickers_json))
    finally:
        db.close()


@app.get("/")
def ui_index():
    return FileResponse(_STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/tickers", response_model=list[TickerOut])
def list_tickers(db: Session = Depends(get_db)):
    rows = db.scalars(select(Ticker).order_by(Ticker.kind, Ticker.id)).all()
    return list(rows)


@app.get("/api/news", response_model=list[NewsOut])
def list_news(
    ticker: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(NewsItem).order_by(desc(NewsItem.created_at)).limit(limit)
    if ticker:
        q = (
            select(NewsItem)
            .where(NewsItem.ticker_id == ticker)
            .order_by(desc(NewsItem.created_at))
            .limit(limit)
        )
    return list(db.scalars(q).all())


@app.post("/api/poll")
def run_poll(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    notify: str = Query("digest"),
    cfg: Settings = Depends(get_cfg),
):
    """Start background poll scoped to filter. Returns immediately."""
    raw = (notify or "digest").strip().lower()
    if raw in ("true", "1", "each", "yes"):
        mode = "each"
    elif raw in ("false", "0", "off", "quiet", "no"):
        mode = "off"
    elif raw == "digest":
        mode = "digest"
    else:
        raise HTTPException(
            status_code=422,
            detail=f"notify must be digest|off|each (got {notify!r})",
        )

    started = start_poll_job(
        ticker_id=ticker_id or None,
        kind=kind or None,
        category=category or None,
        limit=cfg.poll_limit,
        notify=mode,
    )
    if not started.get("ok"):
        raise HTTPException(status_code=409, detail=started)
    return started


@app.get("/api/poll/status")
def poll_status():
    return get_poll_status()


@app.get("/api/metrics", response_model=list[MetricOut])
def list_metrics(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    q = select(Ticker).order_by(Ticker.id)
    if ticker_id:
        q = q.where(Ticker.id == ticker_id)
    else:
        if kind:
            q = q.where(Ticker.kind == kind)
        if category:
            q = q.where(Ticker.category == category)
    rows = list(db.scalars(q))
    if limit:
        rows = rows[:limit]
    items = [(t.id, t.kind, t.name) for t in rows]
    metrics = fetch_metrics_for(items)
    return [
        MetricOut(
            ticker_id=m.ticker_id,
            kind=m.kind,
            name=m.name,
            last=m.last,
            changepct=m.changepct,
            div_yield=m.div_yield,
            coupon_percent=m.coupon_percent,
            currency=m.currency,
            board=m.board,
            error=m.error,
        )
        for m in metrics
    ]
