from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import logging
import threading
import time

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from portfolio_news.bcs_client import classify_asset_class, get_bcs_client, match_holding
from portfolio_news.config import Settings, get_settings
from portfolio_news.db import NewsAiCache, NewsItem, Ticker, TickerAiReviewCache, make_session_factory
from portfolio_news.focus import list_focus_tickers, replace_focus, set_focus
from portfolio_news.import_tickers import load_tickers_from_json, upsert_tickers
from portfolio_news.metrics_moex import (
    candle_to_dict,
    effective_moex_limit,
    fetch_coupons_for,
    fetch_dividends_for,
    fetch_metrics_for,
    metric_to_dict,
)
from portfolio_news.poll_job import get_poll_status, request_cancel_poll, start_poll_job

log = logging.getLogger(__name__)

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
    # F-A (null if not classified yet)
    ai_label: Optional[str] = None
    ai_urgency: Optional[str] = None
    ai_reason: Optional[str] = None
    ai_model: Optional[str] = None
    ai_as_of: Optional[datetime] = None


class NewsAiClassifyIn(BaseModel):
    ids: Optional[list[int]] = None
    today_only: bool = True
    limit: int = Field(30, ge=1, le=40)


class NewsAiClassifyOut(BaseModel):
    ok: bool = True
    classified: int = 0
    skipped: int = 0
    ids: list[int] = Field(default_factory=list)
    error: str = ""


class NewsAiStatusOut(BaseModel):
    enabled: bool
    has_key: bool
    ready: bool
    hint: str = ""


class TickerAiReviewIn(BaseModel):
    ticker: str
    force: bool = False
    news_limit: int = Field(12, ge=1, le=25)


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


class FocusOut(BaseModel):
    tickers: list[str]
    n: int = 0


class FocusPut(BaseModel):
    tickers: list[str] = Field(default_factory=list)


class FocusTierIn(BaseModel):
    tier: str  # focus | hold


def _scoped_tickers(
    db: Session,
    *,
    ticker_id: Optional[str],
    kind: Optional[str],
    category: Optional[str],
    limit: int,
    ids: Optional[list[str]] = None,
) -> list[Ticker]:
    q = select(Ticker).order_by(Ticker.id)
    if ticker_id:
        q = q.where(Ticker.id == ticker_id)
    elif ids:
        clean = [x.strip() for x in ids if x and str(x).strip()]
        if clean:
            q = q.where(Ticker.id.in_(clean))
        if kind:
            q = q.where(Ticker.kind == kind)
        if category:
            q = q.where(Ticker.category == category)
    else:
        if kind:
            q = q.where(Ticker.kind == kind)
        if category:
            q = q.where(Ticker.category == category)
    rows = list(db.scalars(q))
    if ids and not ticker_id:
        # preserve UI order (BCS list), drop unknown
        by_id = {t.id: t for t in rows}
        ordered: list[Ticker] = []
        for raw in ids:
            tid = (raw or "").strip()
            if tid and tid in by_id:
                ordered.append(by_id[tid])
        rows = ordered
    if limit:
        rows = rows[:limit]
    return rows


def _parse_ids(ids: Optional[str]) -> Optional[list[str]]:
    if not ids or not str(ids).strip():
        return None
    parts = [p.strip() for p in str(ids).split(",") if p.strip()]
    return parts or None


def _moex_id_list(
    db: Session,
    *,
    ticker_id: Optional[str],
    ids: Optional[str],
) -> Optional[list[str]]:
    """K5: when no ticker/ids, default MOEX scope to BCS holdings."""
    id_list = _parse_ids(ids)
    if ticker_id or id_list is not None:
        return id_list
    from portfolio_news.bcs_scope import resolve_bcs_scope

    scope_ids, _err = resolve_bcs_scope(db)
    return scope_ids or []


@app.on_event("startup")
def _ensure_tickers():
    settings = get_settings()
    db = _SessionLocal()
    try:
        if settings.tickers_json.exists():
            upsert_tickers(db, load_tickers_from_json(settings.tickers_json))
    finally:
        db.close()
    try:
        from portfolio_news.day_poller import start_day_poller

        start_day_poller(_SessionLocal, interval_sec=settings.day_poll_sec)
    except Exception:  # noqa: BLE001
        pass


@app.get("/api/day")
def day_attribution(
    force: bool = Query(
        False,
        description="Sync MOEX refresh (rare; UI uses SQLite + background poller)",
    ),
    top: int = Query(8, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """KA: day Δ from SQLite snapshot (updated every DAY_POLL_SEC in background)."""
    import time as _time

    from portfolio_news.day_cache import load_day_snapshot
    from portfolio_news.day_poller import day_poll_status, refresh_day_snapshot

    if force:
        refresh_day_snapshot(_SessionLocal, force_moex=True)

    loaded = load_day_snapshot(db)
    poll = day_poll_status()
    if loaded is None:
        # kick first fill if poller hasn't written yet
        if not poll.get("running"):
            threading.Thread(
                target=refresh_day_snapshot,
                args=(_SessionLocal,),
                kwargs={"force_moex": True},
                daemon=True,
            ).start()
        return {
            "ok": False,
            "error": "",
            "configured": True,
            "pending": True,
            "day_rub": None,
            "day_pct": None,
            "top": [],
            "missing": 0,
            "poll": poll,
        }

    attr, updated_at = loaded
    age = _time.time() - updated_at
    data = attr.to_dict()
    data["configured"] = True
    data["updated_at"] = updated_at
    data["age_sec"] = round(age, 1)
    data["stale"] = age > 90
    data["source"] = "sqlite"
    data["poll"] = poll
    data["poll_interval_sec"] = get_settings().day_poll_sec
    # top_n already baked into snapshot; ignore top param for cache hits
    _ = top
    return data


@app.get("/api/capital")
def capital_curve(
    days: int = Query(1100, ge=7, le=1200),
    force: bool = Query(False, description="Rebuild weekly points from deals + MOEX"),
    db: Session = Depends(get_db),
):
    """K6: portfolio totals for capital line (weekly history + today)."""
    from portfolio_news.capital_cache import list_capital_days, today_local

    if force:
        from portfolio_news.capital_replay import rebuild_weekly_capital

        rebuild_weekly_capital(db)
    points = list_capital_days(db, days=days)
    return {
        "ok": True,
        "days": days,
        "today": today_local(),
        "n": len(points),
        "points": points,
        "grain": "week",
    }


def _holdings_qty_map() -> dict[str, float]:
    """ticker → quantity from BCS cache (skip cash). Empty if broker down."""
    cfg = get_cfg()
    client = get_bcs_client(
        refresh_token=cfg.bcs_trade_refresh_token,
        client_id=cfg.bcs_trade_client_id or "trade-api-read",
    )
    snap = client.fetch_holdings(force=False)
    if not snap.holdings:
        return {}
    out: dict[str, float] = {}
    for h in snap.holdings:
        ac = (h.asset_class or "").strip().lower()
        if ac == "cash":
            continue
        tid = (h.ticker or h.sec_code or "").strip().upper()
        if not tid or not h.quantity:
            continue
        out[tid] = float(h.quantity)
    return out


def _snowball_qty_map() -> dict[str, float]:
    """ticker → qty from last Snowball journal (when BCS holdings are empty)."""
    from datetime import date

    from portfolio_news.snowball_ledger import book_as_of, find_snowball_csv, load_events

    path = find_snowball_csv()
    if path is None:
        return {}
    try:
        return book_as_of(load_events(path), date.today()).papers()
    except Exception:  # noqa: BLE001
        return {}


@app.get("/api/calendar")
def payout_calendar(
    days: int = Query(365, ge=7, le=730),
    force: bool = Query(False, description="Rebuild from MOEX now (slow)"),
    db: Session = Depends(get_db),
):
    """K7: upcoming dividends/coupons for own papers, from SQLite cache."""
    import time as _time

    from portfolio_news.calendar_own import (
        apply_quantities,
        calendar_running,
        load_calendar,
        refresh_calendar,
    )

    if force:
        refresh_calendar(_SessionLocal, ahead_days=days)

    loaded = load_calendar(db)
    if loaded is None:
        if not calendar_running():
            threading.Thread(
                target=refresh_calendar,
                args=(_SessionLocal,),
                kwargs={"ahead_days": days},
                daemon=True,
            ).start()
        return {
            "ok": False,
            "pending": True,
            "error": "",
            "events": [],
            "total_amount": None,
            "ahead_days": days,
        }

    data, updated_at = loaded
    # Cached rebuilds sometimes store per_unit without BCS qty → UI shows "N дат".
    # Live BCS first; if broker is down — Snowball journal qty.
    try:
        qty_by = _holdings_qty_map()
    except Exception:  # noqa: BLE001
        qty_by = {}
    if not qty_by:
        qty_by = _snowball_qty_map()
    if qty_by:
        data = apply_quantities(data, qty_by, only_own=True)

    age = _time.time() - updated_at
    data["updated_at"] = updated_at
    data["age_sec"] = round(age, 1)
    data["pending"] = False
    data["running"] = calendar_running()
    # rebuild once a day in background; UI keeps showing the old list meanwhile
    if age > 24 * 3600 and not calendar_running():
        threading.Thread(
            target=refresh_calendar,
            args=(_SessionLocal,),
            kwargs={"ahead_days": days},
            daemon=True,
        ).start()
        data["running"] = True
    return data


def _html(path: Path):
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/")
def ui_index():
    """Main UI = Snowball-like dashboard (approved 2026-09-10)."""
    return _html(_STATIC / "dashboard-demo.html")


@app.get("/demo")
def ui_demo():
    """Alias of main dashboard."""
    return _html(_STATIC / "dashboard-demo.html")


@app.get("/pay-demo")
def ui_pay_chart_demo():
    """K7 chart design sandbox — not the live calendar."""
    return _html(_STATIC / "pay-chart-demo.html")


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
    focus: bool = Query(False, description="KB: only Focus tickers when set is non-empty"),
    limit: int = Query(50, ge=1, le=200),
    ai: Optional[str] = Query(None, description="hide_noise = drop label=noise"),
    db: Session = Depends(get_db),
):
    """K5: default feed = news for BCS holdings only (not full tickers DB)."""
    from portfolio_news.bcs_scope import resolve_bcs_scope

    q = select(NewsItem).order_by(desc(NewsItem.created_at)).limit(limit)
    if ticker:
        q = (
            select(NewsItem)
            .where(NewsItem.ticker_id == ticker)
            .order_by(desc(NewsItem.created_at))
            .limit(limit)
        )
    elif focus:
        focus_ids = list_focus_tickers(db)
        if focus_ids:
            q = (
                select(NewsItem)
                .where(NewsItem.ticker_id.in_(focus_ids))
                .order_by(desc(NewsItem.created_at))
                .limit(limit)
            )
    else:
        scope_ids, _err = resolve_bcs_scope(db)
        if scope_ids:
            q = (
                select(NewsItem)
                .where(NewsItem.ticker_id.in_(scope_ids))
                .order_by(desc(NewsItem.created_at))
                .limit(limit)
            )
    rows = list(db.scalars(q).all())
    from portfolio_news.sources.news_noise import is_noise_title

    rows = [r for r in rows if not is_noise_title(r.title or "")]
    ai_map = _news_ai_map(db, [r.id for r in rows])
    hide_noise = (ai or "").strip().lower() == "hide_noise"
    out: list[NewsOut] = []
    for r in rows:
        cache = ai_map.get(r.id)
        if hide_noise and cache is not None and cache.label == "noise":
            continue
        out.append(_news_to_out(r, cache))
    return out


def _news_ai_map(db: Session, ids: list[int]) -> dict[int, NewsAiCache]:
    if not ids:
        return {}
    rows = db.scalars(select(NewsAiCache).where(NewsAiCache.news_id.in_(ids))).all()
    return {r.news_id: r for r in rows}


def _news_to_out(row: NewsItem, cache: Optional[NewsAiCache] = None) -> NewsOut:
    return NewsOut(
        id=row.id,
        ticker_id=row.ticker_id,
        title=row.title,
        url=row.url,
        source=row.source or "",
        published_at=row.published_at,
        created_at=row.created_at,
        notified=row.notified,
        ai_label=(cache.label if cache and cache.label else None),
        ai_urgency=(cache.urgency if cache else None),
        ai_reason=(cache.reason if cache and cache.reason else None),
        ai_model=(cache.model if cache and cache.model else None),
        ai_as_of=(cache.as_of if cache else None),
    )


@app.get("/api/news/ai-status", response_model=NewsAiStatusOut)
def news_ai_status(cfg: Settings = Depends(get_cfg)):
    """F-A: whether button classify is ready (flag + key)."""
    has_key = bool((cfg.deepseek_api_key or "").strip())
    enabled = bool(cfg.ai_noise_enabled)
    ready = enabled and has_key
    if not enabled:
        hint = "в .env: AI_NOISE_ENABLED=true"
    elif not has_key:
        hint = "задай DEEPSEEK_API_KEY в Portfolio_News/.env"
    else:
        hint = ""
    return NewsAiStatusOut(enabled=enabled, has_key=has_key, ready=ready, hint=hint)


@app.post("/api/news/ai-classify", response_model=NewsAiClassifyOut)
def news_ai_classify(
    body: NewsAiClassifyIn,
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_cfg),
):
    """F-A: button-driven DeepSeek classify for today's BCS-scope news (sync batch)."""
    from portfolio_news.ai_noise import classify_news_batch
    from portfolio_news.bcs_scope import resolve_bcs_scope
    from portfolio_news.poller import news_is_today_for_toast

    if not cfg.ai_noise_enabled:
        raise HTTPException(
            status_code=400,
            detail="ai_noise_enabled=false — поставь AI_NOISE_ENABLED=true в .env",
        )
    api_key = (cfg.deepseek_api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY не задан в Portfolio_News/.env",
        )

    limit = int(body.limit or 30)
    if body.ids:
        q = select(NewsItem).where(NewsItem.id.in_(body.ids)).order_by(desc(NewsItem.created_at))
        candidates = list(db.scalars(q).all())
    else:
        scope_ids, _err = resolve_bcs_scope(db)
        q = select(NewsItem).order_by(desc(NewsItem.created_at)).limit(200)
        if scope_ids:
            q = (
                select(NewsItem)
                .where(NewsItem.ticker_id.in_(scope_ids))
                .order_by(desc(NewsItem.created_at))
                .limit(200)
            )
        candidates = list(db.scalars(q).all())
        if body.today_only:
            filtered = []
            for n in candidates:
                ts = n.published_at or n.created_at
                if news_is_today_for_toast(ts):
                    filtered.append(n)
            candidates = filtered

    batch = candidates[:limit]
    if not batch:
        return NewsAiClassifyOut(ok=True, classified=0, skipped=0, ids=[])

    payload = [
        {
            "id": n.id,
            "ticker": n.ticker_id,
            "title": n.title,
            "source": n.source or "",
        }
        for n in batch
    ]
    try:
        results = classify_news_batch(api_key, payload)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        log.exception("ai-classify failed")
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc

    done_ids: list[int] = []
    for row in results:
        nid = int(row["id"])
        cache = db.get(NewsAiCache, nid)
        if cache is None:
            cache = NewsAiCache(news_id=nid)
            db.add(cache)
        cache.label = str(row["label"])
        cache.urgency = row.get("urgency")
        cache.reason = str(row.get("reason") or "")
        cache.model = str(row.get("model") or "deepseek-chat")
        as_of = row.get("as_of")
        cache.as_of = as_of if isinstance(as_of, datetime) else datetime.utcnow()
        done_ids.append(nid)
    db.commit()
    skipped = len(batch) - len(done_ids)
    return NewsAiClassifyOut(
        ok=True,
        classified=len(done_ids),
        skipped=max(0, skipped),
        ids=done_ids,
    )


@app.get("/api/ai/ticker-review/{ticker}")
def get_ticker_ai_review(ticker: str, db: Session = Depends(get_db)):
    """F-B: cached one-shot review (null payload if never run)."""
    tid = (ticker or "").strip().upper()
    if not tid:
        raise HTTPException(status_code=400, detail="ticker required")
    row = db.get(TickerAiReviewCache, tid)
    if row is None or not row.payload_json:
        return {"ok": False, "ticker": tid, "from_cache": False, "data": None}
    try:
        import json as _json

        data = _json.loads(row.payload_json)
    except Exception:  # noqa: BLE001
        return {"ok": False, "ticker": tid, "from_cache": False, "data": None}
    return {
        "ok": bool(row.ok),
        "ticker": tid,
        "from_cache": True,
        "updated_at": row.updated_at,
        "data": data,
    }


@app.post("/api/ai/ticker-review")
def post_ticker_ai_review(
    body: TickerAiReviewIn,
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_cfg),
):
    """F-B: button one-shot DeepSeek review for ticker news (not chat, no orders)."""
    import json as _json

    from portfolio_news.ai_ticker import review_ticker_news
    from portfolio_news.review_facts import resolve_sector

    if not cfg.ai_noise_enabled:
        raise HTTPException(
            status_code=400,
            detail="ai_noise_enabled=false — поставь AI_NOISE_ENABLED=true в .env",
        )
    api_key = (cfg.deepseek_api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY не задан в Portfolio_News/.env",
        )

    tid = (body.ticker or "").strip().upper()
    if not tid:
        raise HTTPException(status_code=400, detail="ticker required")

    if not body.force:
        cached = db.get(TickerAiReviewCache, tid)
        if cached and cached.ok and cached.payload_json:
            age = time.time() - float(cached.updated_at or 0)
            if age < 6 * 3600:  # 6h fresh
                try:
                    data = _json.loads(cached.payload_json)
                    return {
                        "ok": True,
                        "ticker": tid,
                        "from_cache": True,
                        "updated_at": cached.updated_at,
                        "data": data,
                    }
                except Exception:  # noqa: BLE001
                    pass

    row = db.get(Ticker, tid) or db.get(Ticker, tid.lower())
    if row is None:
        for t in db.scalars(select(Ticker)).all():
            if str(t.id).upper() == tid:
                row = t
                break
    kind = ((row.kind if row else "") or "equity").strip().lower()
    if kind not in ("equity", "bond", "fund"):
        kind = "equity"
    name = ((row.name if row else "") or tid).strip()
    category = ((row.category if row else "") or "").strip()
    sector = resolve_sector(tid, category)
    look = sector.get("look_for") or ""
    if isinstance(look, (list, tuple)):
        look = ", ".join(str(x) for x in look)
    ks_labels = f"{sector.get('id', '')}: {sector.get('label', '')}; смотри: {look}"

    q = (
        select(NewsItem)
        .where(NewsItem.ticker_id == tid)
        .order_by(desc(NewsItem.created_at))
        .limit(int(body.news_limit or 12))
    )
    # also match case variants
    news_rows = list(db.scalars(q).all())
    if not news_rows:
        q2 = (
            select(NewsItem)
            .where(NewsItem.ticker_id.in_([tid, tid.lower(), tid.capitalize()]))
            .order_by(desc(NewsItem.created_at))
            .limit(int(body.news_limit or 12))
        )
        news_rows = list(db.scalars(q2).all())

    news_payload = [
        {"id": n.id, "title": n.title, "source": n.source or ""} for n in news_rows
    ]
    try:
        data = review_ticker_news(
            api_key,
            ticker=tid,
            news=news_payload,
            kind=kind,
            name=name,
            ks_labels=ks_labels,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("ai ticker-review failed")
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc

    data["news_ids"] = [n["id"] for n in news_payload if n.get("id") is not None]
    now = time.time()
    cache = db.get(TickerAiReviewCache, tid)
    if cache is None:
        cache = TickerAiReviewCache(ticker=tid)
        db.add(cache)
    cache.payload_json = _json.dumps(data, ensure_ascii=False)
    cache.updated_at = now
    cache.ok = 1
    db.commit()
    return {
        "ok": True,
        "ticker": tid,
        "from_cache": False,
        "updated_at": now,
        "data": data,
    }


@app.get("/api/focus", response_model=FocusOut)
def get_focus(db: Session = Depends(get_db)):
    """KB: list of Focus tickers (остальные = Hold)."""
    tickers = list_focus_tickers(db)
    return FocusOut(tickers=tickers, n=len(tickers))


@app.put("/api/focus", response_model=FocusOut)
def put_focus(body: FocusPut, db: Session = Depends(get_db)):
    """KB: replace entire Focus set."""
    tickers = replace_focus(db, body.tickers)
    return FocusOut(tickers=tickers, n=len(tickers))


@app.put("/api/focus/{ticker_id}")
def put_focus_ticker(ticker_id: str, body: FocusTierIn, db: Session = Depends(get_db)):
    """KB: set one ticker to focus|hold."""
    tier = (body.tier or "").strip().lower()
    if tier not in ("focus", "hold"):
        raise HTTPException(status_code=422, detail="tier must be focus|hold")
    result = set_focus(db, ticker_id, focus=(tier == "focus"))
    return {"ticker": ticker_id.strip().upper(), "tier": result}

@app.post("/api/poll")
def run_poll(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    notify: Optional[str] = Query(
        None,
        description="digest|off|each; default from NOTIFY_DEFAULT / notify_default",
    ),
    all_tickers: bool = Query(
        False,
        description="Legacy: poll full tickers DB (default false = K5 BCS holdings only)",
    ),
    cfg: Settings = Depends(get_cfg),
):
    """Start background poll. K5: default scope = BCS holdings only. K9: toast rules."""
    raw = (notify if notify is not None else (cfg.notify_default or "digest"))
    raw = str(raw).strip().lower()
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
        bcs_only=not all_tickers,
    )
    if not started.get("ok"):
        raise HTTPException(status_code=409, detail=started)
    return started


@app.get("/api/notify")
def notify_settings(cfg: Settings = Depends(get_cfg)):
    """K9: current server default toast mode (UI may override via poll ?notify=)."""
    raw = (cfg.notify_default or "digest").strip().lower()
    if raw not in ("digest", "off", "each"):
        raw = "digest"
    return {"default": raw, "modes": ["digest", "off", "each"]}


@app.get("/api/poll/status")
def poll_status():
    return get_poll_status()


@app.post("/api/poll/cancel")
def poll_cancel():
    """Soft-cancel: stop after current ticker/source, don't start new ones."""
    return request_cancel_poll()


@app.get("/api/metrics")
def list_metrics(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ids: Optional[str] = Query(None, description="Comma-separated ticker ids (BCS portfolio order)"),
    limit: int = Query(0, ge=0, le=200),
    db: Session = Depends(get_db),
):
    id_list = _moex_id_list(db, ticker_id=ticker_id, ids=ids)
    eff = effective_moex_limit(ticker_id=ticker_id, limit=limit)
    rows = _scoped_tickers(
        db,
        ticker_id=ticker_id,
        kind=kind,
        category=category,
        limit=eff,
        ids=id_list,
    )
    by_id = {t.id: t for t in rows}
    order = [ticker_id] if ticker_id else (id_list or [t.id for t in rows])
    items: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for tid in order:
        if not tid or tid in seen:
            continue
        seen.add(tid)
        t = by_id.get(tid)
        if t:
            items.append((t.id, t.kind, t.name, t.isin or ""))
        elif id_list is not None:
            items.append((tid, kind or "equity", tid, ""))
    if limit:
        items = items[:limit]
    metrics = fetch_metrics_for(items)
    return [metric_to_dict(m) for m in metrics]


@app.get("/api/dividends", response_model=list[DividendOut])
def list_dividends(
    ticker_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ids: Optional[str] = Query(None),
    limit: int = Query(0, ge=0, le=200),
    db: Session = Depends(get_db),
):
    id_list = _moex_id_list(db, ticker_id=ticker_id, ids=ids)
    eff = effective_moex_limit(ticker_id=ticker_id, limit=limit)
    rows = _scoped_tickers(
        db,
        ticker_id=ticker_id,
        kind=kind,
        category=category,
        limit=eff,
        ids=id_list,
    )
    by_id = {t.id: t for t in rows}
    order = [ticker_id] if ticker_id else (id_list or [t.id for t in rows])
    items: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for tid in order:
        if not tid or tid in seen:
            continue
        seen.add(tid)
        t = by_id.get(tid)
        if t:
            items.append((t.id, t.kind, t.name))
        elif id_list is not None:
            items.append((tid, kind or "equity", tid))
    if limit:
        items = items[:limit]
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
    ids: Optional[str] = Query(None),
    limit: int = Query(0, ge=0, le=200),
    db: Session = Depends(get_db),
):
    id_list = _moex_id_list(db, ticker_id=ticker_id, ids=ids)
    eff = effective_moex_limit(ticker_id=ticker_id, limit=limit)
    rows = _scoped_tickers(
        db,
        ticker_id=ticker_id,
        kind=kind,
        category=category,
        limit=eff,
        ids=id_list,
    )
    by_id = {t.id: t for t in rows}
    order = [ticker_id] if ticker_id else (id_list or [t.id for t in rows])
    items: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for tid in order:
        if not tid or tid in seen:
            continue
        seen.add(tid)
        t = by_id.get(tid)
        if t:
            items.append((t.id, t.kind, t.name))
        elif id_list is not None:
            items.append((tid, kind or "bond", tid))
    if limit:
        items = items[:limit]
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


def _enrich_holdings_payload(holdings: list[dict], db: Session) -> None:
    """Fill asset_class (+ empty name) from tickers DB without mutating BCS cache."""
    if not holdings:
        return
    by_id: dict[str, Ticker] = {}
    by_isin: dict[str, Ticker] = {}
    for t in db.scalars(select(Ticker)).all():
        by_id[str(t.id).upper()] = t
        if t.isin:
            by_isin[str(t.isin).upper()] = t
    for h in holdings:
        tid = str(h.get("ticker") or h.get("sec_code") or "").strip().upper()
        isin = str(h.get("isin") or "").strip().upper()
        row = by_id.get(tid) or (by_isin.get(isin) if isin else None)
        if row and not (h.get("name") or "").strip() and row.name:
            h["name"] = row.name
        db_kind = (row.kind if row else "") or ""
        h["asset_class"] = classify_asset_class(
            ticker=str(h.get("ticker") or ""),
            sec_code=str(h.get("sec_code") or ""),
            isin=str(h.get("isin") or ""),
            class_code=str(h.get("class_code") or ""),
            name=str(h.get("name") or ""),
            db_kind=db_kind,
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
    if snap.ok and data.get("holdings"):
        _enrich_holdings_payload(data["holdings"], db)
    if snap.ok and snap.total_value is not None:
        from portfolio_news.capital_cache import maybe_record_from_holdings

        maybe_record_from_holdings(
            db,
            total_value=snap.total_value,
            cash=snap.cash,
            currency=snap.currency or "RUB",
            ok=True,
        )
    return data


@app.get("/api/holdings/status")
def holdings_status():
    cfg = get_settings()
    return {
        "configured": bool(cfg.bcs_trade_refresh_token.strip()),
        "client_id": cfg.bcs_trade_client_id or "trade-api-read",
    }


def _ops_window(
    year: Optional[str], date_from: Optional[str], date_to: Optional[str]
) -> tuple[str, str]:
    """`year=2024` is shorthand for the whole calendar year."""
    y = (year or "").strip()
    if y and y.isdigit() and len(y) == 4:
        return f"{y}-01-01", f"{y}-12-31"
    return (date_from or "").strip(), (date_to or "").strip()


def _ops_kinds(kind: Optional[str]) -> list[str]:
    raw = (kind or "").strip().lower()
    if not raw or raw == "all":
        return []
    return [k for k in (p.strip() for p in raw.split(",")) if k in ("equity", "bond", "fund")]


def _refresh_bcs_ops(db: Session, *, force: bool) -> str:
    """Top up the BCS cache; history itself comes from the journal."""
    from portfolio_news.ops_cache import cache_count, merge_live_into_cache

    client = _bcs()
    if not force and cache_count(db) > 0:
        return ""
    snap = client.fetch_operations(force=force, ticker="", limit=500)
    if snap.ok and snap.operations:
        merge_live_into_cache(db, snap)
        return ""
    return snap.error or ""


@app.get("/api/operations")
def list_operations(
    force: bool = Query(False),
    ticker: Optional[str] = Query(None, description="Ticker id or company name substring"),
    kind: Optional[str] = Query(None, description="equity|bond|fund (comma-separated)"),
    year: Optional[str] = Query(None, description="YYYY shorthand for a full year"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, ge=0, le=5000, description="0 = no limit"),
    journal: bool = Query(True, description="Include Snowball journal history"),
    db: Session = Depends(get_db),
):
    """K8: deal history = BCS cache + Snowball journal, filtered by kind/period."""
    from portfolio_news.ops_history import build_history

    err = _refresh_bcs_ops(db, force=force)
    lo, hi = _ops_window(year, date_from, date_to)
    data = build_history(
        db,
        kinds=_ops_kinds(kind),
        date_from=lo,
        date_to=hi,
        ticker=ticker or "",
        limit=limit,
        include_journal=journal,
    )
    has_rows = bool(data["operations"]) or data["all_total"] > 0
    data.update(
        {
            "configured": _bcs().configured or data["journal_rows"] > 0,
            "ok": has_rows or not err,
            "error": "" if has_rows else err,
            "fetched_at": time.time(),
            "raw_keys": ["sqlite_cache", "snowball_journal"],
            "source": "+".join(data["sources"]) or "empty",
            "date_from": lo,
            "date_to": hi,
        }
    )
    return data


@app.get("/api/operations.csv")
def operations_csv(
    ticker: Optional[str] = Query(None, description="Ticker id or company name substring"),
    kind: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    journal: bool = Query(True),
    db: Session = Depends(get_db),
):
    """K8: same filters as /api/operations, dumped as ';'-separated CSV."""
    from portfolio_news.ops_history import build_history, to_csv

    lo, hi = _ops_window(year, date_from, date_to)
    data = build_history(
        db,
        kinds=_ops_kinds(kind),
        date_from=lo,
        date_to=hi,
        ticker=ticker or "",
        limit=0,
        include_journal=journal,
    )
    body = to_csv(data["operations"])
    stamp = datetime.now().strftime("%Y%m%d")
    name = f"deals_{stamp}.csv"
    return Response(
        # BOM so Excel opens Cyrillic correctly
        content="\ufeff" + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/api/position/{ticker}")
def position_card(
    ticker: str,
    force: bool = Query(False),
    moex: bool = Query(
        False,
        description="Optional MOEX last price if BCS market_price missing (slow; off by default)",
    ),
    db: Session = Depends(get_db),
):
    """K4: position facts — avg, buy dates, unrealized PnL, weight (no advice).

    Uses BCS holdings cache + SQLite ops. Does **not** wait on MOEX by default
    (offline / slow net still get a card from broker facts).
    """
    from portfolio_news.ops_cache import list_cached_operations
    from portfolio_news.position_card import build_position_card

    tid = (ticker or "").strip().upper()
    if not tid:
        raise HTTPException(status_code=400, detail="ticker required")

    client = _bcs()
    snap = client.fetch_holdings(force=force)
    if not snap.configured:
        return {
            "ok": False,
            "ticker": tid,
            "error": snap.error or "BCS_TRADE_REFRESH_TOKEN не задан в .env",
            "configured": False,
        }
    if not snap.ok and not snap.holdings:
        return {
            "ok": False,
            "ticker": tid,
            "error": snap.error or "BCS holdings недоступны",
            "configured": True,
            "stale": snap.stale,
        }

    row = db.get(Ticker, tid) or db.get(Ticker, tid.lower())
    if row is None:
        for t in db.scalars(select(Ticker)).all():
            if str(t.id).upper() == tid:
                row = t
                break
    isin = (row.isin if row else "") or ""
    hit = match_holding(snap.holdings, ticker_id=tid, isin=isin)

    ops = list_cached_operations(db, ticker=tid, limit=500)

    moex_last = None
    moex_note = ""
    # MOEX только по флагу и только если у БКС нет цены — иначе карточка
    # висит на ConnectTimeout iss.moex.com при плохом инете.
    if (
        moex
        and hit is not None
        and hit.market_price is None
    ):
        kind = (row.kind if row else "equity") or "equity"
        if kind not in ("equity", "bond", "fund"):
            kind = "equity"
        try:
            from portfolio_news.metrics_moex import fetch_metric

            m = fetch_metric(tid, kind, (hit.name or tid), isin=isin or hit.isin or "")
            if m.last is not None:
                moex_last = float(m.last)
            elif getattr(m, "error", None):
                moex_note = str(m.error)[:200]
        except Exception as exc:  # noqa: BLE001
            moex_note = str(exc)[:200]

    card = build_position_card(
        ticker=tid,
        holding=hit,
        operations=ops,
        holdings=list(snap.holdings),
        total_value=snap.total_value,
        moex_last=moex_last,
        configured=True,
    )
    data = card.to_dict()
    if snap.stale:
        data["stale"] = True
    if snap.error and card.ok:
        data["holdings_note"] = snap.error
    if moex_note and card.ok:
        data["moex_note"] = moex_note
    return data


@app.get("/api/review/{ticker}")
def review_ticker(
    ticker: str,
    force: bool = Query(False, description="Bypass fresh cache and refetch MOEX"),
    db: Session = Depends(get_db),
):
    """KS: checkpoint facts under position card. Cache-first; no buy/sell text."""
    from portfolio_news.calendar_own import load_calendar, today_local
    from portfolio_news.day_attribution import is_cash_holding
    from portfolio_news.metrics_moex import fetch_metric
    from portfolio_news.position_card import build_position_card
    from portfolio_news.review_facts import (
        build_review_payload,
        cache_is_fresh,
        load_review_cache,
        review_cache_complete,
        save_review_cache,
    )
    from portfolio_news.ops_cache import list_cached_operations

    tid = (ticker or "").strip().upper()
    if not tid:
        raise HTTPException(status_code=400, detail="ticker required")

    cached = load_review_cache(db, tid)
    if cached and not force:
        data, upd = cached
        if cache_is_fresh(upd) and review_cache_complete(data):
            data = dict(data)
            data["from_cache"] = True
            data["stale"] = False
            return data

    client = _bcs()
    snap = client.fetch_holdings(force=False)
    row = db.get(Ticker, tid) or db.get(Ticker, tid.lower())
    if row is None:
        for t in db.scalars(select(Ticker)).all():
            if str(t.id).upper() == tid:
                row = t
                break
    isin = ((row.isin if row else "") or "").strip()
    category = ((row.category if row else "") or "").strip()
    kind = ((row.kind if row else "") or "equity").strip().lower()
    if kind not in ("equity", "bond", "fund"):
        kind = "equity"

    hit = None
    weight = None
    qty = None
    name = (row.name if row else "") or tid
    if snap.holdings:
        hit = match_holding(snap.holdings, ticker_id=tid, isin=isin)
        if hit is not None:
            if is_cash_holding(hit):
                return {
                    "ok": True,
                    "ticker": tid,
                    "kind": "cash",
                    "name": hit.name or tid,
                    "isin": "",
                    "sector": {"id": "unknown", "label": "кэш", "look_for": "не сверка чек-поинта"},
                    "position_line": "денежные средства",
                    "fields": [],
                    "flags": [],
                    "verdict": None,
                    "disclaimer": "кэш · не бумага",
                    "updated_at": time.time(),
                    "mock": False,
                }
            name = (hit.name or name).strip()
            qty = hit.quantity
            ac = (hit.asset_class or "").strip().lower()
            if not ac or ac == "other":
                ac = classify_asset_class(
                    ticker=hit.ticker or "",
                    sec_code=hit.sec_code or "",
                    isin=hit.isin or isin,
                    class_code=hit.class_code or "",
                    name=hit.name or "",
                    db_kind=kind,
                )
            if ac == "bond":
                kind = "bond"
            elif ac == "fund":
                kind = "fund"
            elif ac in ("stock", "equity"):
                kind = "equity"
            ops = list_cached_operations(db, ticker=tid, limit=500)
            card = build_position_card(
                ticker=tid,
                holding=hit,
                operations=ops,
                holdings=list(snap.holdings),
                total_value=snap.total_value,
            )
            weight = card.weight_pct
            if hit.isin:
                isin = hit.isin

    cal_events: list = []
    cal_as_of = ""
    loaded = load_calendar(db)
    if loaded:
        cal_data, cal_upd = loaded
        cal_events = list(cal_data.get("events") or [])
        if cal_upd:
            cal_as_of = datetime.fromtimestamp(cal_upd, tz=timezone(timedelta(hours=5))).strftime(
                "%Y-%m-%d %H:%M"
            )

    metric = None
    moex_err = ""
    try:
        metric = fetch_metric(tid, kind, name or tid, isin=isin)
        if getattr(metric, "error", ""):
            moex_err = str(metric.error)[:200]
            # keep partial metric if any fields present
            if metric.last is None and not metric.coupon_percent and not metric.div_yield:
                metric = None
    except Exception as exc:  # noqa: BLE001
        moex_err = str(exc)[:200]
        metric = None

    if metric is None and cached and not force:
        data, upd = cached
        data = dict(data)
        data["from_cache"] = True
        data["stale"] = True
        data["error"] = moex_err or data.get("error") or "MOEX недоступен · показан кэш"
        # refresh position line if we have holdings
        if weight is not None or qty is not None:
            bits = ["уже в портфеле"]
            if qty is not None:
                bits.append(f"qty {qty}")
            if weight is not None:
                bits.append(f"доля {weight:.2f}%".replace(".", ","))
            bits.append("кэш на добор: вручную (нет источника)")
            data["position_line"] = " · ".join(bits)
        return data

    smartlab_row = None
    smartlab_as_of = ""
    smartlab_alias = False
    dohod_facts = None
    dohod_as_of = ""
    fund_ter = None
    fund_ter_as_of = ""
    if kind == "equity":
        try:
            from portfolio_news.fundamentals_smartlab import (
                get_fundamentals_map,
                resolve_fundamental,
            )

            # Universe TTL/incomplete handles refresh; don't refetch 5 HTML pages on every ?force=
            fmap, smartlab_as_of = get_fundamentals_map(db, force=False)
            smartlab_row, _, smartlab_alias = resolve_fundamental(fmap, tid)
        except Exception as exc:  # noqa: BLE001
            log.warning("smartlab fundamentals for review failed: %s", exc)
    elif kind == "bond" and isin:
        try:
            from portfolio_news.bonds_dohod import get_dohod_bond

            dohod_facts, dohod_as_of = get_dohod_bond(db, isin, force=force)
        except Exception as exc:  # noqa: BLE001
            log.warning("dohod bond for review failed: %s", exc)
    elif kind == "fund":
        try:
            from portfolio_news.funds_cbr_ter import get_fund_ter_map, resolve_fund_ter
            from portfolio_news.funds_investfunds import resolve_fund_isin

            if not isin:
                isin = resolve_fund_isin(tid) or isin
            fmap, fund_ter_as_of = get_fund_ter_map(db, force=force)
            if isin:
                fund_ter = resolve_fund_ter(fmap, isin)
        except Exception as exc:  # noqa: BLE001
            log.warning("cbr fund ter for review failed: %s", exc)

    payload = build_review_payload(
        ticker=tid,
        kind=kind,
        name=name,
        isin=isin,
        category=category,
        weight_pct=weight,
        qty=float(qty) if qty is not None else None,
        metric=metric,
        calendar_events=cal_events,
        calendar_as_of=cal_as_of,
        today=today_local(),
        smartlab=smartlab_row,
        smartlab_as_of=smartlab_as_of,
        smartlab_alias=smartlab_alias,
        dohod=dohod_facts,
        dohod_as_of=dohod_as_of,
        fund_ter=fund_ter,
        fund_ter_as_of=fund_ter_as_of,
    )
    if moex_err and metric is None:
        payload.error = moex_err
        # partial OK: SmartLab/Dohod/calendar may still fill slots
        payload.ok = any(not getattr(f, "missing", True) for f in payload.fields)
    elif moex_err:
        payload.error = moex_err

    out = payload.to_dict()
    out["from_cache"] = False
    out["stale"] = False
    try:
        save_review_cache(db, tid, out)
    except Exception as exc:  # noqa: BLE001
        log.warning("review cache save failed: %s", exc)
    return out


@app.get("/api/chart/{ticker}")
def chart_ticker(
    ticker: str,
    days: int = Query(
        0,
        ge=0,
        le=8000,
        description="Lookback calendar days; 0 = full MOEX history (default)",
    ),
    interval: int = Query(24, description="MOEX candle interval; 24=day"),
    kind: Optional[str] = Query(None, description="equity|bond|fund; default from tickers DB"),
    force: bool = Query(False, description="Bypass SQLite candle cache"),
    db: Session = Depends(get_db),
):
    """K3: MOEX close series + BCS trade markers for one ticker."""
    from portfolio_news.chart_cache import resolve_chart_candles
    from portfolio_news.ops_cache import list_cached_operations

    tid = (ticker or "").strip().upper()
    if not tid:
        raise HTTPException(status_code=400, detail="ticker required")

    resolved_kind = (kind or "").strip().lower()
    row = db.get(Ticker, tid) or db.get(Ticker, tid.lower())
    if row is None:
        for t in db.scalars(select(Ticker)).all():
            if str(t.id).upper() == tid:
                row = t
                break
    if resolved_kind not in ("equity", "bond", "fund"):
        resolved_kind = (row.kind if row else "equity") or "equity"
        if resolved_kind not in ("equity", "bond", "fund"):
            resolved_kind = "equity"
    # ISIN-as-ticker (RU000A…) — bond even if tickers DB empty / kind hint lost
    if resolved_kind != "bond" and tid.startswith("RU000"):
        resolved_kind = "bond"
    isin = ((row.isin if row else "") or "").strip()
    if not isin and tid.startswith("RU000"):
        isin = tid

    from_date = ""
    if int(days) > 0:
        from datetime import date, timedelta

        from_date = (date.today() - timedelta(days=int(days))).isoformat()

    points, secid, board, err, from_cache, stale = resolve_chart_candles(
        db,
        tid,
        resolved_kind,
        isin=isin,
        days=int(days),
        interval=int(interval) or 24,
        force=bool(force),
    )
    # Bonds: MOEX candles are % of par; avg/markers are ₽/шт — one scale for LWC.
    if resolved_kind == "bond" and points:
        from portfolio_news.capital_replay import candles_unit_rub

        points = candles_unit_rub(points, "bond")

    from portfolio_news.ops_history import build_history

    hist = build_history(db, ticker=tid, limit=0, include_journal=True)
    markers: list[dict] = []
    for op in hist.get("operations") or []:
        side = str(op.get("side") or "").strip().lower()
        if side not in ("buy", "sell"):
            continue
        markers.append(
            {
                "deal_id": str(op.get("deal_id") or op.get("id") or ""),
                "executed_at": str(op.get("executed_at") or op.get("day") or ""),
                "side": side,
                "price": op.get("price"),
                "quantity": op.get("quantity"),
                "volume": op.get("volume"),
            }
        )
    # chronological for chart overlay
    markers.sort(key=lambda m: m.get("executed_at") or "")

    ok = bool(points)
    return {
        "ok": ok,
        "error": "" if ok else (err or "Нет свечей MOEX для тикера"),
        "ticker": tid,
        "kind": resolved_kind,
        "price_unit": "rub_per_bond" if resolved_kind == "bond" else "price",
        "secid": secid,
        "board": board,
        "interval": int(interval) or 24,
        "from": from_date,
        "from_cache": bool(from_cache),
        "stale": bool(stale),
        "candles": [candle_to_dict(p) for p in points],
        "markers": markers,
        "n_candles": len(points),
        "n_markers": len(markers),
    }


# Local assets (e.g. offline logos under static/logos/)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")