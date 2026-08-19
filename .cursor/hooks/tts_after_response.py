"""
Cursor hook: afterAgentResponse → очередь в tts_daemon.
Читает JSON из stdin. Выключить: файл Cursor_TTS/TTS_OFF.
Текст только извлекается и режется по длине; финальная подготовка — в демоне (text_prep).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # DS_Projects
OFF_FLAG = ROOT / "Cursor_TTS" / "TTS_OFF"
PID_FILE = ROOT / "Cursor_TTS" / "tts_speech.pid"
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


def extract_text(data: dict) -> str:
    """На Windows берём чистый UTF-8 текст из транскрипта."""
    transcript = data.get("transcript_path")
    if transcript:
        path = Path(str(transcript))
        if path.is_file():
            text = read_last_assistant_message(path)
            if text:
                log(f"loaded assistant text from transcript: chars={len(text)}")
                return text

    text = str(data.get("text") or "")
    replacement_count = text.count("�") + text.count("?")
    if replacement_count:
        log(f"stdin text may be corrupted: bad_chars={replacement_count}")
    return text


MAX_SPEECH_CHARS = 12000


def speak_async(text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False
    ) as tmp:
        tmp.write(text)
        tmp_path = tmp.name

    flags = 0x08000000 if sys.platform == "win32" else 0
    speak_edge = ROOT / "Cursor_TTS" / "speak_edge.py"

    if speak_edge.is_file():
        process = subprocess.Popen(
            [sys.executable, str(speak_edge), tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        log(f"Edge-TTS client queued: pid={process.pid}, chars={len(text)}")
        return

    safe = tmp_path.replace("'", "''")
    safe_pid_file = str(PID_FILE).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = 1; $s.Volume = 100; "
        f"$t = Get-Content -LiteralPath '{safe}' -Raw -Encoding UTF8; "
        "$s.Speak($t); "
        f"Remove-Item -LiteralPath '{safe}' -Force -ErrorAction SilentlyContinue; "
        f"Remove-Item -LiteralPath '{safe_pid_file}' -Force -ErrorAction SilentlyContinue"
    )
    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    PID_FILE.write_text(str(process.pid), encoding="ascii")
    log(f"SAPI fallback started: pid={process.pid}, chars={len(text)}")


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
    gen = str(data.get("generation_id") or "")
    status = str(data.get("status") or "")
    if event == "stop" and status in {"aborted", "error"}:
        log(f"skip stop status={status}")
        return 0

    stamp = ROOT / "Cursor_TTS" / ".tts_last_generation"
    if gen and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == gen:
        log(f"skip duplicate generation event={event}")
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
        speak_async(text)
        if gen:
            stamp.write_text(gen, encoding="utf-8")
    except Exception as error:
        log(f"Speech failed: {type(error).__name__}: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
