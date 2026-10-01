"""Offline tests for Pulse allowlist SSR parser + ticker filter."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from portfolio_news.sources.pulse_allowlist import (
    PulseAllowlistSource,
    extract_posts_from_ssr_json,
    parse_profile_html,
    post_matches_ticker,
    v1_nicknames,
)


def _state(items: list[dict], nickname: str = "Interfax") -> dict:
    return {
        "stores": {
            "seoSsrData": {
                "pulseGetProfilePage": {
                    "profile": {"data": {"nickname": nickname}},
                    "feed": {"data": {"items": items, "hasNext": False}},
                }
            }
        }
    }


def _html_with_state(items: list[dict], nickname: str = "Interfax") -> str:
    blob = json.dumps(_state(items, nickname), ensure_ascii=False)
    return (
        "<html><body>"
        '<script type="application/json">{"noise":true}</script>'
        f'<script id="__TRAMVAI_STATE__" type="application/json">{blob}</script>'
        "</body></html>"
    )


def _article(post_id: str, title: str, nickname: str = "Interfax") -> dict:
    return {
        "discriminator": "post",
        "id": post_id,
        "publishedAt": "2026-10-01T06:50:56.086Z",
        "owner": {"nickname": nickname},
        "content": {"discriminator": "article", "title": title},
        "extension": {"instrument": {"items": []}},
    }


def _simple(
    post_id: str,
    body: str,
    tickers: list[str],
    nickname: str = "Advokat_Manasyan",
) -> dict:
    return {
        "discriminator": "post",
        "id": post_id,
        "publishedAt": "2026-09-30T12:00:00.000Z",
        "owner": {"nickname": nickname},
        "content": {"discriminator": "simple", "body": body},
        "extension": {
            "instrument": {
                "items": [{"ticker": t, "discriminator": "share"} for t in tickers]
            }
        },
    }


class ParseTramvaiTests(unittest.TestCase):
    def test_extract_article(self):
        posts = extract_posts_from_ssr_json(
            _state([_article("aaa", "Сбербанк отчитался о прибыли за квартал")]),
            nickname="Interfax",
            base="https://www.tbank-online.com",
        )
        self.assertEqual(len(posts), 1)
        self.assertIn("Сбербанк", posts[0].title)
        self.assertIn("/Interfax/aaa/", posts[0].url)
        self.assertIsNotNone(posts[0].published_at)

    def test_html_prefers_tramvai_id(self):
        html = _html_with_state(
            [_article("aaa", "Газпром объявил дивиденды")],
        )
        posts = parse_profile_html(
            html, nickname="Interfax", base="https://www.tbank-online.com"
        )
        self.assertEqual(len(posts), 1)
        self.assertIn("Газпром", posts[0].title)

    def test_missing_shape_empty(self):
        posts = extract_posts_from_ssr_json(
            {"stores": {}},
            nickname="Interfax",
            base="https://www.tbank-online.com",
        )
        self.assertEqual(posts, [])

    def test_multi_instrument_needs_text(self):
        posts = extract_posts_from_ssr_json(
            _state(
                [
                    _simple(
                        "bbb",
                        "Общий обзор без бумаги",
                        ["SBER", "GAZP", "LKOH", "MTSS"],
                    )
                ],
                nickname="Advokat_Manasyan",
            ),
            nickname="Advokat_Manasyan",
            base="https://www.tbank-online.com",
        )
        self.assertEqual(len(posts), 1)
        self.assertFalse(post_matches_ticker(posts[0], "SBER", "Сбербанк"))

        posts2 = extract_posts_from_ssr_json(
            _state(
                [
                    _simple(
                        "ccc",
                        "Как оспорить решение по [$SBER](/invest/stocks/SBER)",
                        ["SBER", "GAZP", "LKOH", "MTSS"],
                    )
                ],
                nickname="Advokat_Manasyan",
            ),
            nickname="Advokat_Manasyan",
            base="https://www.tbank-online.com",
        )
        self.assertTrue(post_matches_ticker(posts2[0], "SBER", "Сбербанк"))


class PulseAllowlistSourceTests(unittest.TestCase):
    def test_v1_excludes_investokrat(self):
        cfg = {
            "v1": ["Interfax", "Advokat_Manasyan"],
            "maybe": ["Investokrat"],
        }
        self.assertEqual(v1_nicknames(cfg), ["Interfax", "Advokat_Manasyan"])

    def test_fetch_filters_and_caches(self):
        interfax_html = _html_with_state(
            [
                _article("p1", "Сбербанк повысил дивиденды"),
                _article("p2", "Японский индекс обновил максимум"),
            ]
        )
        advokat_html = _html_with_state(
            [
                _simple(
                    "p3",
                    "Оспаривание решения собрания про [$GAZP](/x)",
                    ["GAZP"],
                )
            ],
            nickname="Advokat_Manasyan",
        )

        cfg = {
            "mirror_base": "https://www.tbank-online.com",
            "v1": ["Interfax", "Advokat_Manasyan"],
            "maybe": ["Investokrat"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pulse_allowlist.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")

            responses = {
                "https://www.tbank-online.com/invest/social/profile/Interfax/": interfax_html,
                "https://www.tbank-online.com/invest/social/profile/Advokat_Manasyan/": advokat_html,
            }
            call_count = {"n": 0}

            def fake_get(url, **_kwargs):
                call_count["n"] += 1
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.text = responses[url]
                resp.apparent_encoding = "utf-8"
                return resp

            src = PulseAllowlistSource(config_path=path)
            with patch("portfolio_news.sources.pulse_allowlist.requests.Session") as Sess:
                sess = MagicMock()
                sess.get.side_effect = fake_get
                Sess.return_value = sess

                sber = src.fetch("SBER", "Сбербанк", "equity")
                self.assertEqual(len(sber), 1)
                self.assertEqual(sber[0].source, "pulse_allowlist")
                self.assertIn("Сбербанк", sber[0].title)

                gazp = src.fetch("GAZP", "Газпром", "equity")
                self.assertEqual(len(gazp), 1)
                self.assertIn("Оспаривание", gazp[0].title)

                # One Session; two profile GETs cached for the poll instance.
                self.assertEqual(call_count["n"], 2)
                called_urls = [c.args[0] for c in sess.get.call_args_list]
                self.assertTrue(all("Investokrat" not in u for u in called_urls))


if __name__ == "__main__":
    unittest.main()
