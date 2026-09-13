"""Minimal MOEX ISS daily candles for TQBR equities."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import requests

_HEADERS = {
    "User-Agent": "ChartSandbox/0.1 (+local; personal)",
    "Accept": "application/json",
}
_TIMEOUT = 10.0
_PAGE = 500
_BOARDS = ("TQBR", "TQTF", "TQIF", "SMAL")


def _iss_get(path: str, params: dict[str, Any] | None = None) -> dict:
    url = f"https://iss.moex.com{path}"
    resp = requests.get(url, params=params or {}, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _table(data: dict, name: str) -> list[dict]:
    block = data.get(name) or {}
    columns = block.get("columns") or []
    rows = block.get("data") or []
    return [dict(zip(columns, row)) for row in rows]


def _f(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def resolve_board(secid: str) -> str:
    """Pick a tradable board for SECID (prefer TQBR)."""
    data = _iss_get(
        "/iss/securities.json",
        {"q": secid, "iss.meta": "off", "limit": 20},
    )
    secs = _table(data, "securities")
    tid = secid.upper()
    exact = [s for s in secs if str(s.get("secid", "")).upper() == tid]
    pool = exact or secs
    for preferred in _BOARDS:
        for s in pool:
            board = str(s.get("primary_boardid") or s.get("boardid") or "").strip()
            if board == preferred:
                return board
    for s in pool:
        board = str(s.get("primary_boardid") or s.get("boardid") or "").strip()
        if board and board not in {"INAV", "INPF", "RTSI"}:
            return board
    return "TQBR"


def _candle_time(begin: str) -> str | None:
    """Lightweight Charts business day: YYYY-MM-DD."""
    s = (begin or "").strip()
    if not s:
        return None
    # "2024-01-15 00:00:00" -> "2024-01-15"
    return s[:10]


def rows_to_candles(rows: list[dict]) -> list[dict[str, Any]]:
    """Pure ISS candles table → LWC candle dicts (no network)."""
    out: list[dict[str, Any]] = []
    for r in rows:
        t = _candle_time(str(r.get("begin") or ""))
        o, h, low, c = _f(r.get("open")), _f(r.get("high")), _f(r.get("low")), _f(r.get("close"))
        if not t or o is None or h is None or low is None or c is None:
            continue
        item: dict[str, Any] = {
            "time": t,
            "open": o,
            "high": h,
            "low": low,
            "close": c,
        }
        vol = _f(r.get("volume"))
        if vol is not None:
            item["volume"] = vol
        out.append(item)
    return out


def fetch_daily_candles(
    ticker: str,
    *,
    days: int = 365,
) -> tuple[list[dict[str, Any]], str, str]:
    """Return (candles, board, error). Candles: time/open/high/low/close/volume."""
    secid = ticker.strip().upper()
    if not secid:
        return [], "", "empty ticker"

    till = date.today()
    frm = till - timedelta(days=max(1, int(days)))
    params: dict[str, Any] = {
        "iss.meta": "off",
        "interval": 24,
        "from": frm.isoformat(),
        "till": till.isoformat(),
    }

    try:
        board = resolve_board(secid)
    except Exception as exc:  # noqa: BLE001
        return [], "", f"resolve: {exc}"

    boards_try = [board] + [b for b in _BOARDS if b != board] + [""]
    last_err = ""

    for cand_board in boards_try:
        collected: list[dict] = []
        start = 0
        while True:
            page = dict(params)
            page["start"] = start
            if cand_board:
                path = (
                    f"/iss/engines/stock/markets/shares/boards/{quote(cand_board)}"
                    f"/securities/{quote(secid)}/candles.json"
                )
            else:
                path = (
                    f"/iss/engines/stock/markets/shares"
                    f"/securities/{quote(secid)}/candles.json"
                )
            try:
                data = _iss_get(path, page)
            except requests.RequestException as exc:
                last_err = str(exc)
                break
            rows = _table(data, "candles")
            if not rows:
                break
            collected.extend(rows)
            if len(rows) < _PAGE:
                break
            start += len(rows)

        if not collected:
            continue

        out = rows_to_candles(collected)
        if out:
            return out, cand_board or board, ""

    return [], board, last_err or "no candles"
