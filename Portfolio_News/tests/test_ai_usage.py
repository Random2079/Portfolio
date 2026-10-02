"""DeepSeek usage meter: JSONL log + day/month totals."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from portfolio_news.ai_usage import estimate_usd, record_usage, summarize_usage

_TZ = timezone(timedelta(hours=5))


class AiUsageTests(unittest.TestCase):
    def test_estimate_splits_cache_hit(self):
        usd = estimate_usd(
            {
                "prompt_tokens": 1_000_000,
                "prompt_cache_hit_tokens": 1_000_000,
                "completion_tokens": 0,
            }
        )
        self.assertAlmostEqual(usd, 0.028, places=6)

    def test_record_and_summarize_today_vs_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            record_usage(
                "news_classify",
                {"prompt_tokens": 1000, "completion_tokens": 200},
                path=path,
            )
            record_usage(None, None, path=path)  # ignored, must not raise
            now = datetime.now(_TZ)
            earlier = (now.replace(day=1) if now.day > 1 else now).strftime("%Y-%m-%d")
            with path.open("a", encoding="utf-8") as fh:
                fh.write(
                    '{"ts": "%sT00:00:01+05:00", "prompt_tokens": 10, '
                    '"completion_tokens": 0, "usd_est": 0.5}\n' % earlier
                )
                fh.write("not json\n")
            s = summarize_usage(path=path, now=now)
        self.assertEqual(s["month_calls"], 2)
        self.assertEqual(s["month_tokens"], 1210)
        self.assertGreaterEqual(s["today_calls"], 1)
        self.assertGreater(s["month_usd"], 0.5)

    def test_missing_log_is_zero(self):
        s = summarize_usage(path=Path(tempfile.gettempdir()) / "nope_ai_usage.jsonl")
        self.assertEqual(s["month_calls"], 0)
        self.assertEqual(s["today_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
