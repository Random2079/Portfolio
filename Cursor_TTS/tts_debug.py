"""
Отладка TTS: пишет в Cursor_TTS/tts_debug.log
Смотри, когда озвучка споткнулась — какой кусок и почему.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEBUG_LOG = ROOT / "tts_debug.log"
LAST_CLEAN = ROOT / "tts_last_clean.txt"


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def debug_log(message: str) -> None:
    line = f"[{_stamp()}] {message}\n"
    try:
        with DEBUG_LOG.open("a", encoding="utf-8") as file:
            file.write(line)
    except OSError:
        pass


def save_last_clean(text: str) -> None:
    try:
        LAST_CLEAN.write_text(text, encoding="utf-8")
    except OSError:
        pass


def suspicious_chars(text: str) -> list[str]:
    """Символы, которые часто ломают TTS (не буквы/цифры/простая пунктуация)."""
    found: list[str] = []
    seen: set[str] = set()
    for ch in text:
        if ch.isalnum() or ch.isspace():
            continue
        if ch in ".,!?;:%+-":
            continue
        if ch in seen:
            continue
        seen.add(ch)
        code = f"U+{ord(ch):04X}"
        found.append(f"{ch!r} ({code})")
    return found


def log_clean_result(raw_preview: str, cleaned: str) -> None:
    save_last_clean(cleaned)
    bad = suspicious_chars(cleaned)
    debug_log(
        f"CLEAN chars={len(cleaned)} "
        f"suspicious={bad if bad else 'none'} "
        f"preview={cleaned[:180]!r}"
    )
    if raw_preview and raw_preview[:80] != cleaned[:80]:
        debug_log(f"RAW_PREVIEW={raw_preview[:180]!r}")


def log_chunk_ok(index: int, total: int, part: str) -> None:
    debug_log(f"CHUNK_OK {index}/{total} chars={len(part)} preview={part[:100]!r}")


def log_chunk_fail(index: int, total: int, part: str, error: BaseException) -> None:
    bad = suspicious_chars(part)
    debug_log(
        f"CHUNK_FAIL {index}/{total} "
        f"error={type(error).__name__}: {error} "
        f"suspicious={bad if bad else 'none'} "
        f"text={part[:240]!r}"
    )


def log_speak_start(chars: int, parts: int) -> None:
    debug_log(f"SPEAK_START chars={chars} parts={parts}")


def log_interrupted(reason: str = "new speak") -> None:
    debug_log(f"INTERRUPTED reason={reason}")


def log_speak_done(ok_parts: int, fail_parts: int, total_parts: int = 0) -> None:
    extra = f" total={total_parts}" if total_parts else ""
    debug_log(f"SPEAK_DONE ok={ok_parts} fail={fail_parts}{extra}")
