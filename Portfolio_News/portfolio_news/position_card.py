"""K4: position facts card — avg / buy dates / unrealized PnL / weight (no advice)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from portfolio_news.bcs_client import Holding, Operation
from portfolio_news.day_attribution import is_cash_holding


@dataclass
class AvgVsPrice:
    """Fact: current vs average (per unit). Not a recommendation."""

    diff: Optional[float] = None  # current − avg (₽)
    diff_pct: Optional[float] = None  # % of avg


@dataclass
class PositionCard:
    ok: bool
    ticker: str
    error: str = ""
    configured: bool = True
    name: str = ""
    qty: Optional[float] = None
    avg_price: Optional[float] = None
    current_price: Optional[float] = None
    current_price_source: str = ""  # bcs | moex | ""
    avg_vs_price: AvgVsPrice = field(default_factory=AvgVsPrice)
    market_value: Optional[float] = None
    cost_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    first_buy: Optional[str] = None
    last_buy: Optional[str] = None
    n_buys: int = 0
    weight_pct: Optional[float] = None
    portfolio_value: Optional[float] = None
    currency: str = "RUB"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def buy_date_bounds(ops: list[Operation]) -> tuple[Optional[str], Optional[str], int]:
    """First/last buy timestamps from cached deals; count of buy sides."""
    buys = [
        o
        for o in ops
        if (o.side or "").strip().lower() == "buy" and (o.executed_at or "").strip()
    ]
    if not buys:
        return None, None, 0
    buys_sorted = sorted(buys, key=lambda o: o.executed_at or "")
    return buys_sorted[0].executed_at, buys_sorted[-1].executed_at, len(buys)


def portfolio_paper_value(
    holdings: list[Holding],
    *,
    total_value: Optional[float] = None,
) -> Optional[float]:
    """Denominator for weight_%: prefer broker total, else sum of paper MV."""
    if total_value is not None and total_value > 0:
        return float(total_value)
    s = 0.0
    any_mv = False
    for h in holdings:
        if is_cash_holding(h):
            continue
        if h.market_value is not None:
            s += float(h.market_value)
            any_mv = True
    return s if any_mv else None


def _avg_vs(avg: Optional[float], current: Optional[float]) -> AvgVsPrice:
    if avg is None or current is None:
        return AvgVsPrice()
    a = float(avg)
    c = float(current)
    diff = c - a
    pct = (diff / a * 100.0) if a != 0 else None
    return AvgVsPrice(diff=diff, diff_pct=pct)


def _unrealized(
    h: Holding,
    *,
    current: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Return (pnl ₽, pnl %). Prefer broker fields; else cost/MV or qty×Δ."""
    if h.pnl is not None:
        pct = h.pnl_pct
        if pct is None and h.cost_value not in (None, 0) and h.pnl is not None:
            pct = float(h.pnl) / float(h.cost_value) * 100.0
        return float(h.pnl), (float(pct) if pct is not None else None)

    if h.market_value is not None and h.cost_value is not None:
        pnl = float(h.market_value) - float(h.cost_value)
        pct = (
            pnl / float(h.cost_value) * 100.0
            if h.cost_value != 0
            else None
        )
        return pnl, pct

    if (
        h.quantity is not None
        and h.avg_price is not None
        and current is not None
    ):
        pnl = float(h.quantity) * (float(current) - float(h.avg_price))
        pct = (
            (float(current) - float(h.avg_price)) / float(h.avg_price) * 100.0
            if h.avg_price != 0
            else None
        )
        return pnl, pct
    return None, None


def build_position_card(
    *,
    ticker: str,
    holding: Optional[Holding],
    operations: list[Operation],
    holdings: list[Holding],
    total_value: Optional[float] = None,
    moex_last: Optional[float] = None,
    configured: bool = True,
) -> PositionCard:
    """Pure assembly of K4 card from holdings + ops (+ optional MOEX last)."""
    tid = (ticker or "").strip().upper()
    if not tid:
        return PositionCard(ok=False, ticker="", error="ticker required", configured=configured)

    if holding is None:
        return PositionCard(
            ok=False,
            ticker=tid,
            error=f"Нет позиции {tid} в holdings БКС",
            configured=configured,
        )

    first_buy, last_buy, n_buys = buy_date_bounds(operations)

    current = holding.market_price
    src = "bcs" if current is not None else ""
    if current is None and moex_last is not None:
        current = float(moex_last)
        src = "moex"

    pf = portfolio_paper_value(holdings, total_value=total_value)
    mv = holding.market_value
    weight: Optional[float] = None
    if mv is not None and pf is not None and pf > 0:
        weight = float(mv) / float(pf) * 100.0

    pnl, pnl_pct = _unrealized(holding, current=current)
    avg = holding.avg_price

    return PositionCard(
        ok=True,
        ticker=tid,
        error="",
        configured=configured,
        name=(holding.name or "").strip(),
        qty=holding.quantity,
        avg_price=avg,
        current_price=current,
        current_price_source=src,
        avg_vs_price=_avg_vs(avg, current),
        market_value=mv,
        cost_value=holding.cost_value,
        unrealized_pnl=pnl,
        unrealized_pnl_pct=pnl_pct,
        first_buy=first_buy,
        last_buy=last_buy,
        n_buys=n_buys,
        weight_pct=weight,
        portfolio_value=pf,
        currency=(holding.currency or "RUB") or "RUB",
    )
