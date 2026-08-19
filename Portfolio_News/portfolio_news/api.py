from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from portfolio_news.bcs_client import get_bcs_client, match_holding
from portfolio_news.config import Settings, get_settings
from portfolio_news.db import NewsItem, Ticker, make_session_factory
from portfolio_news.import_tickers import load_tickers_from_json, upsert_tickers
from portfolio_news.metrics_moex import (
    effective_moex_limit,
    fetch_coupons_for,
    fetch_dividends_for,
    fetch_metrics_for,
    metric_to_dict,
)
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


class DividendOut(BaseModel):
    ticker_id: str
    name: str
    secid: str = ""
    isin: str = ""
    registryclosedate: str = ""
    value: Optional[float] = None
    currencyid: str = ""
    extra: dict = Field(default_factory=dict)
    error: str = ""


class CouponOut(BaseModel):
    ticker_id: str
    name: str
    secid: str = ""
    isin: str = ""
    coupondate: str = ""
    recorddate: str = ""
    startdate: str = ""
    value: Optional[float] = None
    valueprc: Optional[float] = None
    currencyid: str = ""
    extra: dict = Field(default_factory=dict)
    error: str = ""


def _scoped_tickers(
    db: Session,
    *,
    ticker_id: Optional[str],
    kind: Optional[str],
    category: Optional[str],
    limit: int,
) -> list[Ticker]:
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
    return rows


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
    path = _STATIC / "index.html"
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


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


@app.get("/api/metrics")
def list_metrics(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    eff = effective_moex_limit(ticker_id=ticker_id, limit=limit)
    rows = _scoped_tickers(
        db, ticker_id=ticker_id, kind=kind, category=category, limit=eff
    )
    items = [(t.id, t.kind, t.name, t.isin or "") for t in rows]
    metrics = fetch_metrics_for(items)
    return [metric_to_dict(m) for m in metrics]


@app.get("/api/dividends", response_model=list[DividendOut])
def list_dividends(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    eff = effective_moex_limit(ticker_id=ticker_id, limit=limit)
    rows = _scoped_tickers(
        db, ticker_id=ticker_id, kind=kind, category=category, limit=eff
    )
    items = [(t.id, t.kind, t.name) for t in rows]
    return [
        DividendOut(
            ticker_id=d.ticker_id,
            name=d.name,
            secid=d.secid,
            isin=d.isin,
            registryclosedate=d.registryclosedate,
            value=d.value,
            currencyid=d.currencyid,
            extra=d.extra,
            error=d.error,
        )
        for d in fetch_dividends_for(items)
    ]


@app.get("/api/coupons", response_model=list[CouponOut])
def list_coupons(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    eff = effective_moex_limit(ticker_id=ticker_id, limit=limit)
    rows = _scoped_tickers(
        db, ticker_id=ticker_id, kind=kind, category=category, limit=eff
    )
    items = [(t.id, t.kind, t.name) for t in rows]
    return [
        CouponOut(
            ticker_id=c.ticker_id,
            name=c.name,
            secid=c.secid,
            isin=c.isin,
            coupondate=c.coupondate,
            recorddate=c.recorddate,
            startdate=c.startdate,
            value=c.value,
            valueprc=c.valueprc,
            currencyid=c.currencyid,
            extra=c.extra,
            error=c.error,
        )
        for c in fetch_coupons_for(items)
    ]


def _bcs():
    cfg = get_settings()
    return get_bcs_client(
        refresh_token=cfg.bcs_trade_refresh_token,
        client_id=cfg.bcs_trade_client_id or "trade-api-read",
    )


@app.get("/api/holdings")
def list_holdings(
    force: bool = Query(False),
    ticker_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """BCS portfolio positions (read-only). Empty if token not configured."""
    snap = _bcs().fetch_holdings(force=force)
    data = snap.to_dict()
    if ticker_id and snap.ok:
        t = db.get(Ticker, ticker_id)
        isin = (t.isin if t else "") or ""
        hit = match_holding(snap.holdings, ticker_id=ticker_id, isin=isin)
        data["match"] = asdict(hit) if hit else None
        data["holdings"] = [asdict(hit)] if hit else []
    return data


@app.get("/api/holdings/status")
def holdings_status():
    cfg = get_settings()
    return {
        "configured": bool(cfg.bcs_trade_refresh_token.strip()),
        "client_id": cfg.bcs_trade_client_id or "trade-api-read",
    }
