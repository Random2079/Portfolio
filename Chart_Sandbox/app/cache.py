"""Disk cache for MOEX candle payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"


def cache_path(ticker: str, days: int) -> Path:
    tid = ticker.strip().upper() or "UNKNOWN"
    return CACHE_DIR / f"{tid}_{int(days)}.json"


def read_cache(ticker: str, days: int) -> dict[str, Any] | None:
    path = cache_path(ticker, days)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    candles = data.get("candles")
    if not isinstance(candles, list) or not candles:
        return None
    return data


def write_cache(ticker: str, days: int, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(ticker, days)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
