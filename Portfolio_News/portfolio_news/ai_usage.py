"""DeepSeek usage meter: local token log + account balance (MAP §7F)."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from portfolio_news.config import DATA_DIR

log = logging.getLogger(__name__)

USAGE_LOG = DATA_DIR / "ai_usage.jsonl"
BALANCE_URL = "https://api.deepseek.com/user/balance"
_TZ = timezone(timedelta(hours=5))  # Asia/Yekaterinburg

# USD per 1M tokens, deepseek-chat. Prices drift — balance from the API is the
# source of truth; these only turn token counts into a rough $ estimate.
PRICE_IN_MISS = 0.28
PRICE_IN_HIT = 0.028
PRICE_OUT = 0.42

_BALANCE_TTL_SEC = 300
_balance_lock = threading.Lock()
_balance_cache: dict[str, Any] = {"at": 0.0, "value": None}
_log_lock = threading.Lock()


def estimate_usd(usage: dict[str, Any]) -> float:
    prompt = int(usage.get("prompt_tokens") or 0)
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or max(prompt - hit, 0))
    out = int(usage.get("completion_tokens") or 0)
    return (hit * PRICE_IN_HIT + miss * PRICE_IN_MISS + out * PRICE_OUT) / 1_000_000


def record_usage(kind: str, usage: Optional[dict[str, Any]], *, path: Path = USAGE_LOG) -> None:
    """Append one call to the JSONL log. Never raises — metering must not break AI."""
    if not isinstance(usage, dict):
        return
    row = {
        "ts": datetime.now(_TZ).isoformat(timespec="seconds"),
        "kind": kind or "other",
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens") or 0),
        "usd_est": round(estimate_usd(usage), 6),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _log_lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("ai usage log write failed", exc_info=True)


def summarize_usage(*, path: Path = USAGE_LOG, now: Optional[datetime] = None) -> dict[str, Any]:
    """Totals for today and the current month (local TZ)."""
    now = now or datetime.now(_TZ)
    day_key = now.strftime("%Y-%m-%d")
    month_key = now.strftime("%Y-%m")
    out = {
        "today_calls": 0,
        "today_tokens": 0,
        "today_usd": 0.0,
        "month_calls": 0,
        "month_tokens": 0,
        "month_usd": 0.0,
    }
    if not path.is_file():
        return out
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = str(r.get("ts") or "")
        if not ts.startswith(month_key):
            continue
        tokens = int(r.get("prompt_tokens") or 0) + int(r.get("completion_tokens") or 0)
        usd = float(r.get("usd_est") or 0.0)
        out["month_calls"] += 1
        out["month_tokens"] += tokens
        out["month_usd"] += usd
        if ts.startswith(day_key):
            out["today_calls"] += 1
            out["today_tokens"] += tokens
            out["today_usd"] += usd
    out["today_usd"] = round(out["today_usd"], 4)
    out["month_usd"] = round(out["month_usd"], 4)
    return out


def fetch_balance(api_key: str, *, force: bool = False, timeout: float = 5.0) -> Optional[dict[str, Any]]:
    """{currency, total} from DeepSeek /user/balance; cached, None on failure."""
    key = (api_key or "").strip()
    if not key:
        return None
    with _balance_lock:
        fresh = time.time() - float(_balance_cache["at"]) < _BALANCE_TTL_SEC
        if fresh and not force:
            return _balance_cache["value"]
    req = urllib.request.Request(
        BALANCE_URL,
        headers={"Accept": "application/json", "Authorization": f"Bearer {key}"},
        method="GET",
    )
    value: Optional[dict[str, Any]] = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        infos = body.get("balance_infos") or []
        if infos:
            first = infos[0]
            value = {
                "currency": str(first.get("currency") or ""),
                "total": float(first.get("total_balance") or 0.0),
                "available": bool(body.get("is_available", True)),
            }
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        log.info("deepseek balance fetch failed: %s", exc)
    with _balance_lock:
        _balance_cache["at"] = time.time()
        _balance_cache["value"] = value
    return value


def invalidate_balance() -> None:
    with _balance_lock:
        _balance_cache["at"] = 0.0
