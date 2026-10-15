import unittest

from hh_auto.apply import page_looks_like_captcha
from hh_auto.cover import render_cover
from hh_auto.limits import can_apply, record_apply, refresh_day
from hh_auto.score import keywords_table, rank_vacancies, score_vacancy
from hh_auto.stats import load_report
from hh_auto.ui import _ui_opts


class TestCaptcha(unittest.TestCase):
    def test_detect(self):
        self.assertTrue(page_looks_like_captcha("", "https://hh.ru/showcaptcha"))
        self.assertTrue(page_looks_like_captcha("Я не робот", "https://hh.ru/vacancy/1"))
        self.assertFalse(page_looks_like_captcha("Откликнуться на вакансию Python", "https://hh.ru/vacancy/1"))
        self.assertFalse(page_looks_like_captcha("var captcha = null; vacancy list", "https://hh.ru/search/vacancy"))


class TestScore(unittest.TestCase):
    def test_hits_python_fastapi(self):
        v = {
            "title": "Junior Python",
            "requirement": "FastAPI, Git",
            "responsibility": "REST API",
        }
        sc, hits = score_vacancy(v, ["Python", "FastAPI", "Docker"])
        self.assertGreaterEqual(sc, 2)
        self.assertIn("Python", hits)
        self.assertIn("FastAPI", hits)

    def test_min_score_filters(self):
        vacancies = [
            {"title": "Java junior", "requirement": "", "responsibility": ""},
            {"title": "Python dev", "requirement": "SQLite", "responsibility": "парсинг"},
        ]
        ranked = rank_vacancies(vacancies, ["Python", "SQLite", "парсинг"], min_score=2)
        self.assertEqual(len(ranked), 1)
        self.assertIn("Python", ranked[0]["title"])

    def test_keywords_freq(self):
        vacancies = [
            {"title": "Python", "requirement": "Git", "responsibility": ""},
            {"title": "Python FastAPI", "requirement": "", "responsibility": ""},
        ]
        rows = keywords_table(vacancies, ["Python", "FastAPI", "Rust"])
        d = {t: n for t, _, n in rows}
        self.assertEqual(d.get("Python"), 2)
        self.assertEqual(d.get("FastAPI"), 1)
        self.assertNotIn("Rust", d)


class TestCover(unittest.TestCase):
    def test_with_company(self):
        text = render_cover("Отклик на «{title}» ({company}).", {"title": "Python", "company": "ООО Рога"})
        self.assertIn("Python", text)
        self.assertIn("ООО Рога", text)

    def test_empty_company(self):
        text = render_cover("Отклик на «{title}» ({company}).", {"title": "Python", "company": ""})
        self.assertNotIn("()", text)
        self.assertIn("Python", text)


class TestLimits(unittest.TestCase):
    def test_daily_limit(self):
        state = {"date": "2099-01-01", "applied_ids": [], "count": 40}
        state = refresh_day(state, "UTC")
        # если сегодня не 2099 — refresh обнулит; добьём лимит вручную
        state = {"date": state["date"], "applied_ids": [f"id{i}" for i in range(40)], "count": 40}
        ok, reason = can_apply(state, "id99", 40, "UTC")
        self.assertFalse(ok)
        self.assertEqual(reason, "daily_limit")

    def test_already_applied(self):
        state = {"date": "", "applied_ids": [], "count": 0}
        state = refresh_day(state, "UTC")
        state = record_apply(state, "x1", "UTC")
        ok, reason = can_apply(state, "x1", 40, "UTC")
        self.assertFalse(ok)
        self.assertEqual(reason, "already_applied")


class TestStats(unittest.TestCase):
    def test_report_shape(self):
        report = load_report({"daily_limit": 40, "timezone": "Asia/Yekaterinburg"})
        self.assertIn("sent_today", report)
        self.assertIn("remaining", report)
        self.assertEqual(report["daily_limit"], 40)
        self.assertGreaterEqual(report["remaining"], 0)


class TestUiOpts(unittest.TestCase):
    def test_defaults_and_clamp(self):
        opts = _ui_opts({})
        self.assertEqual(opts["appearance_mode"], "dark")
        self.assertEqual(opts["color_theme"], "dark-blue")
        bad = _ui_opts({"ui": {"appearance_mode": "neon", "color_theme": "pink", "font_size": 99}})
        self.assertEqual(bad["appearance_mode"], "dark")
        self.assertEqual(bad["color_theme"], "dark-blue")
        self.assertEqual(bad["font_size"], 22)


if __name__ == "__main__":
    unittest.main()
