"""Chart_Sandbox FastAPI: candles + markers + static UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import cache as disk_cache
from app.crypto_book import fetch_futures_orderbook
from app.liquidity import build_liquidity_map
from app.moex import fetch_daily_candles

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
MARKERS_PATH = ROOT / "data" / "markers.json"

app = FastAPI(title="Chart_Sandbox", version="0.1.0")


def _load_markers_file() -> dict[str, list[dict[str, Any]]]:
    if not MARKERS_PATH.is_file():
        return {}
    try:
        data = json.loads(MARKERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@app.get("/api/candles/{ticker}")
def api_candles(
    ticker: str,
    days: int = Query(365, ge=1, le=5000),
    force: int = Query(0, ge=0, le=1),
) -> dict[str, Any]:
    tid = ticker.strip().upper()
    cached = None if force else disk_cache.read_cache(tid, days)

    if cached and not force:
        return {
            "ticker": tid,
            "board": str(cached.get("board") or ""),
            "days": days,
            "stale": False,
            "error": "",
            "candles": cached.get("candles") or [],
            "source": "cache",
        }

    candles, board, err = fetch_daily_candles(tid, days=days)
    if candles:
        payload = {
            "ticker": tid,
            "board": board,
            "days": days,
            "candles": candles,
        }
        disk_cache.write_cache(tid, days, payload)
        return {
            "ticker": tid,
            "board": board,
            "days": days,
            "stale": False,
            "error": "",
            "candles": candles,
            "source": "moex",
        }

    # Network / empty: fall back to disk cache
    fallback = disk_cache.read_cache(tid, days)
    if fallback:
        return {
            "ticker": tid,
            "board": str(fallback.get("board") or board),
            "days": days,
            "stale": True,
            "error": err or "moex failed",
            "candles": fallback.get("candles") or [],
            "source": "cache",
        }

    return {
        "ticker": tid,
        "board": board,
        "days": days,
        "stale": False,
        "error": err or "no candles",
        "candles": [],
        "source": "none",
    }


@app.get("/api/markers/{ticker}")
def api_markers(ticker: str) -> dict[str, Any]:
    tid = ticker.strip().upper()
    all_m = _load_markers_file()
    items = all_m.get(tid) or []
    if not isinstance(items, list):
        items = []
    return {"ticker": tid, "markers": items}


@app.get("/api/liquidity/{ticker}")
def api_liquidity(
    ticker: str,
    days: int = Query(365, ge=1, le=5000),
    force: int = Query(0, ge=0, le=1),
) -> dict[str, Any]:
    """Swing / equal-high-low liquidity estimate for chart + backtester."""
    candle_payload = api_candles(ticker, days=days, force=force)
    candles = candle_payload.get("candles") or []
    liq = build_liquidity_map(candles)
    return {
        "ticker": candle_payload.get("ticker") or ticker.strip().upper(),
        "days": days,
        "board": candle_payload.get("board") or "",
        "source": candle_payload.get("source") or "",
        "stale": bool(candle_payload.get("stale")),
        "error": candle_payload.get("error") or "",
        **liq,
    }


@app.get("/api/crypto/orderbook/{symbol}")
def api_crypto_orderbook(
    symbol: str,
    limit: int = Query(50, ge=5, le=1000),
) -> dict[str, Any]:
    """Binance USDT-M futures L2 depth (public). Default BTCUSDT."""
    book, err = fetch_futures_orderbook(symbol, limit=limit)
    if err:
        return {
            "ok": False,
            "error": err,
            "venue": "binance_usdm",
            "symbol": symbol.strip().upper(),
            "bids": [],
            "asks": [],
        }
    return {"ok": True, "error": "", **book}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/crypto")
def crypto_dom() -> FileResponse:
    return FileResponse(STATIC / "crypto.html")


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
