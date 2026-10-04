"""Bond ISIN → issuer name/aliases for news matching (and optional equity ticker)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_DEFAULT_PATH = Path(__file__).with_name("bond_issuer.json")

# Strip series / BO suffixes from BCS short names when absent from json.
_SERIES_TAIL = re.compile(
    r"\s+(?:БО[-–]?\s*)?(?:ООО\s+)?(?:серия\s+)?[\dA-ZА-ЯPР\-–]+(?:\s*\(.*\))?\s*$",
    re.I,
)


@dataclass(frozen=True)
class BondIssuer:
    isin: str
    issuer: str
    aliases: tuple[str, ...]
    equity_ticker: Optional[str] = None

    def search_query(self) -> str:
        """Space-joined aliases for Google / SmartLab / TG title match."""
        parts: list[str] = []
        for a in (self.issuer, *self.aliases):
            a = (a or "").strip()
            if a and a not in parts:
                parts.append(a)
        if self.equity_ticker:
            et = self.equity_ticker.strip().upper()
            if et and et not in parts:
                parts.append(et)
        return " ".join(parts)


def load_bond_issuer_config(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _guess_issuer_from_name(name: str) -> Optional[str]:
    raw = (name or "").strip()
    if not raw:
        return None
    # Drop trailing series junk: «Магнит БО-004Р-08» → «Магнит»
    cut = _SERIES_TAIL.sub("", raw).strip(" -–")
    if len(cut) >= 3 and cut.upper() != raw.upper():
        return cut
    # Fallback: first 1–3 tokens before digit-heavy token
    toks = raw.replace(",", " ").split()
    keep: list[str] = []
    for t in toks:
        if re.search(r"\d", t) and len(keep) >= 1:
            break
        if t.upper() in ("БО", "BO", "ООО", "ПАО", "АО", "ГК"):
            if not keep:
                continue
            break
        keep.append(t)
        if len(keep) >= 4:
            break
    guess = " ".join(keep).strip(" -–")
    return guess if len(guess) >= 3 else None


def resolve_bond_issuer(
    ticker_id: str,
    *,
    name: str = "",
    search_query: str = "",
    config: dict[str, Any] | None = None,
) -> Optional[BondIssuer]:
    """Resolve issuer for a bond ISIN/ticker. None if not a bond-like id."""
    tid = (ticker_id or "").strip().upper()
    if not tid.startswith("RU000"):
        return None
    cfg = config if config is not None else load_bond_issuer_config()
    by = cfg.get("by_isin") if isinstance(cfg.get("by_isin"), dict) else {}
    row = by.get(tid)
    if isinstance(row, dict):
        issuer = str(row.get("issuer") or "").strip()
        aliases = tuple(
            str(a).strip()
            for a in (row.get("aliases") or [])
            if str(a).strip()
        )
        eq = row.get("equity_ticker")
        equity = str(eq).strip().upper() if eq else None
        if issuer:
            return BondIssuer(
                isin=tid,
                issuer=issuer,
                aliases=aliases or (issuer,),
                equity_ticker=equity or None,
            )
    # Heuristic from BCS name / search_query
    guess = _guess_issuer_from_name(name) or _guess_issuer_from_name(search_query)
    if not guess:
        return None
    return BondIssuer(isin=tid, issuer=guess, aliases=(guess,), equity_ticker=None)


def news_query_for_ticker(
    ticker_id: str,
    *,
    kind: str = "",
    name: str = "",
    search_query: str = "",
) -> str:
    """Query string to pass into NewsSource.fetch (issuer-aware for bonds)."""
    k = (kind or "").strip().lower()
    base = (search_query or name or ticker_id or "").strip()
    if k == "bond" or (ticker_id or "").upper().startswith("RU000"):
        bi = resolve_bond_issuer(
            ticker_id, name=name, search_query=search_query
        )
        if bi:
            return bi.search_query()
    return base


def bond_isins_for_equity(equity_ticker: str, *, config: dict | None = None) -> list[str]:
    """ISINs in map that point at this equity ticker (info only; URL is global-unique)."""
    et = (equity_ticker or "").strip().upper()
    if not et:
        return []
    cfg = config if config is not None else load_bond_issuer_config()
    by = cfg.get("by_isin") if isinstance(cfg.get("by_isin"), dict) else {}
    out: list[str] = []
    for isin, row in by.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("equity_ticker") or "").strip().upper() == et:
            out.append(str(isin).upper())
    return out
