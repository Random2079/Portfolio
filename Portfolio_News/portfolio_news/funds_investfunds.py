"""Optional ticker → ISIN via investfunds autocomplete (free HTML/JSON).

Used only when holdings/MOEX did not give ISIN for a fund. Result is tiny;
prefer CBR universe keyed by ISIN for TER itself.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

_SEARCH_URL = "https://investfunds.ru/funds/index.php"
_HEADERS = {
    "User-Agent": "PortfolioNews/0.2 (+local; personal monitor)",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://investfunds.ru/funds/",
}


def resolve_fund_isin(ticker: str, *, timeout: float = 20.0) -> Optional[str]:
    """Return ISIN for MOEX ticker (e.g. BCSR) or None."""
    term = (ticker or "").strip().upper()
    if not term or len(term) < 2:
        return None
    vh = hashlib.md5(term.encode("utf-8")).hexdigest()
    try:
        sess = requests.Session()
        sess.headers.update(_HEADERS)
        sess.get("https://investfunds.ru/funds/", timeout=timeout)
        resp = sess.get(
            _SEARCH_URL,
            params={"searchString": term, "verifyHash": vh},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("investfunds isin resolve %s failed: %s", term, exc)
        return None
    results = data.get("currentResults") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return None
    for item in results:
        if not isinstance(item, dict):
            continue
        kod = str(item.get("kod_micex") or "").strip().upper()
        isin = str(item.get("isin") or "").strip().upper()
        if isin.startswith("RU") and (not kod or kod == term):
            return isin
    # fallback: first result with ISIN
    for item in results:
        if not isinstance(item, dict):
            continue
        isin = str(item.get("isin") or "").strip().upper()
        if isin.startswith("RU"):
            return isin
    return None
