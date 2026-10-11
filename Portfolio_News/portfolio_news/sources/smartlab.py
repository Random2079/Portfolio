from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import requests

from portfolio_news.poll_stats import (
    EMPTY_TITLE_OR_LINK,
    IS_NOISE_TITLE,
    OUTPUT_LIMIT,
    TITLE_MATCHES_TICKER,
    diag_drop,
    diag_error,
    diag_feed_total,
    diag_limit,
    diag_passed,
    diag_raw_seen,
)
from portfolio_news.sources.base import RawNews
from portfolio_news.sources.news_noise import is_noise_title, title_matches_ticker

_HEADERS = {
    "User-Agent": "PortfolioNews/0.1 (+local; personal monitor)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

SMARTLAB_NEWS_RSS = "https://smart-lab.ru/news/rss/"
_SCAN_CAP = 80
_OUT_CAP = 10


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
        except requests.RequestException as exc:
            diag_error("http", str(exc))
            return []
        feed = feedparser.parse(resp.content)
        entries = list(feed.entries)
        diag_feed_total(len(entries))
        tokens = _tokens(ticker_id, search_query)
        if not tokens:
            return []
        out: list[RawNews] = []
        scanned = entries[:_SCAN_CAP]
        for entry in scanned:
            diag_raw_seen(1)
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                diag_drop(EMPTY_TITLE_OR_LINK)
                continue
            if is_noise_title(title):
                diag_drop(IS_NOISE_TITLE)
                continue
            if not title_matches_ticker(title, ticker_id, search_query):
                diag_drop(TITLE_MATCHES_TICKER)
                continue
            if len(out) >= _OUT_CAP:
                diag_drop(OUTPUT_LIMIT)
                continue
            out.append(
                RawNews(
                    title=title[:512],
                    url=link[:1024],
                    source=self.name,
                    published_at=_parse_date(entry),
                )
            )
            diag_passed(1)
        # Cap hit if we filled out and more matching candidates existed, or scan full.
        diag_limit(
            _OUT_CAP,
            hit=len(out) >= _OUT_CAP or len(entries) >= _SCAN_CAP,
        )
        return out
