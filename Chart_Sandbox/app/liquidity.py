"""Estimated liquidity / stop clusters from OHLC (not a real order book).

Retail-SMC style heuristics for Chart_Sandbox backtests:
- swing highs → liquidity / sell-stops above
- swing lows → liquidity / buy-stops below
- equal highs/lows → pooled levels
"""

from __future__ import annotations

from typing import Any


def _f(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def detect_swings(
    candles: list[dict[str, Any]],
    *,
    left: int = 3,
    right: int = 3,
) -> list[dict[str, Any]]:
    """Return swing points: {time, price, kind: high|low, index}."""
    n = len(candles)
    out: list[dict[str, Any]] = []
    if n < left + right + 1:
        return out

    for i in range(left, n - right):
        hi = _f(candles[i].get("high"))
        lo = _f(candles[i].get("low"))
        t = candles[i].get("time")
        if hi is None or lo is None or not t:
            continue

        is_high = True
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            hj = _f(candles[j].get("high"))
            lj = _f(candles[j].get("low"))
            if hj is not None and hj >= hi:
                is_high = False
            if lj is not None and lj <= lo:
                is_low = False

        if is_high:
            out.append({"time": t, "price": hi, "kind": "high", "index": i})
        if is_low:
            out.append({"time": t, "price": lo, "kind": "low", "index": i})
    return out


def _cluster_levels(
    swings: list[dict[str, Any]],
    *,
    kind: str,
    tol_pct: float = 0.003,
) -> list[dict[str, Any]]:
    """Group near-equal swing prices into liquidity pools."""
    pts = sorted((s for s in swings if s.get("kind") == kind), key=lambda s: float(s["price"]))
    if not pts:
        return []

    pools: list[dict[str, Any]] = []
    cur = [pts[0]]
    for p in pts[1:]:
        base = float(cur[0]["price"])
        if abs(float(p["price"]) - base) / base <= tol_pct:
            cur.append(p)
        else:
            if len(cur) >= 2:
                avg = sum(float(x["price"]) for x in cur) / len(cur)
                pools.append(
                    {
                        "kind": "equal_high" if kind == "high" else "equal_low",
                        "price": round(avg, 6),
                        "count": len(cur),
                        "times": [x["time"] for x in cur],
                        "side": "stops_above" if kind == "high" else "stops_below",
                        "note": "equal swings → pooled liquidity (estimate)",
                    }
                )
            cur = [p]
    if len(cur) >= 2:
        avg = sum(float(x["price"]) for x in cur) / len(cur)
        pools.append(
            {
                "kind": "equal_high" if kind == "high" else "equal_low",
                "price": round(avg, 6),
                "count": len(cur),
                "times": [x["time"] for x in cur],
                "side": "stops_above" if kind == "high" else "stops_below",
                "note": "equal swings → pooled liquidity (estimate)",
            }
        )
    return pools


def build_liquidity_map(
    candles: list[dict[str, Any]],
    *,
    left: int = 3,
    right: int = 3,
    tol_pct: float = 0.003,
) -> dict[str, Any]:
    """Full map for chart overlay + future backtester."""
    swings = detect_swings(candles, left=left, right=right)
    pools = _cluster_levels(swings, kind="high", tol_pct=tol_pct) + _cluster_levels(
        swings, kind="low", tol_pct=tol_pct
    )

    zones: list[dict[str, Any]] = []
    for s in swings:
        if s["kind"] == "high":
            zones.append(
                {
                    "time": s["time"],
                    "price": s["price"],
                    "side": "stops_above",
                    "label": "liq↑",
                    "source": "swing_high",
                }
            )
        else:
            zones.append(
                {
                    "time": s["time"],
                    "price": s["price"],
                    "side": "stops_below",
                    "label": "liq↓",
                    "source": "swing_low",
                }
            )

    return {
        "disclaimer": (
            "Estimated from OHLC swings / equal highs-lows. "
            "Not MOEX order-book or real stop placement."
        ),
        "swings": swings,
        "pools": pools,
        "zones": zones,
    }
