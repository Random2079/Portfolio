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
Классифицируй каждую новость для инвестора с портфелем (тикер уже известен).

Метки label:
- noise — мусор / кликбейт / не про эмитента / макро-страшилка без бумаги / реклама
- relevant — стоит глянуть (факт, отчёт, оферта, рейтинг, корпоративка по тикеру)
- dup — смысл уже был / повтор той же истории другими словами

urgency только если label=relevant: low | mid | high.
reason — коротко по-русски, ≤120 символов. Без торговых советов.

Верни ТОЛЬКО JSON:
{{
  "items": [
    {{"id": 1, "label": "noise|relevant|dup", "urgency": "low|mid|high|null", "reason": "..."}}
  ]
}}

Новости:
{payload}
"""


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


def _call_deepseek(api_key: str, user_content: str, *, timeout: int = 90) -> str:
    payload = json.dumps(
        {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": PROMPT_SYSTEM},
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
    """Classify a batch. Each item: {id, ticker, title, source?}.

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
        lines.append(
            f"- id={nid} ticker={ticker} source={source or '—'} title={title}"
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
        row = dict(by_id[nid])
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
) -> dict:
    rows = classify_news_batch(
        api_key,
        [{"id": news_id, "ticker": ticker, "title": title, "source": source}],
    )
    if not rows:
        raise RuntimeError("модель не вернула классификацию")
    return rows[0]
