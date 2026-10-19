import unittest

from hh_auto.apply import page_looks_like_captcha
from hh_auto.cover import render_cover
from hh_auto.limits import can_apply, record_apply, refresh_day
from hh_auto.score import keywords_table, rank_vacancies, score_vacancy
from hh_auto import playwright_headless
from hh_auto.stats import load_report
from hh_auto.tg_scan import _looks_relevant, _parse_posts, posts_to_vacancies
from hh_auto.ui import _ui_opts
from hh_auto.kwork_ai import scrub_cover
from hh_auto.kwork_search import filter_projects, keyword_hits
from hh_auto.kwork_usage import estimate_usd, summarize_usage
from hh_auto.yj_resolve import clean_yj_url, extract_hh_urls, extract_yj_urls


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


class TestHeadless(unittest.TestCase):
    def test_default_true(self):
        self.assertTrue(playwright_headless({}))
        self.assertTrue(playwright_headless({"playwright": {}}))
        self.assertFalse(playwright_headless({"playwright": {"headless": False}}))
        self.assertTrue(playwright_headless({"playwright": {"headless": True}}))


class TestTgScan(unittest.TestCase):
    def test_reject_course_keep_python_junior(self):
        self.assertFalse(_looks_relevant("Курс нейросети промокод КАМПУС"))
        self.assertTrue(
            _looks_relevant("#junior #удаленка Python Developer опыт 1–3 года FastAPI")
        )
        self.assertFalse(_looks_relevant("#senior Python от 6 лет Kafka"))

    def test_parse_and_vacancy(self):
        html = """
        <div data-post="job_python/1" class="tgme_widget_message">
          <time datetime="2026-10-19T12:00:00+00:00"></time>
          <div class="tgme_widget_message_text js-message_text">
            #junior #удаленка IBS Инженер Python опыт 1–3 года FastAPI Git
          </div>
        </div>
        """
        posts = _parse_posts(html, "job_python")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["url"], "https://t.me/job_python/1")
        vacs = posts_to_vacancies(posts)
        self.assertEqual(len(vacs), 1)
        self.assertEqual(vacs[0]["level_guess"], "juniorish")
        self.assertTrue(vacs[0]["remote"])


class TestYjResolve(unittest.TestCase):
    def test_extract_and_clean(self):
        html = (
            'href="https://youngjunior.ru/python/jobs/69397?utm_source=telegram&amp;amp;utm_medium=junejob" '
            'href="https://youngjunior.ru/design/jobs/1" '
            "https://hh.ru/vacancy/138296473"
        )
        yj = extract_yj_urls(html)
        self.assertIn("https://youngjunior.ru/python/jobs/69397", yj)
        self.assertTrue(all("/design/" not in u for u in yj))
        self.assertEqual(
            clean_yj_url(
                "https://youngjunior.ru/python/jobs/1?utm_source=telegram&amp;utm_medium=x"
            ),
            "https://youngjunior.ru/python/jobs/1",
        )
        self.assertEqual(extract_hh_urls(html), ["https://hh.ru/vacancy/138296473"])


class TestKworkFilter(unittest.TestCase):
    def test_keyword_hits(self):
        hits = keyword_hits("Нужен Python бот и парсинг", ["python", "бот", "java"])
        self.assertIn("python", hits)
        self.assertIn("бот", hits)
        self.assertNotIn("java", hits)

    def test_filter_min_score(self):
        projects = [
            {"title": "Логотип", "description": "дизайн"},
            {"title": "Парсер", "description": "Python playwright автоматизация"},
        ]
        got = filter_projects(
            projects,
            ["python", "playwright", "бот", "парс", "автоматиз"],
            min_score=1,
        )
        self.assertEqual(len(got), 1)
        self.assertIn("Парсер", got[0]["title"])


class TestKworkAiScrub(unittest.TestCase):
    def test_strip_markdown_and_ai(self):
        raw = "```markdown\n**Привет** я ИИ помощник\n```"
        out = scrub_cover(raw)
        self.assertNotIn("**", out)
        self.assertNotIn("```", out)


class TestKworkUsage(unittest.TestCase):
    def test_estimate_and_summarize_empty(self):
        usd = estimate_usd({"prompt_tokens": 1000, "completion_tokens": 500})
        self.assertGreater(usd, 0)
        s = summarize_usage()
        self.assertIn("today_tokens", s)
        self.assertIn("month_tokens", s)


if __name__ == "__main__":
    unittest.main()
