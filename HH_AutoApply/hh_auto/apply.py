"""Слой B: Playwright login + apply. Капчу не обходим — стоп."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from hh_auto import DATA, ensure_data_dir, load_config
from hh_auto.cover import render_cover
from hh_auto.limits import can_apply, load_state, record_apply, save_state

CAPTCHA_HINTS = ("showcaptcha", "я не робот", "подтвердите, что вы не робот", "are you a robot")


def _state_path(cfg: dict[str, Any]) -> Path:
    rel = (cfg.get("playwright") or {}).get("storage_state") or "data/storage_state.json"
    p = Path(rel)
    if p.is_absolute():
        return p
    return DATA.parent / p


def _apply_state_path() -> Path:
    return DATA / "apply_state.json"


def _log_path() -> Path:
    return DATA / "apply_log.jsonl"


def _append_log(row: dict[str, Any]) -> None:
    ensure_data_dir()
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def page_looks_like_captcha(text: str, url: str = "") -> bool:
    """URL challenge / явная фраза. Голое 'captcha' в JS-бандле — не считаем."""
    u = (url or "").casefold()
    if "showcaptcha" in u or "/captcha" in u:
        return True
    low = (text or "").casefold()
    if len(low) > 4000:
        low = low[:4000]
    return any(h in low for h in CAPTCHA_HINTS)


def _visible_captcha(page: Any) -> bool:
    if page_looks_like_captcha(page.title() or "", page.url or ""):
        return True
    for sel in (
        'iframe[src*="captcha"]',
        'iframe[src*="smartcaptcha"]',
        "[class*='SmartCaptcha']",
    ):
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


def _vacancy_id_from_url(url: str) -> str:
    m = re.search(r"/vacancy/(\d+)", url)
    if m:
        return m.group(1)
    return url


def load_ranked(path: Path | None = None) -> list[dict[str, Any]]:
    ensure_data_dir()
    if path and path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    files = sorted(DATA.glob("ranked_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            "Нет ranked_*.json — сначала: python -m hh_auto search"
        )
    with files[0].open(encoding="utf-8") as f:
        return json.load(f)


def cmd_login(cfg: dict[str, Any]) -> int:
    from playwright.sync_api import sync_playwright

    pw_cfg = cfg.get("playwright") or {}
    state_file = _state_path(cfg)
    ensure_data_dir()
    headless = bool(pw_cfg.get("headless"))
    slow = int(pw_cfg.get("slow_mo_ms") or 0)

    print("Откроется Chromium → зайди в hh.ru (логин).")
    print("Когда профиль открыт — вернись в терминал и нажми Enter.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://hh.ru/applicant/resumes", wait_until="domcontentloaded")
        input(">>> Enter после логина … ")
        if _visible_captcha(page):
            browser.close()
            print("Похоже на капчу — state не сохранён. Разгадай вручную и login снова.")
            return 2
        context.storage_state(path=str(state_file))
        browser.close()

    print(f"Сохранено: {state_file}")
    return 0


def _find_respond_button(page: Any):
    """Кнопка отклика — несколько стратегий, hh часто меняет вёрстку."""
    candidates = [
        page.get_by_role("button", name=re.compile("отклик", re.I)),
        page.get_by_role("link", name=re.compile("отклик", re.I)),
        page.locator("button:has-text('Откликнуться')"),
        page.locator("a:has-text('Откликнуться')"),
        page.locator("[data-qa='vacancy-response-link-top']"),
        page.locator("[data-qa='vacancy-response-button']"),
    ]
    for loc in candidates:
        try:
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def _fill_cover_if_present(page: Any, cover: str) -> bool:
    if not cover:
        return False
    areas = [
        page.locator("textarea[data-qa='textarea-letter']"),
        page.locator("textarea[name='letter']"),
        page.get_by_role("textbox", name=re.compile("сопровод|письм", re.I)),
        page.locator("textarea").first,
    ]
    for area in areas:
        try:
            if area.count() and area.first.is_visible():
                area.first.fill(cover)
                return True
        except Exception:
            continue
    return False


def _confirm_if_present(page: Any) -> None:
    for loc in (
        page.get_by_role("button", name=re.compile("отправ|откликн|готово|сохранить", re.I)),
        page.locator("[data-qa='vacancy-response-submit-popup']"),
        page.locator("button:has-text('Отправить')"),
    ):
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                return
        except Exception:
            continue


def apply_one(
    page: Any,
    vacancy: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    url = vacancy.get("url") or ""
    vid = str(vacancy.get("id") or _vacancy_id_from_url(url))
    cover = vacancy.get("cover") or ""
    result = {
        "id": vid,
        "url": url,
        "title": vacancy.get("title"),
        "dry_run": dry_run,
        "status": "unknown",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(800)
    if _visible_captcha(page):
        result["status"] = "captcha"
        return result

    btn = _find_respond_button(page)
    if btn is None:
        body = page.inner_text("body")[:4000].casefold()
        if "вы откликнулись" in body or "отклик отправлен" in body:
            result["status"] = "already_on_hh"
        else:
            result["status"] = "no_button"
        return result

    if dry_run:
        result["status"] = "dry_run_ok"
        result["button"] = "found"
        return result

    btn.click(timeout=10000)
    page.wait_for_timeout(1000)
    if _visible_captcha(page):
        result["status"] = "captcha"
        return result
    filled = _fill_cover_if_present(page, cover)
    result["cover_filled"] = filled
    result["cover_len"] = len(cover)
    _confirm_if_present(page)
    page.wait_for_timeout(800)
    if _visible_captcha(page):
        result["status"] = "captcha"
        return result
    result["status"] = "applied"
    return result


def cmd_apply(
    cfg: dict[str, Any],
    dry_run: bool,
    limit: int | None,
    ranked_path: Path | None,
    cancel_event: Any | None = None,
) -> int:
    from playwright.sync_api import sync_playwright

    ensure_data_dir()
    state_file = _state_path(cfg)
    if not state_file.exists():
        print("Нет storage_state. Сначала: python -m hh_auto login")
        return 1

    vacancies = load_ranked(ranked_path)
    daily = int(limit if limit is not None else (cfg.get("daily_limit") or 40))
    tz = cfg.get("timezone") or "Asia/Yekaterinburg"
    st = load_state(_apply_state_path())
    pw_cfg = cfg.get("playwright") or {}
    headless = bool(pw_cfg.get("headless"))
    slow = int(pw_cfg.get("slow_mo_ms") or 0)
    cover_template = (
        cfg.get("cover_template")
        or "Здравствуйте! Откликаюсь на «{title}» ({company}).\n"
        "<<< ЗАГОТОВКА: замени cover_template в config.json своим текстом. >>>"
    )

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"{mode} · кандидатов {len(vacancies)} · лимит сегодня {daily}")

    def _cancelled() -> bool:
        return bool(cancel_event is not None and cancel_event.is_set())

    applied_now = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow)
        context = browser.new_context(storage_state=str(state_file))
        page = context.new_page()

        for v in vacancies:
            if _cancelled():
                print("⏸ отмена — стоп по кнопке")
                break
            vid = str(
                v.get("id")
                or _vacancy_id_from_url(v.get("url") or "")
            )
            ok, reason = can_apply(st, vid, daily, tz)
            if not ok:
                print(f"  skip {vid}: {reason}")
                if reason == "daily_limit":
                    break
                continue

            print(
                f"  → [{v.get('score')}] {v.get('title')} — {v.get('company')}"
            )
            # Сопроводительное: из ranked.cover или свежий render из cover_template
            if not (v.get("cover") or "").strip():
                v = dict(v)
                v["cover"] = render_cover(cover_template, v)
            try:
                row = apply_one(page, v, dry_run=dry_run)
            except Exception as e:
                row = {
                    "id": vid,
                    "url": v.get("url"),
                    "status": "error",
                    "error": str(e),
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }

            _append_log(row)
            print(f"     status={row.get('status')}")

            if row.get("status") == "captcha":
                print("Капча/challenge — СТОП. Разгадай вручную, потом снова.")
                context.storage_state(path=str(state_file))
                browser.close()
                return 2

            if not dry_run and row.get("status") in frozenset({"already_on_hh", "applied"}):
                st = record_apply(st, vid, tz)
                save_state(_apply_state_path(), st)
                applied_now += 1
                if applied_now >= daily:
                    break
                continue

            if dry_run:
                if row.get("status") != "dry_run_ok":
                    continue
                applied_now += 1
                if applied_now >= min(daily, 5):
                    print("dry-run: хватит 5 для смоука (или --limit)")
                    break

        context.storage_state(path=str(state_file))
        browser.close()

    if _cancelled():
        print(f"⏸ Отменено. Обработано: {applied_now}. Лог: {_log_path()}")
        return 3
    print(f"Готово. Обработано в этом запуске: {applied_now}. Лог: {_log_path()}")
    return 0
