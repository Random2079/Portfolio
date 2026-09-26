"""K8: unified deal history + filters.

BCS cache covers only the broker's recent window (exact ids/UTC stamps);
the Snowball journal holds everything since 2023. Merge both, prefer BCS on
overlap, then filter by asset kind and date range.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_news.db import BcsOperation, Ticker

log = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=5))
KINDS = ("equity", "bond", "fund")


def kind_map(session: Session) -> dict[str, str]:
    """ticker → kind from the tickers DB (needed for funds on TQBR)."""
    return {
        str(t.id).strip().upper(): (t.kind or "").strip().lower()
        for t in session.scalars(select(Ticker))
    }


def name_map(session: Session) -> dict[str, str]:
    """ticker → display name from tickers DB (ops search by company)."""
    return {
        str(t.id).strip().upper(): (t.name or "").strip()
        for t in session.scalars(select(Ticker))
        if str(t.id).strip()
    }


def resolve_kind(ticker: str, class_code: str = "", db_kind: str = "") -> str:
    from portfolio_news.capital_replay import moex_kind

    return moex_kind(ticker, class_code, db_kind)


def parse_stamp(raw: str) -> Optional[datetime]:
    """Broker 'Z' stamps and journal '+05:00' stamps → aware datetime."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(s[:10]).replace(tzinfo=_TZ)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ)
    return dt


def local_day(raw: str) -> str:
    dt = parse_stamp(raw)
    if dt is None:
        return ""
    return dt.astimezone(_TZ).date().isoformat()


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dedupe_key(row: dict[str, Any]) -> tuple:
    """Same paper, same local day, same side and size = same deal.

    Price is deliberately out: BCS quotes bonds in percent of par (98.08)
    while the journal stores rubles (984.62), so prices never match there.
    """
    q = _num(row.get("quantity"))
    return (
        (row.get("ticker") or "").strip().upper(),
        row.get("day") or "",
        (row.get("side") or "").strip().lower(),
        round(q, 4) if q is not None else None,
    )


def bcs_rows(session: Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in session.scalars(select(BcsOperation)):
        out.append(
            {
                "deal_id": r.deal_id,
                "ticker": (r.ticker or "").strip().upper(),
                "class_code": r.class_code or "",
                "side": (r.side or "").strip().lower(),
                "quantity": r.quantity,
                "price": r.price,
                "volume": r.volume,
                "commission": r.commission,
                "currency": r.currency or "RUB",
                "executed_at": r.executed_at or "",
                "day": local_day(r.executed_at or ""),
                "note": "",
                "source": "bcs",
            }
        )
    return out


def journal_rows(csv_path: Optional[Path] = None) -> list[dict[str, Any]]:
    from portfolio_news.snowball_ledger import (
        find_snowball_csv,
        load_events,
        trades_from_journal,
    )

    path = find_snowball_csv(csv_path)
    if path is None:
        return []
    try:
        events = load_events(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("ops history journal read failed: %s", exc)
        return []
    rows = trades_from_journal(events)
    for r in rows:
        r["source"] = "journal"
    return rows


def merge_rows(
    bcs: Iterable[dict[str, Any]],
    journal: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """BCS wins on overlap (real deal_id + broker timestamp).

    Counts matter: two same-size deals on one day must not collapse into one,
    so each BCS row consumes at most one journal row with the same key.
    """
    rows = list(bcs)
    budget: dict[tuple, int] = {}
    for row in rows:
        key = dedupe_key(row)
        budget[key] = budget.get(key, 0) + 1
    for row in journal:
        key = dedupe_key(row)
        left = budget.get(key, 0)
        if left > 0:
            budget[key] = left - 1
            continue
        rows.append(row)
    rows.sort(
        key=lambda r: (parse_stamp(r.get("executed_at") or "") or datetime.min.replace(tzinfo=_TZ)),
        reverse=True,
    )
    return rows


def annotate_kinds(rows: list[dict[str, Any]], db_kinds: dict[str, str]) -> None:
    """Set kind and put bond prices on one scale (₽ per bond, not % of par)."""
    from portfolio_news.capital_replay import unit_rub

    cache: dict[tuple[str, str], str] = {}
    for r in rows:
        tid = (r.get("ticker") or "").strip().upper()
        cc = (r.get("class_code") or "").strip().upper()
        key = (tid, cc)
        if key not in cache:
            cache[key] = resolve_kind(tid, cc, db_kinds.get(tid, ""))
        kind = cache[key]
        r["kind"] = kind
        px = _num(r.get("price"))
        if kind == "bond" and px is not None:
            r["price_raw"] = px
            r["price"] = unit_rub(px, "bond")


def filter_rows(
    rows: list[dict[str, Any]],
    *,
    kinds: Optional[Iterable[str]] = None,
    date_from: str = "",
    date_to: str = "",
    ticker: str = "",
    names: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """Filter by kind/date and free-text ticker query.

    ``ticker`` matches if the query is a substring of the ticker id **or**
    of the company name (from ``names`` / row ``name``), case-insensitive.
    """
    want = {k.strip().lower() for k in (kinds or []) if k and k.strip()}
    q = (ticker or "").strip()
    q_up = q.upper()
    q_cf = q.casefold()
    name_by = names or {}
    lo = (date_from or "").strip()[:10]
    hi = (date_to or "").strip()[:10]
    out = []
    for r in rows:
        if want and r.get("kind") not in want:
            continue
        if q:
            tid = (r.get("ticker") or "").strip().upper()
            name = (r.get("name") or name_by.get(tid) or "").strip()
            if q_up not in tid and q_cf not in name.casefold():
                continue
        day = r.get("day") or ""
        if lo and day and day < lo:
            continue
        if hi and day and day > hi:
            continue
        out.append(r)
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {k: 0 for k in KINDS}
    bought = sold = 0.0
    years: set[str] = set()
    for r in rows:
        k = r.get("kind")
        if k in counts:
            counts[k] += 1
        day = r.get("day") or ""
        if len(day) >= 4:
            years.add(day[:4])
        vol = _num(r.get("volume")) or 0.0
        if (r.get("side") or "") == "buy":
            bought += vol
        elif (r.get("side") or "") == "sell":
            sold += vol
    return {
        "counts": counts,
        "years": sorted(years),
        "bought_volume": bought,
        "sold_volume": sold,
    }


def build_history(
    session: Session,
    *,
    kinds: Optional[Iterable[str]] = None,
    date_from: str = "",
    date_to: str = "",
    ticker: str = "",
    limit: int = 0,
    include_journal: bool = True,
) -> dict[str, Any]:
    """Merged + annotated + filtered deal history (no network)."""
    bcs = bcs_rows(session)
    jrn = journal_rows() if include_journal else []
    rows = merge_rows(bcs, jrn)
    annotate_kinds(rows, kind_map(session))
    all_summary = summarize(rows)
    hits = filter_rows(
        rows,
        kinds=kinds,
        date_from=date_from,
        date_to=date_to,
        ticker=ticker,
        names=name_map(session),
    )
    total = len(hits)
    shown = hits[: limit] if limit and limit > 0 else hits
    sources = sorted({r.get("source") or "" for r in rows if r.get("source")})
    return {
        "operations": shown,
        "total": total,
        "shown": len(shown),
        "all_total": len(rows),
        "years": all_summary["years"],
        "counts": all_summary["counts"],
        "filtered": summarize(hits),
        "sources": sources,
        "journal_rows": len(jrn),
        "bcs_rows": len(bcs),
    }


_CSV_COLUMNS = (
    ("day", "Дата"),
    ("executed_at", "Время"),
    ("ticker", "Тикер"),
    ("kind", "Тип"),
    ("side", "Сторона"),
    ("quantity", "Количество"),
    ("price", "Цена"),
    ("volume", "Сумма"),
    ("commission", "Комиссия"),
    ("currency", "Валюта"),
    ("source", "Источник"),
)


def to_csv(rows: Iterable[dict[str, Any]]) -> str:
    """Excel-friendly: ';' delimiter and ',' decimals (ru locale)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow([title for _key, title in _CSV_COLUMNS])
    for r in rows:
        line = []
        for key, _title in _CSV_COLUMNS:
            v = r.get(key)
            if isinstance(v, float):
                line.append(f"{v:.4f}".rstrip("0").rstrip(".").replace(".", ","))
            else:
                line.append("" if v is None else str(v))
        w.writerow(line)
    return buf.getvalue()
