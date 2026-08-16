from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "PortfolioNews/0.2 (+local; personal monitor)",
    "Accept": "application/json",
}

# MOEX board mapping heuristics
_EQ_BOARDS = ("TQBR", "TQTF", "SMAL")
_BOND_BOARDS = ("TQCB", "TQOB", "TQIR")


@dataclass
class MetricRow:
    ticker_id: str
    kind: str
    name: str
    last: Optional[float] = None
    changepct: Optional[float] = None
    div_yield: Optional[float] = None  # % if available
    coupon_percent: Optional[float] = None  # bond coupon rate %
    currency: str = "RUB"
    board: str = ""
    error: str = ""


def _iss_get(path: str, params: dict | None = None) -> dict:
    url = f"https://iss.moex.com{path}"
    resp = requests.get(url, params=params or {}, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _table(data: dict, name: str) -> list[dict]:
    block = data.get(name) or {}
    columns = block.get("columns") or []
    rows = block.get("data") or []
    return [dict(zip(columns, row)) for row in rows]


def _find_secid(ticker_id: str, kind: str) -> tuple[str, str]:
    """Return (secid, board) for MOEX."""
    # Bonds often stored as ISIN
    q = ticker_id
    data = _iss_get(
        "/iss/securities.json",
        {"q": q, "iss.meta": "off", "limit": 20},
    )
    secs = _table(data, "securities")
    if not secs:
        return ticker_id, ""

    preferred = _BOND_BOARDS if kind == "bond" else _EQ_BOARDS
    # Prefer exact SECID match
    exact = [s for s in secs if str(s.get("secid", "")).upper() == ticker_id.upper()]
    pool = exact or secs
    for s in pool:
        board = str(s.get("primary_boardid") or s.get("boardid") or "")
        if board in preferred or not preferred:
            return str(s.get("secid") or ticker_id), board
    s0 = pool[0]
    return str(s0.get("secid") or ticker_id), str(s0.get("primary_boardid") or "")


def fetch_metric(ticker_id: str, kind: str, name: str = "") -> MetricRow:
    row = MetricRow(ticker_id=ticker_id, kind=kind, name=name or ticker_id)
    try:
        secid, board = _find_secid(ticker_id, kind)
        row.board = board
        # Marketdata + securities description
        path = f"/iss/engines/stock/markets/{'bonds' if kind == 'bond' else 'shares'}/securities/{quote(secid)}.json"
        params = {"iss.meta": "off"}
        if board:
            params["board"] = board
        # Try shares then bonds if needed
        try:
            data = _iss_get(path, params)
        except requests.HTTPError:
            alt = "shares" if kind == "bond" else "bonds"
            path = f"/iss/engines/stock/markets/{alt}/securities/{quote(secid)}.json"
            data = _iss_get(path, params)

        md_rows = _table(data, "marketdata")
        sec_rows = _table(data, "securities")
        if md_rows:
            md = md_rows[0]
            last = md.get("LAST") or md.get("MARKETPRICE") or md.get("LCURRENTPRICE")
            if last is not None:
                row.last = float(last)
            chg = md.get("LASTTOPREVPRICE") or md.get("CHANGE")
            if chg is not None:
                try:
                    row.changepct = float(chg)
                except (TypeError, ValueError):
                    pass
        if sec_rows:
            sec = sec_rows[0]
            # Dividend yield sometimes in securities
            for key in ("DIVYIELD", "YIELD", "YIELDATWAP"):
                if sec.get(key) is not None and kind != "bond":
                    try:
                        row.div_yield = float(sec[key])
                        break
                    except (TypeError, ValueError):
                        pass
            for key in ("COUPONPERCENT",):
                if sec.get(key) is not None and kind == "bond":
                    try:
                        row.coupon_percent = float(sec[key])
                    except (TypeError, ValueError):
                        pass
                    break
            if row.coupon_percent is None and sec.get("COUPONVALUE") is not None and kind == "bond":
                try:
                    # raw coupon value — store as-is in coupon_percent field only if percent missing
                    pass
                except (TypeError, ValueError):
                    pass
            if sec.get("CURRENCYID"):
                row.currency = str(sec["CURRENCYID"])
    except Exception as exc:  # noqa: BLE001
        log.warning("MOEX metric failed for %s: %s", ticker_id, exc)
        row.error = str(exc)
    return row


def fetch_metrics_for(
    items: list[tuple[str, str, str]],
    *,
    limit: int = 0,
) -> list[MetricRow]:
    """items: list of (id, kind, name)."""
    out: list[MetricRow] = []
    for i, (tid, kind, name) in enumerate(items):
        if limit and i >= limit:
            break
        out.append(fetch_metric(tid, kind, name))
    return out
