"""Dividend calendar from Smart-Lab table (ISS /securities/.../dividends is empty now)."""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from portfolio_news.metrics_moex import DividendRow

log = logging.getLogger(__name__)

SMARTLAB_DIV_URL = "https://smart-lab.ru/dividends/index/order_by_cut_off_date/desc/"
_HEADERS = {
    "User-Agent": "PortfolioNews/0.2 (+local; personal monitor)",
    "Accept": "text/html,application/xhtml+xml",
}

_ROW = re.compile(r'<tr class="(dividend_[^"]*)">(.*?)</tr>', re.I | re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_TICKER = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", html or "")).strip()


def _ru_num(raw: str) -> Optional[float]:
    s = (raw or "").replace("\xa0", "").replace(" ", "").replace("%", "")
    s = s.replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ru_date(raw: str) -> str:
    m = _DATE.match((raw or "").strip())
    if not m:
        return ""
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def parse_smartlab_dividend_html(html: str) -> list[DividendRow]:
    """Pure HTML parser — testable without network."""
    out: list[DividendRow] = []
    seen: set[tuple[str, str]] = set()
    for m in _ROW.finditer(html or ""):
        cls, body = m.group(1), m.group(2)
        texts = [_strip(td) for td in _TD.findall(body)]
        if len(texts) < 4:
            continue
        ticker = (texts[1] if len(texts) > 1 else "").strip().upper()
        if not _TICKER.match(ticker):
            continue
        value = _ru_num(texts[3]) if len(texts) > 3 else None
        dates = [_ru_date(x) for x in texts if _DATE.match(x.strip())]
        dates = [d for d in dates if d]
        if not dates:
            continue
        # last-buy, registry, pay — registry is the middle one when all three exist
        reg = dates[1] if len(dates) >= 2 else dates[0]
        key = (ticker, reg)
        if key in seen:
            continue
        seen.add(key)
        name = texts[0] if texts else ticker
        out.append(
            DividendRow(
                ticker_id=ticker,
                name=name or ticker,
                secid=ticker,
                registryclosedate=reg,
                value=value,
                currencyid="RUB",
                extra={"source": "smartlab", "row_class": cls},
            )
        )
    return out


def fetch_smartlab_dividends() -> list[DividendRow]:
    try:
        resp = requests.get(SMARTLAB_DIV_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("smartlab dividends failed: %s", exc)
        return []
    rows = parse_smartlab_dividend_html(resp.text)
    log.info("smartlab dividends: %s rows", len(rows))
    return rows
