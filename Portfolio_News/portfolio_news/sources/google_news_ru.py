from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests

from portfolio_news.sources.base import RawNews

_HEADERS = {
    "User-Agent": "PortfolioNews/0.1 (+local; personal monitor)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _parse_date(entry) -> Optional[datetime]:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            return parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            continue
    return None


def _query_for(ticker_id: str, search_query: str, kind: str) -> str:
    q = (search_query or ticker_id).strip()
    if kind == "bond":
        # ISIN alone rarely appears in headlines; use human name / issuer fragment
        if q.upper().startswith("RU000"):
            q = ticker_id if not ticker_id.startswith("RU000") else q
        # drop series noise lightly
        for noise in ("БО-", "001Р", "002P", "002Р", "003P", "ООО", "АО"):
            pass
    # Prefer short MOEX ticker in query when equity
    if kind == "equity" and ticker_id and not ticker_id.startswith("RU000"):
        if ticker_id.upper() not in q.upper():
            q = f"{ticker_id} {q}"
    return q.strip() or ticker_id


class GoogleNewsRuSource:
    """RU Google News RSS search — stable free feed, good for MOEX names."""

    name = "google_news_ru"

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        q = _query_for(ticker_id, search_query, kind)
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(q)}&hl=ru&gl=RU&ceid=RU:ru"
        )
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            return []
        feed = feedparser.parse(resp.content)
        out: list[RawNews] = []
        for entry in feed.entries[:15]:
            link = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not link or not title:
                continue
            out.append(
                RawNews(
                    title=title[:512],
                    url=link[:1024],
                    source=self.name,
                    published_at=_parse_date(entry),
                )
            )
        return out
