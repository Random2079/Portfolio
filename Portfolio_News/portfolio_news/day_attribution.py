"""KA — дневная атрибуция портфеля (стоимость + Δ день + топ вкладчиков).

Дневной Δ по бумаге: qty×(last−prev) из MOEX, иначе market_value×pct/(100+pct).
Без советов — только факты.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Protocol

from portfolio_news.bcs_client import Holding
from portfolio_news.metrics_moex import MetricRow, fetch_metric

log = logging.getLogger(__name__)

_CACHE_TTL_SEC = 180.0  # свежий ответ без похода в MOEX
_STALE_MAX_SEC = 1800.0  # отдаём устаревший кэш сразу, refresh в фоне
_TOP_N = 8
_MAX_WORKERS = 12

_cache_lock = threading.Lock()
_cache: Optional["DayAttribution"] = None
_cache_at: float = 0.0
_refresh_lock = threading.Lock()
_refresh_running = False


@dataclass
class DayQuote:
    ticker: str
    last: Optional[float] = None
    prevprice: Optional[float] = None
    changepct: Optional[float] = None
    error: str = ""


@dataclass
class DayContributor:
    ticker: str
    name: str = ""
    day_rub: Optional[float] = None
    day_pct: Optional[float] = None
    weight_pct: Optional[float] = None  # share of |Σ day_rub| among ranked
    market_value: Optional[float] = None


@dataclass
class DayAttribution:
    ok: bool
    error: str = ""
    total_value: Optional[float] = None
    day_rub: Optional[float] = None
    day_pct: Optional[float] = None
    covered_value: Optional[float] = None  # value of positions with a day quote
    missing: int = 0
    top: list[DayContributor] = field(default_factory=list)
    fetched_at: float = 0.0
    source: str = "moex"  # day Δ from MOEX vs BCS holdings
    stale: bool = False  # served from process cache while refresh may run

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _HasQuote(Protocol):
    ticker: str
    last: Optional[float]
    prevprice: Optional[float]
    changepct: Optional[float]


_CASH_IDS = frozenset({"RUB", "USD", "EUR", "CNY", "HKD", "GBP", "CHF"})


def is_cash_holding(h: Holding) -> bool:
    tid = (h.ticker or h.sec_code or "").strip().upper()
    return tid in _CASH_IDS


def day_delta_rub(
    *,
    quantity: Optional[float],
    market_value: Optional[float],
    last: Optional[float] = None,
    prevprice: Optional[float] = None,
    changepct: Optional[float] = None,
) -> Optional[float]:
    """₽ change for one position today. Prefer qty×(last−prev)."""
    if (
        quantity is not None
        and last is not None
        and prevprice is not None
        and last != prevprice
    ):
        return float(quantity) * (float(last) - float(prevprice))
    if (
        quantity is not None
        and last is not None
        and prevprice is not None
        and last == prevprice
    ):
        return 0.0
    if changepct is not None and market_value is not None:
        pct = float(changepct)
        mv = float(market_value)
        if pct <= -100:
            return None
        # mv = qty×last; last = prev×(1+pct/100) → Δ = mv × pct/(100+pct)
        return mv * pct / (100.0 + pct)
    if changepct is not None and quantity is not None and last is not None:
        pct = float(changepct)
        if pct <= -100:
            return None
        prev = float(last) / (1.0 + pct / 100.0)
        return float(quantity) * (float(last) - prev)
    return None


def compute_day_attribution(
    holdings: list[Holding],
    quotes: dict[str, DayQuote] | dict[str, _HasQuote],
    *,
    top_n: int = _TOP_N,
    intentional_skip: Optional[set[str]] = None,
) -> DayAttribution:
    """Pure attribution from BCS holdings + day quotes (no I/O).

    ``intentional_skip`` — tickers we never asked MOEX for (bonds, etc.);
    they do not inflate ``missing``.
    """
    skip = {t.strip().upper() for t in (intentional_skip or set()) if t}
    papers = [h for h in holdings if not is_cash_holding(h)]
    total = 0.0
    total_ok = False
    # Value of papers that participate in day Δ (exclude intentional bond skips)
    active_total = 0.0
    active_ok = False
    for h in papers:
        if h.market_value is None:
            continue
        mv = float(h.market_value)
        total += mv
        total_ok = True
        tid = (h.ticker or h.sec_code or "").strip().upper()
        alt = (h.sec_code or "").strip().upper()
        if tid in skip or (alt and alt in skip):
            continue
        active_total += mv
        active_ok = True

    rows: list[DayContributor] = []
    day_sum = 0.0
    day_ok = False
    covered = 0.0
    missing = 0

    for h in papers:
        tid = (h.ticker or h.sec_code or "").strip().upper()
        alt = (h.sec_code or "").strip().upper()
        if not tid:
            missing += 1
            continue
        if tid in skip or (alt and alt in skip):
            continue
        q = quotes.get(tid)
        if q is None:
            # try sec_code alias
            q = quotes.get(alt) if alt else None
        if q is None:
            missing += 1
            continue

        last = getattr(q, "last", None)
        prev = getattr(q, "prevprice", None)
        pct = getattr(q, "changepct", None)
        rub = day_delta_rub(
            quantity=h.quantity,
            market_value=h.market_value,
            last=last,
            prevprice=prev,
            changepct=pct,
        )
        if rub is None:
            missing += 1
            continue

        day_sum += rub
        day_ok = True
        if h.market_value is not None:
            covered += float(h.market_value)

        # Prefer quote changepct; else derive from last/prev
        day_pct = pct
        if day_pct is None and last is not None and prev not in (None, 0):
            day_pct = (float(last) / float(prev) - 1.0) * 100.0

        rows.append(
            DayContributor(
                ticker=tid,
                name=(h.name or "").strip(),
                day_rub=rub,
                day_pct=day_pct,
                market_value=h.market_value,
            )
        )

    day_pct_port: Optional[float] = None
    # % of the moving sleeve (stocks/funds), not diluted by skipped bonds
    pct_base_value = covered if covered > 0 else (active_total if active_ok else None)
    base = (pct_base_value - day_sum) if (day_ok and pct_base_value is not None) else None
    if base is not None and abs(base) > 1e-9:
        day_pct_port = (day_sum / base) * 100.0
    elif day_ok and pct_base_value is not None and pct_base_value > 0 and abs(day_sum) < 1e-9:
        day_pct_port = 0.0

    # Rank by absolute ₽ contribution; keep sign
    ranked = sorted(rows, key=lambda r: abs(r.day_rub or 0.0), reverse=True)
    abs_sum = sum(abs(r.day_rub or 0.0) for r in ranked) or None
    top: list[DayContributor] = []
    for r in ranked[: max(1, top_n)]:
        w = None
        if abs_sum and r.day_rub is not None:
            w = abs(r.day_rub) / abs_sum * 100.0
        top.append(
            DayContributor(
                ticker=r.ticker,
                name=r.name,
                day_rub=r.day_rub,
                day_pct=r.day_pct,
                weight_pct=w,
                market_value=r.market_value,
            )
        )

    return DayAttribution(
        ok=True,
        error="",
        total_value=total if total_ok else None,
        day_rub=day_sum if day_ok else None,
        day_pct=day_pct_port,
        covered_value=covered if day_ok else None,
        missing=missing,
        top=top,
        fetched_at=time.time(),
        source="moex",
    )


def _kind_for_holding(h: Holding, kind_by_ticker: dict[str, str]) -> str:
    tid = (h.ticker or h.sec_code or "").strip().upper()
    cc = (h.class_code or "").upper()
    name = h.name or ""
    hay = f"{cc} {name}"
    if "TQTF" in hay or "ETF" in hay.upper() or "ПИФ" in name:
        return "equity"  # MOEX shares market for ETFs on TQTF
    if any(b in hay for b in ("TQCB", "TQOB", "TQIR")) or "ОФЗ" in name:
        return "bond"
    if tid.startswith("RU000"):
        return "bond"
    return kind_by_ticker.get(tid, "equity")


def _skip_day_moex_fetch(h: Holding, kind_by_ticker: dict[str, str]) -> bool:
    """Bonds rarely have usable day fields and dominate timeout — skip MOEX fetch."""
    if is_cash_holding(h):
        return True
    if (getattr(h, "asset_class", None) or "").strip().lower() == "bond":
        return True
    return _kind_for_holding(h, kind_by_ticker) == "bond"


def _quote_from_metric(m: MetricRow) -> DayQuote:
    return DayQuote(
        ticker=(m.ticker_id or m.secid or "").upper(),
        last=m.last,
        prevprice=m.prevprice,
        changepct=m.changepct,
        error=m.error or "",
    )


def fetch_quotes_for_holdings(
    holdings: list[Holding],
    *,
    kind_by_ticker: Optional[dict[str, str]] = None,
    max_workers: int = _MAX_WORKERS,
) -> dict[str, DayQuote]:
    """MOEX day quotes for paper holdings (parallel, no live BCS).

    Skips cash + bonds (slow / empty day fields). Callers should pass the
    same skip set into ``compute_day_attribution(..., intentional_skip=…)``
    so bonds do not inflate ``missing``.
    """
    kinds = kind_by_ticker or {}
    papers = [h for h in holdings if not is_cash_holding(h)]
    jobs: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for h in papers:
        if _skip_day_moex_fetch(h, kinds):
            continue
        tid = (h.ticker or h.sec_code or "").strip().upper()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        kind = _kind_for_holding(h, kinds)
        jobs.append((tid, kind, h.name or tid, h.isin or ""))

    out: dict[str, DayQuote] = {}
    if not jobs:
        return out

    def _one(item: tuple[str, str, str, str]) -> DayQuote:
        tid, kind, name, isin = item
        try:
            m = fetch_metric(tid, kind, name, isin=isin)
            return _quote_from_metric(m)
        except Exception as exc:  # noqa: BLE001
            log.warning("day quote failed %s: %s", tid, exc)
            return DayQuote(ticker=tid, error=str(exc))

    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, j): j[0] for j in jobs}
        for fut in as_completed(futs):
            q = fut.result()
            if q.ticker:
                out[q.ticker.upper()] = q
    return out


def intentional_day_skips(
    holdings: list[Holding],
    kind_by_ticker: Optional[dict[str, str]] = None,
) -> set[str]:
    """Tickers skipped for MOEX day quotes (bonds / cash handled elsewhere)."""
    kinds = kind_by_ticker or {}
    out: set[str] = set()
    for h in holdings:
        if is_cash_holding(h):
            continue
        if not _skip_day_moex_fetch(h, kinds):
            continue
        tid = (h.ticker or h.sec_code or "").strip().upper()
        if tid:
            out.add(tid)
        alt = (h.sec_code or "").strip().upper()
        if alt:
            out.add(alt)
    return out


def _compute_and_store(
    holdings: list[Holding],
    *,
    kind_by_ticker: Optional[dict[str, str]],
    top_n: int,
) -> DayAttribution:
    global _cache, _cache_at
    papers = [h for h in holdings if not is_cash_holding(h)]
    skip = intentional_day_skips(holdings, kind_by_ticker)
    expected = [
        h
        for h in papers
        if (h.ticker or h.sec_code or "").strip().upper() not in skip
    ]
    quotes = fetch_quotes_for_holdings(holdings, kind_by_ticker=kind_by_ticker)
    attr = compute_day_attribution(
        holdings, quotes, top_n=top_n, intentional_skip=skip
    )
    if attr.day_rub is None and not attr.error:
        if not papers:
            attr.error = "Нет бумаг в holdings (только валюта / пусто)"
            attr.ok = False
        elif not expected:
            attr.error = "Нет акций/фондов для дневного Δ (только облигации?)"
            attr.ok = False
        elif not quotes:
            attr.error = "Нет котировок MOEX для позиций"
            attr.ok = False
        elif attr.missing >= len(expected):
            attr.error = "Нет дневных цен MOEX по позициям"
            attr.ok = False
        else:
            attr.error = "Не удалось посчитать дневной Δ"
            attr.ok = False
    elif not quotes and attr.day_rub is None:
        attr.error = attr.error or "Нет котировок MOEX для позиций"
        attr.ok = False
    attr.stale = False
    attr.fetched_at = time.time()
    with _cache_lock:
        _cache = attr
        _cache_at = time.time()
    return attr


def _spawn_background_refresh(
    holdings: list[Holding],
    *,
    kind_by_ticker: Optional[dict[str, str]],
    top_n: int,
) -> None:
    global _refresh_running

    def _run() -> None:
        global _refresh_running
        try:
            _compute_and_store(
                holdings, kind_by_ticker=kind_by_ticker, top_n=top_n
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("background day refresh failed: %s", exc)
        finally:
            with _refresh_lock:
                _refresh_running = False

    with _refresh_lock:
        if _refresh_running:
            return
        _refresh_running = True
    threading.Thread(target=_run, name="day-attr-refresh", daemon=True).start()


def build_day_attribution(
    holdings: list[Holding],
    *,
    kind_by_ticker: Optional[dict[str, str]] = None,
    top_n: int = _TOP_N,
    force: bool = False,
) -> DayAttribution:
    """Holdings → MOEX quotes → attribution.

    Fresh cache (<3 min): instant.
    Older ok cache (<30 min): return stale immediately + refresh in background.
    """
    global _cache, _cache_at
    now = time.time()
    stale: Optional[DayAttribution] = None
    holdings_snap: list[Holding] = []
    kinds: dict[str, str] = {}
    with _cache_lock:
        if not force and _cache is not None and _cache.ok:
            age = now - _cache_at
            if age < _CACHE_TTL_SEC:
                hit = _cache
                hit.stale = False
                return hit
            if age < _STALE_MAX_SEC:
                stale = DayAttribution(
                    ok=_cache.ok,
                    error=_cache.error,
                    total_value=_cache.total_value,
                    day_rub=_cache.day_rub,
                    day_pct=_cache.day_pct,
                    covered_value=_cache.covered_value,
                    missing=_cache.missing,
                    top=list(_cache.top),
                    fetched_at=_cache.fetched_at,
                    source=_cache.source,
                    stale=True,
                )
                holdings_snap = list(holdings)
                kinds = dict(kind_by_ticker or {})

    if stale is not None:
        _spawn_background_refresh(
            holdings_snap, kind_by_ticker=kinds, top_n=top_n
        )
        return stale

    try:
        return _compute_and_store(
            holdings, kind_by_ticker=kind_by_ticker, top_n=top_n
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("day attribution failed: %s", exc)
        msg = str(exc)
        if "timed out" in msg.lower() or "ConnectTimeout" in msg:
            msg = "MOEX не отвечает (таймаут)"
        # last resort: any previous ok cache
        with _cache_lock:
            if _cache is not None and _cache.ok:
                return DayAttribution(
                    ok=True,
                    error=_cache.error,
                    total_value=_cache.total_value,
                    day_rub=_cache.day_rub,
                    day_pct=_cache.day_pct,
                    covered_value=_cache.covered_value,
                    missing=_cache.missing,
                    top=list(_cache.top),
                    fetched_at=_cache.fetched_at,
                    source=_cache.source,
                    stale=True,
                )
        return DayAttribution(ok=False, error=msg, fetched_at=time.time())


def clear_day_cache() -> None:
    global _cache, _cache_at
    with _cache_lock:
        _cache = None
        _cache_at = 0.0
