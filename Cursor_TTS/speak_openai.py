"""
OpenAI TTS (облако): быстрый эксперимент для повседневной озвучки.
Ключ: OPENAI_API_KEY в окружении или Cursor_TTS/.env
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DEFAULT_MODEL = "tts-1"
DEFAULT_VOICE = "nova"
OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
}
# Стабильный набор для панели (проверенные id tts-1)
PANEL_VOICES = [
    ("nova", "Nova (жен., яркий)"),
    ("shimmer", "Shimmer (жен., мягкий)"),
    ("alloy", "Alloy (нейтральный)"),
    ("echo", "Echo (муж.)"),
    ("onyx", "Onyx (муж., низкий)"),
    ("fable", "Fable (сторителлинг)"),
]


def _load_dotenv() -> None:
    if not ENV_FILE.is_file():
        return
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
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


def get_api_key() -> str:
    _load_dotenv()
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def normalize_voice(voice: str | None) -> str:
    v = (voice or DEFAULT_VOICE).strip().lower() or DEFAULT_VOICE
    known = {code for code, _ in PANEL_VOICES} | OPENAI_VOICES
    return v if v in known else DEFAULT_VOICE


def warmup(voice: str | None = None) -> None:
    """Проверка ключа + крошечный запрос (прогрев HTTP, не GPU)."""
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY не задан. Создай Cursor_TTS/.env с OPENAI_API_KEY=sk-..."
        )
    out = ROOT / "_openai_warmup.wav"
    try:
        synthesize_wav("Ок.", out, voice=normalize_voice(voice))
    finally:
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass


def synthesize_wav(
    text: str,
    out_path: Path,
    *,
    voice: str | None = None,
    model: str | None = None,
) -> None:
    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")
    # OpenAI лимит ~4096 символов на запрос
    if len(text) > 4000:
        text = text[:4000]

    key = get_api_key()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY не задан. Создай Cursor_TTS/.env с OPENAI_API_KEY=sk-..."
        )

    payload = {
        "model": (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "voice": normalize_voice(voice),
        "input": text,
        "response_format": "wav",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI TTS HTTP {error.code}: {detail}") from error

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio)
    if out_path.stat().st_size < 64:
        raise RuntimeError("OpenAI TTS returned empty audio")
