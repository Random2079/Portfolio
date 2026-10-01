"""Title denylist + near-dup fingerprints for pre-AI news noise."""

from __future__ import annotations

import unittest

from portfolio_news.sources.google_news_ru import _query_for
from portfolio_news.sources.news_noise import (
    is_geo_macro_keep_title,
    is_near_duplicate_title,
    is_noise_title,
    normalize_title_for_dup,
    remember_title_fingerprint,
    title_fingerprint,
    title_matches_ticker,
)


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
        self.assertFalse(
            is_noise_title("Сбербанк увеличил свободный денежный поток во втором квартале")
        )

    def test_profit_and_tech_analysis(self):
        self.assertTrue(
            is_noise_title("Идея в Профите по SBER: лонг от поддержки - БКС Экспресс")
        )
        self.assertTrue(is_noise_title("Профите по GAZP: тейк у сопротивления"))
        self.assertTrue(
            is_noise_title("Технический анализ акций Яндекс на 30 сентября - Финам")
        )
        self.assertTrue(is_noise_title("#сильный_рост SBER сегодня в моменте"))
        self.assertFalse(
            is_noise_title("Сбербанк утвердил стратегию до 2028 года")
        )

    def test_futures_noise_keeps_bonds(self):
        self.assertTrue(is_noise_title("Фьючерс на индекс МосБиржи: обзор сессии"))
        self.assertTrue(
            is_noise_title("Котировки фьючерса Si-12.25 на вечерней сессии")
        )
        self.assertFalse(
            is_noise_title("Газпром разместил облигации серии 001Р-07")
        )
        self.assertFalse(
            is_noise_title("Оферта по выпуску ВДО Роснано приближается")
        )


class NearDupTests(unittest.TestCase):
    def test_strips_site_tails(self):
        a = normalize_title_for_dup("Сбербанк купил банк - БКС Экспресс")
        b = normalize_title_for_dup("Сбербанк купил банк - Финам")
        c = normalize_title_for_dup("Сбербанк купил банк — Smart-Lab")
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertEqual(title_fingerprint(a), title_fingerprint("Сбербанк купил банк"))

    def test_profit_suffix_normalized(self):
        a = title_fingerprint("Газпром отчитался в Профите")
        b = title_fingerprint("Газпром отчитался")
        self.assertEqual(a, b)

    def test_seen_set(self):
        seen: set[str] = set()
        self.assertFalse(
            is_near_duplicate_title("Сбербанк дивиденды - БКС Экспресс", seen)
        )
        remember_title_fingerprint("Сбербанк дивиденды - БКС Экспресс", seen)
        self.assertTrue(
            is_near_duplicate_title("Сбербанк дивиденды - Финам", seen)
        )
        self.assertFalse(
            is_near_duplicate_title("ЛУКОЙЛ повысил дивиденды - Финам", seen)
        )


class GeoMacroKeepTests(unittest.TestCase):
    def test_geo_title_not_noise(self):
        titles = [
            "Эскалация конфликта: рынки ждут новых санкций",
            "Перемирие на Украине: реакция Мосбиржи",
            "Удар ракеты по инфраструктуре — нефть растёт",
            "НАТО обсуждает помощь Киеву",
            "Мобилизация: что это значит для банковского сектора",
        ]
        for t in titles:
            self.assertTrue(is_geo_macro_keep_title(t), msg=t)
            self.assertFalse(is_noise_title(t), msg=t)

    def test_profit_still_noise_even_with_geo_word(self):
        # Hard spam wins: geo-keep does not rescue Profit / tech spam.
        self.assertTrue(
            is_noise_title("Идея в Профите по SBER: лонг от поддержки после санкций")
        )
        self.assertTrue(
            is_noise_title("Технический анализ акций Газпром: война и уровни - Финам")
        )

    def test_geo_with_sber_attaches(self):
        self.assertTrue(
            title_matches_ticker(
                "Санкции против банков: что будет со Сбербанком",
                "SBER",
                "Сбербанк",
            )
        )
        self.assertFalse(
            is_noise_title("Санкции против банков: что будет со Сбербанком")
        )


class ShortTickerAttachTests(unittest.TestCase):
    def test_short_ticker_needs_issuer_name(self):
        # Bare letter "t" must not attach Trump/macro SmartLab headlines.
        self.assertFalse(
            title_matches_ticker(
                "Trump threatens new tariffs on Europe",
                "T",
                "Т-Технологии",
            )
        )
        self.assertTrue(
            title_matches_ticker(
                "Т-Технологии определит цену допэмиссии",
                "T",
                "Т-Технологии",
            )
        )

    def test_short_t_geopolitics_still_rejected(self):
        # Geo-keep does not weaken short-ticker attach guard.
        self.assertFalse(
            title_matches_ticker(
                "Эскалация войны и новые санкции США",
                "T",
                "Т-Технологии",
            )
        )
        self.assertFalse(
            title_matches_ticker(
                "Trump threatens new tariffs on Europe",
                "T",
                "Т-Технологии",
            )
        )

    def test_long_ticker_substring_ok(self):
        self.assertTrue(
            title_matches_ticker(
                "SBER дивиденды за 2025 год",
                "SBER",
                "Сбербанк",
            )
        )
        self.assertTrue(
            title_matches_ticker(
                "Сбербанк повысил прогноз",
                "SBER",
                "Сбербанк",
            )
        )


class QueryExclusionsTests(unittest.TestCase):
    def test_equity_has_minus(self):
        q = _query_for("YDEX", "Яндекс", "equity")
        self.assertIn("YDEX", q)
        self.assertIn("-ставки", q)
        self.assertIn("-кэф", q)
        self.assertIn("технический анализ", q)


if __name__ == "__main__":
    unittest.main()
