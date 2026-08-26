"""
Microsoft Edge online TTS (бесплатно, без OpenAI/санкций).
Нужен пакет: pip install edge-tts
"""
from __future__ import annotations

import asyncio
from pathlib import Path

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"
PANEL_VOICES = [
    ("ru-RU-SvetlanaNeural", "Светлана (Edge, жен.)"),
    ("ru-RU-DariyaNeural", "Дарья (Edge, жен.)"),
    ("ru-RU-DmitryNeural", "Дмитрий (Edge, муж.)"),
]


def normalize_voice(voice: str | None) -> str:
    v = (voice or DEFAULT_VOICE).strip() or DEFAULT_VOICE
    known = {code for code, _ in PANEL_VOICES}
    return v if v in known else DEFAULT_VOICE


def warmup(voice: str | None = None) -> None:
    """Лёгкая проверка: список голосов / импорт (без полного synth)."""
    try:
        import edge_tts  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "edge-tts не установлен. pip install edge-tts"
        ) from error
    # короткий synth — прогрев HTTP к Microsoft
    out = Path(__file__).resolve().parent / "_edge_warmup.mp3"
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
) -> None:
    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")
    try:
        import edge_tts
    except ImportError as error:
        raise RuntimeError(
            "edge-tts не установлен. pip install edge-tts"
        ) from error

    voice_id = normalize_voice(voice)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(str(out_path))

    asyncio.run(_run())
    if not out_path.is_file() or out_path.stat().st_size < 64:
        raise RuntimeError("edge-tts returned empty audio")
