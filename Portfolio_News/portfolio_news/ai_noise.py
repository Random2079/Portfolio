"""F-A: DeepSeek JSON-only noise filter for news feed (no buy/sell)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Sequence

log = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
_TZ = timezone(timedelta(hours=5))  # Asia/Yekaterinburg

_ALLOWED_LABELS = frozenset({"noise", "relevant", "dup"})
_ALLOWED_URGENCY = frozenset({"low", "mid", "high"})

PROMPT_SYSTEM = (
    "Ты фильтр новостной ленты портфеля. "
    "Отвечаешь ТОЛЬКО валидным JSON, без markdown и без текста вне JSON. "
    "Запрещено: купи/продавай, таргет цены, ордер, усредняй, докупай."
)

PROMPT_BATCH = """\
Классифицируй каждую новость для инвестора с портфелем.
Дан только заголовок, без текста статьи: не разгоняй urgency из кликбейта.

Метки label:
- noise — мусор / кликбейт / реклама / тех.спам / ставка/форум / не рыночный шум
- relevant — стоит глянуть: факт, отчёт, оферта, рейтинг, корпоративка по тикеру;
  ИЛИ геополитика/макро по России (война, эскалация, мир/перемирие, санкции, удары),
  если может двинуть рынок широко (MOEX / нефть / банки) — даже «без одной бумаги».
  Не ставь noise только потому что «макро без тикера».
- dup — смысл уже был / повтор той же истории другими словами

urgency только если label=relevant: low | mid | high.
high — только жёсткое событие из заголовка: оферта/техдефолт/дефолт/ковенанты,
суд/иск/банкротство, допэмиссия/SPO, санкции/налог/регуляторный удар прямо по тикеру/сектору.
Отчётность, дивиденды, размещение, макро/гео без явного удара — обычно mid/low, не high.
Слова «срочно», «обвал», «ракета», «важно» сами по себе не high.
Для рыночно-значимой геополитики по РФ предпочитай mid; high только при явной связи с рынком/сектором.
reason — коротко по-русски, ≤120 символов. Без торговых советов.

Верни ТОЛЬКО JSON:
{{
  "items": [
    {{"id": 1, "label": "noise|relevant|dup", "urgency": "low|mid|high|null", "reason": "..."}}
  ]
}}

Примеры:
- title="Лукойл опубликовал отчёт МСФО" → relevant, mid
- title="Эмитент допустил техдефолт по облигациям" → relevant, high
- title="Акции могут вырасти на 30%, идея аналитика" → noise, low/null
- title="Суд взыскал с эмитента крупный долг" → relevant, high

Новости:
{payload}
"""

_HIGH_EVENT_RE = re.compile(
    r"\b("
    r"тех\s*дефолт|техническ\w*\s+дефолт|дефолт|ковенант\w*|оферт\w*|"
    r"суд\w*|иск\w*|банкрот\w*|реструктуризац\w*|"
    r"допэмисс\w*|spo|размыти\w*|"
    r"санкци\w*|замороз\w*|арест\w*|"
    r"налог\w*|пошлин\w*|тариф\w*|цб|ключев\w+\s+ставк\w*"
    r")\b",
    re.I,
)

_CLICKBAIT_HIGH_RE = re.compile(
    r"\b(срочно|молния|ракета|обвал|паника|шок|важно|пора брать|идея|таргет)\b",
    re.I,
)


def high_allowed_from_title(title: str, *, kind: str = "") -> bool:
    """Guardrail: title-only F-A must not put `high` on pure clickbait."""
    t = (title or "").strip()
    if not t:
        return False
    if _HIGH_EVENT_RE.search(t):
        return True
    if _CLICKBAIT_HIGH_RE.search(t):
        return False
    return False


def calibrate_urgency(row: dict, item: dict) -> dict:
    """Post-model guard so News feed urgency matches F-B's stricter semantics."""
    if row.get("label") != "relevant" or row.get("urgency") != "high":
        return row
    if high_allowed_from_title(
        str(item.get("title") or ""),
        kind=str(item.get("kind") or ""),
    ):
        return row
    out = dict(row)
    out["urgency"] = "mid"
    reason = str(out.get("reason") or "").strip()
    suffix = "high снят: в заголовке нет жёсткого события"
    out["reason"] = (reason + "; " + suffix if reason else suffix)[:120]
    return out


def _now_local() -> datetime:
    return datetime.now(_TZ).replace(tzinfo=None)


def extract_json_object(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Не удалось найти JSON в ответе:\n{raw[:400]}")
    data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект")
    return data


def parse_classify_item(data: dict, *, default_id: Optional[int] = None) -> dict:
    """Normalize one model item → {id?, label, urgency, reason}."""
    if not isinstance(data, dict):
        raise ValueError("item must be object")
    label = str(data.get("label") or "").strip().lower()
    if label not in _ALLOWED_LABELS:
        raise ValueError(f"bad label: {label!r}")
    urg_raw = data.get("urgency")
    urgency: Optional[str] = None
    if label == "relevant":
        urgency = str(urg_raw or "mid").strip().lower()
        if urgency not in _ALLOWED_URGENCY:
            urgency = "mid"
    reason = str(data.get("reason") or "").strip().replace("\n", " ")
    if len(reason) > 120:
        reason = reason[:117] + "..."
    out: dict[str, Any] = {
        "label": label,
        "urgency": urgency,
        "reason": reason,
    }
    if "id" in data and data["id"] is not None:
        try:
            out["id"] = int(data["id"])
        except (TypeError, ValueError) as exc:
            raise ValueError("bad id") from exc
    elif default_id is not None:
        out["id"] = int(default_id)
    return out


def parse_classify_response(raw: str | dict) -> list[dict]:
    """Parse model JSON (object with items[] or single item) → list of normalized dicts."""
    data = extract_json_object(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    if "items" in data:
        items = data.get("items") or []
        if not isinstance(items, list):
            raise ValueError("items must be list")
        return [parse_classify_item(x) for x in items if isinstance(x, dict)]
    if "label" in data:
        return [parse_classify_item(data)]
    raise ValueError("expected items[] or label")


def _call_deepseek(
    api_key: str,
    user_content: str,
    *,
    system: str | None = None,
    timeout: int = 90,
    kind: str = "news_classify",
) -> str:
    payload = json.dumps(
        {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system or PROMPT_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 2000,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail[:300]}") from exc
    from portfolio_news.ai_usage import record_usage

    record_usage(kind, body.get("usage") if isinstance(body, dict) else None)
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("DeepSeek: пустой/кривой ответ") from exc


def classify_news_batch(
    api_key: str,
    items: Sequence[dict],
    *,
    model: str = DEEPSEEK_MODEL,
) -> list[dict]:
    """Classify a batch. Each item: {id, ticker, title, source?, kind?, name?, role?}.

    Returns list of {id, label, urgency, reason, model, as_of}.
    """
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY не задан")
    if not items:
        return []

    lines = []
    for it in items:
        nid = int(it["id"])
        ticker = str(it.get("ticker") or "").strip()
        title = str(it.get("title") or "").strip()
        source = str(it.get("source") or "").strip()
        kind = str(it.get("kind") or "").strip()
        name = str(it.get("name") or "").strip()
        role = str(it.get("role") or "").strip()
        lines.append(
            " ".join(
                [
                    f"- id={nid}",
                    f"ticker={ticker}",
                    f"kind={kind or '—'}",
                    f"name={name or '—'}",
                    f"role={role or '—'}",
                    f"source={source or '—'}",
                    f"title={title}",
                ]
            )
        )
    user = PROMPT_BATCH.format(payload="\n".join(lines))
    raw = _call_deepseek(key, user)
    parsed = parse_classify_response(raw)
    by_id = {p["id"]: p for p in parsed if "id" in p}
    as_of = _now_local()
    out: list[dict] = []
    for it in items:
        nid = int(it["id"])
        if nid not in by_id:
            log.warning("ai_noise: missing id=%s in model response", nid)
            continue
        row = calibrate_urgency(dict(by_id[nid]), it)
        row["model"] = model
        row["as_of"] = as_of
        out.append(row)
    return out


def classify_news_item(
    api_key: str,
    *,
    news_id: int,
    ticker: str,
    title: str,
    source: str = "",
    kind: str = "",
    name: str = "",
    role: str = "",
) -> dict:
    rows = classify_news_batch(
        api_key,
        [
            {
                "id": news_id,
                "ticker": ticker,
                "title": title,
                "source": source,
                "kind": kind,
                "name": name,
                "role": role,
            }
        ],
    )
    if not rows:
        raise RuntimeError("модель не вернула классификацию")
    return rows[0]
