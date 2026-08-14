from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import requests

from portfolio_news.sources.base import RawNews

_HEADERS = {
    "User-Agent": "PortfolioNews/0.1 (+local; personal monitor)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

SMARTLAB_NEWS_RSS = "https://smart-lab.ru/news/rss/"


def _parse_date(entry) -> Optional[datetime]:
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None


def _tokens(ticker_id: str, search_query: str) -> list[str]:
    toks = []
    for part in (ticker_id, search_query):
        if not part:
            continue
        toks.append(part.lower())
        for w in part.replace(",", " ").split():
            w = w.strip().lower()
            if len(w) >= 3 and w not in toks:
                toks.append(w)
    # drop pure ISIN from required match set for bonds — keep name tokens
    return [t for t in toks if not (t.startswith("ru000") and len(t) > 8)]


class SmartLabRssSource:
    """Smart-Lab news RSS filtered by ticker / name tokens."""

    name = "smartlab"

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        try:
            resp = requests.get(SMARTLAB_NEWS_RSS, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            return []
        feed = feedparser.parse(resp.content)
        tokens = _tokens(ticker_id, search_query)
        if not tokens:
            return []
        out: list[RawNews] = []
        for entry in feed.entries[:80]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            hay = title.lower()
            if not any(tok in hay for tok in tokens):
                continue
            out.append(
                RawNews(
                    title=title[:512],
                    url=link[:1024],
                    source=self.name,
                    published_at=_parse_date(entry),
                )
            )
            if len(out) >= 10:
                break
        return out
