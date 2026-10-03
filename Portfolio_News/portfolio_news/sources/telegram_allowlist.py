"""Public Telegram preview scrape (no userbot): t.me/s/{slug}."""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from portfolio_news.sources.base import RawNews
from portfolio_news.sources.news_noise import is_noise_title, title_matches_ticker

log = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).with_name("telegram_allowlist.json")
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.8",
}

_MSG_RE = re.compile(
    r'<div[^>]*class="[^"]*tgme_widget_message[^"]*"[^>]*data-post="([^"]+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    re.I | re.S,
)
_TEXT_RE = re.compile(
    r'<div[^>]*class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.I | re.S,
)
_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"', re.I)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class _TgPost:
    url: str
    title: str
    body: str
    published_at: Optional[datetime]


def load_tg_config(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT_CONFIG
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def v1_slugs(cfg: dict[str, Any] | None = None) -> list[str]:
    data = cfg if cfg is not None else load_tg_config()
    out: list[str] = []
    for row in data.get("v1") or []:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip().lstrip("@")
        if slug:
            out.append(slug)
    return out


def _plain(fragment: str) -> str:
    t = fragment.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = _TAG_RE.sub("", t)
    t = html_lib.unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _parse_dt(raw: str) -> Optional[datetime]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def parse_preview_html(html: str, *, slug: str) -> list[_TgPost]:
    """Parse t.me/s/{slug} widget HTML into posts."""
    posts: list[_TgPost] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'data-post="([^"]+)"',
        html,
        re.I,
    ):
        post_id = (m.group(1) or "").strip()
        if not post_id or post_id in seen:
            continue
        if "/" not in post_id:
            continue
        seen.add(post_id)
        start = m.start()
        chunk = html[start : start + 8000]
        tm = _TEXT_RE.search(chunk)
        if not tm:
            continue
        body = _plain(tm.group(1))
        if not body:
            continue
        first = body.splitlines()[0].strip()
        title = (first or body)[:512]
        tdm = _TIME_RE.search(chunk)
        url = "https://t.me/" + post_id
        posts.append(
            _TgPost(
                url=url[:1024],
                title=title,
                body=body,
                published_at=_parse_dt(tdm.group(1) if tdm else ""),
            )
        )
    return posts


def fetch_channel_posts(
    slug: str,
    *,
    preview_base: str = "https://t.me/s",
    timeout: float = 25.0,
    session: requests.Session | None = None,
) -> list[_TgPost]:
    slug = (slug or "").strip().lstrip("@")
    if not slug:
        return []
    url = f"{preview_base.rstrip('/')}/{slug}"
    sess = session or requests.Session()
    try:
        resp = sess.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("telegram preview fail %s: %s", slug, exc)
        return []
    posts = parse_preview_html(resp.text, slug=slug)
    log.info("telegram preview: %s → %s posts", slug, len(posts))
    return posts


def post_matches_ticker(post: _TgPost, ticker_id: str, search_query: str) -> bool:
    hay = f"{post.title}\n{post.body[:1200]}"
    return title_matches_ticker(hay, ticker_id, search_query)


class TelegramAllowlistSource:
    """Whitelist public TG channels via t.me/s preview (Рубиндей v1)."""

    name = "telegram_allowlist"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        timeout: float = 25.0,
        slugs: list[str] | None = None,
        preview_base: str | None = None,
    ) -> None:
        self._config_path = config_path or _DEFAULT_CONFIG
        self._timeout = timeout
        self._slugs_override = slugs
        self._base_override = preview_base
        self._loaded = False
        self._posts: list[_TgPost] | None = None
        self._session: requests.Session | None = None

    def _cfg(self) -> dict[str, Any]:
        return load_tg_config(self._config_path)

    def _slugs(self) -> list[str]:
        if self._slugs_override is not None:
            return list(self._slugs_override)
        return v1_slugs(self._cfg())

    def _base(self) -> str:
        if self._base_override:
            return self._base_override.rstrip("/")
        return str(self._cfg().get("preview_base") or "https://t.me/s").rstrip("/")

    def _ensure_posts(self) -> list[_TgPost]:
        if self._loaded and self._posts is not None:
            return self._posts
        self._loaded = True
        if self._session is None:
            self._session = requests.Session()
        all_posts: list[_TgPost] = []
        for slug in self._slugs():
            all_posts.extend(
                fetch_channel_posts(
                    slug,
                    preview_base=self._base(),
                    timeout=self._timeout,
                    session=self._session,
                )
            )
        self._posts = all_posts
        return self._posts

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        del kind
        try:
            posts = self._ensure_posts()
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram allowlist load failed: %s", exc)
            return []
        out: list[RawNews] = []
        for post in posts:
            if is_noise_title(post.title):
                continue
            if not post_matches_ticker(post, ticker_id, search_query):
                continue
            out.append(
                RawNews(
                    title=post.title[:512],
                    url=post.url,
                    source=self.name,
                    published_at=post.published_at,
                )
            )
            if len(out) >= 12:
                break
        return out
