"""Bond facts from Dohod.ru connector (getbondinfo by ISIN)."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import requests
from sqlalchemy.orm import Session

from portfolio_news.db import DohodBondCache

log = logging.getLogger(__name__)

DOHOD_CONNECTOR = (
    "https://www.dohod.ru/assets/components/dohodbonds/connectorweb.php"
)
_HEADERS = {
    "User-Agent": "PortfolioNews/0.2 (+local; personal monitor)",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.dohod.ru/analytic/bonds",
}
_CACHE_FRESH_SEC = 12 * 3600

_COUPON_TYPE_MAP = {
    1: "фикс",
    2: "переменный",
    3: "флоат",
    4: "флоат / линк",
}


@dataclass
class DohodBondFacts:
    isin: str
    name: str = ""
    coupon_type: str = ""
    coupon_rate: Optional[float] = None
    offer_date: str = ""
    offer_note: str = ""  # put / call / погашение
    maturity_date: str = ""
    ytm: Optional[float] = None
    ytm_note: str = ""  # «к оферте» / «к погашению»
    rating: str = ""
    rating_agency: str = ""
    price: Optional[float] = None
    nkd: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DohodBondFacts":
        return cls(
            isin=str(d.get("isin") or ""),
            name=str(d.get("name") or ""),
            coupon_type=str(d.get("coupon_type") or ""),
            coupon_rate=_opt_float(d.get("coupon_rate")),
            offer_date=str(d.get("offer_date") or ""),
            offer_note=str(d.get("offer_note") or ""),
            maturity_date=str(d.get("maturity_date") or ""),
            ytm=_opt_float(d.get("ytm")),
            ytm_note=str(d.get("ytm_note") or ""),
            rating=str(d.get("rating") or ""),
            rating_agency=str(d.get("rating_agency") or ""),
            price=_opt_float(d.get("price")),
            nkd=_opt_float(d.get("nkd")),
        )


def _opt_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date_only(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # 2027-03-03T00:00:00 → 2027-03-03
    return s[:10]


def parse_dohod_bondinfo(data: dict[str, Any]) -> DohodBondFacts:
    """Pure JSON mapper — testable without network."""
    isin = str(data.get("isin") or "").strip().upper()
    bond = data.get("bond") if isinstance(data.get("bond"), dict) else {}
    add = data.get("addInfo") if isinstance(data.get("addInfo"), dict) else {}

    rate_name = str(bond.get("rateTypeName") or "").strip()
    if not rate_name:
        # fallback if only code present at top-level (info list style)
        code = data.get("coupon_type") or data.get("rateTypeCode")
        try:
            rate_name = _COUPON_TYPE_MAP.get(int(code), "")  # type: ignore[arg-type]
        except (TypeError, ValueError):
            rate_name = ""

    event = str(data.get("event") or "").strip().lower()
    effective = _date_only(data.get("effectiveDate") or data.get("effective_date"))
    offer_date = ""
    offer_note = ""
    if "put" in event or "продать" in event or "оферт" in event:
        offer_date = effective
        offer_note = "put / оферта"
    elif "call" in event or "выкуп" in event:
        offer_date = effective
        offer_note = "call / выкуп"
    # corpActions: prefer nearest future put/offer window
    actions = data.get("corpActions") if isinstance(data.get("corpActions"), list) else []
    from datetime import date

    today = date.today().isoformat()
    future_puts: list[tuple[str, str]] = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        put = _date_only(a.get("putDate") or a.get("periodOfferFromDate"))
        if not put:
            continue
        note = "оферта (corpActions)"
        future_puts.append((put, note))
    future_puts.sort(key=lambda x: x[0])
    upcoming = [x for x in future_puts if x[0] >= today]
    if upcoming:
        offer_date, offer_note = upcoming[0]
    elif not offer_date and future_puts:
        # only past offers known
        offer_date, offer_note = future_puts[-1]
        offer_note = offer_note + " · прошл."

    mat = _date_only(
        bond.get("maturityDate")
        or bond.get("maturityDateCalc")
        or bond.get("expiryDateCalc")
        or data.get("maturity_date")
    )

    ytm = _opt_float(data.get("ytmCalc") or data.get("ytmMatCalc") or data.get("fact_yield"))
    ytm_note = ""
    if ytm is not None:
        if offer_date and offer_note:
            ytm_note = "к оферте/событию"
        else:
            ytm_note = "к погашению (расчёт Dohod)"

    rating = str(
        data.get("creditRatingText")
        or data.get("credit_rating_text")
        or data.get("otherRatingText")
        or ""
    ).strip()
    agency_bits = []
    for key, label in (("akra", "АКРА"), ("expert", "Эксперт"), ("sp", "S&P"), ("fitch", "Fitch"), ("moody", "Moody")):
        val = str(data.get(key) or "").strip()
        if val:
            agency_bits.append(f"{label} {val}")
    if agency_bits and not rating:
        rating = agency_bits[0]
    rating_agency = "; ".join(agency_bits[:2])

    name = str(
        data.get("mdShortName")
        or data.get("nameShortHdeSec")
        or add.get("nameShortHde")
        or data.get("name")
        or ""
    ).strip()

    return DohodBondFacts(
        isin=isin,
        name=name,
        coupon_type=rate_name or "",
        coupon_rate=_opt_float(data.get("couponRate") or data.get("current_coupon_prc")),
        offer_date=offer_date,
        offer_note=offer_note,
        maturity_date=mat,
        ytm=ytm,
        ytm_note=ytm_note,
        rating=rating,
        rating_agency=rating_agency,
        price=_opt_float(data.get("price")),
        nkd=_opt_float(add.get("nkd") or data.get("nkd")),
    )


def fetch_dohod_bond(isin: str) -> Optional[DohodBondFacts]:
    tid = (isin or "").strip().upper()
    if not tid:
        return None
    try:
        resp = requests.get(
            DOHOD_CONNECTOR,
            params={"action": "getbondinfo", "isin": tid},
            headers=_HEADERS,
            timeout=35,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("dohod getbondinfo %s failed: %s", tid, exc)
        return None
    if not isinstance(data, dict) or not data.get("isin"):
        log.warning("dohod getbondinfo %s: empty/unexpected", tid)
        return None
    return parse_dohod_bondinfo(data)


def _now() -> float:
    return time.time()


def load_dohod_bond_cache(session: Session, isin: str) -> Optional[tuple[DohodBondFacts, float]]:
    import json

    tid = (isin or "").strip().upper()
    row = session.get(DohodBondCache, tid)
    if row is None or not (row.payload_json or "").strip():
        return None
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return DohodBondFacts.from_dict(data), float(row.updated_at or 0.0)


def save_dohod_bond_cache(session: Session, facts: DohodBondFacts) -> None:
    import json

    tid = (facts.isin or "").strip().upper()
    if not tid:
        return
    row = session.get(DohodBondCache, tid)
    if row is None:
        row = DohodBondCache(isin=tid)
        session.add(row)
    row.payload_json = json.dumps(facts.to_dict(), ensure_ascii=False)
    row.updated_at = _now()
    row.ok = 1
    session.commit()


def dohod_cache_fresh(updated_at: float, *, max_age: float = _CACHE_FRESH_SEC) -> bool:
    return updated_at > 0 and (_now() - updated_at) < max_age


def get_dohod_bond(
    session: Session, isin: str, *, force: bool = False
) -> tuple[Optional[DohodBondFacts], str]:
    """Cache-first single-ISIN facts. Returns (facts, as_of)."""
    from datetime import datetime, timedelta, timezone

    tid = (isin or "").strip().upper()
    as_of = ""
    if not tid:
        return None, ""

    if not force:
        cached = load_dohod_bond_cache(session, tid)
        if cached and dohod_cache_fresh(cached[1]):
            facts, upd = cached
            as_of = datetime.fromtimestamp(upd, tz=timezone(timedelta(hours=5))).strftime(
                "%Y-%m-%d %H:%M"
            )
            return facts, as_of

    fetched = fetch_dohod_bond(tid)
    if fetched:
        try:
            save_dohod_bond_cache(session, fetched)
        except Exception as exc:  # noqa: BLE001
            log.warning("dohod cache save failed: %s", exc)
        as_of = datetime.now(timezone(timedelta(hours=5))).strftime("%Y-%m-%d %H:%M")
        return fetched, as_of

    cached = load_dohod_bond_cache(session, tid)
    if cached:
        facts, upd = cached
        as_of = datetime.fromtimestamp(upd, tz=timezone(timedelta(hours=5))).strftime(
            "%Y-%m-%d %H:%M"
        )
        return facts, as_of
    return None, ""
