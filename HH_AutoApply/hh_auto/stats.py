"""Отчётность по откликам: apply_state (лимит дня) + apply_log (статусы/история)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from hh_auto import DATA, ensure_data_dir, load_config
from hh_auto.limits import _OFFSETS, _today, load_state, refresh_day

APPLY_STATE = DATA / "apply_state.json"
APPLY_LOG = DATA / "apply_log.jsonl"
RESUME_STATE = DATA / "resume_state.json"

# статусы, которые считаем «успешным откликом» в логе (для сверки)
OK_STATUSES = frozenset({"applied", "already_on_hh"})
SKIP_STATUSES = frozenset(
    {
        "no_button",
        "already_applied",
        "daily_limit",
        "dry_run_ok",
        "already_raised_skip",
    }
)
ERROR_STATUSES = frozenset({"error", "captcha", "captcha-stop"})


def _tz(cfg: dict[str, Any]):
    name = cfg.get("timezone") or "Asia/Yekaterinburg"
    return _OFFSETS.get(name) or _OFFSETS["Asia/Yekaterinburg"], name


def _parse_ts(ts: str, tz) -> datetime | None:
    if not ts:
        return None
    try:
        if "T" in ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt
    except Exception:
        return None


def archive_and_clear_log(path: Path | None = None) -> Path | None:
    """Старый лог → apply_log_archive_*.jsonl, текущий обнулить. State/лимит не трогает."""
    ensure_data_dir()
    p = path or APPLY_LOG
    if not p.exists() or p.stat().st_size == 0:
        p.write_text("", encoding="utf-8")
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = p.parent / f"apply_log_archive_{stamp}.jsonl"
    p.replace(dest)
    p.write_text("", encoding="utf-8")
    return dest


def read_log(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or APPLY_LOG
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_resume_state(path: Path | None = None) -> dict[str, Any]:
    p = path or RESUME_STATE
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_resume_state(state: dict[str, Any], path: Path | None = None) -> None:
    ensure_data_dir()
    p = path or RESUME_STATE
    with p.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_report(cfg: dict[str, Any] | None = None, recent_n: int = 15) -> dict[str, Any]:
    """Канон дня: apply_state.count после refresh_day. Лог — статусы и лента."""
    cfg = cfg or load_config()
    tz, tz_name = _tz(cfg)
    daily_limit = int(cfg.get("daily_limit") or 100)

    state = refresh_day(load_state(APPLY_STATE), tz_name)
    today_iso = _today(tz_name).isoformat()
    sent_today = int(state.get("count") or 0)
    remaining = max(0, daily_limit - sent_today)

    rows = read_log()
    by_status: Counter[str] = Counter()
    total_ok = 0
    today_by_status: Counter[str] = Counter()
    for row in rows:
        st = str(row.get("status") or "unknown")
        by_status[st] += 1
        if st in OK_STATUSES or st == "applied":
            total_ok += 1
        dt = _parse_ts(str(row.get("ts") or ""), tz)
        if dt and dt.astimezone(tz).date().isoformat() == today_iso:
            today_by_status[st] += 1

    recent = list(reversed(rows[-recent_n:])) if rows else []
    resume = load_resume_state()

    return {
        "timezone": tz_name,
        "today": today_iso,
        "daily_limit": daily_limit,
        "sent_today": sent_today,
        "remaining": remaining,
        "total_ok_log": total_ok,
        "total_log_events": len(rows),
        "by_status": dict(by_status),
        "today_by_status": dict(today_by_status),
        "recent": recent,
        "apply_state": state,
        "resume": resume,
        "canon": "apply_state.count — дневной лимит; apply_log — статусы/история",
    }


def format_stats_text(report: dict[str, Any]) -> str:
    lines = [
        f"📍 Сегодня ({report['today']}, {report['timezone']})",
        f"  ✅ отправлено: {report['sent_today']} / лимит {report['daily_limit']}",
        f"  🎯 осталось пройти: {report['remaining']}",
        f"  📊 всего ok в логе: {report['total_ok_log']} · событий: {report['total_log_events']}",
        f"  📖 канон: {report['canon']}",
    ]
    if report.get("by_status"):
        parts = [f"{k}={v}" for k, v in sorted(report["by_status"].items(), key=lambda x: (-x[1], x[0]))]
        lines.append("  🧩 статусы: " + ", ".join(parts))
    resume = report.get("resume") or {}
    if resume:
        lines.append(
            f"  📄 резюме: last={resume.get('last_status')} @ {resume.get('last_ts') or '—'}"
        )
    lines.append("  👀 последние:")
    for row in report.get("recent") or []:
        title = (row.get("title") or row.get("id") or "")[:48]
        lines.append(f"    · {row.get('ts', '?')} [{row.get('status')}] {title}")
    if not report.get("recent"):
        lines.append("    · (пусто)")
    return "\n".join(lines)
