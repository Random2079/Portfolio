"""Official issuer facts: e-disclosure company card (CDP) + Азипи fallback.

Interfax company.aspx is behind a JS-check that blocks requests and a fresh
Playwright/Chrome. Attach to an already-open Chrome with
`--remote-debugging-port` (dedicated profile, not the bank login one).
Азипи day-лента stays the fallback when CDP is down.
Match company.aspx rows by company_id (no title_matches_ticker). Азипи: INN/aliases.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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
_CDP_PORTS = (9222, 9333)


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


def company_html_usable(html: str) -> bool:
    """True if HTML looks like a real company.aspx event table, not the JS-check."""
    if not html:
        return False
    low = html.lower()
    if "xpvnsulc" in low or "checking your browser" in low:
        return False
    return "event.aspx?eventid=" in low


def cdp_endpoint_candidates(*, extra: str | None = None) -> list[str]:
    out: list[str] = []
    env = (os.environ.get("EDISC_CDP_URL") or "").strip().rstrip("/")
    if extra:
        extra = extra.strip().rstrip("/")
        if extra:
            out.append(extra)
    if env:
        out.append(env)
    out.extend(f"http://127.0.0.1:{p}" for p in _CDP_PORTS)
    out.append("http://[::1]:9222")
    seen: set[str] = set()
    uniq: list[str] = []
    for ep in out:
        if ep not in seen:
            seen.add(ep)
            uniq.append(ep)
    return uniq


def resolve_cdp_endpoint(
    *,
    timeout: float = 0.8,
    get: Callable[..., Any] | None = None,
    extra: str | None = None,
    candidates: list[str] | None = None,
    probe: Callable[[str], bool] | None = None,
) -> Optional[str]:
    """Return a live CDP HTTP endpoint, or None if Chrome has no debug port."""
    urls = candidates if candidates is not None else cdp_endpoint_candidates(extra=extra)
    if probe is not None:
        for ep in urls:
            try:
                if probe(ep):
                    return ep
            except Exception:  # noqa: BLE001
                continue
        return None
    getter = get or requests.get
    for ep in urls:
        try:
            resp = getter(f"{ep}/json/version", timeout=timeout)
            ok = bool(getattr(resp, "ok", False) or getattr(resp, "status_code", 0) == 200)
            if ok:
                return ep
        except Exception:  # noqa: BLE001
            continue
    return None


def fetch_company_html_cdp(
    company_id: int,
    *,
    browser: Any,
    portal_url: str,
    timeout_ms: int = 25000,
) -> Optional[str]:
    """Read company.aspx HTML from an already-connected CDP browser. Never closes the browser."""
    needle = f"company.aspx?id={int(company_id)}"
    contexts = list(getattr(browser, "contexts", None) or [])
    if not contexts:
        log.warning("e-disclosure CDP: no browser contexts")
        return None
    context = contexts[0]
    owned = False
    page = None
    try:
        for p in list(context.pages or []):
            url = getattr(p, "url", "") or ""
            if "e-disclosure.ru" in url and needle in url:
                page = p
                break
        if page is None:
            page = context.new_page()
            owned = True
            page.goto(portal_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_selector("a[href*='event.aspx?EventId=']", timeout=min(8000, timeout_ms))
            except Exception:  # noqa: BLE001
                pass
        html = page.content()
        return html if isinstance(html, str) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("e-disclosure CDP company %s fail: %s", company_id, exc)
        return None
    finally:
        if owned and page is not None:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass


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
    """Issuer facts: Interfax company.aspx via CDP, Азипи day-лента as fallback."""

    name = "e_disclosure"

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        timeout: float = 25.0,
        lookback_days: int = 7,
        base: str | None = None,
        cdp_url: str | None = None,
        cdp_get_html: Callable[[int], Optional[str]] | None = None,
    ) -> None:
        self._config_path = config_path or _CONFIG_PATH
        self._timeout = timeout
        self._lookback_days = max(1, min(int(lookback_days), 14))
        self._base_override = base
        self._cdp_url_override = cdp_url
        self._cdp_get_html = cdp_get_html
        self._loaded = False
        self._events: list[DisclosureEvent] | None = None
        self._session: requests.Session | None = None
        self._html_by_company: dict[str, Optional[str]] = {}
        self._cdp_endpoint: Optional[str] = None
        self._cdp_resolved = False
        self._cdp_dead = False
        self._pw: Any = None
        self._browser: Any = None

    def _cfg(self) -> dict[str, Any]:
        return load_edisc_config(self._config_path)

    def _base(self) -> str:
        if self._base_override:
            return self._base_override.rstrip("/")
        cfg = self._cfg()
        raw = str(cfg.get("azipi_day_url") or "https://e-disclosure.azipi.ru/?msg_day={day}")
        return raw.split("/?")[0].rstrip("/") or "https://e-disclosure.azipi.ru"

    def _portal_company_url(self, company_id: int) -> str:
        tmpl = str(self._cfg().get("portal_company_url") or "https://www.e-disclosure.ru/portal/company.aspx?id={company_id}")
        return tmpl.format(company_id=int(company_id))

    def _endpoint(self) -> Optional[str]:
        if self._cdp_resolved:
            return self._cdp_endpoint
        self._cdp_resolved = True
        self._cdp_endpoint = resolve_cdp_endpoint(extra=self._cdp_url_override)
        if not self._cdp_endpoint:
            log.info(
                "e-disclosure CDP: no debug port (9222/9333). "
                "Start dedicated Chrome: scripts/start_chrome_edisc_cdp.cmd — fallback Азипи"
            )
        return self._cdp_endpoint

    def _connect_cdp(self) -> Any:
        if self._cdp_get_html is not None:
            return None
        if self._cdp_dead:
            return None
        if self._browser is not None:
            return self._browser
        ep = self._endpoint()
        if not ep:
            self._cdp_dead = True
            return None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("e-disclosure CDP: playwright not installed — fallback Азипи")
            self._cdp_dead = True
            return None
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(ep)
            log.info("e-disclosure CDP attached %s", ep)
            return self._browser
        except Exception as exc:  # noqa: BLE001
            log.warning("e-disclosure CDP connect fail: %s — fallback Азипи", exc)
            self._cdp_dead = True
            self._disconnect_cdp()
            return None

    def _disconnect_cdp(self) -> None:
        # Do not browser.close() — that would kill the user's Chrome.
        self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None

    def _company_html(self, company_id: int) -> Optional[str]:
        key = str(int(company_id))
        if key in self._html_by_company:
            return self._html_by_company[key]
        html: Optional[str] = None
        if self._cdp_get_html is not None:
            try:
                html = self._cdp_get_html(int(company_id))
            except Exception as exc:  # noqa: BLE001
                log.warning("e-disclosure CDP inject fail %s: %s", company_id, exc)
                html = None
        else:
            browser = self._connect_cdp()
            if browser is not None:
                html = fetch_company_html_cdp(
                    int(company_id),
                    browser=browser,
                    portal_url=self._portal_company_url(int(company_id)),
                    timeout_ms=int(self._timeout * 1000),
                )
        if html and company_html_usable(html):
            self._html_by_company[key] = html
            return html
        if html:
            log.info("e-disclosure company %s HTML not usable (JS-check?) — Азипи", company_id)
        self._html_by_company[key] = None
        return None

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

    def _to_raw(self, events: list[DisclosureEvent]) -> list[RawNews]:
        out: list[RawNews] = []
        for ev in events:
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

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        rec = issuer_record(ticker_id, search_query=search_query, kind=kind, cfg=self._cfg())
        if not rec:
            return []
        cid = rec.get("company_id")
        if cid not in (None, "", 0):
            try:
                html = self._company_html(int(cid))
            except Exception as exc:  # noqa: BLE001
                log.warning("e-disclosure company fetch failed: %s", exc)
                html = None
            if html:
                # Company card is already the issuer's table — no title_matches_ticker.
                return self._to_raw(parse_company_events_html(html))
        try:
            events = self._ensure_events()
        except Exception as exc:  # noqa: BLE001
            log.warning("e-disclosure azipi load failed: %s", exc)
            return []
        matched = [ev for ev in events if event_matches_issuer(ev, rec)]
        return self._to_raw(matched)
