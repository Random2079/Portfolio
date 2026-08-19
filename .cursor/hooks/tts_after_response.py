"""
Cursor hook: afterAgentResponse → очередь в tts_daemon.
Читает JSON из stdin. Выключить: файл Cursor_TTS/TTS_OFF.
Текст только извлекается и режется по длине; финальная подготовка — в демоне (text_prep).
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # DS_Projects
OFF_FLAG = ROOT / "Cursor_TTS" / "TTS_OFF"
LOG_FILE = Path(tempfile.gettempdir()) / "cursor_tts_hook.log"
sys.path.insert(0, str(ROOT / "Cursor_TTS"))
try:
    from tts_debug import log_clean_result
except ImportError:
    def log_clean_result(raw_preview: str, cleaned: str) -> None:
        return None


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")



def read_hook_payload() -> dict:
    """Читает JSON от Cursor. На Windows stdin часто кривой — логируем сырьё."""
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    raw = sys.stdin.read()
    log(f"stdin chars={len(raw)} preview={raw[:120]!r}")

    if not raw.strip():
        raise ValueError("stdin empty")

    raw = raw.lstrip("\ufeff").strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("payload is not an object")
    return data


def read_last_assistant_message(path: Path) -> str:
    """Берёт последний нормальный ответ assistant из JSONL-транскрипта."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if item.get("role") != "assistant":
            continue

        content = item.get("message", {}).get("content", [])
        text_parts = [
            part.get("text", "")
            for part in content
            if part.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if part.strip())
        if text:
            return text

    return ""


# Cursor на Windows отдаёт текст как UTF-8 байты, декодированные через cp1251.
# Такие пары встречаются в любой кириллице, покалеченной этим способом.
_MOJIBAKE_MARKERS = ("Рµ", "Рѕ", "РЅ", "СЂ", "СЃ", "Рё", "РІ", "Р°", "вЂ")


def fix_mojibake(text: str) -> str:
    """Разворачивает utf-8-как-cp1251 обратно. Не трогает нормальный текст."""
    if not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text

    # Построчно: одна нерасшифруемая строка не должна ронять весь текст.
    out = []
    for line in text.split("\n"):
        try:
            out.append(line.encode("cp1251").decode("utf-8"))
        except UnicodeError:
            out.append(line)
    return "\n".join(out)


def extract_text(data: dict) -> str:
    """Сначала прямой payload text, transcript — только fallback."""
    text = str(data.get("text") or "").strip()
    if text:
        text = fix_mojibake(text)
        log(f"loaded assistant text from payload: chars={len(text)}")
        return text

    transcript = data.get("transcript_path")
    if transcript:
        path = Path(str(transcript))
        if path.is_file():
            text = read_last_assistant_message(path)
            if text:
                log(f"loaded assistant text from transcript: chars={len(text)}")
                return text

    text = str(data.get("text") or "")
    replacement_count = text.count("") + text.count("?")
    if replacement_count:
        log(f"stdin text may be corrupted: bad_chars={replacement_count}")
    return text


MAX_SPEECH_CHARS = 12000


def enqueue_auto(text: str, data: dict) -> None:
    from speak_edge import ensure_daemon, send_command

    ensure_daemon()
    payload = {
        "cmd": "enqueue_auto",
        "entry": {
            "text": text,
            "conversation_id": str(data.get("conversation_id") or ""),
            "generation_id": str(data.get("generation_id") or ""),
            "source": str(data.get("hook_event_name") or "afterAgentResponse"),
        },
    }
    reply = send_command(payload, timeout=5.0)
    if not reply.get("ok"):
        raise RuntimeError(str(reply.get("error") or "enqueue_auto failed"))
    log(
        "Edge-TTS auto queued: "
        f"chars={len(text)} conv={payload['entry']['conversation_id'][:12]} "
        f"gen={payload['entry']['generation_id'][:12]} "
        f"source={payload['entry']['source']}"
    )


def main() -> int:
    log("Hook invoked")

    if OFF_FLAG.exists():
        log("TTS disabled by TTS_OFF")
        return 0

    try:
        data = read_hook_payload()
    except Exception as error:
        log(f"Payload failed: {type(error).__name__}: {error}")
        return 0

    event = str(data.get("hook_event_name") or "")
    status = str(data.get("status") or "")

    if event == "stop":
        try:
            from speak_edge import ensure_daemon, send_command

            ensure_daemon()
            send_command({"cmd": "stop"}, timeout=2.0)
            log(f"hook stop -> daemon stop (status={status})")
        except Exception as error:
            log(f"hook stop failed: {type(error).__name__}: {error}")
        return 0

    text = extract_text(data).strip()

    log_clean_result(text[:200], text[:200])
    if len(text) < 8:
        log(f"Text too short: chars={len(text)}")
        return 0

    if len(text) > MAX_SPEECH_CHARS:
        text = text[:MAX_SPEECH_CHARS] + " … дальше слишком длинно, обрезано."
        log(f"Text capped at {MAX_SPEECH_CHARS} chars")

    try:
        enqueue_auto(text, data)
    except Exception as error:
        log(f"Speech failed: {type(error).__name__}: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
