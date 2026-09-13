"""BCS Trade API — read-only portfolio client.

Auth: refresh_token + client_id=trade-api-read (Keycloak).
Docs: https://trade-api.bcs.ru
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

log = logging.getLogger(__name__)

_HOLDINGS_LAST_GOOD = Path(__file__).resolve().parent.parent / "data" / "holdings_last_good.json"

AUTH_URL = (
    "https://be.broker.ru/trade-api-keycloak/realms/tradeapi"
    "/protocol/openid-connect/token"
)
PORTFOLIO_URL = "https://be.broker.ru/trade-api-bff-portfolio/api/v1/portfolio"
LIMITS_URL = "https://be.broker.ru/trade-api-bff-limit/api/v1/limits"
# Docs path is POST /api/v1/trades/search, but the live host is trade-details
# (bff-operations returns Angie HTML 404 for the same path — see bcs-mcp AGENTS.md).
TRADES_SEARCH_URL = (
    "https://be.broker.ru/trade-api-bff-trade-details/api/v1/trades/search"
)

CLIENT_ID_READ = "trade-api-read"
# Soft cache so UI tab switches don't hammer BCS
_CACHE_TTL_SEC = 45.0
# Connect fails fast; read can wait a bit for portfolio JSON
_TIMEOUT = (5.0, 20.0)


def friendly_bcs_error(exc: BaseException) -> str:
    """Short RU message for UI (not a raw urllib dump)."""
    text = str(exc)
    low = text.lower()
    if "getaddrinfo failed" in low or "nameresolutionerror" in low or "failed to resolve" in low:
        return (
            "Не резолвится be.broker.ru (DNS). "
            "Проверь интернет / VPN / zapret — без доступа к БКС позиции не обновятся."
        )
    if "connecttimeout" in low or "timed out" in low or "timeout" in low:
        return (
            "БКС не ответил вовремя (таймаут до be.broker.ru). "
            "Сеть режет или API лежит — лента/MOEX могут работать, позиции — нет."
        )
    if "connection" in low and ("refused" in low or "reset" in low or "aborted" in low):
        return "Связь с be.broker.ru оборвалась. Попробуй позже или другой сеть/VPN."
    if "bcs http 404" in low or "http 404" in low:
        return (
            "БКС не отдаёт историю сделок (HTTP 404). "
            "Нужен сервис trade-api-bff-trade-details (не bff-operations). "
            "Позиции могут работать, сделки — нет."
        )
    if "refresh token" in low or "invalid/expired" in low:
        return text
    if len(text) > 220:
        return text[:200] + "…"
    return text


# UI /api grouping: stock | fund | bond | cash | other
_CASH_IDS = frozenset({"RUB", "USD", "EUR", "CNY", "HKD", "GBP", "CHF", "CASH"})
_BOND_BOARDS = frozenset({"TQCB", "TQOB", "TQIR", "EQOB", "TQRD", "TQOY", "TQIU"})
_FUND_BOARDS = frozenset({"TQTF", "TQIF", "TQTD", "TQTE"})  # ETF / БПИФ boards


def classify_asset_class(
    *,
    ticker: str = "",
    sec_code: str = "",
    isin: str = "",
    class_code: str = "",
    name: str = "",
    db_kind: str = "",
) -> str:
    """Classify a position for Hold/Focus grouping.

    Returns: cash | stock | fund | bond | other.
    Boards / ISIN / name first; optional tickers-DB kind as fallback
    (needed for БПИФ on TQBR like BCSR/GOLD when BCS omits type).
    """
    tid = (ticker or sec_code or "").strip().upper()
    isin_u = (isin or "").strip().upper()
    if not isin_u and tid.startswith("RU000"):
        isin_u = tid
    cc = (class_code or "").strip().upper()
    nm = (name or "").strip()
    nm_l = nm.lower()
    hay = f"{cc} {nm}"

    if tid in _CASH_IDS or "денеж" in nm_l:
        return "cash"
    if cc in _BOND_BOARDS:
        return "bond"
    if cc in _FUND_BOARDS:
        return "fund"
    if isin_u.startswith("RU000A") or isin_u.startswith("SU"):
        return "bond"
    if tid.startswith("RU000A") or tid.startswith("SU"):
        return "bond"
    if any(
        x in nm_l
        for x in ("облиг", "офз", "серия", "бо-п", "бо-0", "бо 0", "купон")
    ):
        return "bond"
    if any(
        x in hay.upper()
        for x in ("ETF", "BPIF", "БПИФ")
    ) or "пиф" in nm_l or "etf" in nm_l or "бпиф" in nm_l:
        return "fund"
    # БПИФ на TQBR часто без слова «фонд» в short name (BCSR «Индекс Мосбиржи»)
    if tid in {"BCSR", "GOLD", "TMOS", "SBMX", "SBSP", "FXGD", "FXUS", "FXRU"}:
        return "fund"
    if "фонд" in nm_l or ("индекс" in nm_l and ("мосбирж" in nm_l or "мос биржа" in nm_l)):
        return "fund"

    kind = (db_kind or "").strip().lower()
    if kind in ("bond", "fund"):
        return kind
    if kind in ("equity", "stock", "share", "shares"):
        return "stock"
    if kind == "cash":
        return "cash"

    if cc in ("TQBR", "TQPI", "SMAL", "EQBR"):
        return "stock"
    if tid and not tid.startswith("RU000"):
        return "stock"
    return "other"


@dataclass
class Holding:
    ticker: str = ""
    isin: str = ""
    sec_code: str = ""
    class_code: str = ""
    name: str = ""
    quantity: Optional[float] = None
    avg_price: Optional[float] = None  # open / average
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    cost_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    currency: str = "RUB"
    asset_class: str = ""  # stock | fund | bond | cash | other


@dataclass
class Operation:
    """One executed BCS deal (K1)."""

    deal_id: str = ""
    ticker: str = ""
    class_code: str = ""
    side: str = ""  # buy / sell / …
    quantity: Optional[float] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    commission: Optional[float] = None
    currency: str = "RUB"
    executed_at: str = ""  # ISO or broker raw datetime string

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperationsSnapshot:
    configured: bool
    ok: bool
    error: str = ""
    fetched_at: float = 0.0
    operations: list[Operation] = field(default_factory=list)
    raw_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HoldingsSnapshot:
    configured: bool
    ok: bool
    error: str = ""
    fetched_at: float = 0.0
    total_value: Optional[float] = None
    cash: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    currency: str = "RUB"
    holdings: list[Holding] = field(default_factory=list)
    raw_keys: list[str] = field(default_factory=list)  # debug: top-level keys seen
    stale: bool = False  # True = показали кэш после сетевого фейла

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def holdings_snapshot_from_dict(data: dict[str, Any]) -> HoldingsSnapshot:
    allowed = set(Holding.__dataclass_fields__)
    rows: list[Holding] = []
    for raw in data.get("holdings") or []:
        if not isinstance(raw, dict):
            continue
        rows.append(Holding(**{k: raw[k] for k in allowed if k in raw}))
    return HoldingsSnapshot(
        configured=bool(data.get("configured", True)),
        ok=True,
        error=str(data.get("error") or ""),
        fetched_at=float(data.get("fetched_at") or 0.0),
        total_value=data.get("total_value"),
        cash=data.get("cash"),
        pnl=data.get("pnl"),
        pnl_pct=data.get("pnl_pct"),
        currency=str(data.get("currency") or "RUB"),
        holdings=rows,
        raw_keys=list(data.get("raw_keys") or []),
        stale=True,
    )


def write_holdings_last_good(snap: HoldingsSnapshot) -> None:
    if not snap.ok or not snap.holdings:
        return
    try:
        _HOLDINGS_LAST_GOOD.parent.mkdir(parents=True, exist_ok=True)
        payload = snap.to_dict()
        payload["stale"] = False
        _HOLDINGS_LAST_GOOD.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        log.warning("holdings last-good write failed: %s", exc)


def load_holdings_last_good() -> Optional[HoldingsSnapshot]:
    if not _HOLDINGS_LAST_GOOD.is_file():
        return None
    try:
        data = json.loads(_HOLDINGS_LAST_GOOD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("holdings"):
        return None
    snap = holdings_snapshot_from_dict(data)
    if not snap.holdings:
        return None
    return snap


class BcsClient:
    def __init__(self, refresh_token: str, client_id: str = CLIENT_ID_READ) -> None:
        self._refresh_token = (refresh_token or "").strip()
        self._client_id = (client_id or CLIENT_ID_READ).strip() or CLIENT_ID_READ
        self._access_token = ""
        self._access_expires_at = 0.0
        self._lock = threading.Lock()
        self._cache: Optional[HoldingsSnapshot] = None
        self._ops_cache: Optional[OperationsSnapshot] = None
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "PortfolioNews/0.3 (+local; BCS read-only)"}
        )
        # No urllib3 connect retries — UI already waits once
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            adapter = HTTPAdapter(
                max_retries=Retry(total=0, connect=0, read=0, redirect=0, status=0)
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        except Exception:  # noqa: BLE001
            pass

    @property
    def configured(self) -> bool:
        return bool(self._refresh_token)

    def _ensure_access(self) -> None:
        now = time.time()
        if self._access_token and now < self._access_expires_at - 30:
            return
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
        }
        resp = self._session.post(
            AUTH_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 401:
            raise RuntimeError(
                "BCS refresh token invalid/expired — выпусти новый в кабинете "
                "(trade-api-read), положи в .env"
            )
        if resp.status_code != 200:
            raise RuntimeError(f"BCS auth HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        access = body.get("access_token")
        if not access:
            raise RuntimeError("BCS auth: no access_token in response")
        self._access_token = str(access)
        expires_in = int(body.get("expires_in") or 300)
        self._access_expires_at = now + expires_in
        # Some BCS flows rotate refresh_token
        new_rt = body.get("refresh_token")
        if new_rt and str(new_rt) != self._refresh_token:
            self._refresh_token = str(new_rt)
            log.info("BCS rotated refresh_token in-memory (update .env if needed)")

    def _auth_headers(self) -> dict[str, str]:
        self._ensure_access()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _get_json(self, url: str) -> Any:
        resp = self._session.get(url, headers=self._auth_headers(), timeout=_TIMEOUT)
        if resp.status_code == 401:
            # one retry after forced refresh
            self._access_expires_at = 0
            resp = self._session.get(url, headers=self._auth_headers(), timeout=_TIMEOUT)
        if resp.status_code == 429:
            raise RuntimeError("BCS rate limit (429) — подожди и обнови снова")
        if resp.status_code != 200:
            raise RuntimeError(f"BCS HTTP {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        *,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        resp = self._session.post(
            url,
            headers=self._auth_headers(),
            json=body,
            params=params,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 401:
            self._access_expires_at = 0
            resp = self._session.post(
                url,
                headers=self._auth_headers(),
                json=body,
                params=params,
                timeout=_TIMEOUT,
            )
        if resp.status_code == 429:
            raise RuntimeError("BCS rate limit (429) — подожди и обнови снова")
        if resp.status_code != 200:
            raise RuntimeError(f"BCS HTTP {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    def fetch_holdings(self, *, force: bool = False) -> HoldingsSnapshot:
        if not self.configured:
            return HoldingsSnapshot(
                configured=False,
                ok=False,
                error="BCS_TRADE_REFRESH_TOKEN не задан в .env",
            )
        with self._lock:
            if (
                not force
                and self._cache
                and self._cache.ok
                and not self._cache.stale
                and time.time() - self._cache.fetched_at < _CACHE_TTL_SEC
            ):
                return self._cache
            try:
                snap = self._fetch_uncached()
                snap.stale = False
                snap.error = ""
            except Exception as exc:  # noqa: BLE001
                msg = friendly_bcs_error(exc)
                log.warning("BCS holdings failed: %s", exc)
                # Keep last good snapshot so UI doesn't blank for 30s every tab switch
                if self._cache and self._cache.ok and self._cache.holdings:
                    stale = HoldingsSnapshot(
                        configured=True,
                        ok=True,
                        error=msg,
                        fetched_at=self._cache.fetched_at,
                        total_value=self._cache.total_value,
                        cash=self._cache.cash,
                        pnl=self._cache.pnl,
                        pnl_pct=self._cache.pnl_pct,
                        currency=self._cache.currency,
                        holdings=list(self._cache.holdings),
                        raw_keys=list(self._cache.raw_keys),
                        stale=True,
                    )
                    self._cache = stale
                    return stale
                disk = load_holdings_last_good()
                if disk and disk.holdings:
                    disk.error = msg
                    disk.stale = True
                    self._cache = disk
                    return disk
                snap = HoldingsSnapshot(
                    configured=True,
                    ok=False,
                    error=msg,
                    fetched_at=time.time(),
                    stale=False,
                )
            else:
                write_holdings_last_good(snap)
            self._cache = snap
            return snap

    def fetch_operations(
        self,
        *,
        force: bool = False,
        ticker: str = "",
        limit: int = 100,
    ) -> OperationsSnapshot:
        """Executed deals from BCS (K1). Soft-cached like holdings."""
        if not self.configured:
            return OperationsSnapshot(
                configured=False,
                ok=False,
                error="BCS_TRADE_REFRESH_TOKEN не задан в .env",
            )
        with self._lock:
            if (
                not force
                and self._ops_cache
                and self._ops_cache.ok
                and time.time() - self._ops_cache.fetched_at < _CACHE_TTL_SEC
            ):
                return self._filter_ops(self._ops_cache, ticker=ticker, limit=limit)
            try:
                snap = self._fetch_ops_uncached()
            except Exception as exc:  # noqa: BLE001
                msg = friendly_bcs_error(exc)
                log.warning("BCS deals failed: %s", exc)
                if self._ops_cache and self._ops_cache.ok and self._ops_cache.operations:
                    stale = OperationsSnapshot(
                        configured=True,
                        ok=True,
                        error=msg,
                        fetched_at=self._ops_cache.fetched_at,
                        operations=list(self._ops_cache.operations),
                        raw_keys=list(self._ops_cache.raw_keys),
                    )
                    self._ops_cache = stale
                    return self._filter_ops(stale, ticker=ticker, limit=limit)
                snap = OperationsSnapshot(
                    configured=True,
                    ok=False,
                    error=msg,
                    fetched_at=time.time(),
                )
            self._ops_cache = snap
            return self._filter_ops(snap, ticker=ticker, limit=limit)

    def _fetch_ops_uncached(self) -> OperationsSnapshot:
        # Live: POST …/trade-api-bff-trade-details/api/v1/trades/search
        # page/size = query; body filters use startDateTime/endDateTime
        # (format yyyy-MM-dd'T'HH:mm:ss.SSSX — Z or +0300, not +03:00).
        # Data only since 2026-01-26 per BCS docs.
        date_from = "2026-01-26T00:00:00.000Z"
        date_to = time.strftime("%Y-%m-%dT23:59:59.999Z", time.gmtime())
        body: dict[str, Any] = {
            "startDateTime": date_from,
            "endDateTime": date_to,
        }
        page_size = 100  # API max
        all_ops: list[Operation] = []
        raw_keys: list[str] = []
        page = 0
        total_pages = 1
        while page < total_pages and page < 50:  # hard cap
            raw = self._post_json(
                TRADES_SEARCH_URL,
                body,
                params={"page": page, "size": page_size},
            )
            if isinstance(raw, dict):
                if not raw_keys:
                    raw_keys = sorted(raw.keys())
                try:
                    total_pages = max(1, int(raw.get("totalPages") or 1))
                except (TypeError, ValueError):
                    total_pages = 1
            batch = _parse_deals(raw)
            all_ops.extend(batch)
            if not batch:
                break
            page += 1
        # newest first (parser already sorts per page)
        all_ops.sort(key=lambda o: o.executed_at or "", reverse=True)
        return OperationsSnapshot(
            configured=True,
            ok=True,
            error="",
            fetched_at=time.time(),
            operations=all_ops,
            raw_keys=raw_keys,
        )

    @staticmethod
    def _filter_ops(
        snap: OperationsSnapshot, *, ticker: str = "", limit: int = 100
    ) -> OperationsSnapshot:
        rows = list(snap.operations)
        tid = (ticker or "").strip().upper()
        if tid:
            rows = [o for o in rows if (o.ticker or "").upper() == tid]
        if limit and limit > 0:
            rows = rows[:limit]
        return OperationsSnapshot(
            configured=snap.configured,
            ok=snap.ok,
            error=snap.error,
            fetched_at=snap.fetched_at,
            operations=rows,
            raw_keys=list(snap.raw_keys),
        )

    def _fetch_uncached(self) -> HoldingsSnapshot:
        raw = self._get_json(PORTFOLIO_URL)
        raw_keys: list[str] = []
        if isinstance(raw, dict):
            raw_keys = sorted(raw.keys())
        holdings = _parse_portfolio(raw)

        # Enrich qty from limits if portfolio rows lack quantity
        try:
            limits = self._get_json(LIMITS_URL)
            holdings = _merge_limits(holdings, limits)
        except Exception as exc:  # noqa: BLE001
            log.debug("BCS limits skip: %s", exc)

        summary = _parse_summary(raw)
        return HoldingsSnapshot(
            configured=True,
            ok=True,
            error="",
            fetched_at=time.time(),
            total_value=summary.get("total_value"),
            cash=summary.get("cash"),
            pnl=summary.get("pnl"),
            pnl_pct=summary.get("pnl_pct"),
            currency=str(summary.get("currency") or "RUB"),
            holdings=holdings,
            raw_keys=raw_keys,
        )


def _f(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _s(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _walk_positions(node: Any) -> list[dict]:
    """Find list-of-dicts that look like positions (flexible schema)."""
    if isinstance(node, list):
        if node and isinstance(node[0], dict):
            sample = node[0]
            keys = {k.lower() for k in sample}
            if keys & {
                "ticker",
                "isin",
                "seccode",
                "sec_code",
                "quantity",
                "qty",
                "marketvalue",
                "market_value",
                "openprice",
                "balance",
            }:
                return [x for x in node if isinstance(x, dict)]
        found: list[dict] = []
        for item in node:
            found.extend(_walk_positions(item))
        return found
    if isinstance(node, dict):
        for key in (
            "positions",
            "Positions",
            "assets",
            "securities",
            "portfolio",
            "items",
            "data",
        ):
            if key in node:
                found = _walk_positions(node[key])
                if found:
                    return found
        # nested summary wrapper
        for v in node.values():
            if isinstance(v, (dict, list)):
                found = _walk_positions(v)
                if found:
                    return found
    return []


def _row_to_holding(row: dict) -> Holding:
    lower = {str(k).lower(): v for k, v in row.items()}

    def pick(*names: str) -> Any:
        for n in names:
            if n.lower() in lower:
                return lower[n.lower()]
        return None

    qty = _f(pick("quantity", "qty", "balance", "currentBalance", "current_balance", "lots"))
    avg = _f(
        pick(
            "openPrice",
            "open_price",
            "avgPrice",
            "averagePrice",
            "average_price",
            "balancePrice",
            "price",
        )
    )
    mkt = _f(pick("marketPrice", "market_price", "currentPrice", "last", "current_price"))
    mv = _f(
        pick(
            "marketValue",
            "market_value",
            "currentValue",
            "currentValueRub",
            "current_value",
            "value",
            "amount",
        )
    )
    cost = _f(
        pick(
            "costValue",
            "cost_value",
            "balanceValue",
            "balanceValueRub",
            "invested",
        )
    )
    pnl = _f(pick("profitLoss", "profit_loss", "pnl", "unrealizedPnl", "unrealizedPL"))
    pnl_pct = _f(
        pick("profitLossPct", "profit_loss_pct", "pnlPct", "pnl_pct", "unrealizedPercentPL")
    )
    if cost is None and qty is not None and avg is not None:
        cost = qty * avg
    if mv is None and qty is not None and mkt is not None:
        mv = qty * mkt
    if pnl is None and mv is not None and cost is not None:
        pnl = mv - cost
    if pnl_pct is None and pnl is not None and cost not in (None, 0):
        pnl_pct = (pnl / cost) * 100.0

    ticker = _s(pick("ticker", "secCode", "sec_code", "symbol", "baseAssetTicker"))
    isin = _s(pick("isin", "ISIN"))
    if not isin and ticker.upper().startswith("RU000"):
        isin = ticker

    sec_code = _s(pick("secCode", "sec_code"))
    class_code = _s(pick("classCode", "class_code", "board"))
    name = _s(pick("name", "displayName", "shortName", "short_name", "secName"))
    asset_class = classify_asset_class(
        ticker=ticker,
        sec_code=sec_code,
        isin=isin,
        class_code=class_code,
        name=name,
    )
    return Holding(
        ticker=ticker,
        isin=isin,
        sec_code=sec_code,
        class_code=class_code,
        name=name,
        quantity=qty,
        avg_price=avg,
        market_price=mkt,
        market_value=mv,
        cost_value=cost,
        pnl=pnl,
        pnl_pct=pnl_pct,
        currency=_s(pick("currency", "currencyId", "faceUnit")) or "RUB",
        asset_class=asset_class,
    )


def _dedupe_holdings(holdings: list[Holding]) -> list[Holding]:
    """BCS portfolio list often repeats the same row 4× (same account)."""
    seen: dict[tuple[str, str, str], Holding] = {}
    order: list[tuple[str, str, str]] = []
    for h in holdings:
        key = (
            (h.ticker or h.sec_code or h.isin).upper(),
            (h.class_code or "").upper(),
            (h.currency or "RUB").upper(),
        )
        if key not in seen:
            seen[key] = h
            order.append(key)
    return [seen[k] for k in order]


def _parse_portfolio(raw: Any) -> list[Holding]:
    rows = _walk_positions(raw)
    out: list[Holding] = []
    for row in rows:
        h = _row_to_holding(row)
        if h.ticker or h.isin or h.sec_code:
            out.append(h)
    return _dedupe_holdings(out)


def _parse_summary(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    summary = raw.get("summary") or raw.get("Summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    lower = {str(k).lower(): v for k, v in {**raw, **summary}.items()}
    return {
        "total_value": _f(
            lower.get("totalvalue")
            or lower.get("total_value")
            or lower.get("portfolioValue")
        ),
        "cash": _f(lower.get("cash") or lower.get("money")),
        "pnl": _f(lower.get("profitloss") or lower.get("pnl")),
        "pnl_pct": _f(lower.get("profitlosspct") or lower.get("pnl_pct")),
        "currency": _s(lower.get("currency")) or "RUB",
    }


def _walk_deals(node: Any) -> list[dict]:
    """Find list-of-dicts that look like executed deals."""
    if isinstance(node, list):
        if node and isinstance(node[0], dict):
            sample = node[0]
            keys = {k.lower() for k in sample}
            if keys & {
                "dealid",
                "deal_id",
                "tradeid",
                "trade_id",
                "tradenum",
                "trade_num",
                "executedat",
                "executed_at",
                "tradedatetime",
                "trade_date_time",
                "side",
                "volume",
                "commission",
                "tradequantity",
            } or (
                ("ticker" in keys or "seccode" in keys or "sec_code" in keys)
                and (
                    "price" in keys
                    or "quantity" in keys
                    or "qty" in keys
                    or "tradequantity" in keys
                )
            ):
                return [x for x in node if isinstance(x, dict)]
        found: list[dict] = []
        for item in node:
            found.extend(_walk_deals(item))
        return found
    if isinstance(node, dict):
        for key in (
            "deals",
            "Deals",
            "trades",
            "Trades",
            "records",
            "operations",
            "items",
            "data",
            "content",
        ):
            if key in node:
                found = _walk_deals(node[key])
                if found:
                    return found
        for v in node.values():
            if isinstance(v, (dict, list)):
                found = _walk_deals(v)
                if found:
                    return found
    return []


def _side_norm(val: Any) -> str:
    s = _s(val).lower()
    if s in ("b", "buy", "покупка", "1"):
        return "buy"
    if s in ("s", "sell", "продажа", "2"):
        return "sell"
    return s


def _dt_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        # ms vs sec epoch heuristic
        ts = float(val)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))
        except (OverflowError, OSError, ValueError):
            return str(val)
    return _s(val)


def _row_to_operation(row: dict) -> Operation:
    lower = {str(k).lower(): v for k, v in row.items()}

    def pick(*names: str) -> Any:
        for n in names:
            if n.lower() in lower:
                return lower[n.lower()]
        return None

    qty = _f(
        pick(
            "tradeQuantity",
            "trade_quantity",
            "quantity",
            "qty",
            "lots",
            "tradeQuantityLots",
            "amount",
        )
    )
    price = _f(pick("price", "dealPrice", "deal_price", "avgPrice"))
    volume = _f(pick("volume", "sum", "value", "amountRub", "amount_rub"))
    if volume is None and qty is not None and price is not None:
        volume = qty * price

    return Operation(
        deal_id=_s(
            pick(
                "tradeNum",
                "trade_num",
                "dealId",
                "deal_id",
                "id",
                "tradeId",
                "trade_id",
            )
        ),
        ticker=_s(pick("ticker", "secCode", "sec_code", "symbol")),
        class_code=_s(pick("classCode", "class_code", "board")),
        side=_side_norm(pick("side", "direction", "buySell", "buy_sell")),
        quantity=qty,
        price=price,
        volume=volume,
        commission=_f(pick("commission", "fee", "brokerFee")),
        currency=_s(
            pick(
                "settlementCurrency",
                "priceCurrency",
                "currency",
                "currencyId",
                "faceUnit",
            )
        )
        or "RUB",
        executed_at=_dt_str(
            pick(
                "tradeDateTime",
                "trade_date_time",
                "executedAt",
                "executed_at",
                "dateTime",
                "datetime",
                "date",
                "time",
            )
        ),
    )


def _parse_deals(raw: Any) -> list[Operation]:
    rows = _walk_deals(raw)
    out: list[Operation] = []
    for row in rows:
        op = _row_to_operation(row)
        if op.ticker or op.deal_id or op.executed_at:
            out.append(op)
    # newest first when ISO-ish timestamps present
    out.sort(key=lambda o: o.executed_at or "", reverse=True)
    return out


def _merge_limits(holdings: list[Holding], limits: Any) -> list[Holding]:
    """Fill missing quantity from depoLimit when portfolio omitted it."""
    if not isinstance(limits, dict):
        return holdings
    depo = limits.get("depoLimit") or limits.get("DepoLimit") or []
    if not isinstance(depo, list):
        return holdings
    by_sec: dict[str, float] = {}
    for row in depo:
        if not isinstance(row, dict):
            continue
        lower = {str(k).lower(): v for k, v in row.items()}
        code = _s(lower.get("seccode") or lower.get("sec_code") or lower.get("ticker"))
        bal = _f(
            lower.get("currentbalance")
            or lower.get("current_balance")
            or lower.get("free")
            or lower.get("openbalance")
        )
        if code and bal is not None:
            by_sec[code.upper()] = bal
    if not by_sec:
        return holdings
    for h in holdings:
        if h.quantity is not None:
            continue
        for key in (h.sec_code, h.ticker):
            if key and key.upper() in by_sec:
                h.quantity = by_sec[key.upper()]
                break
    return holdings


def match_holding(
    holdings: list[Holding],
    *,
    ticker_id: str = "",
    isin: str = "",
) -> Optional[Holding]:
    tid = (ticker_id or "").strip().upper()
    isin_u = (isin or "").strip().upper()
    for h in holdings:
        if isin_u and h.isin.upper() == isin_u:
            return h
        if tid and tid in {h.ticker.upper(), h.sec_code.upper(), h.isin.upper()}:
            return h
    return None


_client: Optional[BcsClient] = None
_client_lock = threading.Lock()


def get_bcs_client(refresh_token: str = "", client_id: str = CLIENT_ID_READ) -> BcsClient:
    global _client
    with _client_lock:
        if _client is None or (refresh_token and refresh_token != _client._refresh_token):
            _client = BcsClient(refresh_token=refresh_token, client_id=client_id)
        return _client
