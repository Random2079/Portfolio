"""KS: review / checkpoint facts under position card (no buy/sell advice).

Cache-first SQLite payload; fill from BCS + MOEX + calendar + SmartLab/Dohod.
Missing slots stay [НЕТ ДАННЫХ] with empty source.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from portfolio_news.db import ReviewCache

log = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=5))
_CACHE_FRESH_SEC = 6 * 3600  # reuse cache if younger; still return stale on MOEX fail

# checkpoint sector keys → UI label + "смотрим" line
_SECTORS: dict[str, tuple[str, str]] = {
    "it": ("IT / Tech", "рост, путь к FCF; высокий P/E сам по себе не красный флаг"),
    "dev": ("девелопмент", "контракты/эскроу-пайплайн + NetDebt/EBITDA в рамках цикла"),
    "resources": ("ресурсы / нефть", "FCF, CAPEX, дивидендная политика"),
    "banks": ("лизинг / банки", "P/B, ROE; плечо — рабочий инструмент сектора"),
    "retail_telecom": ("ритейл / телеком", "FCF после CAPEX, долговая нагрузка, див.%"),
    "unknown": ("сектор ?", "сверить отрасль вручную; слоты общие"),
}

# ticker → sector (expand over time; category from tickers DB can override via keywords)
_TICKER_SECTOR: dict[str, str] = {
    "SBER": "banks",
    "SBERP": "banks",
    "VTBR": "banks",
    "TCSG": "banks",
    "T": "banks",
    "CBOM": "banks",
    "SFIN": "banks",
    "MTSS": "retail_telecom",
    "MGNT": "retail_telecom",
    "LENT": "retail_telecom",
    "FIVE": "retail_telecom",
    "RTKM": "retail_telecom",
    "RTKMP": "retail_telecom",
    "YDEX": "it",
    "YNDX": "it",
    "VKCO": "it",
    "POSI": "it",
    "HHRU": "it",
    "OZON": "it",
    "ROSN": "resources",
    "LKOH": "resources",
    "GAZP": "resources",
    "SIBN": "resources",
    "TATN": "resources",
    "TATNP": "resources",
    "NVTK": "resources",
    "SNGS": "resources",
    "SNGSP": "resources",
    "GMKN": "resources",
    "NLMK": "resources",
    "CHMF": "resources",
    "MAGN": "resources",
    "PLZL": "resources",
    "ALRS": "resources",
    "SMLT": "dev",
    "PIKK": "dev",
    "SFTL": "dev",
    "ETLN": "dev",
    "LSRG": "dev",
}

_SECTOR_SLOTS: dict[str, list[tuple[str, str]]] = {
    # (key, label)
    "resources": [
        ("fcf", "FCF / FCF-yield"),
        ("capex", "CAPEX-контекст"),
        ("div_yield", "Див. %"),
        ("pe", "P/E"),
    ],
    "banks": [
        ("pb", "P/B"),
        ("roe", "ROE"),
        ("pe", "P/E"),
        ("div_yield", "Див. %"),
    ],
    "retail_telecom": [
        ("fcf_after_capex", "FCF после CAPEX"),
        ("netdebt_ebitda", "NetDebt / EBITDA"),
        ("div_yield", "Див. %"),
        ("pe", "P/E"),
    ],
    "it": [
        ("fcf_path", "Путь к FCF"),
        ("growth", "Рост (контекст)"),
        ("pe", "P/E"),
        ("div_yield", "Див. %"),
    ],
    "dev": [
        ("escrow_debt", "Эскроу / долг"),
        ("netdebt_ebitda", "NetDebt / EBITDA"),
        ("div_yield", "Див. %"),
    ],
    "unknown": [
        ("div_yield", "Див. %"),
        ("pe", "P/E"),
        ("pb", "P/B"),
    ],
}

_FLAG_STUBS_EQUITY = [
    {"id": "spo", "label": "Допэмиссия не на развитие", "state": "empty"},
    {"id": "dilution", "label": "Размытие / связанные стороны", "state": "empty"},
    {"id": "mgmt", "label": "«Фишка» + ухудшение менеджмента", "state": "empty"},
]

_FLAG_STUBS_BOND = [
    {"id": "sub", "label": "Субординация / ковенанты", "state": "empty"},
    {"id": "tail", "label": "Хвост ВДО ради купона", "state": "empty"},
]

_FLAG_STUBS_FUND = [
    {"id": "ter", "label": "Скрытые издержки / tracking", "state": "empty"},
]


@dataclass
class ReviewField:
    key: str
    label: str
    value: Optional[str] = None
    unit: str = ""
    source: str = ""  # BCS | MOEX | calendar | SmartLab | Dohod | ""
    as_of: str = ""
    missing: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewPayload:
    ok: bool = True
    ticker: str = ""
    kind: str = "equity"  # equity | bond | fund
    name: str = ""
    isin: str = ""
    error: str = ""
    sector: dict[str, str] = field(default_factory=dict)
    position_line: str = ""
    fields: list[ReviewField] = field(default_factory=list)
    flags: list[dict[str, str]] = field(default_factory=list)
    verdict: Optional[str] = None  # null until user sets (UI localStorage)
    disclaimer: str = "цифры и факты · не советы · не покупай/продавай по этому блоку"
    updated_at: float = 0.0
    stale: bool = False
    from_cache: bool = False
    mock: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fields"] = [f.to_dict() if isinstance(f, ReviewField) else f for f in self.fields]
        return d


def _now_ts() -> float:
    return time.time()


def _as_of_now() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d %H:%M")


def resolve_sector(ticker: str, category: str = "") -> dict[str, str]:
    tid = (ticker or "").strip().upper()
    cat = (category or "").strip().lower()
    sid = _TICKER_SECTOR.get(tid, "")
    if not sid and cat:
        if any(x in cat for x in ("банк", "bank", "финанс", "лизинг")):
            sid = "banks"
        elif any(x in cat for x in ("нефт", "газ", "металл", "руд", "угол", "энерг")):
            sid = "resources"
        elif any(x in cat for x in ("ритейл", "телеком", "связь", "retail")):
            sid = "retail_telecom"
        elif any(x in cat for x in ("it", "интернет", "софт", "tech")):
            sid = "it"
        elif any(x in cat for x in ("девелоп", "строи", "недвиж")):
            sid = "dev"
    if not sid:
        sid = "unknown"
    label, look = _SECTORS.get(sid, _SECTORS["unknown"])
    return {"id": sid, "label": label, "look_for": look}


def _field(
    key: str,
    label: str,
    *,
    value: Optional[str] = None,
    source: str = "",
    as_of: str = "",
    unit: str = "",
) -> ReviewField:
    missing = value is None or str(value).strip() == ""
    return ReviewField(
        key=key,
        label=label,
        value=None if missing else str(value),
        unit=unit,
        source="" if missing else source,
        as_of="" if missing else as_of,
        missing=missing,
    )


def _fmt_num(v: Optional[float], *, pct: bool = False, decimals: int = 2) -> Optional[str]:
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if pct:
        return f"{n:.{decimals}f}".replace(".", ",") + "%"
    s = f"{n:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",")


def _bond_class(listlevel: Optional[int]) -> str:
    """Heuristic only — not a recommendation."""
    if listlevel is None:
        return ""
    if int(listlevel) <= 1:
        return "ядро (1–2 уровень листинга, эвристика)"
    if int(listlevel) == 2:
        return "середина (2 ур., эвристика)"
    return "хвост / 3 ур. (эвристика · не = докупай)"


def _next_calendar_event(
    events: list[dict[str, Any]],
    ticker: str,
    kinds: tuple[str, ...],
    today: str,
) -> Optional[dict[str, Any]]:
    tid = ticker.upper()
    future = []
    for e in events:
        if not isinstance(e, dict):
            continue
        if str(e.get("ticker") or "").upper() != tid:
            continue
        if str(e.get("kind") or "") not in kinds:
            continue
        day = str(e.get("pay_date") or "")[:10]
        if day >= today:
            future.append(e)
    if not future:
        return None
    future.sort(key=lambda x: str(x.get("pay_date") or ""))
    return future[0]


def _equity_from_smartlab(
    fund: Any,
    *,
    preferred_alias: bool,
    as_of: str,
) -> dict[str, tuple[Optional[str], str]]:
    """Map FundamentalRow → slot key → (formatted value, source note)."""
    if fund is None:
        return {}
    out: dict[str, tuple[Optional[str], str]] = {}
    pe = _fmt_num(getattr(fund, "pe", None))
    if pe:
        out["pe"] = (pe, "SmartLab")
    pb = _fmt_num(getattr(fund, "pb", None))
    if pb:
        out["pb"] = (pb, "SmartLab")
    roe = _fmt_num(getattr(fund, "roe", None), pct=True)
    if roe:
        out["roe"] = (roe, "SmartLab")
    debt = _fmt_num(getattr(fund, "debt_ebitda", None))
    if debt:
        out["netdebt_ebitda"] = (debt + " (долг/EBITDA)", "SmartLab")
    # div: preferred → ап if present, else ао
    dy = None
    if preferred_alias and getattr(fund, "div_yield_ap", None) is not None:
        dy = _fmt_num(fund.div_yield_ap, pct=True)
    elif getattr(fund, "div_yield_ao", None) is not None:
        dy = _fmt_num(fund.div_yield_ao, pct=True)
    elif getattr(fund, "div_yield_ap", None) is not None:
        dy = _fmt_num(fund.div_yield_ap, pct=True)
    if dy:
        out["div_yield"] = (dy, "SmartLab")

    fcf_bn = _fmt_num(getattr(fund, "fcf_bn", None), decimals=1)
    fcf_y = _fmt_num(getattr(fund, "fcf_yield", None), pct=True, decimals=1)
    fcf_share = _fmt_num(getattr(fund, "fcf_share", None), decimals=1)
    fcf_bits = []
    if fcf_bn:
        fcf_bits.append(f"{fcf_bn} млрд ₽")
    if fcf_y:
        fcf_bits.append(f"yield {fcf_y}")
    if not fcf_bits and fcf_share:
        fcf_bits.append(f"{fcf_share} ₽/акц.")
    fcf_txt = " · ".join(fcf_bits) if fcf_bits else None
    if fcf_txt:
        # FCF from SmartLab already = after CAPEX (их определение)
        out["fcf"] = (fcf_txt, "SmartLab")
        out["fcf_after_capex"] = (fcf_txt, "SmartLab")
        out["fcf_path"] = (fcf_txt, "SmartLab")

    capex = _fmt_num(getattr(fund, "capex_bn", None), decimals=1)
    if capex:
        out["capex"] = (f"{capex} млрд ₽", "SmartLab")

    # IT «рост»: выручка YoY с field=revenue; иначе хотя бы период отчёта.
    growth_bits: list[str] = []
    rev_yoy = getattr(fund, "revenue_yoy", None)
    if rev_yoy is not None:
        try:
            n = float(rev_yoy)
            sign = "+" if n > 0 else ""
            growth_bits.append(f"выручка {sign}{n:.1f}".replace(".", ",") + "% YoY")
        except (TypeError, ValueError):
            pass
    rev_bn = _fmt_num(getattr(fund, "revenue_bn", None), decimals=1)
    if rev_bn:
        growth_bits.append(f"{rev_bn} млрд ₽")
    report = str(getattr(fund, "report", "") or "").strip()
    if report:
        growth_bits.append(f"отчёт {report}")
    if growth_bits:
        out["growth"] = (" · ".join(growth_bits), "SmartLab")

    # Девелоп «эскроу/долг»:
    # SmartLab не даёт «денег на эскроу-счетах» — берём контракты на продажу (пайплайн)
    # + долг/EBITDA. Явная подпись, без выдуманного cash escrow.
    esc_bits: list[str] = []
    ps_rub = _fmt_num(getattr(fund, "pending_sales_rub", None), decimals=1)
    ps_m2 = _fmt_num(getattr(fund, "pending_sales_m2", None), decimals=0)
    apt_m2 = _fmt_num(getattr(fund, "apartment_sales_m2", None), decimals=0)
    if ps_rub:
        esc_bits.append(f"контракты {ps_rub} млрд ₽")
    if ps_m2:
        esc_bits.append(f"{ps_m2} тыс м²")
    elif apt_m2:
        esc_bits.append(f"продажи {apt_m2} тыс м²")
    if debt:
        esc_bits.append(f"долг/EBITDA {debt}")
    if esc_bits:
        out["escrow_debt"] = (" · ".join(esc_bits), "SmartLab")
    _ = as_of
    return out


def build_review_payload(
    *,
    ticker: str,
    kind: str,
    name: str = "",
    isin: str = "",
    category: str = "",
    weight_pct: Optional[float] = None,
    qty: Optional[float] = None,
    metric: Any = None,
    calendar_events: Optional[list[dict[str, Any]]] = None,
    calendar_as_of: str = "",
    today: str = "",
    smartlab: Any = None,
    smartlab_as_of: str = "",
    smartlab_alias: bool = False,
    dohod: Any = None,
    dohod_as_of: str = "",
    fund_ter: Any = None,
    fund_ter_as_of: str = "",
) -> ReviewPayload:
    """Pure-ish builder (inject metric / calendar / smartlab / dohod / fund_ter for tests)."""
    tid = (ticker or "").strip().upper()
    k = (kind or "equity").strip().lower()
    if k not in ("equity", "bond", "fund"):
        k = "equity"
    today = today or datetime.now(_TZ).date().isoformat()
    as_of_m = _as_of_now()
    if metric is not None and getattr(metric, "updatetime", ""):
        as_of_m = str(metric.updatetime)[:16] or as_of_m
    as_of_sl = smartlab_as_of or as_of_m
    as_of_dh = dohod_as_of or as_of_m
    as_of_ter = fund_ter_as_of or as_of_m

    sector = resolve_sector(tid, category)
    pos_bits = ["уже в портфеле"]
    if qty is not None:
        pos_bits.append(f"qty { _fmt_num(float(qty), decimals=4) or qty }")
    if weight_pct is not None:
        pos_bits.append(f"доля {_fmt_num(float(weight_pct), decimals=2)}%")
    pos_bits.append("кэш на добор: вручную (нет источника)")
    position_line = " · ".join(pos_bits)

    fields: list[ReviewField] = []
    events = calendar_events or []

    if k == "bond":
        m = metric
        d = dohod
        coup = None
        if m is not None and getattr(m, "coupon_percent", None) is not None:
            coup = _fmt_num(m.coupon_percent, pct=True)
        elif m is not None and getattr(m, "coupon_value", None) is not None:
            coup = _fmt_num(m.coupon_value) + " ₽"
        elif d is not None and getattr(d, "coupon_rate", None) is not None:
            coup = _fmt_num(d.coupon_rate, pct=True)
        coup_src = "MOEX" if (m is not None and (getattr(m, "coupon_percent", None) is not None or getattr(m, "coupon_value", None) is not None)) else ("Dohod" if coup else "")
        fields.append(
            _field(
                "coupon",
                "Купон",
                value=coup,
                source=coup_src,
                as_of=as_of_m if coup_src == "MOEX" else as_of_dh,
            )
        )
        ctype = None
        ctype_src = ""
        if d is not None and getattr(d, "coupon_type", ""):
            ctype = str(d.coupon_type)
            ctype_src = "Dohod"
        fields.append(_field("coupon_type", "Фикс / флоат", value=ctype, source=ctype_src, as_of=as_of_dh if ctype else ""))
        nkd_val = _fmt_num(getattr(m, "accruedint", None) if m else None)
        nkd_src = "MOEX"
        if nkd_val is None and d is not None and getattr(d, "nkd", None) is not None:
            nkd_val = _fmt_num(d.nkd)
            nkd_src = "Dohod"
        fields.append(
            _field(
                "accrued",
                "НКД",
                value=nkd_val,
                source=nkd_src if nkd_val else "",
                as_of=(as_of_m if nkd_src == "MOEX" else as_of_dh) if nkd_val else "",
                unit="₽",
            )
        )
        last = _fmt_num(getattr(m, "last", None) if m else None)
        price_src = "MOEX"
        if last:
            last = last + "%"
        elif d is not None and getattr(d, "price", None) is not None:
            last = _fmt_num(d.price) + "%"
            price_src = "Dohod"
        fields.append(
            _field(
                "price",
                "Цена",
                value=last,
                source=price_src if last else "",
                as_of=(as_of_m if price_src == "MOEX" else as_of_dh) if last else "",
            )
        )
        mat = (getattr(m, "matdate", "") or "") if m else ""
        mat = mat[:10] if mat else ""
        mat_src = "MOEX" if mat else ""
        if not mat and d is not None and getattr(d, "maturity_date", ""):
            mat = str(d.maturity_date)[:10]
            mat_src = "Dohod"
        fields.append(
            _field("matdate", "Погашение", value=mat or None, source=mat_src, as_of=as_of_m if mat_src == "MOEX" else as_of_dh)
        )
        offer_v = None
        if d is not None and getattr(d, "offer_date", ""):
            note = getattr(d, "offer_note", "") or ""
            offer_v = str(d.offer_date)[:10]
            if note:
                offer_v = f"{offer_v} · {note}"
        fields.append(
            _field("offer", "Оферта", value=offer_v, source="Dohod" if offer_v else "", as_of=as_of_dh if offer_v else "")
        )
        ytm = _fmt_num(getattr(m, "yield_", None) if m else None, pct=True)
        ytm_s = f"{ytm} (от цены доски)" if ytm else None
        ytm_src = "MOEX" if ytm_s else ""
        if not ytm_s and d is not None and getattr(d, "ytm", None) is not None:
            ytm = _fmt_num(d.ytm, pct=True)
            note = getattr(d, "ytm_note", "") or ""
            ytm_s = f"{ytm} ({note})" if note else ytm
            ytm_src = "Dohod"
        fields.append(
            _field(
                "ytm",
                "Доходность (YTM)",
                value=ytm_s,
                source=ytm_src,
                as_of=(as_of_m if ytm_src == "MOEX" else as_of_dh) if ytm_s else "",
            )
        )
        rating_v = None
        if d is not None and getattr(d, "rating", ""):
            rating_v = str(d.rating)
            agency = getattr(d, "rating_agency", "") or ""
            if agency and agency not in rating_v:
                rating_v = f"{rating_v} · {agency}"
        fields.append(
            _field("rating", "Рейтинг", value=rating_v, source="Dohod" if rating_v else "", as_of=as_of_dh if rating_v else "")
        )
        lvl = getattr(m, "listlevel", None) if m else None
        fields.append(
            _field(
                "bond_class",
                "Класс",
                value=_bond_class(lvl) or None,
                source="MOEX",
                as_of=as_of_m,
            )
        )
        nxt = _next_calendar_event(events, tid, ("coupon",), today)
        if nxt:
            amt = nxt.get("amount")
            lab = str(nxt.get("pay_date") or "")[:10]
            if amt is not None:
                lab = f"{lab} · {_fmt_num(float(amt))} ₽"
            fields.append(
                _field(
                    "next_coupon",
                    "Ближ. купон",
                    value=lab,
                    source="calendar",
                    as_of=calendar_as_of or as_of_m,
                )
            )
        else:
            nc = (getattr(m, "next_coupon", "") or "") if m else ""
            if not nc and d is not None:
                # getbondinfo nextCouponDate not always mapped; skip
                nc = ""
            fields.append(
                _field(
                    "next_coupon",
                    "Ближ. купон",
                    value=nc[:10] or None,
                    source="MOEX" if nc else "",
                    as_of=as_of_m if nc else "",
                )
            )
        flags = list(_FLAG_STUBS_BOND)
        disp_name = name or (getattr(d, "name", "") if d else "") or (getattr(m, "shortname", "") if m else "") or tid
    elif k == "fund":
        m = metric
        theme = name or (getattr(m, "shortname", "") if m else "") or None
        fields.append(_field("theme", "Бенчмарк / тема", value=theme, source="BCS" if name else "MOEX", as_of=as_of_m))
        ter_txt = None
        ter_src = ""
        if fund_ter is not None:
            disp = getattr(fund_ter, "display", None)
            ter_txt = disp() if callable(disp) else None
            if not ter_txt:
                ter_txt = str(getattr(fund_ter, "uk_fee_raw", "") or "").strip() or None
            if ter_txt:
                ter_src = "ЦБ ПИФ"
        fields.append(
            _field(
                "ter",
                "TER / комиссия",
                value=ter_txt,
                source=ter_src,
                as_of=as_of_ter if ter_txt else "",
            )
        )
        flags = list(_FLAG_STUBS_FUND)
        disp_name = theme or tid
    else:
        # equity — sector slots; SmartLab fills multiples; MOEX div as fallback
        m = metric
        sl_map = _equity_from_smartlab(smartlab, preferred_alias=smartlab_alias, as_of=as_of_sl)
        filled: dict[str, tuple[Optional[str], str, str]] = {}
        # key → (value, source, as_of)
        for key, (val, src) in sl_map.items():
            filled[key] = (val, src, as_of_sl)
        if "div_yield" not in filled and m is not None and getattr(m, "div_yield", None) is not None:
            filled["div_yield"] = (_fmt_num(m.div_yield, pct=True), "MOEX", as_of_m)
        for key, label in _SECTOR_SLOTS.get(sector["id"], _SECTOR_SLOTS["unknown"]):
            trip = filled.get(key)
            if trip:
                val, src, ao = trip
                fields.append(_field(key, label, value=val, source=src, as_of=ao))
            else:
                fields.append(_field(key, label, value=None))
        nxt = _next_calendar_event(events, tid, ("dividend",), today)
        if nxt:
            lab = str(nxt.get("pay_date") or "")[:10]
            per = nxt.get("per_unit")
            if per is not None:
                lab = f"{lab} · {_fmt_num(float(per))} ₽/шт"
            fields.append(
                _field(
                    "next_div",
                    "Ближ. див.",
                    value=lab,
                    source="calendar",
                    as_of=calendar_as_of or as_of_m,
                )
            )
        else:
            fields.append(_field("next_div", "Ближ. див.", value=None))
        flags = list(_FLAG_STUBS_EQUITY)
        disp_name = name or (getattr(m, "name", "") if m else "") or tid

    isin_out = isin or (getattr(metric, "isin", "") if metric else "") or ""
    return ReviewPayload(
        ok=True,
        ticker=tid,
        kind=k,
        name=disp_name,
        isin=isin_out,
        sector=sector,
        position_line=position_line,
        fields=fields,
        flags=flags,
        verdict=None,
        updated_at=_now_ts(),
        mock=False,
    )


def load_review_cache(session: Session, ticker: str) -> Optional[tuple[dict[str, Any], float]]:
    tid = (ticker or "").strip().upper()
    row = session.get(ReviewCache, tid)
    if row is None or not (row.payload_json or "").strip():
        return None
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data, float(row.updated_at or 0.0)


def save_review_cache(session: Session, ticker: str, payload: dict[str, Any]) -> None:
    tid = (ticker or "").strip().upper()
    row = session.get(ReviewCache, tid)
    if row is None:
        row = ReviewCache(ticker=tid)
        session.add(row)
    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.updated_at = float(payload.get("updated_at") or _now_ts())
    row.ok = 1 if payload.get("ok") else 0
    session.commit()


def cache_is_fresh(updated_at: float, *, max_age: float = _CACHE_FRESH_SEC) -> bool:
    return updated_at > 0 and (_now_ts() - updated_at) < max_age


def review_cache_complete(data: dict[str, Any]) -> bool:
    """Reject stale-shaped payloads (e.g. fund without TER layer)."""
    if not isinstance(data, dict):
        return False
    kind = str(data.get("kind") or "").strip().lower()
    fields = data.get("fields")
    if not isinstance(fields, list):
        return False
    by_key = {
        str(f.get("key") or ""): f
        for f in fields
        if isinstance(f, dict)
    }
    if kind == "fund":
        ter = by_key.get("ter")
        if not isinstance(ter, dict):
            return False
        # Incomplete if TER slot exists but never filled after CBR layer shipped
        if ter.get("missing") and not (ter.get("value") or "").strip():
            # allow genuine missing (isin unknown) only when we already tried:
            # still force rebuild once by treating empty source+missing as incomplete
            # when as_of empty — old cache before CBR TER
            if not (ter.get("source") or "").strip() and not (ter.get("as_of") or "").strip():
                return False
    return True
