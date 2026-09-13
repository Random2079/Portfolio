"""Binance USDT-M futures order book (public, no API key)."""

from __future__ import annotations

from typing import Any

import requests

_HEADERS = {
    "User-Agent": "ChartSandbox/0.1 (+local; crypto depth)",
    "Accept": "application/json",
}
_FAPI = "https://fapi.binance.com"
_TIMEOUT = 8.0


def fetch_futures_orderbook(
    symbol: str = "BTCUSDT",
    *,
    limit: int = 50,
) -> tuple[dict[str, Any], str]:
    """Return (payload, error). Bids/asks: [{price, qty}, ...] best first."""
    sym = (symbol or "BTCUSDT").strip().upper()
    lim = int(limit)
    if lim not in (5, 10, 20, 50, 100, 500, 1000):
        lim = 50
    try:
        resp = requests.get(
            f"{_FAPI}/fapi/v1/depth",
            params={"symbol": sym, "limit": lim},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return {}, str(exc)

    def _side(rows: list) -> list[dict[str, float]]:
        out: list[dict[str, float]] = []
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                out.append({"price": float(row[0]), "qty": float(row[1])})
            except (TypeError, ValueError):
                continue
        return out

    bids = _side(data.get("bids"))
    asks = _side(data.get("asks"))
    best_bid = bids[0]["price"] if bids else None
    best_ask = asks[0]["price"] if asks else None
    mid = None
    spread = None
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid

    # cumulative size from touch (liquidity walls)
    def _cum(levels: list[dict[str, float]]) -> list[dict[str, float]]:
        c = 0.0
        out = []
        for lv in levels:
            c += lv["qty"]
            out.append({**lv, "cum": c})
        return out

    return {
        "venue": "binance_usdm",
        "symbol": sym,
        "lastUpdateId": data.get("lastUpdateId"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread": spread,
        "bids": _cum(bids),
        "asks": _cum(asks),
    }, ""
