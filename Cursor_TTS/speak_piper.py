"""
Локальный Piper TTS (ONNX): текст → wav.
Модель: Cursor_TTS/models/*.onnx (+ рядом .onnx.json).
Скачать: python download_piper_voice.py ru_RU-dmitri-medium
"""
from __future__ import annotations

import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / "models" / "ru_RU-dmitri-medium.onnx"

_lock = threading.RLock()
_voice = None
_voice_path: Path | None = None


def _resolve_model(model: str | Path | None) -> Path:
    if model is None or str(model).strip() == "":
        path = DEFAULT_MODEL
    else:
        path = Path(model)
        if not path.is_absolute():
            path = ROOT / path
    return path


def _load_voice(model_path: Path):
    global _voice, _voice_path
    from piper import PiperVoice

    if _voice is not None and _voice_path == model_path:
        return _voice
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Piper model not found: {model_path}\n"
            f"Run: python download_piper_voice.py {model_path.stem}"
        )
    json_path = Path(str(model_path) + ".json")
    if not json_path.is_file():
        raise FileNotFoundError(
            f"Piper config missing: {json_path}\n"
            "Download both .onnx and .onnx.json into Cursor_TTS/models/"
        )
    _voice = PiperVoice.load(str(model_path))
    _voice_path = model_path
    return _voice


def warmup(model: str | Path | None = None) -> None:
    with _lock:
        _load_voice(_resolve_model(model))


def synthesize_wav(text: str, model: str | Path | None, out_path: Path) -> None:
    """Синтез в WAV (16-bit mono)."""
    import wave

    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")

    with _lock:
        voice = _load_voice(_resolve_model(model))
        with wave.open(str(out_path), "wb") as wav_file:
            # piper-tts ≥1.2: synthesize_wav; старый API: synthesize
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(text, wav_file)
            else:
                voice.synthesize(text, wav_file)
