from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy.orm import Session

from portfolio_news.db import Ticker


def normalize_kind(asset: str, category: str = "", name: str = "", sector: str = "") -> str:
    """equity | bond | fund."""
    cat = (category or "").strip().lower()
    sec = (sector or "").strip().lower()
    nm = (name or "").strip().lower()
    blob = f"{cat} {sec} {nm}"
    aid = (asset or "").strip()
    if aid.startswith("RU000") or "блигац" in blob:
        return "bond"
    if cat == "etf" or "etf" in blob or "бпиф" in nm or "пиф" in nm or "фонд" in cat:
        return "fund"
    return "equity"


def _kind_from_row(asset: str, category: str, sector: str, name: str = "") -> str:
    return normalize_kind(asset, category=category, name=name, sector=sector)


def load_tickers_from_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = list(data.get("tickers") or [])
    for item in rows:
        item["kind"] = normalize_kind(
            str(item.get("id") or ""),
            category=str(item.get("category") or ""),
            name=str(item.get("name") or ""),
        )
    return rows


def load_tickers_from_snowball_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asset = (row.get("Актив") or "").strip()
            if not asset:
                continue
            name = (row.get("Название актива") or "").strip()
            isin = (row.get("ISIN") or "").strip()
            cat = (row.get("Категория") or "").strip()
            sector = (row.get("Сектор") or "").strip()
            typ = (row.get("Тип") or "").strip()
            kind = _kind_from_row(asset, cat, sector, name)
            if kind == "equity":
                category = sector or cat
            else:
                category = cat or sector
            rows.append(
                {
                    "id": asset,
                    "name": name,
                    "isin": isin or (asset if kind == "bond" else ""),
                    "kind": kind,
                    "category": category,
                    "bond_type": typ or None,
                    "search_query": name or asset,
                }
            )
    return rows


def upsert_tickers(session: Session, items: list[dict]) -> int:
    n = 0
    for item in items:
        tid = str(item["id"]).strip()
        if not tid:
            continue
        kind = normalize_kind(
            tid,
            category=str(item.get("category") or ""),
            name=str(item.get("name") or ""),
        )
        existing = session.get(Ticker, tid)
        fields = {
            "name": item.get("name") or tid,
            "isin": item.get("isin") or "",
            "kind": kind,
            "category": item.get("category") or "",
            "search_query": item.get("search_query") or item.get("name") or tid,
        }
        if existing is None:
            session.add(Ticker(id=tid, **fields))
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
        n += 1
    session.commit()
    return n
