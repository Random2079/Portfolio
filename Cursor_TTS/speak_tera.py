"""
TeraTTSv2 (локальный ONNX RU TTS).
Модель: TeraSpace/TeraTTSv2 (кэш HuggingFace).
Темп: duration_scale — больше = медленнее, меньше = быстрее (дефолт 1.0).
Первый load в процесс демона часто 30–90 с — это норма, не зависон.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

DEFAULT_VOICE = "ru_f1"
DEFAULT_DURATION_SCALE = 1.0
PANEL_VOICES = [
    ("ru_f1", "Tera · жен. ru_f1"),
    ("ru_f2", "Tera · жен. ru_f2"),
    ("ru_m5", "Tera · муж. ru_m5"),
    ("ru_m1", "Tera · муж. ru_m1"),
]

_lock = threading.RLock()
_tts = None


def normalize_voice(voice: str | None) -> str:
    v = (voice or DEFAULT_VOICE).strip() or DEFAULT_VOICE
    known = {code for code, _ in PANEL_VOICES}
    return v if v in known else DEFAULT_VOICE


def normalize_duration_scale(value: float | None) -> float:
    try:
        scale = float(value if value is not None else DEFAULT_DURATION_SCALE)
    except (TypeError, ValueError):
        scale = DEFAULT_DURATION_SCALE
    return max(0.6, min(1.5, scale))


def _get_tts():
    global _tts
    with _lock:
        if _tts is not None:
            return _tts
        from transformers import AutoModel

        threads = max(2, (os.cpu_count() or 4) // 2)
        t0 = time.perf_counter()
        try:
            from tts_debug import debug_log

            debug_log("TERA load begin (ONNX into RAM)")
        except Exception:
            pass
        _tts = AutoModel.from_pretrained(
            "TeraSpace/TeraTTSv2",
            trust_remote_code=True,
            provider="CPUExecutionProvider",
            threads=threads,
        )
        try:
            from tts_debug import debug_log

            debug_log(f"TERA load done sec={time.perf_counter() - t0:.1f}")
        except Exception:
            pass
        return _tts


def warmup(voice: str | None = None, duration_scale: float | None = None) -> None:
    out = Path(__file__).resolve().parent / "_tera_warmup.wav"
    try:
        synthesize_wav(
            "Ок.",
            out,
            voice=normalize_voice(voice),
            duration_scale=normalize_duration_scale(duration_scale),
        )
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
    duration_scale: float | None = None,
    lang: str = "ru",
) -> None:
    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")
    # Tera требует теги: <ru>…</ru> или <en>…</en> (можно миксовать в одном вызове).
    if "<ru>" not in text and "<en>" not in text:
        tag = "en" if str(lang).strip().lower() == "en" else "ru"
        text = f"<{tag}>{text}</{tag}>"

    tts = _get_tts()
    voice_id = normalize_voice(voice)
    scale = normalize_duration_scale(duration_scale)
    with _lock:
        waveform = tts.generate_speech(
            text,
            voice=voice_id,
            duration_scale=scale,
        )
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tts.save_wav(str(out_path), waveform)
    if not out_path.is_file() or out_path.stat().st_size < 64:
        raise RuntimeError("tera returned empty audio")
