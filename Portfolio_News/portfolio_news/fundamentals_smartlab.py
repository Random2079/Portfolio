"""Equity multiples from Smart-Lab /q/shares_fundamental/ (HTML tables)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import requests
from sqlalchemy.orm import Session

from portfolio_news.db import SmartlabFundamentalsCache

log = logging.getLogger(__name__)

SMARTLAB_FUND_URL = "https://smart-lab.ru/q/shares_fundamental/"
# Extra one-metric tables (same HTML shape; merge by ticker).
SMARTLAB_FIELD_URLS: tuple[str, ...] = (
    "https://smart-lab.ru/q/shares_fundamental/?field=fcf",
    "https://smart-lab.ru/q/shares_fundamental/?field=fcf_yield",
    "https://smart-lab.ru/q/shares_fundamental/?field=capex",
    "https://smart-lab.ru/q/shares_fundamental/?field=fcf_share",
    # IT/рост: выручка + «Изм. %, г/г» (только на этой таблице — см. parse)
    "https://smart-lab.ru/q/shares_fundamental/?field=revenue",
    # девелоп: контракты/продажи (прокси эскроу-пайплайна; кэша «денег на эскроу» в таблице нет)
    "https://smart-lab.ru/q/shares_fundamental/?field=pending_apartment_sales_rub",
    "https://smart-lab.ru/q/shares_fundamental/?field=pending_apartment_sales",
    "https://smart-lab.ru/q/shares_fundamental/?field=apartment_sales",
)
_HEADERS = {
    "User-Agent": "PortfolioNews/0.2 (+local; personal monitor)",
    "Accept": "text/html,application/xhtml+xml",
}
_CACHE_FRESH_SEC = 12 * 3600
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
_TAG = re.compile(r"<[^>]+>")
_TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.I | re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)

# header fragment (lower, spaces stripped) → field key; longer fragments first
_COL_MAP: list[tuple[str, str]] = [
    ("тикер", "ticker"),
    ("доходностьfcf", "fcf_yield"),
    ("fcf/акцию", "fcf_share"),
    ("fcf,млрд", "fcf_bn"),
    ("fcf", "fcf_bn"),
    ("capex,млрд", "capex_bn"),
    ("capex", "capex_bn"),
    ("контрактынапродажуруб", "pending_sales_rub"),
    ("контрактынапродажум", "pending_sales_m2"),
    ("продажинедвижимости", "apartment_sales_m2"),
    ("выручка,млрд", "revenue_bn"),
    ("выручка", "revenue_bn"),
    ("p/e", "pe"),
    ("p/b", "pb"),
    ("p/s", "ps"),
    ("ev/ebitda", "ev_ebitda"),
    ("долг/ebitda", "debt_ebitda"),
    ("дд ао", "div_yield_ao"),
    ("дд ап", "div_yield_ap"),
    ("roe", "roe"),
    ("отчет", "report"),
    ("отчёт", "report"),
]

_NUM_KEYS = (
    "pe",
    "pb",
    "ps",
    "ev_ebitda",
    "debt_ebitda",
    "div_yield_ao",
    "div_yield_ap",
    "roe",
    "fcf_bn",
    "fcf_yield",
    "capex_bn",
    "fcf_share",
    "pending_sales_rub",
    "pending_sales_m2",
    "apartment_sales_m2",
    "revenue_bn",
    "revenue_yoy",
)


@dataclass
class FundamentalRow:
    ticker: str
    pe: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    ev_ebitda: Optional[float] = None
    debt_ebitda: Optional[float] = None
    div_yield_ao: Optional[float] = None
    div_yield_ap: Optional[float] = None
    roe: Optional[float] = None
    fcf_bn: Optional[float] = None  # млрд ₽
    fcf_yield: Optional[float] = None  # %
    capex_bn: Optional[float] = None  # млрд ₽
    fcf_share: Optional[float] = None  # ₽/акцию
    pending_sales_rub: Optional[float] = None  # контракты на продажу, млрд ₽
    pending_sales_m2: Optional[float] = None  # контракты, тыс. м²
    apartment_sales_m2: Optional[float] = None  # продажи недвижимости, тыс. м²
    revenue_bn: Optional[float] = None  # выручка, млрд ₽
    revenue_yoy: Optional[float] = None  # выручка изм. %, г/г
    report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def row_from_dict(ticker: str, d: dict[str, Any]) -> FundamentalRow:
    return FundamentalRow(
        ticker=ticker,
        pe=d.get("pe"),
        pb=d.get("pb"),
        ps=d.get("ps"),
        ev_ebitda=d.get("ev_ebitda"),
        debt_ebitda=d.get("debt_ebitda"),
        div_yield_ao=d.get("div_yield_ao"),
        div_yield_ap=d.get("div_yield_ap"),
        roe=d.get("roe"),
        fcf_bn=d.get("fcf_bn"),
        fcf_yield=d.get("fcf_yield"),
        capex_bn=d.get("capex_bn"),
        fcf_share=d.get("fcf_share"),
        pending_sales_rub=d.get("pending_sales_rub"),
        pending_sales_m2=d.get("pending_sales_m2"),
        apartment_sales_m2=d.get("apartment_sales_m2"),
        revenue_bn=d.get("revenue_bn"),
        revenue_yoy=d.get("revenue_yoy"),
        report=str(d.get("report") or ""),
    )


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", html or "")).strip()


def _ru_num(raw: str) -> Optional[float]:
    s = (raw or "").replace("\xa0", "").replace(" ", "").replace("%", "")
    s = s.replace(",", ".")
    if not s or s in {"-", "—", "–", "n/a", "N/A"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _header_key(th: str) -> Optional[str]:
    t = (th or "").lower().replace(" ", "")
    t = t.replace("&nbsp;", "")
    for frag, key in _COL_MAP:
        if frag.replace(" ", "") in t:
            return key
    return None


def parse_smartlab_fundamental_html(html: str) -> dict[str, FundamentalRow]:
    """Pure HTML parser — testable without network. Merges all data tables by ticker."""
    out: dict[str, FundamentalRow] = {}
    for table in _TABLE.findall(html or ""):
        rows = _TR.findall(table)
        if not rows:
            continue
        header_idx: dict[str, int] = {}
        data_start = 0
        for ri, row in enumerate(rows[:3]):
            ths = [_strip(x) for x in _TH.findall(row)]
            if not ths:
                continue
            for i, th in enumerate(ths):
                key = _header_key(th)
                if key:
                    header_idx[key] = i
            # «Изм. %, г/г» есть на многих field-таблицах — YoY выручки только
            # рядом с колонкой «Выручка» (иначе подтянем YoY контрактов/FCF).
            if "revenue_bn" in header_idx:
                for i, th in enumerate(ths):
                    t = (th or "").lower().replace(" ", "").replace("&nbsp;", "")
                    if "г/г" in t and "изм" in t:
                        header_idx["revenue_yoy"] = i
                        break
            if "ticker" in header_idx:
                data_start = ri + 1
                break
        if "ticker" not in header_idx:
            continue
        for row in rows[data_start:]:
            tds = [_strip(x) for x in _TD.findall(row)]
            if not tds:
                continue
            ti = header_idx["ticker"]
            if ti >= len(tds):
                continue
            ticker = tds[ti].strip().upper()
            if not _TICKER_RE.match(ticker):
                continue
            row_obj = out.get(ticker) or FundamentalRow(ticker=ticker)

            def _get(key: str) -> Optional[str]:
                i = header_idx.get(key)
                if i is None or i >= len(tds):
                    return None
                return tds[i]

            for key in _NUM_KEYS:
                raw = _get(key)
                if raw is None:
                    continue
                num = _ru_num(raw)
                if num is not None:
                    setattr(row_obj, key, num)
            rep = _get("report")
            if rep:
                row_obj.report = rep
            out[ticker] = row_obj
    return out


def merge_fundamental_maps(
    base: dict[str, FundamentalRow], extra: dict[str, FundamentalRow]
) -> dict[str, FundamentalRow]:
    """Merge field-table rows into base; keep existing non-null values."""
    for ticker, add in extra.items():
        cur = base.get(ticker) or FundamentalRow(ticker=ticker)
        for key in _NUM_KEYS:
            new_v = getattr(add, key, None)
            if new_v is not None:
                setattr(cur, key, new_v)
        if add.report and not cur.report:
            cur.report = add.report
        base[ticker] = cur
    return base


def fetch_smartlab_fundamentals() -> dict[str, FundamentalRow]:
    rows: dict[str, FundamentalRow] = {}
    try:
        resp = requests.get(SMARTLAB_FUND_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        rows = parse_smartlab_fundamental_html(resp.text)
    except Exception as exc:  # noqa: BLE001
        log.warning("smartlab fundamentals failed: %s", exc)
        return {}

    for url in SMARTLAB_FIELD_URLS:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            part = parse_smartlab_fundamental_html(resp.text)
            merge_fundamental_maps(rows, part)
        except Exception as exc:  # noqa: BLE001
            log.warning("smartlab field fetch failed %s: %s", url, exc)

    with_fcf = sum(1 for r in rows.values() if r.fcf_bn is not None or r.fcf_yield is not None)
    log.info("smartlab fundamentals: %s tickers (%s with FCF)", len(rows), with_fcf)
    return rows


def _cache_has_fcf_layer(raw: dict[str, Any]) -> bool:
    """Old / partial caches must refresh (FCF/CAPEX + pending sales + revenue YoY)."""
    n_fcf = 0
    n_capex = 0
    n_pending = 0
    n_rev_yoy = 0
    for d in raw.values():
        if not isinstance(d, dict):
            continue
        if d.get("fcf_bn") is not None:
            n_fcf += 1
        if d.get("capex_bn") is not None:
            n_capex += 1
        if d.get("pending_sales_rub") is not None or d.get("pending_sales_m2") is not None:
            n_pending += 1
        if d.get("revenue_yoy") is not None:
            n_rev_yoy += 1
    return n_fcf >= 50 and n_capex >= 50 and n_pending >= 1 and n_rev_yoy >= 50


def _now() -> float:
    return time.time()


def load_fundamentals_cache(session: Session) -> Optional[tuple[dict[str, Any], float]]:
    row = session.get(SmartlabFundamentalsCache, 1)
    if row is None or not (row.payload_json or "").strip():
        return None
    import json

    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data, float(row.updated_at or 0.0)


def save_fundamentals_cache(session: Session, by_ticker: dict[str, FundamentalRow]) -> None:
    import json

    payload = {t: r.to_dict() for t, r in by_ticker.items()}
    row = session.get(SmartlabFundamentalsCache, 1)
    if row is None:
        row = SmartlabFundamentalsCache(id=1)
        session.add(row)
    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.updated_at = _now()
    row.ok = 1 if payload else 0
    session.commit()


def fundamentals_cache_fresh(updated_at: float, *, max_age: float = _CACHE_FRESH_SEC) -> bool:
    return updated_at > 0 and (_now() - updated_at) < max_age


def get_fundamentals_map(
    session: Session, *, force: bool = False
) -> tuple[dict[str, FundamentalRow], str]:
    """Cache-first universe. Returns (map, as_of_iso_hint)."""
    from datetime import datetime, timedelta, timezone

    as_of = ""
    if not force:
        cached = load_fundamentals_cache(session)
        if cached and fundamentals_cache_fresh(cached[1]) and _cache_has_fcf_layer(cached[0]):
            raw, upd = cached
            out = {t: row_from_dict(t, d) for t, d in raw.items() if isinstance(d, dict)}
            as_of = datetime.fromtimestamp(upd, tz=timezone(timedelta(hours=5))).strftime(
                "%Y-%m-%d %H:%M"
            )
            return out, as_of

    fetched = fetch_smartlab_fundamentals()
    cached = load_fundamentals_cache(session)
    combined: dict[str, FundamentalRow] = {}
    if cached:
        combined = {
            t: row_from_dict(t, d) for t, d in cached[0].items() if isinstance(d, dict)
        }
    if fetched:
        # overlay: new non-null wins; failed field pages don't wipe older values
        merge_fundamental_maps(combined, fetched)
    if combined:
        try:
            save_fundamentals_cache(session, combined)
        except Exception as exc:  # noqa: BLE001
            log.warning("smartlab fund cache save failed: %s", exc)
        as_of = datetime.now(timezone(timedelta(hours=5))).strftime("%Y-%m-%d %H:%M")
        return combined, as_of

    return {}, ""


def resolve_fundamental(
    by_ticker: dict[str, FundamentalRow], ticker: str
) -> tuple[Optional[FundamentalRow], str, bool]:
    """Return (row, lookup_ticker, used_alias). Preferred (…P) falls back to common."""
    tid = (ticker or "").strip().upper()
    if tid in by_ticker:
        return by_ticker[tid], tid, False
    if len(tid) > 2 and tid.endswith("P"):
        base = tid[:-1]
        if base in by_ticker:
            return by_ticker[base], base, True
    return None, tid, False
