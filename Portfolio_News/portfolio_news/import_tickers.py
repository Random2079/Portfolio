from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy.orm import Session

from portfolio_news.db import Ticker


def _kind_from_row(asset: str, category: str, sector: str) -> str:
    blob = f"{category} {sector}".lower()
    if asset.startswith("RU000") or "блигац" in blob:
        return "bond"
    return "equity"


def load_tickers_from_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("tickers") or [])


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
            kind = _kind_from_row(asset, cat, sector)
            rows.append(
                {
                    "id": asset,
                    "name": name,
                    "isin": isin or (asset if kind == "bond" else ""),
                    "kind": kind,
                    "category": cat or sector,
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
        existing = session.get(Ticker, tid)
        fields = {
            "name": item.get("name") or tid,
            "isin": item.get("isin") or "",
            "kind": item.get("kind") or "equity",
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
