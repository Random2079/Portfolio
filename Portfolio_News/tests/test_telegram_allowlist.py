"""Offline tests for public Telegram preview parser."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from portfolio_news.sources.telegram_allowlist import (
    TelegramAllowlistSource,
    parse_preview_html,
    post_matches_ticker,
    v1_slugs,
)

_FIXTURE = """
<html><body>
<div class="tgme_widget_message js-widget_message" data-post="rubinday50/100">
  <div class="tgme_widget_message_bubble">
    <div class="tgme_widget_message_text js-message_text">Сбербанк отчитался о прибыли за квартал<br>ещё вода</div>
    <time datetime="2026-10-03T10:00:00+00:00"></time>
  </div>
</div>
<div class="tgme_widget_message js-widget_message" data-post="rubinday50/101">
  <div class="tgme_widget_message_bubble">
    <div class="tgme_widget_message_text js-message_text">Макро без бумаги: ЦБ оставил ставку</div>
    <time datetime="2026-10-03T11:00:00+00:00"></time>
  </div>
</div>
</body></html>
"""


class ParsePreviewTests(unittest.TestCase):
    def test_parse_two_posts(self):
        posts = parse_preview_html(_FIXTURE, slug="rubinday50")
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0].url, "https://t.me/rubinday50/100")
        self.assertIn("Сбербанк", posts[0].title)

    def test_match_sber_not_macro(self):
        posts = parse_preview_html(_FIXTURE, slug="rubinday50")
        sber, macro = posts
        self.assertTrue(post_matches_ticker(sber, "SBER", "Сбербанк"))
        self.assertFalse(post_matches_ticker(macro, "SBER", "Сбербанк"))

    def test_v1_has_rubinday(self):
        self.assertIn("rubinday50", v1_slugs())


class SourceFetchTests(unittest.TestCase):
    def test_fetch_uses_cache_and_filters(self):
        src = TelegramAllowlistSource(slugs=["rubinday50"], preview_base="https://t.me/s")
        fake = MagicMock()
        resp = MagicMock()
        resp.text = _FIXTURE
        resp.raise_for_status = MagicMock()
        fake.get.return_value = resp
        src._session = fake
        rows = src.fetch("SBER", "Сбербанк", "equity")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source, "telegram_allowlist")
        self.assertEqual(fake.get.call_count, 1)
        rows2 = src.fetch("SBER", "Сбербанк", "equity")
        self.assertEqual(fake.get.call_count, 1)
        self.assertEqual(len(rows2), 1)


if __name__ == "__main__":
    unittest.main()
