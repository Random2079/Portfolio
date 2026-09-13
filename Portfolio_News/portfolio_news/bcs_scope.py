"""K5: news/MOEX scope = tickers from current BCS holdings only."""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.orm import Session

from portfolio_news.bcs_client import Holding, get_bcs_client
from portfolio_news.config import get_settings
from portfolio_news.import_tickers import upsert_tickers


def _holding_ticker(h: Holding) -> str:
    return (h.ticker or h.sec_code or "").strip().upper()


def _kind_from_holding(h: Holding) -> str:
    ac = (h.asset_class or "").strip().lower()
    if ac == "bond":
        return "bond"
    if ac == "fund":
        return "fund"
    if ac in ("stock", "equity"):
        return "equity"
    # fallback heuristics
    tid = _holding_ticker(h)
    if tid.startswith("RU000") or (h.isin or "").upper().startswith("RU000"):
        return "bond"
    return "equity"


def ticker_ids_from_holdings(holdings: Sequence[Holding]) -> list[str]:
    """Unique instrument tickers in portfolio order; skip cash / empty."""
    out: list[str] = []
    seen: set[str] = set()
    for h in holdings:
        ac = (h.asset_class or "").strip().lower()
        if ac == "cash":
            continue
        tid = _holding_ticker(h)
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def holdings_to_ticker_items(holdings: Sequence[Holding]) -> list[dict]:
    """Minimal ticker rows so news FK / MOEX kind resolve without full Snowball dump."""
    items: list[dict] = []
    seen: set[str] = set()
    for h in holdings:
        if (h.asset_class or "").strip().lower() == "cash":
            continue
        tid = _holding_ticker(h)
        if not tid or tid in seen:
            continue
        seen.add(tid)
        name = (h.name or tid).strip() or tid
        items.append(
            {
                "id": tid,
                "name": name,
                "isin": (h.isin or "").strip(),
                "kind": _kind_from_holding(h),
                "category": "",
                "search_query": name,
            }
        )
    return items


def ensure_tickers_from_holdings(session: Session, holdings: Sequence[Holding]) -> list[str]:
    """Upsert holdings into tickers table; return ordered ids."""
    ids = ticker_ids_from_holdings(holdings)
    items = holdings_to_ticker_items(holdings)
    if items:
        upsert_tickers(session, items)
    return ids


def resolve_bcs_scope(
    session: Session,
    *,
    force: bool = False,
    client=None,
) -> tuple[list[str], str]:
    """Load BCS holdings → ensure tickers → return (ids, error).

    error empty on success (including empty portfolio).
    """
    cfg = get_settings()
    if client is None:
        token = (cfg.bcs_trade_refresh_token or "").strip()
        if not token:
            return [], "bcs_not_configured"
        client = get_bcs_client(
            refresh_token=token,
            client_id=cfg.bcs_trade_client_id or "trade-api-read",
        )
    snap = client.fetch_holdings(force=force)
    if not snap.configured:
        return [], "bcs_not_configured"
    if not snap.ok and not snap.holdings:
        return [], snap.error or "holdings_unavailable"
    ids = ensure_tickers_from_holdings(session, snap.holdings)
    return ids, ""


def filter_ticker_id_to_scope(
    ticker_id: Optional[str],
    scope_ids: list[str],
) -> tuple[Optional[str], str]:
    """If ticker_id set, must be in scope. Returns (effective_id_or_None, error)."""
    if not ticker_id:
        return None, ""
    tid = ticker_id.strip().upper()
    if not tid:
        return None, ""
    if scope_ids and tid not in {x.upper() for x in scope_ids}:
        return None, f"ticker_not_in_bcs:{tid}"
    return tid, ""
