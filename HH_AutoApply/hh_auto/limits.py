from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_OFFSETS = {
    "UTC": timezone.utc,
    "Asia/Yekaterinburg": timezone(timedelta(hours=5)),
}


def _today(tz_name: str) -> date:
    tz = _OFFSETS.get(tz_name) or _OFFSETS["Asia/Yekaterinburg"]
    return datetime.now(tz).date()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"date": "", "applied_ids": [], "count": 0}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def refresh_day(state: dict[str, Any], tz_name: str) -> dict[str, Any]:
    today = _today(tz_name).isoformat()
    if state.get("date") != today:
        return {"date": today, "applied_ids": [], "count": 0}
    return state


def can_apply(
    state: dict[str, Any],
    vacancy_id: str,
    daily_limit: int,
    tz_name: str,
) -> tuple[bool, str]:
    state = refresh_day(state, tz_name)
    if vacancy_id in (state.get("applied_ids") or []):
        return (False, "already_applied")
    if int(state.get("count") or 0) >= int(daily_limit):
        return (False, "daily_limit")
    return (True, "ok")


def record_apply(state: dict[str, Any], vacancy_id: str, tz_name: str) -> dict[str, Any]:
    state = refresh_day(state, tz_name)
    ids = list(state.get("applied_ids") or [])
    if vacancy_id not in ids:
        ids.append(vacancy_id)
        state["count"] = int(state.get("count") or 0) + 1
    state["applied_ids"] = ids
    state["date"] = _today(tz_name).isoformat()
    return state
