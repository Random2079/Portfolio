"""Title denylist for sports/betting junk."""

from __future__ import annotations

import unittest

from portfolio_news.sources.google_news_ru import _query_for
from portfolio_news.sources.news_noise import is_noise_title


class NoiseTitleTests(unittest.TestCase):
    def test_yandex_esports_bet(self):
        t = "Team Yandex — MOUZ: прогноз (кэф 3.6) 19 сентября 2026 - Ставка ТВ"
        self.assertTrue(is_noise_title(t))

    def test_real_yandex_ok(self):
        self.assertFalse(
            is_noise_title("Яндекс отчитался о росте выручки во втором квартале")
        )

    def test_sber_ok(self):
        self.assertFalse(is_noise_title("Сбербанк повысил прогноз по ключевой ставке ЦБ"))

    def test_cb_rate_ok(self):
        self.assertFalse(is_noise_title("ЦБ сохранил ключевую ставку на уровне 16%"))

    def test_empty(self):
        self.assertTrue(is_noise_title(""))
        self.assertTrue(is_noise_title("   "))

    def test_forum_and_quote_pages(self):
        self.assertTrue(
            is_noise_title("Форум акции Яндекс (YDEX), страница 681 - Smart-Lab")
        )
        self.assertTrue(
            is_noise_title(
                "Акции Яндекс (YDEX) - курс на сегодня, цена и котировки онлайн - Финансы Mail"
            )
        )
        self.assertTrue(
            is_noise_title("Татнефть (TATN) капитализация МСФО - Smart-Lab")
        )
        self.assertTrue(
            is_noise_title(
                "Татнефть (TATN) свободный денежный поток, FCF МСФО (годовые значения)"
            )
        )
        self.assertFalse(
            is_noise_title("СД Т-Технологии 30 сентября определит цену размещения допэмиссии")
        )


class QueryExclusionsTests(unittest.TestCase):
    def test_equity_has_minus(self):
        q = _query_for("YDEX", "Яндекс", "equity")
        self.assertIn("YDEX", q)
        self.assertIn("-ставки", q)
        self.assertIn("-кэф", q)


if __name__ == "__main__":
    unittest.main()
