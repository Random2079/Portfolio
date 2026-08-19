from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
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

# Soft caps for calendar dumps (full history can be huge)
_MAX_DIVIDEND_ROWS = 40
_MAX_COUPON_ROWS = 40

# Process-wide SECID cache: (ticker_id.upper(), kind) -> (secid, board)
_secid_cache: dict[tuple[str, str], tuple[str, str]] = {}
_secid_lock = threading.Lock()


@dataclass
class MetricRow:
    ticker_id: str
    kind: str
    name: str
    secid: str = ""
    isin: str = ""
    shortname: str = ""
    last: Optional[float] = None
    changepct: Optional[float] = None
    prevprice: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    valtoday: Optional[float] = None
    voltoday: Optional[float] = None
    updatetime: str = ""
    lotsize: Optional[float] = None
    listlevel: Optional[int] = None
    div_yield: Optional[float] = None  # % if available
    coupon_percent: Optional[float] = None  # bond coupon rate %
    coupon_value: Optional[float] = None
    next_coupon: str = ""
    coupon_period: Optional[int] = None
    accruedint: Optional[float] = None
    yield_: Optional[float] = None  # YTM from board, not our calc
    matdate: str = ""
    facevalue: Optional[float] = None
    duration: Optional[float] = None
    currency: str = "RUB"
    board: str = ""
    error: str = ""


@dataclass
class DividendRow:
    ticker_id: str
    name: str
    secid: str = ""
    isin: str = ""
    registryclosedate: str = ""
    value: Optional[float] = None
    currencyid: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class CouponRow:
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
    extra: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def clear_secid_cache() -> None:
    with _secid_lock:
        _secid_cache.clear()


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


def _f(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _i(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _s(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _lookup_secid(ticker_id: str, kind: str) -> tuple[str, str]:
    """Return (secid, board) for MOEX (uncached)."""
    q = ticker_id
    data = _iss_get(
        "/iss/securities.json",
        {"q": q, "iss.meta": "off", "limit": 20},
    )
    secs = _table(data, "securities")
    if not secs:
        return ticker_id, ""

    preferred = _BOND_BOARDS if kind == "bond" else _EQ_BOARDS
    exact = [s for s in secs if str(s.get("secid", "")).upper() == ticker_id.upper()]
    pool = exact or secs
    for s in pool:
        board = str(s.get("primary_boardid") or s.get("boardid") or "")
        if board in preferred or not preferred:
            return str(s.get("secid") or ticker_id), board
    s0 = pool[0]
    return str(s0.get("secid") or ticker_id), str(s0.get("primary_boardid") or "")


def resolve_secid(ticker_id: str, kind: str) -> tuple[str, str]:
    """Cached SECID lookup shared by metrics / dividends / coupons."""
    key = (ticker_id.strip().upper(), (kind or "").strip().lower() or "equity")
    with _secid_lock:
        hit = _secid_cache.get(key)
    if hit is not None:
        return hit
    secid, board = _lookup_secid(ticker_id, kind)
    with _secid_lock:
        _secid_cache[key] = (secid, board)
    return secid, board


# Back-compat alias used by older call sites / tests
def _find_secid(ticker_id: str, kind: str) -> tuple[str, str]:
    return resolve_secid(ticker_id, kind)


def fetch_metric(ticker_id: str, kind: str, name: str = "", isin: str = "") -> MetricRow:
    row = MetricRow(ticker_id=ticker_id, kind=kind, name=name or ticker_id, isin=isin or "")
    try:
        secid, board = resolve_secid(ticker_id, kind)
        row.secid = secid
        row.board = board
        market = "bonds" if kind == "bond" else "shares"
        path = f"/iss/engines/stock/markets/{market}/securities/{quote(secid)}.json"
        params: dict[str, str] = {"iss.meta": "off"}
        if board:
            params["board"] = board
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
            row.last = _f(md.get("LAST") or md.get("MARKETPRICE") or md.get("LCURRENTPRICE"))
            row.changepct = _f(md.get("LASTTOPREVPRICE") or md.get("CHANGE"))
            row.prevprice = _f(md.get("PREVPRICE") or md.get("LCLOSEPRICE"))
            row.open = _f(md.get("OPEN"))
            row.high = _f(md.get("HIGH"))
            row.low = _f(md.get("LOW"))
            row.valtoday = _f(md.get("VALTODAY") or md.get("VALTODAY_USD"))
            row.voltoday = _f(md.get("VOLTODAY"))
            ut = _s(md.get("UPDATETIME") or md.get("SYSTIME") or md.get("TIME"))
            ud = _s(md.get("UPDATEDATE") or md.get("TRADEDATE"))
            row.updatetime = f"{ud} {ut}".strip() if ud or ut else ""
            if kind == "bond":
                row.yield_ = _f(md.get("YIELD") or md.get("YIELDDATE") or md.get("WAPRICE"))
                row.duration = _f(md.get("DURATION"))
                row.accruedint = _f(md.get("ACCRUEDINT"))

        if sec_rows:
            sec = sec_rows[0]
            row.shortname = _s(sec.get("SHORTNAME") or sec.get("SECNAME")) or row.shortname
            if not row.isin:
                row.isin = _s(sec.get("ISIN"))
            row.lotsize = _f(sec.get("LOTSIZE"))
            row.listlevel = _i(sec.get("LISTLEVEL"))
            if sec.get("CURRENCYID"):
                row.currency = _s(sec["CURRENCYID"]) or row.currency
            if kind != "bond":
                for key in ("DIVYIELD", "YIELD", "YIELDATWAP"):
                    v = _f(sec.get(key))
                    if v is not None:
                        row.div_yield = v
                        break
            if kind == "bond":
                row.coupon_percent = _f(sec.get("COUPONPERCENT"))
                row.coupon_value = _f(sec.get("COUPONVALUE"))
                row.next_coupon = _s(sec.get("NEXTCOUPON"))
                row.coupon_period = _i(sec.get("COUPONPERIOD"))
                if row.accruedint is None:
                    row.accruedint = _f(sec.get("ACCRUEDINT"))
                if row.yield_ is None:
                    row.yield_ = _f(sec.get("YIELD") or sec.get("YIELDATWAP"))
                row.matdate = _s(sec.get("MATDATE"))
                row.facevalue = _f(sec.get("FACEVALUE"))
                if row.duration is None:
                    row.duration = _f(sec.get("DURATION"))
    except Exception as exc:  # noqa: BLE001
        log.warning("MOEX metric failed for %s: %s", ticker_id, exc)
        row.error = str(exc)
    return row


def fetch_metrics_for(
    items: list[tuple[str, str, str]] | list[tuple[str, str, str, str]],
    *,
    limit: int = 0,
) -> list[MetricRow]:
    """items: (id, kind, name) or (id, kind, name, isin)."""
    out: list[MetricRow] = []
    for i, item in enumerate(items):
        if limit and i >= limit:
            break
        if len(item) >= 4:
            tid, kind, name, isin = item[0], item[1], item[2], item[3]
        else:
            tid, kind, name = item[0], item[1], item[2]
            isin = ""
        out.append(fetch_metric(tid, kind, name, isin=isin))
    return out


def parse_dividend_rows(
    ticker_id: str,
    name: str,
    secid: str,
    rows: list[dict],
) -> list[DividendRow]:
    """Pure parser for ISS dividends table (testable without network)."""
    out: list[DividendRow] = []
    for r in rows[:_MAX_DIVIDEND_ROWS]:
        known = {
            "isin",
            "registryclosedate",
            "value",
            "currencyid",
            "secid",
        }
        extra = {k: v for k, v in r.items() if k.lower() not in known and v is not None}
        out.append(
            DividendRow(
                ticker_id=ticker_id,
                name=name or ticker_id,
                secid=secid,
                isin=_s(r.get("isin") or r.get("ISIN")),
                registryclosedate=_s(r.get("registryclosedate") or r.get("REGISTRYCLOSEDATE")),
                value=_f(r.get("value") or r.get("VALUE")),
                currencyid=_s(r.get("currencyid") or r.get("CURRENCYID")),
                extra=extra,
            )
        )
    return out


def parse_coupon_rows(
    ticker_id: str,
    name: str,
    secid: str,
    rows: list[dict],
) -> list[CouponRow]:
    """Pure parser for ISS coupons table (testable without network)."""
    out: list[CouponRow] = []
    for r in rows[:_MAX_COUPON_ROWS]:
        known = {
            "isin",
            "coupondate",
            "recorddate",
            "startdate",
            "value",
            "valueprc",
            "currencyid",
            "secid",
        }
        extra = {k: v for k, v in r.items() if k.lower() not in known and v is not None}
        out.append(
            CouponRow(
                ticker_id=ticker_id,
                name=name or ticker_id,
                secid=secid,
                isin=_s(r.get("isin") or r.get("ISIN")),
                coupondate=_s(r.get("coupondate") or r.get("COUPONDATE")),
                recorddate=_s(r.get("recorddate") or r.get("RECORDDATE")),
                startdate=_s(r.get("startdate") or r.get("STARTDATE")),
                value=_f(r.get("value") or r.get("VALUE")),
                valueprc=_f(r.get("valueprc") or r.get("VALUEPRC")),
                currencyid=_s(r.get("currencyid") or r.get("CURRENCYID")),
                extra=extra,
            )
        )
    return out


def fetch_dividends(ticker_id: str, kind: str, name: str = "") -> list[DividendRow]:
    """Raw MOEX dividends history for one security."""
    try:
        secid, _board = resolve_secid(ticker_id, kind)
        data = _iss_get(
            f"/iss/securities/{quote(secid)}/dividends.json",
            {"iss.meta": "off"},
        )
        rows = _table(data, "dividends")
        if not rows:
            return []
        return parse_dividend_rows(ticker_id, name, secid, rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("MOEX dividends failed for %s: %s", ticker_id, exc)
        return [
            DividendRow(
                ticker_id=ticker_id,
                name=name or ticker_id,
                error=str(exc),
            )
        ]


def fetch_coupons(ticker_id: str, kind: str, name: str = "") -> list[CouponRow]:
    """Raw MOEX bondization coupons for one security."""
    try:
        secid, _board = resolve_secid(ticker_id, kind)
        data = _iss_get(
            f"/iss/securities/{quote(secid)}/bondization.json",
            {"iss.meta": "off"},
        )
        rows = _table(data, "coupons")
        if not rows:
            for key in data:
                if "coupon" in key.lower():
                    rows = _table(data, key)
                    if rows:
                        break
        if not rows:
            return []
        return parse_coupon_rows(ticker_id, name, secid, rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("MOEX bondization failed for %s: %s", ticker_id, exc)
        return [
            CouponRow(
                ticker_id=ticker_id,
                name=name or ticker_id,
                error=str(exc),
            )
        ]


def fetch_dividends_for(
    items: list[tuple[str, str, str]],
    *,
    limit: int = 0,
) -> list[DividendRow]:
    out: list[DividendRow] = []
    for i, (tid, kind, name) in enumerate(items):
        if limit and i >= limit:
            break
        out.extend(fetch_dividends(tid, kind, name))
    return out


def fetch_coupons_for(
    items: list[tuple[str, str, str]],
    *,
    limit: int = 0,
) -> list[CouponRow]:
    out: list[CouponRow] = []
    for i, (tid, kind, name) in enumerate(items):
        if limit and i >= limit:
            break
        out.extend(fetch_coupons(tid, kind, name))
    return out


def metric_to_dict(m: MetricRow) -> dict[str, Any]:
    d = asdict(m)
    # expose yield_ as "yield" in JSON
    d["yield"] = d.pop("yield_", None)
    return d


# Default ticker fan-out when client sends limit=0 (matches UI "whole portfolio" cap)
MOEX_DEFAULT_TICKER_LIMIT = 15


def effective_moex_limit(*, ticker_id: Optional[str], limit: int) -> int:
    """Resolve API limit: explicit > 0 wins; single ticker uncapped; else default 15."""
    if ticker_id:
        return limit if limit > 0 else 0  # 0 = no slice beyond the one ticker
    if limit > 0:
        return limit
    return MOEX_DEFAULT_TICKER_LIMIT
