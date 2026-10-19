"""DeepSeek: fit + cover + price для заявки на Kwork."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"

# корень DS_Projects — рядом с HH_AutoApply
_DS_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_key_from_env_file(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == "DEEPSEEK_API_KEY":
            return v.strip().strip('"').strip("'")
    return ""


def load_deepseek_api_key() -> str:
    """DEEPSEEK_API_KEY из env или ближайших .env (не коммитить)."""
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key
    # DS_Projects/.env · рядом с проектом · Portfolio_News / YT (общие ключи на машине)
    candidates = [
        _DS_ROOT / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        _DS_ROOT / "Portfolio_News" / ".env",
        _DS_ROOT / "YouTube_Translator" / ".env",
    ]
    for env_path in candidates:
        key = _read_key_from_env_file(env_path)
        if key:
            return key
    return ""


def _clamp_price(price: int, cfg: dict[str, Any], budget: int | None) -> int:
    kw = cfg.get("kwork") or {}
    lo = int(kw.get("price_min_rub") or 5000)
    hi = int(kw.get("price_max_rub") or 120000)
    default = int(kw.get("price_default_rub") or 35000)
    p = int(price or default)
    if budget and budget > 0:
        # не выше бюджета заказа (если указан)
        hi = min(hi, max(lo, budget))
    return max(lo, min(hi, p))


def scrub_cover(text: str) -> str:
    """Убрать markdown / явные ИИ-маркеры (модерация биржи)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json|markdown|text)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    t = t.replace("**", "").replace("__", "")
    # выкинуть фразы-маркеры
    banned = (
        r"(?i)как (?:ии|нейросеть|языковая модель)",
        r"(?i)я (?:искусственный|ai|chatgpt|deepseek|gpt)",
        r"(?i)сгенерирован[ао]?",
    )
    for pat in banned:
        t = re.sub(pat, "", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:3500]


def _call_deepseek(
    api_key: str,
    *,
    system: str,
    user: str,
    model: str,
    temperature: float = 0.55,
    max_tokens: int = 1200,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
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
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail[:300]}") from exc
    try:
        from hh_auto.kwork_usage import record_usage

        record_usage("kwork_cover", body.get("usage") if isinstance(body, dict) else None)
    except Exception:
        pass
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("DeepSeek: пустой/кривой ответ") from exc


def _extract_json(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group(0))
        raise


SYSTEM_PROMPT = """Ты помогаешь фрилансеру написать заявку на бирже Kwork.
Ответь ТОЛЬКО JSON-объектом с полями:
fit (bool) — подходит ли заказ под стек Python / Playwright / боты / парсинг / автоматизация;
score (int 0-10) — насколько подходит;
price_rub (int) — цена в рублях в разумных пределах бюджета заказа;
days (int) — срок в днях;
cover (string) — текст предложения заказчику на русском.

Правила cover:
- пиши как живой человек, коротко (5–10 предложений), без канцелярита и без markdown;
- не упоминай ИИ, нейросети, Cursor, агентов, ChatGPT;
- не ври про коммерческий стаж в найме; можно про свои проекты и стек;
- обратись к сути ТЗ, что сделаешь и как;
- без эмодзи и без «рада сотрудничеству!!!».
Если заказ не про Python/автоматизацию/парсинг/ботов — fit=false, cover пустой."""


def propose_for_project(cfg: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Вернуть {fit, score, price_rub, days, cover, raw?} или fit=false при ошибке ключа."""
    api_key = load_deepseek_api_key()
    if not api_key:
        return {
            "fit": False,
            "score": 0,
            "price_rub": 0,
            "days": 0,
            "cover": "",
            "error": "no_deepseek_key",
        }

    kw = cfg.get("kwork") or {}
    model = str(kw.get("deepseek_model") or DEFAULT_MODEL)
    tags = cfg.get("profile_tags") or []
    bio = str(kw.get("bio") or "").strip()
    budget = project.get("budget_rub")
    default_price = int(kw.get("price_default_rub") or 35000)

    user = (
        f"Профиль: {bio}\n"
        f"Теги: {', '.join(tags[:25])}\n"
        f"Цена по умолчанию: {default_price} ₽\n"
        f"Бюджет заказа (если есть): {budget}\n\n"
        f"Заголовок: {project.get('title')}\n"
        f"Покупатель: {project.get('buyer')}\n"
        f"Описание:\n{(project.get('description') or '')[:3500]}\n"
    )

    try:
        raw = _call_deepseek(api_key, system=SYSTEM_PROMPT, user=user, model=model)
        data = _extract_json(raw)
    except Exception as exc:
        return {
            "fit": False,
            "score": 0,
            "price_rub": 0,
            "days": 0,
            "cover": "",
            "error": str(exc)[:300],
        }

    fit = bool(data.get("fit"))
    try:
        score = int(data.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    try:
        price = int(data.get("price_rub") or default_price)
    except (TypeError, ValueError):
        price = default_price
    try:
        days = int(data.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    cover = scrub_cover(str(data.get("cover") or ""))
    if not cover:
        fit = False

    return {
        "fit": fit,
        "score": score,
        "price_rub": _clamp_price(price, cfg, budget if isinstance(budget, int) else None),
        "days": max(1, min(60, days)),
        "cover": cover,
    }
