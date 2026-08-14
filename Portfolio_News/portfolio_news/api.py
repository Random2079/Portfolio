from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from portfolio_news.config import Settings, get_settings
from portfolio_news.db import NewsItem, Ticker, make_session_factory
from portfolio_news.import_tickers import load_tickers_from_json, upsert_tickers
from portfolio_news.poller import poll_once

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


app = FastAPI(title="Portfolio News", version="0.1.0")
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


@app.on_event("startup")
def _ensure_tickers():
    settings = get_settings()
    db = _SessionLocal()
    try:
        count = db.scalar(select(Ticker.id).limit(1))
        if count is None and settings.tickers_json.exists():
            upsert_tickers(db, load_tickers_from_json(settings.tickers_json))
    finally:
        db.close()


@app.get("/")
def ui_index():
    """React UI (CDN) — works without Node/npm. Vite app lives in frontend/ when Node is available."""
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
        q = select(NewsItem).where(NewsItem.ticker_id == ticker).order_by(desc(NewsItem.created_at)).limit(limit)
    return list(db.scalars(q).all())


@app.post("/api/poll")
def run_poll(
    notify: bool = True,
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_cfg),
):
    return poll_once(db, limit=cfg.poll_limit, notify=notify)
