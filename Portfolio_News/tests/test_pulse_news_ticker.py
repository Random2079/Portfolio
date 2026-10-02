"""Offline tests for Pulse news-by-ticker SSR parser + filters."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from portfolio_news.sources.pulse_news_ticker import (
    PulseNewsTickerSource,
    extract_news_items_from_html,
    item_kept,
    news_page_url,
)


def _item(
    *,
    post_id: str,
    title: str,
    tickers: list[str],
    nickname: str = "T-Investments",
    inserted: str = "2026-10-01T06:40:08.530Z",
) -> dict:
    return {
        "id": post_id,
        "inserted": inserted,
        "status": "published",
        "serviceTags": [{"id": "news-article"}],
        "owner": {"nickname": nickname},
        "content": {
            "type": "news",
            "title": title,
            "announce": title,
            "instruments": [
                {"type": "share", "ticker": t} for t in tickers
            ],
        },
    }


def _child_html(ticker: str, items: list[dict]) -> str:
    payload = {
        "pulse-news-by-ticker@0.41.0": {
            "stores": {
                "investSocialNewsByTicker": {
                    ticker: {"nextCursor": "1", "hasNext": False, "items": items}
                }
            }
        }
    }
    blob = json.dumps(payload, ensure_ascii=False)
    return (
        "<html><body>"
        '<script type="application/json">{"noise":true}</script>'
        f'<script type="application/json">{blob}</script>'
        "</body></html>"
    )


class ParseNewsTickerTests(unittest.TestCase):
    def test_extract_items(self):
        html = _child_html(
            "X5",
            [_item(post_id="aaa", title="Затраты Х5 на логистику выросли", tickers=["X5"])],
        )
        items = extract_news_items_from_html(html, "X5")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "aaa")

    def test_missing_store_empty(self):
        html = '<script type="application/json">{"stores":{}}</script>'
        self.assertEqual(extract_news_items_from_html(html, "X5"), [])

    def test_item_kept_basic(self):
        it = _item(post_id="a", title="Северсталь купила металлоцентр", tickers=["CHMF"])
        self.assertTrue(item_kept(it, "CHMF", "Северсталь", drop_nicks=set()))

    def test_drop_nickname(self):
        it = _item(
            post_id="a",
            title="Какие компании сократили сотрудников",
            tickers=["SBER"],
            nickname="T-Journal",
        )
        self.assertFalse(item_kept(it, "SBER", "Сбербанк", drop_nicks={"T-Journal"}))

    def test_drop_target_title(self):
        it = _item(
            post_id="a",
            title="Аналитики повысили целевую цену по X5",
            tickers=["X5"],
        )
        self.assertFalse(item_kept(it, "X5", "X5", drop_nicks=set()))

    def test_broad_digest_needs_prose(self):
        it = _item(
            post_id="a",
            title="Дайджест рынка акций без имён",
            tickers=["TRNFP", "SBER", "GAZP", "LKOH", "X5"],
        )
        self.assertFalse(item_kept(it, "TRNFP", "Транснефть", drop_nicks=set()))
        it2 = _item(
            post_id="b",
            title="Транснефть и шельф: что предложило Минприроды",
            tickers=["TRNFP", "SBER", "GAZP", "LKOH", "X5"],
        )
        self.assertTrue(item_kept(it2, "TRNFP", "Транснефть", drop_nicks=set()))


class PulseNewsTickerSourceTests(unittest.TestCase):
    def test_news_page_url(self):
        self.assertEqual(
            news_page_url("x5", base="https://www.tbank-online.com"),
            "https://www.tbank-online.com/invest/stocks/X5/news/",
        )

    def test_fetch_equity_only_and_cache(self):
        html = _child_html(
            "X5",
            [
                _item(
                    post_id="p1",
                    title="Затраты Х5 на логистику выросли",
                    tickers=["X5"],
                ),
                _item(
                    post_id="p2",
                    title="Аналитики повысили целевую цену по X5",
                    tickers=["X5"],
                ),
                _item(
                    post_id="p3",
                    title="Шум от T-Journal",
                    tickers=["X5"],
                    nickname="T-Journal",
                ),
            ],
        )
        call_count = {"n": 0}

        def fake_get(url, **_kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.text = html
            resp.apparent_encoding = "utf-8"
            return resp

        src = PulseNewsTickerSource(
            base="https://www.tbank-online.com",
            drop_nicks={"T-Journal", "Pulse_Official"},
        )
        with patch(
            "portfolio_news.sources.pulse_news_ticker.requests.Session"
        ) as Sess:
            sess = MagicMock()
            sess.get.side_effect = fake_get
            Sess.return_value = sess

            bond = src.fetch("X5", "X5", "bond")
            self.assertEqual(bond, [])
            self.assertEqual(call_count["n"], 0)

            rows = src.fetch("X5", "X5", "equity")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].source, "pulse_news_ticker")
            self.assertIn("логистику", rows[0].title)
            self.assertIn("/T-Investments/p1/", rows[0].url)

            # Second poll tick for same ticker → cached HTML parse, no new GET.
            rows2 = src.fetch("X5", "X5", "equity")
            self.assertEqual(len(rows2), 1)
            self.assertEqual(call_count["n"], 1)


if __name__ == "__main__":
    unittest.main()
