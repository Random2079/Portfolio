"""Поиск проектов на бирже Kwork + keyword filter (стек Python/боты/парсинг)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from hh_auto import DATA, ensure_data_dir, playwright_headless

PROJECT_ID_RE = re.compile(r"/projects/(\d+)")
BUDGET_RE = re.compile(r"(\d[\d\s]*)\s*₽")


def _kwork_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("kwork") or {}


def storage_state_path(cfg: dict[str, Any]):
    from pathlib import Path

    rel = _kwork_cfg(cfg).get("storage_state") or "data/kwork_storage_state.json"
    p = Path(rel)
    if p.is_absolute():
        return p
    return DATA.parent / p


def project_blob(p: dict[str, Any]) -> str:
    return " ".join(
        [
            str(p.get("title") or ""),
            str(p.get("description") or ""),
            str(p.get("buyer") or ""),
        ]
    )


def keyword_hits(blob: str, keywords: list[str]) -> list[str]:
    low = (blob or "").casefold()
    hits: list[str] = []
    for kw in keywords:
        k = (kw or "").strip()
        if not k:
            continue
        if k.casefold() in low:
            hits.append(k)
    return hits


def filter_projects(
    projects: list[dict[str, Any]],
    keywords: list[str],
    min_score: int = 1,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in projects:
        hits = keyword_hits(project_blob(p), keywords)
        row = dict(p)
        row["kw_hits"] = hits
        row["kw_score"] = len(hits)
        if len(hits) >= int(min_score):
            out.append(row)
    out.sort(key=lambda x: (-int(x.get("kw_score") or 0), x.get("title") or ""))
    return out


def _parse_budget(text: str) -> int | None:
    m = BUDGET_RE.search(text or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    try:
        return int(digits) if digits else None
    except ValueError:
        return None


def _extract_cards(page: Any) -> list[dict[str, Any]]:
    """Собрать карточки проектов со страницы выдачи."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    links = page.locator('a[href*="/projects/"]')
    n = min(links.count(), 80)
    for i in range(n):
        try:
            a = links.nth(i)
            href = a.get_attribute("href") or ""
            m = PROJECT_ID_RE.search(href)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            title = (a.inner_text() or "").strip()
            if not title or len(title) < 3:
                continue
            # отбросить навигационные/мусорные
            low = title.casefold()
            if low in ("проекты", "биржа", "смотреть все"):
                continue
            url = href if href.startswith("http") else f"https://kwork.ru{href}"
            if "/view" not in url and url.rstrip("/").endswith(pid):
                url = f"https://kwork.ru/projects/{pid}/view"
            rows.append(
                {
                    "project_id": pid,
                    "title": title.split("\n")[0].strip()[:200],
                    "url": url,
                    "description": "",
                    "buyer": "",
                    "budget_rub": None,
                }
            )
        except Exception:
            continue
    return rows


def _enrich_project(page: Any, project: dict[str, Any]) -> dict[str, Any]:
    """Открыть карточку → описание, покупатель, бюджет."""
    url = project.get("url") or f"https://kwork.ru/projects/{project['project_id']}/view"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(800)
        body = page.inner_text("body") or ""
        # покупатель — часто ссылка на профиль рядом с «Покупатель»
        buyer = ""
        for sel in (
            'a[href*="/user/"]',
            ".want-card__user-name a",
            "[class*='username'] a",
        ):
            try:
                loc = page.locator(sel)
                if loc.count():
                    t = (loc.first.inner_text() or "").strip()
                    if t and t.casefold() not in ("вход", "регистрация"):
                        buyer = t[:80]
                        break
            except Exception:
                continue
        # описание — большой текстовый блок
        desc = ""
        for sel in (
            ".want-card__description",
            "[class*='description']",
            "article",
            "main",
        ):
            try:
                loc = page.locator(sel)
                if loc.count():
                    t = (loc.first.inner_text() or "").strip()
                    if len(t) > 40:
                        desc = t[:4000]
                        break
            except Exception:
                continue
        if not desc:
            desc = body[:3000]
        budget = _parse_budget(body)
        title = project.get("title") or ""
        try:
            h1 = page.locator("h1")
            if h1.count():
                t = (h1.first.inner_text() or "").strip()
                if t:
                    title = t[:200]
        except Exception:
            pass
        row = dict(project)
        row["url"] = page.url or url
        row["title"] = title
        row["description"] = desc
        row["buyer"] = buyer
        row["budget_rub"] = budget
        return row
    except Exception as exc:
        row = dict(project)
        row["description"] = row.get("description") or ""
        row["error"] = str(exc)[:200]
        return row


def fetch_projects(cfg: dict[str, Any], *, enrich: bool = True, max_enrich: int = 12) -> list[dict[str, Any]]:
    """Выдача по search_queries → дедуп → опционально enrich карточек."""
    from playwright.sync_api import sync_playwright

    kw_cfg = _kwork_cfg(cfg)
    queries = list(kw_cfg.get("search_queries") or ["python"])
    keywords = list(kw_cfg.get("keywords") or [])
    min_score = int(kw_cfg.get("min_score") or 1)
    headless = playwright_headless(cfg)
    state_file = storage_state_path(cfg)
    ensure_data_dir()

    by_id: dict[str, dict[str, Any]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_kwargs: dict[str, Any] = {}
        if state_file.exists():
            ctx_kwargs["storage_state"] = str(state_file)
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        for q in queries:
            url = f"https://kwork.ru/projects?keyword={quote_plus(q)}&c=all"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1200)
            except Exception:
                continue
            for card in _extract_cards(page):
                by_id.setdefault(card["project_id"], card)

        projects = list(by_id.values())
        # грубый keyword filter до enrich — меньше запросов
        if keywords:
            projects = filter_projects(projects, keywords, min_score=1)

        if enrich:
            enriched: list[dict[str, Any]] = []
            for proj in projects[: max(1, int(max_enrich))]:
                enriched.append(_enrich_project(page, proj))
            projects = enriched

        browser.close()

    if keywords:
        projects = filter_projects(projects, keywords, min_score=min_score)
    return projects
