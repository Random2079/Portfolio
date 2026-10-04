"""Offline tests for e-disclosure / Азипи parser + CDP resolve/fallback."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from portfolio_news.sources.e_disclosure import (
    EDisclosureSource,
    company_html_usable,
    event_matches_issuer,
    issuer_record,
    parse_azipi_day_html,
    parse_company_events_html,
    resolve_cdp_endpoint,
)

_AZIPI = """
<html><body>
<a href="/messages/4593298/">Выплаченные доходы по эмиссионным ценным бумагам эмитента</a>
Организация: Публичное акционерное общество "Сбербанк России"
ИНН организации: 7707083893
Дата события: 02.10.2026 02.10.2026 18:53:38
<a href="/messages/4593304/">Стоимость чистых активов и расчетная стоимость инвестиционного пая</a>
Организация: Общество с ограниченной ответственностью "РСХБ Управление Активами"
ИНН организации: 7704814182
Дата события: 02.10.2026 02.10.2026 19:43:00
</body></html>
"""

_COMPANY = """
<table>
<tr>
                <td>02.10.2026</td>
                <td class="datetime_nowrap">02.10.2026 18:55</td>
                <td>
                    <a href="/portal/event.aspx?EventId=Gvo5gUDCKUSMbQKM90H82A-B-B" style="color:black;" target="_blank">Выплаченные доходы или иные выплаты, причитающиеся владельцам ценных бумаг эмитента</a>
                </td>
            </tr>
</table>
"""

_BLOCKED = "<html><body>xpvnsulc checking your browser</body></html>"


class ParseTests(unittest.TestCase):
    def test_azipi_two_cards(self):
        evs = parse_azipi_day_html(_AZIPI)
        self.assertEqual(len(evs), 2)
        self.assertEqual(evs[0].inn, "7707083893")
        self.assertIn("Сбербанк", evs[0].org)
        self.assertTrue(evs[0].url.endswith("/messages/4593298/"))
        self.assertIsNotNone(evs[0].published_at)

    def test_company_table(self):
        evs = parse_company_events_html(_COMPANY)
        self.assertEqual(len(evs), 1)
        self.assertIn("EventId=", evs[0].url)
        self.assertIn("Выплаченные доходы", evs[0].title)

    def test_issuer_sber_and_pref(self):
        sber = issuer_record("SBER")
        self.assertEqual(sber.get("inn"), "7707083893")
        pref = issuer_record("SBERP")
        self.assertEqual(pref.get("inn"), "7707083893")

    def test_bond_sber_isin(self):
        rec = issuer_record("RU000A10EF52", kind="bond")
        self.assertEqual(rec.get("inn"), "7707083893")

    def test_match_inn_not_rshb(self):
        evs = parse_azipi_day_html(_AZIPI)
        rec = issuer_record("SBER")
        self.assertTrue(event_matches_issuer(evs[0], rec))
        self.assertFalse(event_matches_issuer(evs[1], rec))

    def test_company_html_usable(self):
        self.assertTrue(company_html_usable(_COMPANY))
        self.assertFalse(company_html_usable(_BLOCKED))
        self.assertFalse(company_html_usable(""))


class CdpResolveTests(unittest.TestCase):
    def test_resolve_none_when_ports_dead(self):
        self.assertIsNone(resolve_cdp_endpoint(probe=lambda _u: False))

    def test_resolve_first_live(self):
        hits: list[str] = []

        def probe(u: str) -> bool:
            hits.append(u)
            return u.endswith(":9333")

        ep = resolve_cdp_endpoint(
            candidates=["http://127.0.0.1:9222", "http://127.0.0.1:9333"],
            probe=probe,
        )
        self.assertEqual(ep, "http://127.0.0.1:9333")
        self.assertEqual(hits, ["http://127.0.0.1:9222", "http://127.0.0.1:9333"])


class SourceFetchTests(unittest.TestCase):
    def test_fetch_filters_and_caches(self):
        src = EDisclosureSource(
            lookback_days=1,
            base="https://e-disclosure.azipi.ru",
            cdp_get_html=lambda _cid: None,
        )
        fake = MagicMock()
        resp = MagicMock()
        resp.text = _AZIPI
        resp.raise_for_status = MagicMock()
        fake.get.return_value = resp
        src._session = fake
        rows = src.fetch("SBER", "Сбербанк", "equity")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source, "e_disclosure")
        self.assertEqual(fake.get.call_count, 1)
        rows2 = src.fetch("SBER", "Сбербанк", "equity")
        self.assertEqual(fake.get.call_count, 1)
        self.assertEqual(len(rows2), 1)

    def test_cdp_company_page_skips_azipi_and_caches_html(self):
        calls: list[int] = []

        def get_html(cid: int) -> str:
            calls.append(cid)
            return _COMPANY

        src = EDisclosureSource(lookback_days=1, cdp_get_html=get_html)
        fake = MagicMock()
        src._session = fake
        rows = src.fetch("SBER", "Сбербанк", "equity")
        self.assertEqual(len(rows), 1)
        self.assertIn("EventId=", rows[0].url)
        fake.get.assert_not_called()
        src.fetch("SBERP", "Сбербанк", "equity")
        self.assertEqual(calls, [3043])

    def test_cdp_blocked_falls_back_azipi(self):
        src = EDisclosureSource(
            lookback_days=1,
            base="https://e-disclosure.azipi.ru",
            cdp_get_html=lambda _cid: _BLOCKED,
        )
        fake = MagicMock()
        resp = MagicMock()
        resp.text = _AZIPI
        resp.raise_for_status = MagicMock()
        fake.get.return_value = resp
        src._session = fake
        rows = src.fetch("SBER", "Сбербанк", "equity")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].url.endswith("/messages/4593298/"))
        self.assertEqual(fake.get.call_count, 1)

    def test_cdp_down_falls_back_azipi(self):
        src = EDisclosureSource(
            lookback_days=1,
            base="https://e-disclosure.azipi.ru",
            cdp_get_html=lambda _cid: None,
        )
        fake = MagicMock()
        resp = MagicMock()
        resp.text = _AZIPI
        resp.raise_for_status = MagicMock()
        fake.get.return_value = resp
        src._session = fake
        rows = src.fetch("ROSN", "Роснефть", "equity")
        self.assertEqual(rows, [])  # fixture has SBER, not ROSN
        self.assertEqual(fake.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
