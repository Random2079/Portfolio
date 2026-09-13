"""Smart-Lab dividend table parser (no network)."""

from __future__ import annotations

import unittest

from portfolio_news.dividends_smartlab import parse_smartlab_dividend_html

_HTML = """
<table>
<tr class="dividend_approved">
  <td><a href="/q/TATN/dividend/">Татнефть</a></td>
  <td>TATN</td>
  <td>2кв 2026</td>
  <td><strong>32,88</strong></td>
  <td><strong>5,3%</strong></td>
  <td></td>
  <td>12.10.2026</td>
  <td>13.10.2026</td>
  <td>23.10.2026</td>
  <td>618,1</td>
</tr>
<tr class="dividend_approved">
  <td>Сбер</td>
  <td>SBER</td>
  <td>2025</td>
  <td>33.3</td>
  <td>1%</td>
  <td></td>
  <td>11.07.2025</td>
  <td>12.07.2025</td>
</tr>
</table>
"""


class SmartlabDivTests(unittest.TestCase):
    def test_parse_ticker_value_registry(self):
        rows = parse_smartlab_dividend_html(_HTML)
        by = {r.ticker_id: r for r in rows}
        self.assertIn("TATN", by)
        self.assertEqual(by["TATN"].registryclosedate, "2026-10-13")
        self.assertAlmostEqual(by["TATN"].value or 0, 32.88, places=2)
        self.assertEqual(by["SBER"].registryclosedate, "2025-07-12")


if __name__ == "__main__":
    unittest.main()
