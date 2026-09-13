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
_EQ_BOARDS = ("TQBR", "TQTF", "TQIF", "SMAL")
# ETF / БПИФ: often TQTF historically, sometimes migrated to TQBR (e.g. BCSR)
_FUND_BOARDS = ("TQTF", "TQIF", "TQTD", "TQTE", "TQBR")
_BOND_BOARDS = ("TQCB", "TQOB", "TQIR")
# iNAV / index / non-trade boards — candles empty or wrong instrument
_SKIP_BOARDS = frozenset(
    {
        "INAV",
        "INPF",
        "RTSI",
        "FIXI",
        "FIXS",
        "CETS",
        "CNGD",
    }
)

# Soft caps for calendar dumps (full history can be huge)
_MAX_DIVIDEND_ROWS = 40
_MAX_COUPON_ROWS = 40
# Daily candles for charts (K3); ISS page size is typically 500
_MAX_CANDLE_ROWS = 800
_CANDLE_PAGE = 500


@dataclass
class CandlePoint:
    """One MOEX candle (usually daily close)."""

    begin: str = ""
    end: str = ""
    open: Optional[float] = None
    close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    value: Optional[float] = None

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


@dataclass
class AmortRow:
    """Bond principal repayment (погашение / амортизация)."""

    ticker_id: str
    name: str
    secid: str = ""
    isin: str = ""
    amortdate: str = ""
    value: Optional[float] = None
    valueprc: Optional[float] = None
    currencyid: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def clear_secid_cache() -> None:
    with _secid_lock:
        _secid_cache.clear()


def _iss_get(path: str, params: dict | None = None, *, timeout: float = 8.0) -> dict:
    url = f"https://iss.moex.com{path}"
    resp = requests.get(url, params=params or {}, headers=_HEADERS, timeout=timeout)
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


def _preferred_boards(kind: str) -> tuple[str, ...]:
    k = (kind or "").strip().lower()
    if k == "bond":
        return _BOND_BOARDS
    if k == "fund":
        return _FUND_BOARDS
    return _EQ_BOARDS


def _board_of(sec: dict) -> str:
    return str(sec.get("primary_boardid") or sec.get("boardid") or "").strip()


def _is_index_or_inav(sec: dict) -> bool:
    """True for iNAV / index rows that must not win over tradable SECID."""
    board = _board_of(sec)
    if board in _SKIP_BOARDS:
        return True
    typ = str(sec.get("type") or "").lower()
    group = str(sec.get("group") or "").lower()
    if group == "stock_index" or typ.startswith("stock_index"):
        return True
    if "index" in typ and "ppif" not in typ and "share" not in typ:
        return True
    return False


def _pick_secid_board(
    secs: list[dict],
    *,
    ticker_id: str,
    kind: str,
    isin: str = "",
) -> tuple[str, str] | None:
    """Pick tradable (secid, board) from ISS securities search rows."""
    if not secs:
        return None
    preferred = _preferred_boards(kind)
    tid = ticker_id.strip().upper()
    isin_u = (isin or "").strip().upper()

    exact = [s for s in secs if str(s.get("secid", "")).upper() == tid]
    isin_hits = []
    if isin_u:
        isin_hits = [
            s
            for s in secs
            if str(s.get("isin") or "").strip().upper() == isin_u
            and not _is_index_or_inav(s)
        ]
    # Prefer exact SECID, then ISIN match, else full list (still skip indexes)
    pools: list[list[dict]] = []
    if exact:
        pools.append(exact)
    if isin_hits:
        pools.append(isin_hits)
    pools.append([s for s in secs if not _is_index_or_inav(s)] or secs)

    seen: set[int] = set()
    for pool in pools:
        for s in pool:
            sid = id(s)
            if sid in seen:
                continue
            seen.add(sid)
            if _is_index_or_inav(s) and s not in exact:
                # allow exact ticker even on odd board only as last resort below
                continue
            board = _board_of(s)
            if board in _SKIP_BOARDS:
                continue
            if board in preferred or (not preferred and board):
                return str(s.get("secid") or ticker_id), board
        # second pass: any non-skip board in this pool
        for s in pool:
            if _is_index_or_inav(s):
                continue
            board = _board_of(s)
            if board and board not in _SKIP_BOARDS:
                return str(s.get("secid") or ticker_id), board
    return None


def _lookup_secid(ticker_id: str, kind: str, isin: str = "") -> tuple[str, str]:
    """Return (secid, board) for MOEX (uncached).

    ETF/БПИФ often appear in ISS search behind iNAV twins (BCSR→BCSRA/INAV).
    Short tickers like GOLD match indexes first — fall back to ISIN when given.
    """
    queries: list[str] = []
    tid = (ticker_id or "").strip()
    isin_s = (isin or "").strip()
    if tid:
        queries.append(tid)
    if isin_s and isin_s.upper() not in {q.upper() for q in queries}:
        queries.append(isin_s)

    last_secs: list[dict] = []
    for q in queries:
        data = _iss_get(
            "/iss/securities.json",
            {"q": q, "iss.meta": "off", "limit": 20},
        )
        secs = _table(data, "securities")
        last_secs = secs or last_secs
        picked = _pick_secid_board(secs, ticker_id=tid or q, kind=kind, isin=isin_s)
        if picked:
            return picked

    if last_secs:
        s0 = last_secs[0]
        board = _board_of(s0)
        if board in _SKIP_BOARDS:
            board = ""
        return str(s0.get("secid") or ticker_id), board
    return ticker_id, ""


def resolve_secid(ticker_id: str, kind: str, isin: str = "") -> tuple[str, str]:
    """Cached SECID lookup shared by metrics / dividends / coupons / candles."""
    key = (
        ticker_id.strip().upper(),
        (kind or "").strip().lower() or "equity",
        (isin or "").strip().upper(),
    )
    with _secid_lock:
        hit = _secid_cache.get(key)
    if hit is not None:
        return hit
    secid, board = _lookup_secid(ticker_id, kind, isin=isin)
    with _secid_lock:
        _secid_cache[key] = (secid, board)
    return secid, board


# Back-compat alias used by older call sites / tests
def _find_secid(ticker_id: str, kind: str) -> tuple[str, str]:
    return resolve_secid(ticker_id, kind)


def _candle_board_candidates(primary: str, kind: str) -> list[str]:
    """Boards to try for candles: primary, then kind-preferred, then market-level."""
    out: list[str] = []
    if primary and primary not in _SKIP_BOARDS:
        out.append(primary)
    for b in _preferred_boards(kind):
        if b not in out:
            out.append(b)
    if "" not in out:
        out.append("")
    return out


def fetch_metric(ticker_id: str, kind: str, name: str = "", isin: str = "") -> MetricRow:
    row = MetricRow(ticker_id=ticker_id, kind=kind, name=name or ticker_id, isin=isin or "")
    try:
        secid, board = resolve_secid(ticker_id, kind, isin=isin)
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


def parse_amort_rows(
    ticker_id: str,
    name: str,
    secid: str,
    rows: list[dict],
) -> list[AmortRow]:
    """Pure parser for ISS amortizations table."""
    out: list[AmortRow] = []
    for r in rows[:_MAX_COUPON_ROWS]:
        known = {
            "isin",
            "amortdate",
            "value",
            "valueprc",
            "currencyid",
            "secid",
        }
        extra = {k: v for k, v in r.items() if k.lower() not in known and v is not None}
        out.append(
            AmortRow(
                ticker_id=ticker_id,
                name=name or ticker_id,
                secid=secid,
                isin=_s(r.get("isin") or r.get("ISIN")),
                amortdate=_s(r.get("amortdate") or r.get("AMORTDATE")),
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


def fetch_bondization(
    ticker_id: str, kind: str, name: str = ""
) -> tuple[list[CouponRow], list[AmortRow]]:
    """One ISS bondization call → coupons + amortizations (погашения)."""
    try:
        secid, _board = resolve_secid(ticker_id, kind)
        data = _iss_get(
            f"/iss/securities/{quote(secid)}/bondization.json",
            {"iss.meta": "off"},
        )
        c_rows = _table(data, "coupons")
        if not c_rows:
            for key in data:
                if "coupon" in key.lower():
                    c_rows = _table(data, key)
                    if c_rows:
                        break
        a_rows = _table(data, "amortizations")
        if not a_rows:
            for key in data:
                if "amort" in key.lower():
                    a_rows = _table(data, key)
                    if a_rows:
                        break
        coupons = parse_coupon_rows(ticker_id, name, secid, c_rows) if c_rows else []
        amorts = parse_amort_rows(ticker_id, name, secid, a_rows) if a_rows else []
        return coupons, amorts
    except Exception as exc:  # noqa: BLE001
        log.warning("MOEX bondization failed for %s: %s", ticker_id, exc)
        return (
            [
                CouponRow(
                    ticker_id=ticker_id,
                    name=name or ticker_id,
                    error=str(exc),
                )
            ],
            [],
        )


def fetch_coupons(ticker_id: str, kind: str, name: str = "") -> list[CouponRow]:
    """Raw MOEX bondization coupons for one security."""
    coupons, _amorts = fetch_bondization(ticker_id, kind, name)
    return coupons


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


def fetch_bondization_for(
    items: list[tuple[str, str, str]],
    *,
    limit: int = 0,
) -> tuple[list[CouponRow], list[AmortRow]]:
    coupons: list[CouponRow] = []
    amorts: list[AmortRow] = []
    for i, (tid, kind, name) in enumerate(items):
        if limit and i >= limit:
            break
        c, a = fetch_bondization(tid, kind, name)
        coupons.extend(c)
        amorts.extend(a)
    return coupons, amorts


def metric_to_dict(m: MetricRow) -> dict[str, Any]:
    d = asdict(m)
    # expose yield_ as "yield" in JSON
    d["yield"] = d.pop("yield_", None)
    return d


def parse_candle_rows(rows: list[dict], *, limit: int = _MAX_CANDLE_ROWS) -> list[CandlePoint]:
    """Pure parser for ISS candles table (testable without network)."""
    out: list[CandlePoint] = []
    for r in rows:
        if limit and len(out) >= limit:
            break
        begin = _s(r.get("begin") or r.get("BEGIN") or r.get("start") or r.get("TRADEDATE"))
        end = _s(r.get("end") or r.get("END"))
        close = _f(r.get("close") or r.get("CLOSE") or r.get("LEGALCLOSEPRICE"))
        if not begin and close is None:
            continue
        out.append(
            CandlePoint(
                begin=begin,
                end=end,
                open=_f(r.get("open") or r.get("OPEN")),
                close=close,
                high=_f(r.get("high") or r.get("HIGH")),
                low=_f(r.get("low") or r.get("LOW")),
                volume=_f(r.get("volume") or r.get("VOLUME")),
                value=_f(r.get("value") or r.get("VALUE")),
            )
        )
    return out


def candle_to_dict(c: CandlePoint) -> dict[str, Any]:
    return asdict(c)


def fetch_candles(
    ticker_id: str,
    kind: str = "equity",
    *,
    interval: int = 24,
    from_date: str = "",
    till_date: str = "",
    limit: int = _MAX_CANDLE_ROWS,
    isin: str = "",
    timeout: float = 12.0,
) -> tuple[list[CandlePoint], str, str, str]:
    """Fetch MOEX ISS candles. Returns (points, secid, board, error).

    ``interval``: 1/10/60 minutes, 24 = day (default), 7 week, 31 month.
    Tries primary board then ETF/share alternates; skips iNAV dead-ends.
    """
    try:
        secid, board = resolve_secid(ticker_id, kind, isin=isin)
        market = "bonds" if kind == "bond" else "shares"
        params: dict[str, str | int] = {
            "iss.meta": "off",
            "interval": int(interval) or 24,
        }
        if from_date:
            params["from"] = from_date
        if till_date:
            params["till"] = till_date

        markets_try = [market, "shares" if market == "bonds" else "bonds"]
        boards_try = _candle_board_candidates(board, kind)
        last_err = ""
        used_board = board
        collected: list[dict] = []
        to = float(timeout) if timeout else 12.0

        for mkt in markets_try:
            for cand_board in boards_try:
                collected = []
                start = 0
                board_err = ""
                while True:
                    page_params = dict(params)
                    page_params["start"] = start
                    if cand_board:
                        path = (
                            f"/iss/engines/stock/markets/{mkt}/boards/{quote(cand_board)}"
                            f"/securities/{quote(secid)}/candles.json"
                        )
                    else:
                        path = (
                            f"/iss/engines/stock/markets/{mkt}"
                            f"/securities/{quote(secid)}/candles.json"
                        )
                    try:
                        data = _iss_get(path, page_params, timeout=to)
                    except requests.HTTPError as exc:
                        board_err = str(exc)
                        last_err = board_err
                        break
                    rows = _table(data, "candles")
                    if not rows:
                        break
                    collected.extend(rows)
                    if len(rows) < _CANDLE_PAGE or (limit and len(collected) >= limit):
                        break
                    start += len(rows)
                if collected:
                    used_board = cand_board or board
                    points = parse_candle_rows(collected, limit=limit)
                    return points, secid, used_board, ""
                # empty 200 → try next board; keep last HTTP err if any
                if board_err:
                    last_err = board_err

        if last_err:
            return [], secid, board, last_err
        return [], secid, board, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("MOEX candles failed for %s: %s", ticker_id, exc)
        return [], "", "", str(exc)


# Default ticker fan-out when client sends limit=0 (matches UI "whole portfolio" cap)
MOEX_DEFAULT_TICKER_LIMIT = 15


def effective_moex_limit(*, ticker_id: Optional[str], limit: int) -> int:
    """Resolve API limit: explicit > 0 wins; single ticker uncapped; else default 15."""
    if ticker_id:
        return limit if limit > 0 else 0  # 0 = no slice beyond the one ticker
    if limit > 0:
        return limit
    return MOEX_DEFAULT_TICKER_LIMIT
