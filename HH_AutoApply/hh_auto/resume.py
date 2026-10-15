"""Авто-поднятие резюме на hh.ru. Идемпотентно: already_raised_skip без спама."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from hh_auto import ensure_data_dir, load_config, playwright_headless
from hh_auto.apply import _append_log, _state_path, _visible_captcha, page_looks_like_captcha
from hh_auto.limits import _OFFSETS, _today
from hh_auto.stats import load_resume_state, save_resume_state

RESUMES_URL = "https://hh.ru/applicant/resumes"
# hh обычно даёт поднять раз в ~4ч; локальный кулдаун чуть меньше суток на всякий
DEFAULT_COOLDOWN_HOURS = 4


def _now_iso(tz_name: str) -> str:
    tz = _OFFSETS.get(tz_name) or _OFFSETS["Asia/Yekaterinburg"]
    return datetime.now(tz).replace(microsecond=0).isoformat()


def _within_cooldown(resume: dict[str, Any], hours: int, tz_name: str) -> bool:
    last = resume.get("last_raised_ts") or resume.get("last_ts")
    if not last or resume.get("last_status") not in {"raised", "already_raised_skip"}:
        return False
    try:
        dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except Exception:
        return False
    tz = _OFFSETS.get(tz_name) or _OFFSETS["Asia/Yekaterinburg"]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return datetime.now(tz) - dt < timedelta(hours=hours)


def _find_raise_controls(page: Any) -> tuple[Any | None, str]:
    """Ищем кнопку/ссылку «поднять». Возвращает (locator|None, reason)."""
    patterns = [
        page.get_by_role("button", name=re.compile(r"поднять", re.I)),
        page.get_by_role("link", name=re.compile(r"поднять", re.I)),
        page.locator("button:has-text('Поднять')"),
        page.locator("a:has-text('Поднять')"),
        page.locator("[data-qa*='resume-update'], [data-qa*='resume-raise'], [data-qa*='raise']"),
        page.locator("button:has-text('поднять в поиске')"),
        page.locator("a:has-text('поднять в поиске')"),
    ]
    for loc in patterns:
        try:
            if loc.count() and loc.first.is_visible():
                return loc.first, "found"
        except Exception:
            continue
    return None, "not_found"


def _page_says_already_raised(page: Any) -> bool:
    try:
        body = (page.locator("body").inner_text(timeout=3000) or "").casefold()
    except Exception:
        body = ""
    hints = (
        "уже поднято",
        "можно будет поднять",
        "поднять можно через",
        "резюме поднято",
        "доступно через",
        "следующее поднятие",
    )
    return any(h in body for h in hints)


def raise_resume(cfg: dict[str, Any] | None = None, *, force: bool = False) -> dict[str, Any]:
    """
    Returns status: raised | already_raised_skip | captcha | error
    """
    cfg = cfg or load_config()
    tz_name = cfg.get("timezone") or "Asia/Yekaterinburg"
    ensure_data_dir()
    resume = load_resume_state()
    cooldown_h = int((cfg.get("resume_bump") or {}).get("cooldown_hours") or DEFAULT_COOLDOWN_HOURS)

    if not force and _within_cooldown(resume, cooldown_h, tz_name):
        result = {
            "status": "already_raised_skip",
            "detail": f"локальный cooldown {cooldown_h}ч (last={resume.get('last_raised_ts') or resume.get('last_ts')})",
            "ts": _now_iso(tz_name),
        }
        _record(result, resume, tz_name, skipped=True)
        return result

    state_file = _state_path(cfg)
    if not state_file.exists():
        result = {
            "status": "error",
            "detail": "Нет storage_state. Сначала: python -m hh_auto login",
            "ts": _now_iso(tz_name),
        }
        _record(result, resume, tz_name)
        return result

    pw_cfg = cfg.get("playwright") or {}
    headless = playwright_headless(cfg)
    slow = int(pw_cfg.get("slow_mo_ms") or 0)

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, slow_mo=slow)
            context = browser.new_context(storage_state=str(state_file))
            page = context.new_page()
            page.goto(RESUMES_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(800)

            if _visible_captcha(page) or page_looks_like_captcha(
                page.locator("body").inner_text(timeout=2000) if page.locator("body").count() else "",
                page.url or "",
            ):
                browser.close()
                result = {
                    "status": "captcha",
                    "detail": "Капча/challenge — стоп. Разгадай вручную.",
                    "ts": _now_iso(tz_name),
                }
                _record(result, resume, tz_name)
                return result

            if _page_says_already_raised(page):
                btn, _ = _find_raise_controls(page)
                if btn is None:
                    browser.close()
                    result = {
                        "status": "already_raised_skip",
                        "detail": "UI: уже поднято / кулдаун на странице",
                        "ts": _now_iso(tz_name),
                    }
                    _record(result, resume, tz_name, skipped=True)
                    return result

            btn, reason = _find_raise_controls(page)
            if btn is None:
                # нет кнопки + нет явного текста → скорее уже недоступно
                browser.close()
                result = {
                    "status": "already_raised_skip",
                    "detail": f"кнопка «Поднять» не найдена ({reason}) — skip",
                    "ts": _now_iso(tz_name),
                }
                _record(result, resume, tz_name, skipped=True)
                return result

            btn.click()
            page.wait_for_timeout(600)
            # подтверждение если есть
            for sel in (
                "button:has-text('Поднять')",
                "button:has-text('Подтвердить')",
                "button:has-text('Да')",
                "[data-qa*='resume-update']",
            ):
                try:
                    loc = page.locator(sel)
                    if loc.count() and loc.first.is_visible():
                        loc.first.click()
                        page.wait_for_timeout(400)
                        break
                except Exception:
                    continue

            page.wait_for_timeout(500)
            if _visible_captcha(page):
                browser.close()
                result = {
                    "status": "captcha",
                    "detail": "Капча после клика — стоп",
                    "ts": _now_iso(tz_name),
                }
                _record(result, resume, tz_name)
                return result

            browser.close()
            result = {
                "status": "raised",
                "detail": "клик «Поднять» выполнен",
                "ts": _now_iso(tz_name),
            }
            _record(result, resume, tz_name, raised=True)
            return result
    except Exception as e:
        result = {
            "status": "error",
            "detail": str(e)[:300],
            "ts": _now_iso(tz_name),
        }
        _record(result, resume, tz_name)
        return result


def _record(
    result: dict[str, Any],
    resume: dict[str, Any],
    tz_name: str,
    *,
    raised: bool = False,
    skipped: bool = False,
) -> None:
    ts = result.get("ts") or _now_iso(tz_name)
    resume["last_status"] = result["status"]
    resume["last_ts"] = ts
    resume["last_detail"] = result.get("detail")
    if raised:
        resume["last_raised_ts"] = ts
        resume["raise_count"] = int(resume.get("raise_count") or 0) + 1
    if skipped and not resume.get("last_raised_ts"):
        # зафиксируем «уже поднято» как точку cooldown, чтобы не долбить
        resume["last_raised_ts"] = ts
    save_resume_state(resume)
    _append_log(
        {
            "kind": "resume_raise",
            "status": result["status"],
            "detail": result.get("detail"),
            "ts": ts,
            "date": _today(tz_name).isoformat(),
        }
    )
