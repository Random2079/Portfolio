"""Official issuer facts: e-disclosure via Азипи day feed (no Interfax JS-check).

Interfax company.aspx is behind an antibot that blocks requests/Playwright from this
PC; Cursor browser can open it. Азипи mirrors the same лента (`/?msg_day=DD.MM.YYYY`)
over plain HTTP. Match holdings by INN / issuer aliases, not generic event titles.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from portfolio_news.bond_issuer import resolve_bond_issuer
from portfolio_news.sources.base import RawNews

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).with_name("e_disclosure_companies.json")
# MSK without tzdata package (Windows stdlib often lacks IANA zones).
_MSK = timezone(timedelta(hours=3), name="MSK")
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}
_TAG_RE = re.compile(r"<[^>]+>")
_MSG_A_RE = re.compile(
    r'<a[^>]+href=["\'](?:https?://[^"\']+)?/messages/(\d+)/["\'][^>]*>(.*?)</a>',
    re.I | re.S,
)
_CARD_RE = re.compile(
    r"MSG\|(\d+)\|([^|]*)\|\s*Организация:\s*(.*?)\s*ИНН организации:\s*(\d{10})"
    r"\s*Дата события:\s*(\d{2}\.\d{2}\.\d{4})"
    r"(?:\s+(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}))?",
    re.I | re.S,
)
_EVENT_ROW_RE = re.compile(
    r"<tr>\s*<td>(\d{2}\.\d{2}\.\d{4})</td>\s*"
    r"<td[^>]*>(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})</td>\s*"
    r"<td>\s*<a[^>]+href=[\"']([^\"']*event\.aspx\?EventId=[^\"']+)[\"'][^>]*>"
    r"(.*?)</a>",
    re.I | re.S,
)


@dataclass(frozen=True)
class DisclosureEvent:
    title: str
    url: str
    org: str
    inn: str
    published_at: Optional[datetime]


def load_edisc_config(path: Path | None = None) -> dict[str, Any]:
    p = path or _CONFIG_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _plain(fragment: str) -> str:
    t = fragment.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    t = _TAG_RE.sub(" ", t)
    t = html_lib.unescape(t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _parse_ru_dt(day: str, clock: str | None = None) -> Optional[datetime]:
    day = (day or "").strip()
    clock = (clock or "").strip()
    try:
        if clock:
            # "02.10.2026 18:53:38" or "02.10.2026 18:55"
            parts = clock.replace("  ", " ").split()
            if len(parts) == 2:
                d, t = parts
                if t.count(":") == 1:
                    t = t + ":00"
                dt = datetime.strptime(f"{d} {t}", "%d.%m.%Y %H:%M:%S")
            else:
                dt = datetime.strptime(day, "%d.%m.%Y")
        else:
            dt = datetime.strptime(day, "%d.%m.%Y")
        return dt.replace(tzinfo=_MSK).astimezone(timezone.utc)
    except ValueError:
        return None


def parse_azipi_day_html(html: str, *, base: str = "https://e-disclosure.azipi.ru") -> list[DisclosureEvent]:
    """Parse Азипи homepage / ?msg_day= cards into events."""
    marked = _MSG_A_RE.sub(lambda m: f"\nMSG|{m.group(1)}|{_plain(m.group(2))}|\n", html)
    marked = _TAG_RE.sub(" ", marked)
    marked = html_lib.unescape(marked)
    marked = re.sub(r"[ \t]+", " ", marked)
    out: list[DisclosureEvent] = []
    seen: set[str] = set()
    base = base.rstrip("/")
    for m in _CARD_RE.finditer(marked):
        mid, title, org, inn, ev_day, pub = m.groups()
        url = f"{base}/messages/{mid}/"
        if url in seen:
            continue
        seen.add(url)
        title = (title or "").strip() or "Существенный факт"
        org = re.sub(r"\s+", " ", (org or "").strip())
        out.append(
            DisclosureEvent(
                title=title[:512],
                url=url[:1024],
                org=org,
                inn=inn,
                published_at=_parse_ru_dt(ev_day, pub),
            )
        )
    return out


def parse_company_events_html(
    html: str,
    *,
    portal_base: str = "https://www.e-disclosure.ru",
) -> list[DisclosureEvent]:
    """Parse Interfax company.aspx event table (when HTML is already unblocked)."""
    out: list[DisclosureEvent] = []
    seen: set[str] = set()
    portal_base = portal_base.rstrip("/")
    for m in _EVENT_ROW_RE.finditer(html):
        ev_day, pub, href, title_html = m.groups()
        href = html_lib.unescape(href.strip())
        if href.startswith("/"):
            url = portal_base + href
        elif href.startswith("http"):
            url = href
        else:
            url = f"{portal_base}/portal/{href.lstrip('/')}"
        url = url[:1024]
        if url in seen:
            continue
        seen.add(url)
        title = _plain(title_html)[:512] or "Существенный факт"
        out.append(
            DisclosureEvent(
                title=title,
                url=url,
                org="",
                inn="",
                published_at=_parse_ru_dt(ev_day, pub),
            )
        )
    return out


def _equity_key(ticker_id: str, cfg: dict[str, Any]) -> str:
    tid = (ticker_id or "").strip().upper()
    prefs = cfg.get("pref_aliases") if isinstance(cfg.get("pref_aliases"), dict) else {}
    alias = str(prefs.get(tid) or "").strip().upper()
    return alias or tid


def issuer_record(ticker_id: str, *, search_query: str = "", kind: str = "", cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """INN + aliases for a holdings ticker (equity, pref, or bond→issuer)."""
    data = cfg if cfg is not None else load_edisc_config()
    by_eq = data.get("by_equity_ticker") if isinstance(data.get("by_equity_ticker"), dict) else {}
    by_iss = data.get("by_issuer") if isinstance(data.get("by_issuer"), dict) else {}
    key = _equity_key(ticker_id, data)
    row = by_eq.get(key)
    if isinstance(row, dict) and (row.get("inn") or row.get("aliases") or row.get("name")):
        return row

    bi = None
    if (kind or "").lower() == "bond" or (ticker_id or "").upper().startswith("RU000"):
        bi = resolve_bond_issuer(ticker_id, search_query=search_query)
        if bi and bi.equity_ticker:
            eq_row = by_eq.get(bi.equity_ticker.upper())
            if isinstance(eq_row, dict):
                return eq_row
        if bi:
            iss_row = by_iss.get(bi.issuer)
            if isinstance(iss_row, dict):
                merged = dict(iss_row)
                aliases = list(merged.get("aliases") or [])
                for a in bi.aliases:
                    if a not in aliases:
                        aliases.append(a)
                merged["aliases"] = aliases
                merged.setdefault("name", bi.issuer)
                return merged
            return {"name": bi.issuer, "aliases": list(bi.aliases), "inn": None}
    return {}


def event_matches_issuer(ev: DisclosureEvent, rec: dict[str, Any]) -> bool:
    inn = str(rec.get("inn") or "").strip()
    if inn and ev.inn == inn:
        return True
    hay = f"{ev.org} {ev.title}".lower()
    names = [str(rec.get("name") or "")]
    names.extend(str(a) for a in (rec.get("aliases") or []))
    for n in names:
        n = n.strip()
        if len(n) >= 4 and n.lower() in hay:
            return True
    return False


def fetch_azipi_day(
    day: date,
    *,
    timeout: float = 25.0,
    session: requests.Session | None = None,
    base: str = "https://e-disclosure.azipi.ru",
) -> list[DisclosureEvent]:
    url = f"{base.rstrip('/')}/?msg_day={day.strftime('%d.%m.%Y')}"
    sess = session or requests.Session()
    try:
        resp = sess.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("e-disclosure azipi day fail %s: %s", day.isoformat(), exc)
        return []
    events = parse_azipi_day_html(resp.text, base=base)
    log.info("e-disclosure azipi %s → %s events", day.isoformat(), len(events))
    return events


class EDisclosureSource:
    """Issuer facts from Азипи day лента (e-disclosure mirror)."""

    name = "e_disclosure"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        timeout: float = 25.0,
        lookback_days: int = 7,
        base: str | None = None,
    ) -> None:
        self._config_path = config_path or _CONFIG_PATH
        self._timeout = timeout
        self._lookback_days = max(1, min(int(lookback_days), 14))
        self._base_override = base
        self._loaded = False
        self._events: list[DisclosureEvent] | None = None
        self._session: requests.Session | None = None

    def _cfg(self) -> dict[str, Any]:
        return load_edisc_config(self._config_path)

    def _base(self) -> str:
        if self._base_override:
            return self._base_override.rstrip("/")
        cfg = self._cfg()
        raw = str(cfg.get("azipi_day_url") or "https://e-disclosure.azipi.ru/?msg_day={day}")
        return raw.split("/?")[0].rstrip("/") or "https://e-disclosure.azipi.ru"

    def _ensure_events(self) -> list[DisclosureEvent]:
        if self._loaded and self._events is not None:
            return self._events
        self._loaded = True
        if self._session is None:
            self._session = requests.Session()
        today = datetime.now(_MSK).date()
        all_ev: list[DisclosureEvent] = []
        seen: set[str] = set()
        for i in range(self._lookback_days):
            day = today - timedelta(days=i)
            for ev in fetch_azipi_day(
                day,
                timeout=self._timeout,
                session=self._session,
                base=self._base(),
            ):
                if ev.url in seen:
                    continue
                seen.add(ev.url)
                all_ev.append(ev)
        self._events = all_ev
        return self._events

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        rec = issuer_record(ticker_id, search_query=search_query, kind=kind, cfg=self._cfg())
        if not rec:
            return []
        try:
            events = self._ensure_events()
        except Exception as exc:  # noqa: BLE001
            log.warning("e-disclosure load failed: %s", exc)
            return []
        out: list[RawNews] = []
        for ev in events:
            if not event_matches_issuer(ev, rec):
                continue
            out.append(
                RawNews(
                    title=ev.title[:512],
                    url=ev.url,
                    source=self.name,
                    published_at=ev.published_at,
                )
            )
            if len(out) >= 12:
                break
        return out
