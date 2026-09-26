"""F-B: one-shot DeepSeek ticker review from news (+ optional KS labels). No buy/sell."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from portfolio_news.ai_noise import (
    DEEPSEEK_MODEL,
    _ALLOWED_URGENCY,
    _call_deepseek,
    _now_local,
    extract_json_object,
)

PROMPT_SYSTEM = (
    "Ты помощник инвестора: one-shot разбор новостей по ОДНОМУ тикеру. "
    "Отвечаешь ТОЛЬКО валидным JSON, без markdown. "
    "Запрещено: купи/продавай, таргет цены, ордер, усредняй, докупай, "
    "«надо брать», прогноз цены. "
    "Только факты из новостей + вопросы к СВОЕЙ стратегии владельца."
)

PROMPT_REVIEW = """\
Тикер: {ticker}
Тип: {kind}
Имя: {name}
Сектор/ярлыки KS (если есть): {ks_labels}

Свежие новости (заголовки; id для ссылки):
{news_block}

Сделай one-shot разбор. Не чат. Не ордер.

Верни ТОЛЬКО JSON:
{{
  "ticker": "{ticker}",
  "summary": "1-2 предложения: о чём новости по сути",
  "hits": ["на что бьёт в бизнесе/балансе/рисках — коротко", "..."],
  "urgency": "low|mid|high",
  "checklist": ["вопрос к своей стратегии 1", "вопрос 2", "..."],
  "caveats": ["дыра в данных / мнение vs факт — если есть"]
}}

Правила:
- hits: 1–5 пунктов; только то, что следует из заголовков (не выдумывай цифры).
- checklist: 2–6 вопросов владельцу портфеля (чек-поинт), без «покупай».
- urgency: high только если явная срочность (оферта скоро, дефолт, допэмиссия, суд) из текста.
- Если новостей мало/шум — скажи в summary и в caveats; checklist всё равно дай.
- По-русски, коротко.
"""


def _str_list(value: Any, *, limit: int = 8, max_len: int = 160) -> list[str]:
    out: list[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        s = str(item or "").strip().replace("\n", " ")
        if not s:
            continue
        if len(s) > max_len:
            s = s[: max_len - 3] + "..."
        out.append(s)
        if len(out) >= limit:
            break
    return out


def parse_ticker_review(raw: str | dict, *, default_ticker: str = "") -> dict:
    """Normalize model JSON → review dict (no model/as_of yet)."""
    data = extract_json_object(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    ticker = str(data.get("ticker") or default_ticker or "").strip().upper()
    urgency = str(data.get("urgency") or "low").strip().lower()
    if urgency not in _ALLOWED_URGENCY:
        urgency = "mid"
    summary = str(data.get("summary") or "").strip().replace("\n", " ")
    if len(summary) > 400:
        summary = summary[:397] + "..."
    return {
        "ticker": ticker,
        "summary": summary,
        "hits": _str_list(data.get("hits"), limit=5),
        "urgency": urgency,
        "checklist": _str_list(data.get("checklist"), limit=6),
        "caveats": _str_list(data.get("caveats"), limit=4),
    }


def review_ticker_news(
    api_key: str,
    *,
    ticker: str,
    news: Sequence[dict],
    kind: str = "equity",
    name: str = "",
    ks_labels: str = "",
    model: str = DEEPSEEK_MODEL,
) -> dict:
    """Call DeepSeek once. news items: {id?, title, source?}."""
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY не задан")
    tid = (ticker or "").strip().upper()
    if not tid:
        raise ValueError("ticker required")

    lines: list[str] = []
    for it in news:
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        nid = it.get("id")
        source = str(it.get("source") or "").strip()
        prefix = f"id={nid} " if nid is not None else ""
        lines.append(f"- {prefix}source={source or '—'} title={title}")
    if not lines:
        lines.append("- (новостей нет — разбор по пустой ленте)")

    user = PROMPT_REVIEW.format(
        ticker=tid,
        kind=(kind or "equity").strip().lower() or "equity",
        name=(name or tid).strip(),
        ks_labels=(ks_labels or "—").strip() or "—",
        news_block="\n".join(lines[:25]),
    )
    raw = _call_deepseek(key, user, system=PROMPT_SYSTEM)
    parsed = parse_ticker_review(raw, default_ticker=tid)
    parsed["ticker"] = tid
    parsed["model"] = model
    as_of = _now_local()
    parsed["as_of"] = as_of.isoformat(timespec="seconds") if isinstance(as_of, datetime) else str(as_of)
    real_n = sum(1 for it in news if str(it.get("title") or "").strip())
    parsed["news_count"] = real_n
    return parsed
