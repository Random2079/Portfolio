"""Один тик Kwork: search → filter → DeepSeek → LIVE apply."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Callable

from hh_auto import DATA, ensure_data_dir
from hh_auto.kwork_ai import propose_for_project
from hh_auto.kwork_apply import (
    apply_state_path,
    kwork_today_count,
    send_proposal,
)
from hh_auto.kwork_search import fetch_projects, filter_projects
from hh_auto.limits import can_apply, load_state, refresh_day


ProgressCb = Callable[[str], None]


def run_tick(
    cfg: dict[str, Any],
    *,
    dry_run: bool = False,
    limit: int | None = None,
    cancel_event: threading.Event | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """
    Возвращает summary: scanned, candidates, sent, skipped, errors, rows.
    """
    def prog(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    kw = cfg.get("kwork") or {}
    if not kw.get("enabled", True):
        return {"ok": False, "error": "kwork.disabled", "rows": []}

    per_tick = int(limit if limit is not None else (kw.get("per_tick_limit") or 3))
    per_tick = max(1, min(per_tick, 10))
    keywords = list(kw.get("keywords") or [])
    min_score = int(kw.get("min_score") or 1)
    tz = cfg.get("timezone") or "Asia/Yekaterinburg"
    daily = int(kw.get("daily_limit") or 15)

    sent_today, _ = kwork_today_count(cfg)
    remaining = max(0, daily - sent_today)
    if remaining <= 0 and not dry_run:
        prog("⏹ дневной лимит Kwork исчерпан")
        return {
            "ok": True,
            "scanned": 0,
            "candidates": 0,
            "sent": 0,
            "skipped": 0,
            "errors": 0,
            "rows": [],
            "detail": "daily_limit",
        }

    cap = min(per_tick, remaining if not dry_run else per_tick)

    prog("🔍 Kwork: ищу проекты…")
    try:
        projects = fetch_projects(cfg, enrich=True, max_enrich=max(8, cap * 4))
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300], "rows": []}

    if cancel_event and cancel_event.is_set():
        return {"ok": False, "error": "cancelled", "rows": []}

    if keywords:
        projects = filter_projects(projects, keywords, min_score=min_score)

    ensure_data_dir()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dump = DATA / f"kwork_projects_{stamp}.json"
    with dump.open("w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)

    state = refresh_day(load_state(apply_state_path()), tz)
    rows: list[dict[str, Any]] = []
    sent = skipped = errors = 0

    for proj in projects:
        if cancel_event and cancel_event.is_set():
            break
        if sent >= cap:
            break

        pid = str(proj.get("project_id") or "")
        if dry_run:
            if pid in (state.get("applied_ids") or []):
                skipped += 1
                continue
        else:
            ok, reason = can_apply(state, pid, daily, tz)
            if not ok:
                skipped += 1
                rows.append(
                    {
                        "project_id": pid,
                        "title": proj.get("title"),
                        "status": reason,
                        "url": proj.get("url"),
                    }
                )
                continue

        prog(f"🧠 DeepSeek: {proj.get('title') or pid}")
        ai = propose_for_project(cfg, proj)
        if not ai.get("fit"):
            skipped += 1
            rows.append(
                {
                    "project_id": pid,
                    "title": proj.get("title"),
                    "status": "skip_fit",
                    "detail": ai.get("error") or f"score={ai.get('score')}",
                    "url": proj.get("url"),
                }
            )
            continue

        prog(f"📨 {'dry-run' if dry_run else 'LIVE'}: {proj.get('title') or pid}")
        result = send_proposal(
            cfg,
            proj,
            cover=str(ai.get("cover") or ""),
            price_rub=int(ai.get("price_rub") or 0),
            days=int(ai.get("days") or 7),
            dry_run=dry_run,
        )
        rows.append(result)
        st = result.get("status")
        if st in ("sent", "dry_run"):
            sent += 1
            if st == "sent":
                state = refresh_day(load_state(apply_state_path()), tz)
        elif st in ("already_applied", "daily_limit", "skip", "skip_fit"):
            skipped += 1
        elif st == "captcha":
            errors += 1
            prog("❌ капча — стоп тика")
            break
        else:
            errors += 1

    summary = {
        "ok": True,
        "scanned": len(projects),
        "candidates": len(projects),
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "rows": rows,
        "dump": str(dump),
        "dry_run": dry_run,
    }
    prog(
        f"✅ тик: scanned={summary['scanned']} sent={sent} skip={skipped} err={errors}"
    )
    return summary


def format_tick_summary(summary: dict[str, Any]) -> str:
    if not summary.get("ok"):
        return f"❌ Kwork tick: {summary.get('error')}"
    lines = [
        f"📍 Kwork tick {'(dry-run)' if summary.get('dry_run') else '(LIVE)'}",
        f"   scanned={summary.get('scanned')} sent={summary.get('sent')} "
        f"skip={summary.get('skipped')} err={summary.get('errors')}",
    ]
    for r in summary.get("rows") or []:
        st = r.get("status")
        lines.append(
            f"   · [{st}] {r.get('buyer') or '—'} — {(r.get('title') or '')[:50]}"
        )
        if r.get("url"):
            lines.append(f"     {r['url']}")
    return "\n".join(lines)
