"""Pulse allowlist v1 — SSR scrape of whitelisted authors via tbank-online mirror.

Fetches profile HTML (Tramvai SSR JSON in ``application/json`` script), extracts
recent posts for nicknames in ``pulse_allowlist.json`` ``v1`` list, then filters
to the ticker under poll (instruments / title / body). Reuses ``news_noise``
denylist; near-dup stays in the poller.

Fragile: mirror HTML / ``seoSsrData.pulseGetProfilePage`` path can change without
notice; failures log and return []. No XHR/social-api (needs session).
"""

from __future__ import annotations

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

_CONFIG_PATH = Path(__file__).with_name("pulse_allowlist.json")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

_TICKER_DOLLAR = re.compile(
    r"(?:\{\$|\$)([A-Za-zА-Яа-я0-9._-]{1,12})\}?",
    re.UNICODE,
)
_STOCK_PATH = re.compile(r"/invest/stocks/[A-Za-z0-9._-]+(?:\?[^)\s]*)?", re.I)
_MD_STOCK_LINK = re.compile(r"\[[^\]]*\]\(/invest/stocks/[^)]+\)", re.I)


@dataclass
class _PulsePost:
    post_id: str
    nickname: str
    title: str
    body: str
    url: str
    published_at: Optional[datetime]
    instrument_tickers: tuple[str, ...]


def load_allowlist_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def v1_nicknames(cfg: dict[str, Any] | None = None) -> list[str]:
    data = cfg if cfg is not None else load_allowlist_config()
    raw = data.get("v1") or []
    out: list[str] = []
    for nick in raw:
        n = str(nick).strip()
        if n and n not in out:
            out.append(n)
    return out


def mirror_base(cfg: dict[str, Any] | None = None) -> str:
    data = cfg if cfg is not None else load_allowlist_config()
    base = str(data.get("mirror_base") or "https://www.tbank-online.com").rstrip("/")
    return base


def profile_url(nickname: str, base: str | None = None) -> str:
    b = (base or mirror_base()).rstrip("/")
    nick = nickname.strip().lstrip("/")
    return f"{b}/invest/social/profile/{nick}/"


def post_url(nickname: str, post_id: str, base: str | None = None) -> str:
    b = (base or mirror_base()).rstrip("/")
    nick = nickname.strip().lstrip("/")
    pid = post_id.strip().strip("/")
    return f"{b}/invest/social/profile/{nick}/{pid}/"


def _parse_published(raw: Any) -> Optional[datetime]:
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


def _title_from_content(content: dict[str, Any]) -> tuple[str, str]:
    """Return (title, body). Article → title; simple → first body line as title."""
    if not isinstance(content, dict):
        return "", ""
    disc = (content.get("discriminator") or "").strip().lower()
    if disc == "article":
        title = str(content.get("title") or "").strip()
        return title, title
    body = str(content.get("body") or content.get("text") or "").strip()
    if not body:
        title = str(content.get("title") or "").strip()
        return title, title
    first = ""
    for line in body.splitlines():
        line = line.strip()
        if line:
            first = line
            break
    if not first:
        first = body[:200].strip()
    return first, body


def _instrument_tickers(post: dict[str, Any]) -> tuple[str, ...]:
    ext = post.get("extension") or {}
    if not isinstance(ext, dict):
        return ()
    items = ((ext.get("instrument") or {}).get("items")) if isinstance(ext.get("instrument"), dict) else None
    if not items:
        return ()
    out: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        tid = str(it.get("ticker") or "").strip().upper()
        if tid and tid not in out:
            out.append(tid)
    return tuple(out)


def extract_posts_from_ssr_json(
    data: dict[str, Any],
    *,
    nickname: str,
    base: str,
) -> list[_PulsePost]:
    """Parse Tramvai stores JSON → posts. Empty if shape changed."""
    try:
        items = (
            data["stores"]["seoSsrData"]["pulseGetProfilePage"]["feed"]["data"]["items"]
        )
    except (KeyError, TypeError):
        log.warning("pulse SSR: missing pulseGetProfilePage.feed for %s", nickname)
        return []
    if not isinstance(items, list):
        return []

    owner_nick = nickname
    out: list[_PulsePost] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        disc = (raw.get("discriminator") or "").strip().lower()
        if disc and disc != "post":
            continue
        post_id = str(raw.get("id") or "").strip()
        if not post_id:
            continue
        owner = raw.get("owner") or {}
        if isinstance(owner, dict) and owner.get("nickname"):
            owner_nick = str(owner["nickname"]).strip() or nickname
        content = raw.get("content") if isinstance(raw.get("content"), dict) else {}
        title, body = _title_from_content(content or {})
        if not title:
            continue
        out.append(
            _PulsePost(
                post_id=post_id,
                nickname=owner_nick,
                title=title[:512],
                body=body or "",
                url=post_url(owner_nick, post_id, base=base)[:1024],
                published_at=_parse_published(raw.get("publishedAt")),
                instrument_tickers=_instrument_tickers(raw),
            )
        )
    return out


def parse_profile_html(html: str, *, nickname: str, base: str) -> list[_PulsePost]:
    """Extract posts from profile SSR HTML.

    Prefer ``#__TRAMVAI_STATE__``; else any ``application/json`` blob that contains
    ``pulseGetProfilePage`` (pages ship several JSON scripts).
    """
    candidates: list[str] = []
    m = re.search(
        r'<script[^>]*id=["\']__TRAMVAI_STATE__["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    )
    if m:
        candidates.append(m.group(1))
    for m in re.finditer(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        blob = m.group(1)
        if blob not in candidates:
            candidates.append(blob)
    if not candidates:
        log.warning("pulse SSR: no JSON script for %s", nickname)
        return []

    last_err: Exception | None = None
    for blob in candidates:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
        if not isinstance(data, dict):
            continue
        posts = extract_posts_from_ssr_json(data, nickname=nickname, base=base)
        if posts:
            return posts
        # Valid JSON but wrong store shape — keep trying other scripts.
        stores = data.get("stores") if isinstance(data.get("stores"), dict) else None
        if stores and "seoSsrData" in stores:
            return posts  # shape known empty feed
    if last_err:
        log.warning("pulse SSR: JSON parse failed for %s: %s", nickname, last_err)
    else:
        log.warning("pulse SSR: no pulseGetProfilePage feed for %s", nickname)
    return []


def fetch_profile_posts(
    nickname: str,
    *,
    base: str | None = None,
    timeout: float = 35.0,
    session: requests.Session | None = None,
) -> list[_PulsePost]:
    b = base or mirror_base()
    url = profile_url(nickname, base=b)
    sess = session or requests
    try:
        resp = sess.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException as exc:
        log.warning("pulse profile fetch failed %s: %s", nickname, exc)
        return []
    return parse_profile_html(resp.text, nickname=nickname, base=b)


def _strip_ticker_chips(text: str) -> str:
    """Remove ``$TICKER`` chips and Pulse stock deep-links from prose."""
    t = text or ""
    t = _MD_STOCK_LINK.sub(" ", t)
    t = _STOCK_PATH.sub(" ", t)
    t = _TICKER_DOLLAR.sub(" ", t)
    return t


def _mentions_ticker_in_text(text: str, ticker_id: str) -> bool:
    hay = text or ""
    tid = (ticker_id or "").strip().upper()
    if not tid or not hay:
        return False
    for m in _TICKER_DOLLAR.finditer(hay):
        if m.group(1).upper() == tid:
            return True
    # whole-token match (avoid short false positives via title_matches_ticker for ≤2)
    if len(tid) <= 2:
        return bool(re.search(rf"(?<!\w){re.escape(tid)}(?!\w)", hay, re.I))
    return tid.lower() in hay.lower()


def post_matches_ticker(
    post: _PulsePost,
    ticker_id: str,
    search_query: str = "",
) -> bool:
    """Scope filter: name/ticker in title|body, or focused instrument tags.

    Advokat often embeds ``$SBER`` chips for every tagged instrument in title/body —
    those chips alone must not attach the post to each holdings ticker. Match on
    chip-stripped prose (issuer name / bare ticker outside chips) or ≤2 instruments.
    """
    tid = (ticker_id or "").strip().upper()
    if not tid:
        return False
    title_prose = _strip_ticker_chips(post.title or "")
    body_prose = _strip_ticker_chips(post.body or "")[:800]
    if title_matches_ticker(title_prose, tid, search_query):
        return True
    if title_matches_ticker(body_prose, tid, search_query):
        return True
    inst = {t.upper() for t in post.instrument_tickers}
    if tid in inst and len(inst) <= 2:
        return True
    return False


class PulseAllowlistSource:
    """NewsSource: allowlisted Pulse authors via SSR mirror (v1 nicknames only)."""

    name = "pulse_allowlist"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        nicknames: list[str] | None = None,
        base: str | None = None,
        timeout: float = 35.0,
    ) -> None:
        self._config_path = config_path
        self._nicknames_override = nicknames
        self._base_override = base
        self._timeout = timeout
        self._posts: list[_PulsePost] | None = None
        self._loaded = False

    def _cfg(self) -> dict[str, Any]:
        return load_allowlist_config(self._config_path)

    def _nicknames(self) -> list[str]:
        if self._nicknames_override is not None:
            return list(self._nicknames_override)
        return v1_nicknames(self._cfg())

    def _base(self) -> str:
        if self._base_override:
            return self._base_override.rstrip("/")
        return mirror_base(self._cfg())

    def _ensure_posts(self) -> list[_PulsePost]:
        if self._loaded and self._posts is not None:
            return self._posts
        self._loaded = True
        base = self._base()
        nicks = self._nicknames()
        if not nicks:
            log.info("pulse allowlist: empty v1 list")
            self._posts = []
            return self._posts
        # Drop is already excluded by reading only v1 (Investokrat stays in maybe).
        sess = requests.Session()
        all_posts: list[_PulsePost] = []
        for nick in nicks:
            posts = fetch_profile_posts(
                nick, base=base, timeout=self._timeout, session=sess
            )
            log.info("pulse allowlist: %s → %s posts", nick, len(posts))
            all_posts.extend(posts)
        self._posts = all_posts
        return self._posts

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        del kind  # same filter for equity/bond/fund; ISIN may appear in instruments
        try:
            posts = self._ensure_posts()
        except Exception as exc:  # noqa: BLE001
            log.warning("pulse allowlist load failed: %s", exc)
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
                    url=post.url[:1024],
                    source=self.name,
                    published_at=post.published_at,
                )
            )
            if len(out) >= 10:
                break
        return out
