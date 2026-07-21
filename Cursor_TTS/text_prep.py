"""
Подготовка текста к озвучке: таблицы + знаки + ru-normalizr (режим TTS).
"""
from __future__ import annotations

import re
from functools import lru_cache

_CUSTOM = {
    "ИИ": "искусственный интеллект",
    "AHK": "авто хот кей",
    "Cursor": "курсор",
    "Silero": "силеро",
}

# Сколько строк таблицы читать вслух (остальное — «и ещё N»)
_MAX_TABLE_ROWS = 6
_MAX_CELL_CHARS = 90


@lru_cache(maxsize=1)
def _normalizer():
    try:
        from ru_normalizr import Normalizer, NormalizeOptions

        return Normalizer(NormalizeOptions.tts())
    except Exception:
        return None


def _clean_cell(value: str) -> str:
    value = re.sub(r"[*_`]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > _MAX_CELL_CHARS:
        value = value[: _MAX_CELL_CHARS - 1].rstrip() + "…"
    return value


def tables_to_speech(text: str) -> str:
    """
    Markdown-таблицы → короткие фразы.
    Было: «Таблица. Строка 1. Колонка: значение. …» (кринж и долго).
    Стало: «Piper: локально, хорошо. RHVoice: локально, средне.»
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

    # Один раз названия колонок, дальше только значения по строкам
    parts: list[str] = []
    if header_names:
        parts.append("Столбцы: " + ", ".join(header_names))

    extra = 0
    for row_index, row in enumerate(body):
        if row_index >= _MAX_TABLE_ROWS:
            extra = len(body) - _MAX_TABLE_ROWS
            break
        cells = [(row[j] if j < len(row) else "").strip() for j in range(len(headers))]
        cells = [_clean_cell(c) for c in cells if True]
        values = [c for c in cells if c]
        if not values:
            continue
        # первая ячейка — тема, остальные через запятую
        if len(values) == 1:
            parts.append(values[0])
        else:
            parts.append(f"{values[0]}: {', '.join(values[1:])}")

    if len(parts) <= (1 if header_names else 0):
        return (parts[0] + ".") if parts else ""

    text = ". ".join(parts) + "."
    if extra > 0:
        text += f" И ещё {extra}."
    return text


def soften_symbols(text: str) -> str:
    """Стрелки, кавычки, списки — без вырезания латиницы."""
    for src, dst in _CUSTOM.items():
        text = re.sub(rf"(?<!\w){re.escape(src)}(?!\w)", dst, text, flags=re.IGNORECASE)

    text = text.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")

    text = re.sub(r"-+>+", " потом ", text)
    text = re.sub(r"=+>+", " потом ", text)
    text = re.sub(r"[→⇒➔➜⟶]+", " потом ", text)
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
    """Латиница, аббревиатуры, числа — через ru-normalizr."""
    engine = _normalizer()
    if engine is None:
        return text
    try:
        return engine.normalize(text)
    except Exception:
        return text


def finalize_speech_text(text: str) -> str:
    text = tables_to_speech(text)
    text = soften_symbols(text)
    text = normalize_tts(text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([,.]){2,}", r"\1", text)
    text = text.replace(" , ", ", ")
    return text.strip()
