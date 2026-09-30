"""Buckets for ops filters: equity sector / bond type+rating / fund style.

No network — KS map + tickers DB + optional DohodBondCache only.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_news.db import DohodBondCache, Ticker
from portfolio_news.review_facts import resolve_sector

# fund ticker → bucket id
_FUND_BUCKET: dict[str, str] = {
    "GOLD": "gold",
    "FXGD": "gold",
    "TGLD": "gold",
    "TMOS": "equity_rf",
    "SBMX": "equity_rf",
    "SBSP": "equity_rf",
    "EQMX": "equity_rf",
    "FXRL": "equity_rf",
    "FXUS": "mixed",
    "FXDE": "mixed",
    "FXCN": "mixed",
    "FXRU": "mixed",
    "BCSR": "mixed",
}

_FUND_LABELS = {
    "gold": "Золото",
    "equity_rf": "Акции РФ",
    "mixed": "Смешанные / др.",
    "other": "Прочее",
}

_BOND_TYPE_LABELS = {
    "ofz": "ОФЗ",
    "corp": "Корп",
    "other": "Др. облиг.",
}


def fund_bucket(ticker: str) -> str:
    tid = (ticker or "").strip().upper()
    return _FUND_BUCKET.get(tid, "other")


def fund_bucket_label(bucket: str) -> str:
    return _FUND_LABELS.get(bucket, _FUND_LABELS["other"])


def bond_type(*, ticker: str, name: str = "", isin: str = "") -> str:
    """ofz | corp | other — cheap heuristics, no network."""
    tid = (ticker or "").strip().upper()
    nm = (name or "").casefold()
    isin_u = (isin or "").strip().upper()
    if tid.startswith("SU") or "офз" in nm or "ofz" in nm:
        return "ofz"
    if isin_u.startswith("SU") or re.match(r"^RU000A0J[A-Z0-9]+$", isin_u):
        # many classic OFZ ISINs; still allow corp RU000A*
        if "офз" in nm or tid.startswith("SU"):
            return "ofz"
    if tid.startswith("RU000") or isin_u.startswith("RU000"):
        if "офз" in nm:
            return "ofz"
        return "corp"
    if re.match(r"^[A-Z]{2,6}$", tid) and tid not in _FUND_BUCKET:
        # short MOEX bond tickers (e.g. issuer codes) → corp by default
        if any(x in nm for x in ("обл", "бо-", "выпуск", "серия")):
            return "corp"
        return "corp"
    return "other"


def bond_type_label(t: str) -> str:
    return _BOND_TYPE_LABELS.get(t, _BOND_TYPE_LABELS["other"])


def rating_bucket(rating: str) -> str:
    """Collapse free-text rating into a chip id."""
    r = (rating or "").strip().upper().replace(" ", "")
    if not r:
        return "nr"
    # take leading letter grade
    m = re.match(r"(AAA|AA\+?|AA|A\+?|A|BBB\+?|BBB|BB\+?|BB|B\+?|B|CCC|CC|C|D)", r)
    if not m:
        if "НЕТ" in r or "N/R" in r or "NR" == r or "WITHDRAWN" in r:
            return "nr"
        return "other"
    g = m.group(1)
    if g.startswith("AAA") or g.startswith("AA"):
        return "aa"
    if g.startswith("A"):
        return "a"
    if g.startswith("BBB"):
        return "bbb"
    if g.startswith("BB") or g.startswith("B"):
        return "bb_b"
    return "low"


_RATING_LABELS = {
    "aa": "AA…AAA",
    "a": "A",
    "bbb": "BBB",
    "bb_b": "BB–B",
    "low": "ниже B",
    "nr": "нет рейтинга",
    "other": "др. рейтинг",
}


def rating_bucket_label(b: str) -> str:
    return _RATING_LABELS.get(b, _RATING_LABELS["other"])


def _ticker_meta(session: Session) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for t in session.scalars(select(Ticker)):
        tid = str(t.id).strip().upper()
        if not tid:
            continue
        out[tid] = {
            "name": (t.name or "").strip(),
            "isin": (t.isin or "").strip().upper(),
            "category": (t.category or "").strip(),
            "kind": (t.kind or "").strip().lower(),
        }
    return out


def _dohod_rating_by_isin(session: Session) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        from portfolio_news.bonds_dohod import DohodBondFacts

        rows = session.scalars(select(DohodBondCache)).all()
    except Exception:  # noqa: BLE001
        return out
    for row in rows:
        isin = (row.isin or "").strip().upper()
        if not isin or not (row.payload_json or "").strip():
            continue
        try:
            import json as _json

            data = _json.loads(row.payload_json)
            if not isinstance(data, dict):
                continue
            facts = DohodBondFacts.from_dict(data)
            rating = (facts.rating or "").strip()
        except Exception:  # noqa: BLE001
            rating = ""
        if rating:
            out[isin] = rating
    return out


def annotate_buckets(session: Session, rows: list[dict[str, Any]]) -> None:
    """Add sector / bond_type / rating_bucket / fund_bucket on each op row."""
    meta = _ticker_meta(session)
    ratings = _dohod_rating_by_isin(session)
    for r in rows:
        tid = (r.get("ticker") or "").strip().upper()
        kind = (r.get("kind") or "").strip().lower()
        m = meta.get(tid) or {}
        name = (r.get("name") or m.get("name") or "").strip()
        isin = (m.get("isin") or "").strip().upper()
        if name and not r.get("name"):
            r["name"] = name

        r["sector_id"] = ""
        r["sector_label"] = ""
        r["bond_type"] = ""
        r["bond_type_label"] = ""
        r["rating"] = ""
        r["rating_bucket"] = ""
        r["rating_bucket_label"] = ""
        r["fund_bucket"] = ""
        r["fund_bucket_label"] = ""

        if kind == "equity":
            sec = resolve_sector(tid, m.get("category") or "")
            r["sector_id"] = sec.get("id") or "unknown"
            r["sector_label"] = sec.get("label") or "сектор ?"
        elif kind == "bond":
            bt = bond_type(ticker=tid, name=name, isin=isin)
            r["bond_type"] = bt
            r["bond_type_label"] = bond_type_label(bt)
            # light "sector" for bonds = type label (ОФЗ / корп / др.)
            r["sector_id"] = bt
            r["sector_label"] = bond_type_label(bt)
            rating = ratings.get(isin) or ratings.get(tid) or ""
            r["rating"] = rating
            rb = rating_bucket(rating)
            r["rating_bucket"] = rb
            r["rating_bucket_label"] = rating_bucket_label(rb)
        elif kind == "fund":
            fb = fund_bucket(tid)
            r["fund_bucket"] = fb
            r["fund_bucket_label"] = fund_bucket_label(fb)
            r["sector_id"] = fb
            r["sector_label"] = fund_bucket_label(fb)
