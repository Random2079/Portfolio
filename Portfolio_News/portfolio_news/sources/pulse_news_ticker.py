"""Pulse news-by-ticker — SSR scrape of /invest/stocks/{TICKER}/news/.

Unlike profile allowlist (authors) and social posts-by-ticker (needs session),
the stock **news** tab embeds ``investSocialNewsByTicker`` in a child-app
``application/json`` script — anonymous HTTP 200 with titles + owners.

Equity only (bonds/funds later). Reuses allowlist ``drop`` nicknames and
``is_noise_title``; soft-drops T-Investments-style target/analyst headlines.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from portfolio_news.sources.base import RawNews
from portfolio_news.sources.news_noise import is_noise_title, title_matches_ticker
from portfolio_news.sources.pulse_allowlist import (
    load_allowlist_config,
    mirror_base,
    post_url,
)

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).with_name("pulse_allowlist.json")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

# T-Investments / wire often tag broad digests onto many tickers.
_MAX_BROAD_INSTRUMENTS = 3

# Soft drop: analyst targets / rating changes (MAP §7S T-Investments note).
_TARGET_TITLE = re.compile(
    r"(целев\w*\s*цен|повысили\s+оценк|понизили\s+оценк|таргет\w*|"
    r"рекоменд\w*\s+(покупать|держать|продавать)|analyst\s+target)",
    re.I,
)


def news_page_url(ticker_id: str, base: str | None = None) -> str:
    b = (base or mirror_base()).rstrip("/")
    tid = (ticker_id or "").strip().upper()
    return f"{b}/invest/stocks/{tid}/news/"


def _parse_inserted(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _drop_nicknames(cfg: dict[str, Any] | None = None) -> set[str]:
    data = cfg if cfg is not None else load_allowlist_config()
    raw = data.get("drop") or []
    return {str(n).strip() for n in raw if str(n).strip()}


def extract_news_items_from_html(html: str, ticker_id: str) -> list[dict[str, Any]]:
    """Parse child-app JSON → ``investSocialNewsByTicker[TICKER].items``."""
    tid = (ticker_id or "").strip().upper()
    if not tid or not html:
        return []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        blob = m.group(1)
        if "investSocialNewsByTicker" not in blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        items = _items_from_child_payload(data, tid)
        if items is not None:
            return items
    log.warning("pulse news ticker: no investSocialNewsByTicker for %s", tid)
    return []


def _items_from_child_payload(
    data: dict[str, Any], ticker_id: str
) -> list[dict[str, Any]] | None:
    """Return items list if store present (even empty); None if shape missing."""
    # Shape A: { "pulse-news-by-ticker@x.y": { "stores": { ... } } }
    for _k, v in data.items():
        if not isinstance(v, dict):
            continue
        stores = v.get("stores")
        if isinstance(stores, dict) and "investSocialNewsByTicker" in stores:
            return _items_from_store(stores["investSocialNewsByTicker"], ticker_id)
    # Shape B: stores at top (unlikely)
    stores = data.get("stores")
    if isinstance(stores, dict) and "investSocialNewsByTicker" in stores:
        return _items_from_store(stores["investSocialNewsByTicker"], ticker_id)
    return None


def _items_from_store(block: Any, ticker_id: str) -> list[dict[str, Any]]:
    if not isinstance(block, dict):
        return []
    entry = block.get(ticker_id) or block.get(ticker_id.lower())
    if entry is None and len(block) == 1:
        entry = next(iter(block.values()))
    if not isinstance(entry, dict):
        return []
    items = entry.get("items")
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _instrument_tickers(item: dict[str, Any]) -> set[str]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    raw = content.get("instruments") if isinstance(content, dict) else None
    if not isinstance(raw, list):
        return set()
    out: set[str] = set()
    for it in raw:
        if not isinstance(it, dict):
            continue
        t = str(it.get("ticker") or "").strip().upper()
        if t:
            out.add(t)
    return out


def _title_of(item: dict[str, Any]) -> str:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    if not isinstance(content, dict):
        return ""
    title = str(content.get("title") or "").strip()
    if title:
        return title
    return str(content.get("announce") or "").strip()


def _nickname_of(item: dict[str, Any]) -> str:
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    if not isinstance(owner, dict):
        return ""
    return str(owner.get("nickname") or "").strip()


def item_kept(
    item: dict[str, Any],
    ticker_id: str,
    search_query: str = "",
    *,
    drop_nicks: set[str] | None = None,
) -> bool:
    """Whether a news-by-ticker item should become RawNews."""
    tid = (ticker_id or "").strip().upper()
    if not tid:
        return False
    if (item.get("status") or "published").strip().lower() not in ("", "published"):
        return False
    title = _title_of(item)
    if not title or is_noise_title(title):
        return False
    if _TARGET_TITLE.search(title):
        return False
    nick = _nickname_of(item)
    if drop_nicks and nick in drop_nicks:
        return False
    inst = _instrument_tickers(item)
    if tid not in inst:
        return False
    # Broad multi-tag digest without issuer/ticker prose → skip.
    if len(inst) > _MAX_BROAD_INSTRUMENTS and not title_matches_ticker(
        title, tid, search_query
    ):
        return False
    return True


def fetch_ticker_news_html(
    ticker_id: str,
    *,
    base: str | None = None,
    timeout: float = 35.0,
    session: requests.Session | None = None,
) -> str:
    url = news_page_url(ticker_id, base=base)
    sess = session or requests
    try:
        resp = sess.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.RequestException as exc:
        log.warning("pulse news ticker fetch failed %s: %s", ticker_id, exc)
        return ""


class PulseNewsTickerSource:
    """NewsSource: Pulse stock-news tab SSR per equity ticker."""

    name = "pulse_news_ticker"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        base: str | None = None,
        timeout: float = 35.0,
        drop_nicks: set[str] | None = None,
    ) -> None:
        self._config_path = config_path or _CONFIG_PATH
        self._base_override = base
        self._timeout = timeout
        self._drop_override = drop_nicks
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._session: requests.Session | None = None

    def _base(self) -> str:
        if self._base_override:
            return self._base_override.rstrip("/")
        return mirror_base(load_allowlist_config(self._config_path))

    def _drop(self) -> set[str]:
        if self._drop_override is not None:
            return set(self._drop_override)
        return _drop_nicknames(load_allowlist_config(self._config_path))

    def _ensure_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _items_for(self, ticker_id: str) -> list[dict[str, Any]]:
        tid = (ticker_id or "").strip().upper()
        if not tid:
            return []
        if tid in self._cache:
            return self._cache[tid]
        html = fetch_ticker_news_html(
            tid,
            base=self._base(),
            timeout=self._timeout,
            session=self._ensure_session(),
        )
        items = extract_news_items_from_html(html, tid) if html else []
        log.info("pulse news ticker: %s → %s items", tid, len(items))
        self._cache[tid] = items
        return items

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        k = (kind or "equity").strip().lower()
        if k not in ("equity", "stock", "share", "shares"):
            return []
        tid = (ticker_id or "").strip().upper()
        if not tid or tid.startswith("RU000"):
            return []
        try:
            items = self._items_for(tid)
        except Exception as exc:  # noqa: BLE001
            log.warning("pulse news ticker load failed %s: %s", tid, exc)
            return []
        drop = self._drop()
        base = self._base()
        out: list[RawNews] = []
        for item in items:
            if not item_kept(item, tid, search_query, drop_nicks=drop):
                continue
            title = _title_of(item)[:512]
            nick = _nickname_of(item) or "pulse"
            post_id = str(item.get("id") or "").strip()
            if not post_id:
                continue
            out.append(
                RawNews(
                    title=title,
                    url=post_url(nick, post_id, base=base)[:1024],
                    source=self.name,
                    published_at=_parse_inserted(item.get("inserted")),
                )
            )
            if len(out) >= 10:
                break
        return out
