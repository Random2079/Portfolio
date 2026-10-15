"""Поиск вакансий.

С апреля 2026 публичный GET /vacancies на api.hh.ru → 403.
Канон: парсинг выдачи сайта через Playwright (hh.ru/search/vacancy).
API оставлен как быстрый probe — при 403 падаем на web.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from hh_auto import DATA, ROOT

API = "https://api.hh.ru/vacancies"
SEARCH_WEB = "https://hh.ru/search/vacancy"
REMOTE_SCHEDULE = "remote"

_VACANCY_HREF = re.compile(r"/vacancy/(\d+)")


def _get_json(url: str, user_agent: str, retries: int = 3) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
            "HH-User-Agent": user_agent,
        },
    )
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt + 1 >= retries:
                break
            import time

            time.sleep(attempt + 1)
    assert last is not None
    raise last


def _looks_junior(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def _is_remote_item(item: dict[str, Any]) -> bool:
    schedule = (item.get("schedule") or {}).get("id") or ""
    if schedule == REMOTE_SCHEDULE:
        return True
    for fmt in item.get("work_format") or []:
        if (fmt.get("id") or "").upper() == "REMOTE":
            return True
    return False


def _area_id(item: dict[str, Any]) -> str:
    area = item.get("area") or {}
    return str(area.get("id") or "")


_HL = re.compile(r"</?highlighttext>", re.I)


def _strip_hl(s: str) -> str:
    return _HL.sub("", s)


def _normalize_card(
    vid: str,
    title: str,
    company: str,
    url: str,
    area: str,
    snippet: str,
    remote: bool,
) -> dict[str, Any]:
    return {
        "id": vid,
        "title": title,
        "company": company,
        "url": url,
        "area": area,
        "schedule": "удалённо" if remote else "",
        "remote": remote,
        "requirement": snippet,
        "responsibility": "",
        "salary": None,
    }


def _storage_state_path(config: dict[str, Any]) -> Path | None:
    rel = (config.get("playwright") or {}).get("storage_state") or "data/storage_state.json"
    p = Path(rel)
    if not p.is_absolute():
        p = ROOT / p
    if p.exists():
        return p
    return None


def _serp_blocked(page: Any) -> bool:
    """Реальный блок/капча, не просто слово captcha в JS бандле."""
    url = (page.url or "").casefold()
    if "showcaptcha" in url or "/captcha" in url:
        return True
    for sel in (
        'iframe[src*="captcha"]',
        'iframe[src*="smartcaptcha"]',
        ".SmartCaptcha",
        "[class*='SmartCaptcha']",
        "[data-testid='checkbox-captcha']",
    ):
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:
            continue
    try:
        title = (page.title() or "").casefold()
        if "captcha" in title or "робот" in title:
            return True
    except Exception:
        return False
    return False


def _build_search_urls(config: dict[str, Any]) -> list[tuple[str, bool]]:
    """Список (url, is_remote_query)."""
    search = config["search"]
    text = search.get("text") or "Python"
    experiences = search.get("experience") or ["noExperience"]
    surgut = str(search.get("area_surgut_id") or "97")
    max_pages = int(search.get("max_pages") or 3)
    urls: list[tuple[str, bool]] = []
    for exp in experiences:
        for page in range(max_pages):
            base = {
                "text": text,
                "experience": exp,
                "page": str(page),
                "items_on_page": str(int(search.get("per_page") or 50)),
            }
            remote_q = dict(base)
            remote_q["schedule"] = REMOTE_SCHEDULE
            urls.append(
                (
                    f"{SEARCH_WEB}?{urllib.parse.urlencode(remote_q)}",
                    True,
                )
            )
            area_q = dict(base)
            area_q["area"] = surgut
            urls.append(
                (
                    f"{SEARCH_WEB}?{urllib.parse.urlencode(area_q)}",
                    False,
                )
            )
    return urls


def _parse_serp_page(
    page: Any,
    remote_flag: bool,
    junior_kw: list[str],
    exp_hint: str,
    require_junior: bool = False,
) -> list[dict[str, Any]]:
    """Достаёт карточки с открытой страницы поиска."""
    out: list[dict[str, Any]] = []
    cards = page.locator(
        '[data-qa="serp-item"], [data-qa="vacancy-serp__vacancy"], '
        'div.serp-item, div[class*="vacancy-serp-item"]'
    )
    n = cards.count()
    for i in range(n):
        try:
            card = cards.nth(i)
            link = card.locator('a[href*="/vacancy/"]').first
            if not link.count():
                continue
            href = link.get_attribute("href") or ""
            m = _VACANCY_HREF.search(href)
            if not m:
                continue
            vid = m.group(1)
            title = (link.inner_text(timeout=2000) or "").strip()
            if not title:
                continue
            company = ""
            for qa in (
                '[data-qa="vacancy-serp__vacancy-employer"]',
                '[data-qa="vacancy-serp__vacancy-employer-name"]',
                "a[data-qa*='employer']",
            ):
                loc = card.locator(qa)
                if loc.count():
                    company = (loc.first.inner_text(timeout=1000) or "").strip()
                    if company:
                        break
            area = ""
            for qa in (
                '[data-qa="vacancy-serp__vacancy-address"]',
                '[data-qa="vacancy-serp__vacancy-area"]',
            ):
                loc = card.locator(qa)
                if loc.count():
                    area = (loc.first.inner_text(timeout=1000) or "").strip()
                    if area:
                        break
            snippet = ""
            for qa in (
                '[data-qa="vacancy-serp__vacancy_snippet_requirement"]',
                '[data-qa="vacancy-serp__vacancy_snippet_responsibility"]',
            ):
                loc = card.locator(qa)
                if loc.count():
                    snippet += " " + (loc.first.inner_text(timeout=1000) or "")
            snippet = snippet.strip()
            blob = f"{title} {snippet}"
            if require_junior and exp_hint != "noExperience":
                if not _looks_junior(blob, junior_kw) and not _looks_junior(
                    title, junior_kw
                ):
                    continue
            if href.startswith("/"):
                url = "https://hh.ru" + href.split("?")[0]
            elif href.startswith("http"):
                url = href.split("?")[0]
            else:
                url = f"https://hh.ru/vacancy/{vid}"
            remote = remote_flag or (
                "удал" in (area + snippet + title).lower()
            )
            out.append(
                _normalize_card(
                    vid=vid,
                    title=title,
                    company=company,
                    url=url,
                    area=area,
                    snippet=snippet,
                    remote=remote,
                )
            )
        except Exception:
            continue
    return out


def fetch_vacancies_web(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Поиск через сайт hh.ru (Playwright)."""
    from playwright.sync_api import sync_playwright

    search = config["search"]
    junior_kw = search.get("junior_keywords") or [
        "junior",
        "джун",
        "стажёр",
        "стажер",
    ]
    pw_cfg = config.get("playwright") or {}
    from hh_auto import playwright_headless

    if "search_headless" in pw_cfg:
        headless = bool(pw_cfg["search_headless"])
    else:
        headless = playwright_headless(config)
    slow = int(pw_cfg.get("slow_mo_ms") or 0)
    state = _storage_state_path(config)
    by_id: dict[str, dict[str, Any]] = {}
    urls = _build_search_urls(config)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow)
        ctx_kwargs: dict[str, Any] = {
            "locale": "ru-RU",
            "user_agent": config.get("user_agent")
            or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        }
        if state is not None:
            ctx_kwargs["storage_state"] = str(state)
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        for url, is_remote in urls:
            exp_hint = "noExperience"
            if "experience=between1And3" in url:
                exp_hint = "between1And3"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1200)
                if _serp_blocked(page):
                    browser.close()
                    raise RuntimeError(
                        "Капча/блок на поиске hh — сделай: python -m hh_auto login "
                        "и повтори search (нужен storage_state)"
                    )
                cards = _parse_serp_page(
                    page,
                    remote_flag=is_remote,
                    junior_kw=junior_kw,
                    exp_hint=exp_hint,
                    require_junior=bool(search.get("require_junior_keywords")),
                )
                for c in cards:
                    by_id[c["id"]] = c
            except RuntimeError:
                raise
            except Exception as e:
                print(f"  warn search page: {e}")

        browser.close()

    return list(by_id.values())


def fetch_vacancies_api(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Старый путь api.hh.ru — с 2026 обычно 403."""
    search = config["search"]
    ua = config.get("user_agent") or "HH-AutoApply/0.1 (tean8282@gmail.com)"
    experiences = search.get("experience") or ["noExperience"]
    junior_kw = search.get("junior_keywords") or [
        "junior",
        "джун",
        "стажёр",
        "стажер",
    ]
    per_page = int(search.get("per_page") or 50)
    max_pages = int(search.get("max_pages") or 3)
    text = search.get("text") or "Python"
    surgut = str(search.get("area_surgut_id") or "97")
    by_id: dict[str, dict[str, Any]] = {}

    def pull(extra: dict[str, str]) -> None:
        for exp in experiences:
            for page in range(max_pages):
                params = {
                    "text": text,
                    "experience": exp,
                    "per_page": str(per_page),
                    "page": str(page),
                    **extra,
                }
                url = f"{API}?{urllib.parse.urlencode(params)}"
                data = _get_json(url, ua)
                for item in data.get("items") or []:
                    vid = str(item.get("id") or "")
                    if not vid:
                        continue
                    blob = " ".join(
                        [
                            item.get("name") or "",
                            (item.get("snippet") or {}).get("requirement") or "",
                            (item.get("snippet") or {}).get("responsibility") or "",
                        ]
                    )
                    if exp != "noExperience":
                        if not _looks_junior(blob, junior_kw) and not _looks_junior(
                            item.get("name") or "", junior_kw
                        ):
                            continue
                    by_id[vid] = item
                pages = int(data.get("pages") or 0)
                if page + 1 >= pages:
                    break

    pull({"schedule": REMOTE_SCHEDULE})
    pull({"area": surgut})

    out: list[dict[str, Any]] = []
    for item in by_id.values():
        remote = _is_remote_item(item)
        in_surgut = _area_id(item) == surgut
        if not remote and not in_surgut:
            continue
        employer = item.get("employer") or {}
        snip = item.get("snippet") or {}
        out.append(
            {
                "id": str(item.get("id")),
                "title": item.get("name") or "",
                "company": employer.get("name") or "",
                "url": item.get("alternate_url") or "",
                "area": (item.get("area") or {}).get("name") or "",
                "schedule": (item.get("schedule") or {}).get("name") or "",
                "remote": remote,
                "requirement": _strip_hl(snip.get("requirement") or ""),
                "responsibility": _strip_hl(snip.get("responsibility") or ""),
                "salary": item.get("salary"),
            }
        )
    return out


def fetch_vacancies(config: dict[str, Any]) -> list[dict[str, Any]]:
    mode = (config.get("search") or {}).get("mode") or "auto"
    if mode == "web":
        print("Поиск: сайт hh.ru (Playwright) …")
        return fetch_vacancies_web(config)
    if mode == "api":
        print("Поиск: api.hh.ru …")
        return fetch_vacancies_api(config)
    try:
        print("Поиск: пробуем api.hh.ru …")
        return fetch_vacancies_api(config)
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise RuntimeError(
                f"hh API HTTP {e.code}: {e.read()[:300]!r}"
            ) from e
        print("api.hh.ru → 403 (публичный поиск закрыт). Переход на сайт …")
    except RuntimeError:
        raise
    except Exception as e:
        print(f"api.hh.ru недоступен ({e}). Переход на сайт …")
    return fetch_vacancies_web(config)
