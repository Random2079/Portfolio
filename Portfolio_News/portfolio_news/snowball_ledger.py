"""Snowball 'Мой портфель' CSV → qty + cash on a date.

Income rows: Quantity is total ₽ (not shares). Bond ISS prices stay in capital_replay.
Two Downloads files from 2026-09-13 are the same journal (2023-07-17 … today).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from portfolio_news.config import DATA_DIR


def parse_num(raw: str) -> float:
    s = (raw or "").strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return 0.0
    return float(s.replace(",", "."))


def parse_day(raw: str) -> Optional[date]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


@dataclass
class Book:
    cash: float = 0.0
    qty: dict[str, float] = field(default_factory=dict)

    def papers(self) -> dict[str, float]:
        return {k: v for k, v in self.qty.items() if v > 1e-6}


def find_snowball_csv(explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit and explicit.is_file():
        return explicit
    if not DATA_DIR.is_dir():
        return None
    hits = sorted(
        DATA_DIR.glob("snowball_export*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return hits[0] if hits else None


def load_events(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r.get("Date") or "", r.get("Event") or "", r.get("Symbol") or ""))
    return rows


def apply_event(book: Book, row: dict[str, Any]) -> None:
    ev = (row.get("Event") or "").strip().upper()
    sym = (row.get("Symbol") or "").strip().upper()
    px = parse_num(row.get("Price") or "")
    q = parse_num(row.get("Quantity") or "")
    fee = parse_num(row.get("FeeTax") or "")
    nkd = parse_num(row.get("NKD") or "")
    no_cash = (row.get("DoNotAdjustCash") or "").strip().lower() == "true"

    if ev in ("", "CUSTOM_HOLDING_SETTINGS"):
        return
    if ev == "CASH_IN":
        book.cash += q * (px if px else 1.0)
        return
    if ev == "CASH_OUT":
        book.cash -= q * (px if px else 1.0)
        return
    if ev == "BUY":
        if sym:
            book.qty[sym] = book.qty.get(sym, 0.0) + q
        if not no_cash:
            book.cash -= px * q + nkd + fee
        return
    if ev == "SELL":
        if sym:
            book.qty[sym] = book.qty.get(sym, 0.0) - q
        if not no_cash:
            book.cash += px * q + nkd - fee
        return
    if ev == "DIVIDEND":
        # Quantity = gross ₽ (Snowball income), not share count.
        if not no_cash:
            book.cash += q - fee
        return
    if ev == "REPAYMENT":
        if sym:
            book.qty[sym] = book.qty.get(sym, 0.0) - q
        if not no_cash:
            book.cash += px * q - fee
        return
    if ev == "AMORTISATION":
        if not no_cash:
            book.cash += q - fee
        return
    if ev == "SPLIT":
        if sym and px:
            book.qty[sym] = book.qty.get(sym, 0.0) * px
        return
    if ev in ("FEE", "TAX"):
        book.cash -= fee
        return


def book_as_of(events: list[dict[str, Any]], as_of: date) -> Book:
    book = Book()
    for row in events:
        d = parse_day(row.get("Date") or "")
        if d is None or d > as_of:
            continue
        apply_event(book, row)
    return book


def calendar_rows_from_journal(
    events: list[dict[str, Any]],
    *,
    start: date,
    end: date,
    names: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """Paid coupons / dividends / redemptions from Snowball journal (2024+)."""
    names = names or {}
    out: list[dict[str, Any]] = []
    for row in events:
        ev = (row.get("Event") or "").strip().upper()
        if ev not in ("DIVIDEND", "REPAYMENT", "AMORTISATION"):
            continue
        d = parse_day(row.get("Date") or "")
        if d is None or d < start or d > end:
            continue
        sym = (row.get("Symbol") or "").strip().upper()
        if not sym or sym == "RUB":
            continue
        px = parse_num(row.get("Price") or "")
        q = parse_num(row.get("Quantity") or "")
        fee = parse_num(row.get("FeeTax") or "")
        if ev == "DIVIDEND":
            cash = q - fee
            if cash <= 0 and px <= 0:
                continue
            kind = "coupon" if sym.startswith("RU000") or sym.startswith("SU") else "dividend"
            per = px if px > 0 else None
            qty = (cash / per) if per and cash > 0 else None
            amount = cash if cash > 0 else None
            note = "купон" if kind == "coupon" else "дивиденд"
        elif ev == "REPAYMENT":
            kind = "redemption"
            amount = px * q if px and q else (q or None)
            per = px if px > 0 else None
            qty = q if q > 0 else None
            note = "погашение"
        else:
            kind = "redemption"
            amount = q if q > 0 else None
            per = px if px > 0 else None
            qty = None
            note = "амортизация"
        out.append(
            {
                "ticker": sym,
                "name": names.get(sym) or sym,
                "kind": kind,
                "pay_date": d.isoformat(),
                "per_unit": per,
                "quantity": qty,
                "amount": amount,
                "currency": (row.get("Currency") or "RUB") or "RUB",
                "note": note,
                "status": "paid" if d < date.today() else "upcoming",
            }
        )
    return out


# Journal timestamps are wall clock in Asia/Yekaterinburg (no offset in CSV).
_LOCAL_OFFSET = "+05:00"


def trades_from_journal(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """K8: BUY/SELL rows as operation-like dicts (full history, not just BCS window)."""
    out: list[dict[str, Any]] = []
    for row in events:
        ev = (row.get("Event") or "").strip().upper()
        if ev not in ("BUY", "SELL"):
            continue
        sym = (row.get("Symbol") or "").strip().upper()
        if not sym or sym == "RUB":
            continue
        raw = (row.get("Date") or "").strip()
        d = parse_day(raw)
        if d is None:
            continue
        stamp = raw.replace(" ", "T")[:19]
        if len(stamp) == 10:
            stamp += "T00:00:00"
        px = parse_num(row.get("Price") or "")
        q = parse_num(row.get("Quantity") or "")
        fee = parse_num(row.get("FeeTax") or "")
        nkd = parse_num(row.get("NKD") or "")
        out.append(
            {
                "deal_id": "",
                "ticker": sym,
                "class_code": "",
                "side": "buy" if ev == "BUY" else "sell",
                "quantity": q or None,
                "price": px or None,
                "volume": (px * q + nkd) if (px and q) else None,
                "commission": fee or None,
                "currency": (row.get("Currency") or "RUB") or "RUB",
                "executed_at": stamp + _LOCAL_OFFSET,
                "day": d.isoformat(),
                "note": (row.get("Note") or "").strip(),
            }
        )
    return out
