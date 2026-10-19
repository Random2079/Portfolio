"""Playwright: login Kwork + LIVE «Предложить услугу»."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from hh_auto import DATA, ensure_data_dir, playwright_headless
from hh_auto.apply import page_looks_like_captcha
from hh_auto.kwork_search import storage_state_path
from hh_auto.limits import can_apply, load_state, record_apply, refresh_day, save_state

CAPTCHA_STOP = "captcha"


def apply_state_path() -> Path:
    return DATA / "kwork_apply_state.json"


def apply_log_path() -> Path:
    return DATA / "kwork_apply_log.jsonl"


def append_log(row: dict[str, Any]) -> None:
    ensure_data_dir()
    with apply_log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_log(limit: int = 50) -> list[dict[str, Any]]:
    p = apply_log_path()
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
    return rows[-limit:]


def format_kwork_feed(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "📭 Kwork лента пуста — пока ничего не отправляли.\n"
    lines = ["📨 Kwork — последние отправки\n"]
    for r in reversed(rows):
        st = r.get("status") or "?"
        icon = "✅" if st == "sent" else ("⏭" if st in ("skip", "dry_run", "already_applied") else "❌")
        buyer = r.get("buyer") or "—"
        title = (r.get("title") or "")[:60]
        price = r.get("price_rub") or ""
        url = r.get("url") or ""
        ts = (r.get("ts") or "")[:19]
        lines.append(f"{icon} {ts} · {buyer} · {title}")
        if price:
            lines.append(f"   💰 {price} ₽ · {st}")
        if url:
            lines.append(f"   🔗 {url}")
        preview = (r.get("cover_preview") or "").strip()
        if preview:
            lines.append(f"   «{preview[:120]}…»" if len(preview) > 120 else f"   «{preview}»")
        lines.append("")
    return "\n".join(lines)


def _visible_captcha(page: Any) -> bool:
    if page_looks_like_captcha(page.title() or "", page.url or ""):
        return True
    for sel in ('iframe[src*="captcha"]', "[class*='Captcha']", "[class*='captcha']"):
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


def _logged_in(page: Any) -> bool:
    """Есть ли сессия продавца (нет «Вход» как главной кнопки / есть seller)."""
    url = (page.url or "").casefold()
    if "/login" in url:
        return False
    try:
        # ссылка «Вход» в шапке = гость
        login_links = page.locator('a[href*="/login"], a:has-text("Вход")')
        # профиль / seller
        seller = page.locator('a[href*="/seller"], a[href*="/user/"]')
        text = (page.inner_text("header") if page.locator("header").count() else "") or ""
        if "Регистрация" in text and "Вход" in text and seller.count() == 0:
            return False
        if "/seller" in url or "Создать кворк" in (page.content() or ""):
            return True
        # если login_links видимы в навбаре — часто гость
        if login_links.count():
            try:
                if login_links.first.is_visible():
                    # но на login-странице всегда; на seller — нет
                    if "создать кворк" in (page.inner_text("body") or "").casefold():
                        return True
                    body = (page.inner_text("body") or "")[:500].casefold()
                    if "личный кабинет" in body or "мои кворки" in body:
                        return True
                    # эвристика: на главной гостя есть «Покупайте фриланс»
                    if "покупайте фриланс" in body:
                        return False
            except Exception:
                pass
        return True
    except Exception:
        return False


def cmd_login(cfg: dict[str, Any]) -> int:
    from playwright.sync_api import sync_playwright

    state_file = storage_state_path(cfg)
    ensure_data_dir()
    slow = int((cfg.get("playwright") or {}).get("slow_mo_ms") or 0)

    print("Откроется Chromium → зайди в kwork.ru (продавец).")
    print("Когда кабинет открыт — вернись в терминал и нажми Enter.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://kwork.ru/login", wait_until="domcontentloaded")
        input(">>> Enter после логина … ")
        if _visible_captcha(page):
            browser.close()
            print("Капча — state не сохранён.")
            return 2
        # sanity: seller
        try:
            page.goto("https://kwork.ru/seller", wait_until="domcontentloaded")
        except Exception:
            pass
        if not _logged_in(page):
            print("Похоже, всё ещё гость. Залогинься и login снова.")
            browser.close()
            return 1
        context.storage_state(path=str(state_file))
        browser.close()

    print(f"Сохранено: {state_file}")
    return 0


def _fill_proposal(page: Any, cover: str, price: int, days: int) -> str | None:
    """Заполнить форму предложения. None = ок, иначе причина ошибки."""
    # кнопка «Предложить услугу»
    clicked = False
    for label in ("Предложить услугу", "Предложить", "Откликнуться"):
        btn = page.get_by_role("button", name=re.compile(label, re.I))
        if btn.count():
            try:
                btn.first.click(timeout=5000)
                clicked = True
                break
            except Exception:
                pass
        link = page.get_by_role("link", name=re.compile(label, re.I))
        if link.count():
            try:
                link.first.click(timeout=5000)
                clicked = True
                break
            except Exception:
                pass
    if not clicked:
        # text locator
        loc = page.locator("text=Предложить услугу")
        if loc.count():
            try:
                loc.first.click(timeout=5000)
                clicked = True
            except Exception:
                pass
    if not clicked:
        return "no_propose_button"

    page.wait_for_timeout(1000)

    # textarea описания
    area = page.locator("textarea")
    if not area.count():
        return "no_textarea"
    try:
        area.first.fill(cover)
    except Exception:
        try:
            area.first.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(cover, delay=5)
        except Exception as exc:
            return f"fill_cover:{exc}"

    # цена
    price_filled = False
    for sel in (
        'input[name*="price"]',
        'input[placeholder*="Цена"]',
        'input[placeholder*="цена"]',
        'input[type="number"]',
    ):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.fill(str(price))
                price_filled = True
                break
            except Exception:
                continue
    if not price_filled:
        # иногда два number: цена и срок
        nums = page.locator('input[type="text"], input[type="number"]')
        if nums.count() >= 1:
            try:
                nums.first.fill(str(price))
                price_filled = True
            except Exception:
                pass

    # срок
    for sel in (
        'input[name*="day"]',
        'input[placeholder*="Срок"]',
        'input[placeholder*="дней"]',
    ):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.fill(str(days))
                break
            except Exception:
                continue

    return None


def _submit_proposal(page: Any) -> str | None:
    for label in ("Отправить", "Предложить услугу", "Откликнуться"):
        btn = page.get_by_role("button", name=re.compile(f"^{label}", re.I))
        if btn.count():
            try:
                btn.last.click(timeout=8000)
                page.wait_for_timeout(1500)
                return None
            except Exception:
                continue
    loc = page.locator("button:has-text('Отправить')")
    if loc.count():
        try:
            loc.last.click(timeout=8000)
            page.wait_for_timeout(1500)
            return None
        except Exception as exc:
            return f"submit:{exc}"
    return "no_submit_button"


def send_proposal(
    cfg: dict[str, Any],
    project: dict[str, Any],
    *,
    cover: str,
    price_rub: int,
    days: int = 7,
    dry_run: bool = False,
) -> dict[str, Any]:
    """LIVE или dry_run. Результат: status + поля для лога."""
    from playwright.sync_api import sync_playwright

    pid = str(project.get("project_id") or "")
    url = project.get("url") or f"https://kwork.ru/projects/{pid}/view"
    tz = cfg.get("timezone") or "Asia/Yekaterinburg"
    daily = int((_kwork_daily(cfg)))
    state = refresh_day(load_state(apply_state_path()), tz)
    base = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "project_id": pid,
        "title": project.get("title"),
        "buyer": project.get("buyer"),
        "url": url,
        "price_rub": price_rub,
        "cover_preview": (cover or "")[:200],
    }
    if dry_run:
        row = {**base, "status": "dry_run"}
        append_log(row)
        return row

    ok, reason = can_apply(state, pid, daily, tz)
    if not ok:
        row = {**base, "status": reason}
        append_log(row)
        return row

    state_file = storage_state_path(cfg)
    if not state_file.exists():
        row = {**base, "status": "no_login", "detail": "python -m hh_auto kwork-login"}
        append_log(row)
        return row

    headless = playwright_headless(cfg)
    slow = int((cfg.get("playwright") or {}).get("slow_mo_ms") or 0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow)
        context = browser.new_context(storage_state=str(state_file))
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1000)
            if _visible_captcha(page):
                row = {**base, "status": CAPTCHA_STOP}
                append_log(row)
                browser.close()
                return row

            err = _fill_proposal(page, cover, price_rub, days)
            if err:
                row = {**base, "status": "error", "detail": err}
                append_log(row)
                browser.close()
                return row

            err = _submit_proposal(page)
            if err:
                row = {**base, "status": "error", "detail": err}
                append_log(row)
                browser.close()
                return row

            if _visible_captcha(page):
                row = {**base, "status": CAPTCHA_STOP}
                append_log(row)
                browser.close()
                return row

            # обновить storage (на всякий)
            try:
                context.storage_state(path=str(state_file))
            except Exception:
                pass

            state = record_apply(state, pid, tz)
            save_state(apply_state_path(), state)
            row = {**base, "status": "sent"}
            append_log(row)
            browser.close()
            return row
        except Exception as exc:
            row = {**base, "status": "error", "detail": str(exc)[:300]}
            append_log(row)
            try:
                browser.close()
            except Exception:
                pass
            return row


def _kwork_daily(cfg: dict[str, Any]) -> int:
    return int((cfg.get("kwork") or {}).get("daily_limit") or 15)


def kwork_today_count(cfg: dict[str, Any]) -> tuple[int, int]:
    tz = cfg.get("timezone") or "Asia/Yekaterinburg"
    state = refresh_day(load_state(apply_state_path()), tz)
    return int(state.get("count") or 0), _kwork_daily(cfg)
