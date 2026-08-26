"""
Анализ субтитров через DeepSeek API.

Режимы:
  - invest  — фильтр под чекпоинт Тё Яна (не «что купить»)
  - general — обычный ролик

Сохраняет ai_analysis.json рядом с субтитрами.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
import urllib.error
from pathlib import Path


class AnalyzeCancelled(Exception):
    """ИИ-разбор прерван пользователем (cancel_event)."""


DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_dotenv() -> None:
    """Подтянуть YouTube_Translator/.env в os.environ (без перезаписи уже заданных)."""
    if not _ENV_FILE.is_file():
        return
    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


def get_deepseek_api_key() -> str:
    _load_dotenv()
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY не задан. "
            "Создай YouTube_Translator/.env из .env.example (файл в .gitignore)."
        )
    return key


PROMPT_SYSTEM = (
    "Ты — фильтр инвест-контента под конкретный чекпоинт пользователя. "
    "Отвечаешь ТОЛЬКО валидным JSON, без markdown и без текста вне JSON. "
    "Не выдумывай цифры, тикеры, даты, оферты и факты, которых нет в субтитрах. "
    "Если чего-то нет в тексте — пиши, что не сказано. "
    "Запрещено выдавать торговый сигнал «с ролика» (купить/продать/усреднить)."
)

PROMPT_GENERAL = """\
Тебе дан текст субтитров (с таймкодами, если они есть).

Сделай разбор ролика для человека, который НЕ хочет смотреть всё целиком.

Верни ТОЛЬКО JSON объект:
{{
  "mode": "general",
  "content_kind": "general",
  "verdict_1_line": "одна строка: о чём и нужен ли вообще",
  "summary": "2-4 коротких абзаца",
  "takeaways": ["что уяснить", "что можно пропустить"],
  "opinions_ignore": ["шум / мнение"],
  "highlights": [{{"seconds": 42, "label": "зачем прыгнуть (3-8 слов)"}}]
}}

Правила:
- verdict_1_line и takeaways — главные.
- highlights: только если ясно зачем прыгать. Нет таймкодов → [].
- по-русски, коротко, без воды.

СУБТИТРЫ:
{text}
"""

# Чекпоинт пользователя (вшит в промпт — это НЕ универсальный аналитик)
PROMPT_INVEST = """\
Тебе дан текст субтитров. Разбери ролик ФИЛЬТРОМ чекпоинта ниже.
Цель НЕ «что купить». Цель: либо «можно забить», либо «одна конкретная дыра/риск/факт».

=== ЧЕКПОИНТ (обязательная логика) ===
1) Это инвест (эмитенты/сигналы) или образовалка (мышление/рамка)?
2) Какие КОНКРЕТНЫЕ утверждения: цифры, даты, оферты, рейтинги, отчёты — не вайб.
3) Это факт или мнение/прогноз?
4) Есть ли привязка к портфелю/секторам? Если нет — НЕ раздувать и НЕ натягивать.
5) Совпадает ли с правилами: отрасль, красные флаги, «бизнес для акционера»?
6) Не давят ли на усреднение / докупку без кэша?
7) Нет ли скрытой рекламы / первички / «успей» / идей из Telegram?
8) Что шум: биография автора, интро, мотивашки, макро-страшилки без бумаги, чужие P&L?
9) Если облигация: тикер+название, оферта/погашение, класс риска — иначе отметить дыру.
10) Финал action: ignore | hold_context | verify_primary — БЕЗ buy/sell сигнала с ролика.

КРАСНЫЕ ФЛАГИ (отмечай, если есть):
- голословно, без цифр и источника
- «точно вырастет / последнее дно / все богатые купили»
- инвестидея из Telegram / «закрытый канал»
- давление купить сейчас, без процедуры
- натягивание любой темы на портфель
- игнор менеджмента / допэмиссий / «бизнес не для акционера»
- ВДО/хвост ради купона, когда нет времени следить
- аналитик как гарантия (аналитики = шум, пока нет фактов)

ИГНОРИРУЙ В РАЗБОРЕ (в opinions_ignore):
биографию автора, длинное интро/подпишись/мотивашки, общие макро-страшилки
без бумаги, «я бы на твоём месте» без цифр, прогнозы ставки/нефти как сигнал к сделке,
чужие P&L и скрины успеха.

HIGHLIGHTS — не оглавление. Только:
- ядро или смена тезиса
- риски/оговорки, которые автор потом топит вайбом
- цифры и даты, которые можно проверить
- момент, где начинается реклама/сигнал
Не нужны: шутки, интро, повторы.

ВЕТКА EDUCATIONAL (если нет конкретных бумаг/сделок):
не натягивать на портфель. Дай: holds_up, framing, what_it_changes_in_thinking.
portfolio_link = none, action чаще ignore или hold_context.

ВЕТКА INVESTMENT:
verdict_1_line в духе: «контекст / шум / проверить эмитента X».
facts_usable — только то, что реально можно стыковать с портфелем или правилами.
Если назвали бумагу — сверка факта в verify_list, НЕ «купи ещё».

=== ФОРМАТ ОТВЕТА (только JSON) ===
{{
  "mode": "invest",
  "content_kind": "investment" | "educational",
  "verdict_1_line": "одна строка",
  "facts_usable": ["факт из текста", "..."],
  "opinions_ignore": ["что игнорить", "..."],
  "red_flags_seen": ["флаг", "..."],
  "checkpoint_fit": "match" | "conflict" | "n/a",
  "portfolio_link": "none" | "holdings" | "watch",
  "action": "ignore" | "hold_context" | "verify_primary",
  "verify_list": ["что сверить в первичке: SmartLab / MOEX / e-disclosure / ..."],
  "assets": ["тикер или название из текста"],
  "claims": ["конкретное утверждение автора"],
  "holds_up": "только educational: держится ли рамка",
  "framing": "только educational: какая рамка мышления",
  "what_it_changes_in_thinking": "только educational: на что влияет",
  "highlights": [
    {{"seconds": 42, "label": "тезис / риск / цифра / реклама"}}
  ]
}}

FORBIDDEN в ответе:
- buy/sell сигнал, «усредняй», «докупай», «успей»
- натягивание темы на тикеры, которых нет в тексте
- выдуманные цифры/даты

СУБТИТРЫ:
{text}
"""


def _prompt_for_mode(mode: str) -> tuple[str, str]:
    if mode == "invest":
        return PROMPT_SYSTEM, PROMPT_INVEST
    return PROMPT_SYSTEM, PROMPT_GENERAL


def _call_deepseek(
    text: str,
    mode: str = "invest",
    cancel_event: threading.Event | None = None,
) -> str:
    _system, user_tmpl = _prompt_for_mode(mode)
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": _system},
            {"role": "user", "content": user_tmpl.format(text=text)},
        ],
        "temperature": 0.2,
        "max_tokens": 2800,
    }).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {get_deepseek_api_key()}",
        },
        method="POST",
    )

    if cancel_event is not None and cancel_event.is_set():
        raise AnalyzeCancelled()

    # urlopen блокирует поток — крутим в фоне, чтобы cancel мог прервать ожидание
    box: dict = {"resp": None, "err": None}

    def _do_request() -> None:
        try:
            box["resp"] = urllib.request.urlopen(req, timeout=90)
        except Exception as exc:  # noqa: BLE001 — пробрасываем наружу через box
            box["err"] = exc

    worker = threading.Thread(target=_do_request, daemon=True)
    worker.start()
    while worker.is_alive():
        if cancel_event is not None and cancel_event.is_set():
            raise AnalyzeCancelled()
        worker.join(timeout=0.25)

    if cancel_event is not None and cancel_event.is_set():
        resp = box.get("resp")
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
        raise AnalyzeCancelled()

    if box["err"] is not None:
        exc = box["err"]
        if isinstance(exc, urllib.error.HTTPError):
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail[:300]}") from exc
        raise exc

    resp = box["resp"]
    if resp is None:
        raise RuntimeError("DeepSeek: пустой ответ")
    try:
        body = json.loads(resp.read().decode("utf-8"))
    finally:
        try:
            resp.close()
        except Exception:
            pass

    return body["choices"][0]["message"]["content"]


def _extract_json_object(raw: str) -> dict:
    raw = raw.strip()
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


def _str_list(value) -> list[str]:
    out: list[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        s = str(item).strip()
        if s:
            out.append(s)
    return out


_ALLOWED_ACTIONS = {"ignore", "hold_context", "verify_primary"}
_ALLOWED_FIT = {"match", "conflict", "n/a"}
_ALLOWED_LINK = {"none", "holdings", "watch"}
_ALLOWED_KIND = {"investment", "educational", "general"}


def _normalize(data: dict, mode: str) -> dict:
    mode = "invest" if mode == "invest" else "general"
    kind = str(data.get("content_kind") or ("investment" if mode == "invest" else "general")).strip()
    if kind not in _ALLOWED_KIND:
        kind = "investment" if mode == "invest" else "general"

    action = str(data.get("action") or "ignore").strip()
    if action not in _ALLOWED_ACTIONS:
        # старые/кривые ответы не превращаем в buy-сигнал
        action = "ignore"

    fit = str(data.get("checkpoint_fit") or "n/a").strip()
    if fit not in _ALLOWED_FIT:
        fit = "n/a"

    link = str(data.get("portfolio_link") or "none").strip()
    if link not in _ALLOWED_LINK:
        link = "none"

    highlights: list[dict] = []
    for item in data.get("highlights") or []:
        if not isinstance(item, dict):
            continue
        try:
            highlights.append({
                "seconds": int(item["seconds"]),
                "label": str(item.get("label", "")).strip(),
            })
        except (KeyError, ValueError, TypeError):
            continue

    verdict = str(data.get("verdict_1_line") or "").strip()
    summary = str(data.get("summary") or "").strip()
    # для UI: если summary пуст — подставляем вердикт
    if not summary and verdict:
        summary = verdict

    return {
        "mode": mode,
        "content_kind": kind,
        "verdict_1_line": verdict,
        "summary": summary,
        "facts_usable": _str_list(data.get("facts_usable")),
        "opinions_ignore": _str_list(data.get("opinions_ignore")),
        "red_flags_seen": _str_list(data.get("red_flags_seen")),
        "checkpoint_fit": fit,
        "portfolio_link": link,
        "action": action,
        "verify_list": _str_list(data.get("verify_list")),
        "assets": _str_list(data.get("assets")),
        "claims": _str_list(data.get("claims")),
        "takeaways": _str_list(data.get("takeaways")),
        "holds_up": str(data.get("holds_up") or "").strip(),
        "framing": str(data.get("framing") or "").strip(),
        "what_it_changes_in_thinking": str(
            data.get("what_it_changes_in_thinking") or ""
        ).strip(),
        "highlights": highlights,
    }


def analyze_subtitles(
    folder_path: str,
    status_cb=None,
    mode: str = "invest",
    cancel_event: threading.Event | None = None,
) -> dict:
    """mode: invest | general. cancel_event → AnalyzeCancelled, без записи json."""
    mode = "invest" if mode == "invest" else "general"

    def _emit(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    def _check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise AnalyzeCancelled()

    _check_cancel()

    timed_path = os.path.join(folder_path, "1_текст_с_таймкодами.txt")
    full_path = os.path.join(folder_path, "0_весь_текст_для_буфера.txt")

    if os.path.exists(timed_path):
        with open(timed_path, "r", encoding="utf-8") as f:
            text = f.read()
    elif os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        raise FileNotFoundError("Нет файлов субтитров в папке")

    if len(text) > 12_000:
        text = text[:12_000] + "\n...[обрезано]"

    _check_cancel()
    label = "инвест-фильтр" if mode == "invest" else "обычный"
    _emit(f"ИИ: разбор ({label}) → DeepSeek…")
    raw = _call_deepseek(text, mode=mode, cancel_event=cancel_event)
    _check_cancel()
    _emit("ИИ: получил ответ, разбираю…")

    result = _normalize(_extract_json_object(raw), mode)
    if mode == "invest":
        if not result["verdict_1_line"] and not result["facts_usable"] and not result["claims"]:
            raise ValueError("ИИ не вернул вердикт/факты")
    elif not result["summary"] and not result["takeaways"] and not result["verdict_1_line"]:
        raise ValueError("ИИ не вернул ни summary, ни тезисов")

    _check_cancel()
    result["source_folder"] = os.path.basename(folder_path)
    out_path = os.path.join(folder_path, "ai_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    legacy = os.path.join(folder_path, "ai_highlights.json")
    with open(legacy, "w", encoding="utf-8") as f:
        json.dump(result["highlights"], f, ensure_ascii=False, indent=2)

    _emit(
        f"ИИ: готово — {result.get('action', '?')} · "
        f"{len(result['highlights'])} моментов"
    )
    return result


def load_saved_analysis(folder_path: str) -> dict | None:
    """Читает ai_analysis.json, если есть (без API)."""
    path = os.path.join(folder_path, "ai_analysis.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
