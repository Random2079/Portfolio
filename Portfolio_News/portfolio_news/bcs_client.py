"""BCS Trade API — read-only portfolio client.

Auth: refresh_token + client_id=trade-api-read (Keycloak).
Docs: https://trade-api.bcs.ru
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import requests

log = logging.getLogger(__name__)

AUTH_URL = (
    "https://be.broker.ru/trade-api-keycloak/realms/tradeapi"
    "/protocol/openid-connect/token"
)
PORTFOLIO_URL = "https://be.broker.ru/trade-api-bff-portfolio/api/v1/portfolio"
LIMITS_URL = "https://be.broker.ru/trade-api-bff-limit/api/v1/limits"

CLIENT_ID_READ = "trade-api-read"
# Soft cache so UI tab switches don't hammer BCS
_CACHE_TTL_SEC = 45.0


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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class BcsClient:
    def __init__(self, refresh_token: str, client_id: str = CLIENT_ID_READ) -> None:
        self._refresh_token = (refresh_token or "").strip()
        self._client_id = (client_id or CLIENT_ID_READ).strip() or CLIENT_ID_READ
        self._access_token = ""
        self._access_expires_at = 0.0
        self._lock = threading.Lock()
        self._cache: Optional[HoldingsSnapshot] = None
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "PortfolioNews/0.3 (+local; BCS read-only)"}
        )

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
            timeout=30,
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
        resp = self._session.get(url, headers=self._auth_headers(), timeout=30)
        if resp.status_code == 401:
            # one retry after forced refresh
            self._access_expires_at = 0
            resp = self._session.get(url, headers=self._auth_headers(), timeout=30)
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
                and time.time() - self._cache.fetched_at < _CACHE_TTL_SEC
            ):
                return self._cache
            try:
                snap = self._fetch_uncached()
            except Exception as exc:  # noqa: BLE001
                log.warning("BCS holdings failed: %s", exc)
                snap = HoldingsSnapshot(
                    configured=True,
                    ok=False,
                    error=str(exc),
                    fetched_at=time.time(),
                )
            self._cache = snap
            return snap

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
    avg = _f(pick("openPrice", "open_price", "avgPrice", "averagePrice", "average_price", "price"))
    mkt = _f(pick("marketPrice", "market_price", "last", "currentPrice"))
    mv = _f(pick("marketValue", "market_value", "value", "amount"))
    cost = _f(pick("costValue", "cost_value", "invested", "balanceValue"))
    pnl = _f(pick("profitLoss", "profit_loss", "pnl", "unrealizedPnl"))
    pnl_pct = _f(pick("profitLossPct", "profit_loss_pct", "pnlPct", "pnl_pct"))
    if cost is None and qty is not None and avg is not None:
        cost = qty * avg
    if mv is None and qty is not None and mkt is not None:
        mv = qty * mkt
    if pnl is None and mv is not None and cost is not None:
        pnl = mv - cost
    if pnl_pct is None and pnl is not None and cost not in (None, 0):
        pnl_pct = (pnl / cost) * 100.0

    return Holding(
        ticker=_s(pick("ticker", "secCode", "sec_code", "symbol")),
        isin=_s(pick("isin", "ISIN")),
        sec_code=_s(pick("secCode", "sec_code")),
        class_code=_s(pick("classCode", "class_code", "board")),
        name=_s(pick("name", "shortName", "short_name", "secName")),
        quantity=qty,
        avg_price=avg,
        market_price=mkt,
        market_value=mv,
        cost_value=cost,
        pnl=pnl,
        pnl_pct=pnl_pct,
        currency=_s(pick("currency", "currencyId", "faceUnit")) or "RUB",
    )


def _parse_portfolio(raw: Any) -> list[Holding]:
    rows = _walk_positions(raw)
    out: list[Holding] = []
    for row in rows:
        h = _row_to_holding(row)
        if h.ticker or h.isin or h.sec_code:
            out.append(h)
    return out


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
