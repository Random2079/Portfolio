"""
Подготовка текста к озвучке: таблицы + знаки + словарь + ru-normalizr.
Языковая маршрутизация — до нормализации, иначе EN-фразы уничтожаются.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRONUNCIATIONS_FILE = ROOT / "pronunciations.json"

_MAX_TABLE_ROWS = 6
_MAX_CELL_CHARS = 90
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+._-]*")
_TOKEN = re.compile(
    r"[A-Za-z][A-Za-z0-9+._-]*|[А-Яа-яЁё]+|\d+|[\s]+|.",
)

_pron_mtime: float | None = None
_pron_cache: dict[str, str] = {}


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    lang: str  # "ru" | "en"


@lru_cache(maxsize=1)
def _normalizer():
    try:
        from ru_normalizr import Normalizer, NormalizeOptions

        return Normalizer(NormalizeOptions.tts())
    except Exception:
        return None


def load_pronunciations() -> dict[str, str]:
    """Ключи в нижнем регистре. Файл перечитывается при изменении mtime."""
    global _pron_mtime, _pron_cache
    path = PRONUNCIATIONS_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return dict(_pron_cache)
    if _pron_mtime == mtime and _pron_cache:
        return dict(_pron_cache)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return dict(_pron_cache)
    if not isinstance(raw, dict):
        return dict(_pron_cache)
    loaded: dict[str, str] = {}
    for key, value in raw.items():
        word = str(key).strip()
        spoken = str(value).strip()
        if word and spoken:
            loaded[word.lower()] = spoken
    _pron_cache = loaded
    _pron_mtime = mtime
    return dict(loaded)


def apply_pronunciations(text: str, vocab: dict[str, str] | None = None) -> str:
    """Замена целых слов без учёта регистра."""
    mapping = vocab if vocab is not None else load_pronunciations()
    if not mapping or not text:
        return text

    def repl(match: re.Match[str]) -> str:
        word = match.group(0)
        spoken = mapping.get(word.lower())
        return spoken if spoken else word

    keys = sorted(mapping.keys(), key=len, reverse=True)
    if not keys:
        return text
    pattern = r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)"
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def _clean_cell(value: str) -> str:
    value = re.sub(r"[*_`]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > _MAX_CELL_CHARS:
        value = value[: _MAX_CELL_CHARS - 1].rstrip() + "…"
    return value


def strip_code_and_diagrams(text: str) -> str:
    """Mermaid/схемы и code fences — не читать содержимое вслух."""
    text = re.sub(
        r"```mermaid[\s\S]*?```",
        " Есть схема, смотри в чате. ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"```[\s\S]*?```", " Блок кода, смотри в чате. ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


_STAGE_CUE_WORDS = (
    "вздох",
    "вздыхает",
    "вдох",
    "выдох",
    "пауза",
    "тишина",
    "смеется",
    "смеётся",
    "смех",
    "шепот",
    "шёпот",
    "кашель",
    "всхлип",
    "стон",
    "sigh",
    "pause",
    "breath",
    "whisper",
    "laugh",
)
_STAGE_CUE_RE = re.compile(
    r"(?i)\b(?:" + "|".join(re.escape(word) for word in _STAGE_CUE_WORDS) + r")\b"
)


def strip_stage_directions(text: str) -> str:
    """Убирает короткие ремарки вида *вздох* / (pause) / [sigh]."""

    def _repl(match: re.Match[str]) -> str:
        body = match.group(1)
        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", body)
        if not words:
            return " "
        # Удаляем только короткие ремарки; длинные скобки оставляем.
        if len(words) > 4:
            return match.group(0)
        joined = " ".join(words)
        return " " if _STAGE_CUE_RE.search(joined) else match.group(0)

    text = re.sub(r"\*{1,2}\s*([^*]{1,64}?)\s*\*{1,2}", _repl, text)
    text = re.sub(r"\(\s*([^)]{1,64}?)\s*\)", _repl, text)
    text = re.sub(r"\[\s*([^\]]{1,64}?)\s*\]", _repl, text)
    return text


def tables_to_speech(text: str) -> str:
    """
    Markdown-таблицы → короткие фразы.
    Каждая строка — отдельное предложение (граница для пауз/нарезки кусков).
    """
    lines = text.splitlines()
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if "|" not in line:
            result.append(line)
            i += 1
            continue

        block: list[str] = []
        while i < len(lines) and "|" in lines[i]:
            block.append(lines[i])
            i += 1

        rows: list[list[str]] = []
        for raw in block:
            cells = [_clean_cell(c) for c in raw.strip().strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-+:?", c or "") for c in cells):
                continue
            if any(cells):
                rows.append(cells)

        if len(rows) < 1:
            result.extend(block)
            continue

        headers = [_clean_cell(h) for h in rows[0]]
        body = rows[1:] if len(rows) > 1 else []
        result.append(_table_rows_to_speech(headers, body))

    return "\n".join(result)


def _table_rows_to_speech(headers: list[str], body: list[list[str]]) -> str:
    header_names = [h for h in headers if h]
    if not body:
        joined = ", ".join(header_names)
        return f"Столбцы: {joined}." if joined else ""

    sentences: list[str] = []
    if header_names:
        sentences.append("Столбцы: " + ", ".join(header_names) + ".")

    extra = 0
    for row_index, row in enumerate(body):
        if row_index >= _MAX_TABLE_ROWS:
            extra = len(body) - _MAX_TABLE_ROWS
            break
        cells = [(row[j] if j < len(row) else "").strip() for j in range(len(headers))]
        cells = [_clean_cell(c) for c in cells]
        values = [c for c in cells if c]
        if not values:
            continue
        if len(values) == 1:
            sentences.append(values[0].rstrip(".") + ".")
        else:
            sentences.append(
                f"{values[0]}: {', '.join(values[1:])}".rstrip(".") + "."
            )

    if extra > 0:
        sentences.append(f"И ещё {extra}.")

    return "\n".join(sentences)


def soften_symbols(text: str) -> str:
    """Стрелки, кавычки, списки — без вырезания латиницы и без словаря."""
    text = text.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")

    text = re.sub(r"-+>+", " затем ", text)
    text = re.sub(r"=+>+", " затем ", text)
    text = re.sub(r"[→⇒➔➜⟶]+", " затем ", text)
    text = re.sub(r"[←⇐⟵]+", " ", text)

    text = re.sub(r"(?m)^\s*[-*•·▪◦●○]+\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = text.replace("•", ". ").replace("·", ". ").replace("▪", ". ")

    text = text.replace("«", "").replace("»", "")
    text = text.replace("„", "").replace("“", "").replace("”", "")
    text = text.replace('"', "").replace("'", "").replace("`", "")

    text = text.replace("—", ", ").replace("–", ", ").replace("−", ", ")
    text = re.sub(r"\s*/\s*", " или ", text)
    text = re.sub(r"\s*\+\s*", " плюс ", text)

    text = re.sub(r"\(([^)]{1,120})\)", r", \1,", text)
    text = re.sub(r"\[([^\]]{1,120})\]", r", \1,", text)

    text = re.sub(r"[~^#_*=|\\<>]+", " ", text)
    text = re.sub(r"[…]{1,}", ". ", text)
    text = re.sub(r"[!]{2,}", "!", text)
    text = re.sub(r"[?]{2,}", "?", text)
    text = re.sub(r"[.]{3,}", ". ", text)
    text = re.sub(r"-{2,}", ", ", text)
    return text


def normalize_tts(text: str) -> str:
    """Латиница, аббревиатуры, числа — через ru-normalizr. Только RU-сегменты."""
    engine = _normalizer()
    if engine is None:
        return text
    try:
        return engine.normalize(text)
    except Exception:
        return text


def _collapse_ws(text: str) -> str:
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    text = re.sub(r"([,.]){2,}", r"\1", text)
    text = text.replace(" , ", ", ")
    return text.strip()


def _is_latin_word(token: str) -> bool:
    return bool(_LATIN_WORD.fullmatch(token))


def _latin_letter_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for ch in letters if ch.isascii())
    return latin / len(letters)


def _prepare_base(text: str) -> str:
    text = strip_code_and_diagrams(text)
    text = strip_stage_directions(text)
    text = tables_to_speech(text)
    return soften_symbols(text)


def segment_languages(
    text: str, vocab: dict[str, str] | None = None
) -> list[SpeechSegment]:
    """
    RU по умолчанию. 1–2 латинских токена / слово из словаря → RU.
    3+ подряд английских слова или ~60–70% латиницы в куске → EN.
    Знаки остаются при соседнем сегменте.
    """
    mapping = vocab if vocab is not None else load_pronunciations()
    text = text.strip()
    if not text:
        return []

    tokens = _TOKEN.findall(text)
    kinds: list[str] = []
    for tok in tokens:
        if _is_latin_word(tok):
            if tok.lower() in mapping:
                kinds.append("dict")
            else:
                kinds.append("en")
        else:
            kinds.append("other")

    en_run_len = [0] * len(tokens)
    i = 0
    while i < len(tokens):
        if kinds[i] != "en":
            i += 1
            continue
        j = i
        count = 0
        k = i
        while k < len(tokens):
            if kinds[k] == "en":
                count += 1
                j = k
                k += 1
                continue
            if tokens[k].strip() == "" or (
                kinds[k] == "other" and not any(ch.isalpha() or ch.isdigit() for ch in tokens[k])
            ):
                k += 1
                continue
            break
        for idx in range(i, j + 1):
            if kinds[idx] == "en":
                en_run_len[idx] = count
        i = j + 1

    langs: list[str] = []
    for idx, kind in enumerate(kinds):
        if kind == "en" and en_run_len[idx] >= 3:
            langs.append("en")
        else:
            langs.append("ru")

    # Кусок с высокой долей латиницы и без кириллицы → EN.
    latin_words = sum(1 for kind in kinds if kind in {"en", "dict"})
    has_cyr = any(
        any(("а" <= ch.lower() <= "я") or ch.lower() == "ё" for ch in tok)
        for tok, kind in zip(tokens, kinds)
        if kind == "other"
    )
    if latin_words >= 3 and _latin_letter_ratio(text) >= 0.6 and not has_cyr:
        langs = ["en"] * len(tokens)

    merged: list[SpeechSegment] = []
    buf = ""
    current: str | None = None
    for tok, lang in zip(tokens, langs):
        if current is None:
            current = lang
            buf = tok
            continue
        if lang == current:
            buf += tok
            continue
        piece = buf.strip()
        if piece:
            merged.append(SpeechSegment(piece, current))
        current = lang
        buf = tok
    if current is not None:
        piece = buf.strip()
        if piece:
            merged.append(SpeechSegment(piece, current))

    if not merged:
        return [SpeechSegment(text, "ru")]
    return merged


def finalize_speech_segments(text: str) -> list[SpeechSegment]:
    """Полная подготовка с языковыми сегментами. ru-normalizr только на RU."""
    base = _prepare_base(text)
    vocab = load_pronunciations()
    raw_segments = segment_languages(base, vocab)
    out: list[SpeechSegment] = []
    for seg in raw_segments:
        if seg.lang == "en":
            cleaned = _collapse_ws(seg.text)
            if cleaned:
                out.append(SpeechSegment(cleaned, "en"))
            continue
        ru = apply_pronunciations(seg.text, vocab)
        ru = normalize_tts(ru)
        ru = _collapse_ws(ru)
        if ru:
            out.append(SpeechSegment(ru, "ru"))
    return out


def finalize_speech_text(text: str, *, apply_dict: bool = True) -> str:
    """Один язык (edge/Silero/Piper dict_only): словарь + нормализация."""
    text = _prepare_base(text)
    if apply_dict:
        text = apply_pronunciations(text)
    text = normalize_tts(text)
    return _collapse_ws(text)
