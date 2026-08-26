"""faster-whisper backend for short RU PTT command clips (free / offline)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

LOG = logging.getLogger("voicemute_stt")

_model = None
_model_key = ""

# Lexicon bias — short tokens/phrases only (full sentences get echoed by Whisper).
COMMAND_PROMPT = (
    "замутить, размутить, размуть, замуть, "
    "уменьши звук, увеличь звук, тише, громче, "
    "уменьши звук пятого, увеличь звук второго, "
    "первого, второго, третьего, четвертого, пятого, всех, последнего"
)

HOTWORDS = (
    "уменьши звук,увеличь звук,тише,громче,"
    "уменьши звук пятого,увеличь звук второго,"
    "размутить всех,замутить всех,замутить,размутить,"
    "первого,второго,третьего,четвертого,пятого,всех,последнего"
)


def _cuda_usable() -> bool:
    """ctranslate2 may report CUDA devices even when cublas DLLs are missing."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:
        return False
    try:
        import ctypes

        for name in ("cublas64_12.dll", "cublas64_11.dll"):
            try:
                ctypes.WinDLL(name)
                return True
            except OSError:
                continue
        LOG.warning("CUDA GPU seen but cublas64_*.dll missing — using CPU")
        return False
    except Exception:
        return False


def _pick_device(prefer: str) -> tuple[str, str]:
    prefer = (prefer or "auto").lower()
    if prefer == "cpu":
        return "cpu", "int8"
    if prefer == "cuda":
        if _cuda_usable():
            return "cuda", "float16"
        LOG.warning("whisper_device=cuda but cublas unavailable — fallback CPU")
        return "cpu", "int8"
    # auto
    if _cuda_usable():
        return "cuda", "float16"
    return "cpu", "int8"


def load_whisper(model_size: str = "small", device: str = "auto") -> Any:
    global _model, _model_key
    from faster_whisper import WhisperModel

    dev, ctype = _pick_device(device)
    key = f"{model_size}:{dev}:{ctype}"
    if _model is not None and _model_key == key:
        return _model
    LOG.info("Loading WhisperModel %s device=%s compute=%s …", model_size, dev, ctype)
    _model = WhisperModel(model_size, device=dev, compute_type=ctype)
    _model_key = key
    LOG.info("Whisper ready (%s)", key)
    return _model


def _force_cpu_reload(model_size: str) -> Any:
    global _model, _model_key
    from faster_whisper import WhisperModel

    LOG.warning("Reloading Whisper on CPU after CUDA/runtime failure…")
    _model = WhisperModel(model_size, device="cpu", compute_type="int8")
    _model_key = f"{model_size}:cpu:int8"
    LOG.info("Whisper ready (%s)", _model_key)
    return _model


def pcm16_to_float32(pcm: bytes) -> np.ndarray:
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _run_transcribe(model: Any, audio: np.ndarray, language: str) -> str:
    # Short PTT: beam 1 is enough and much faster on CPU (~1s vs 2–3s)
    kwargs = dict(
        language=language,
        beam_size=1,
        best_of=1,
        patience=1.0,
        vad_filter=False,
        condition_on_previous_text=False,
        without_timestamps=True,
        initial_prompt=COMMAND_PROMPT,
        temperature=0.0,
    )
    try:
        segments, _info = model.transcribe(audio, hotwords=HOTWORDS, **kwargs)
    except TypeError:
        segments, _info = model.transcribe(audio, **kwargs)
    parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
    return " ".join(parts).strip()


def transcribe_pcm(
    pcm: bytes,
    *,
    model_size: str = "small",
    device: str = "auto",
    language: str = "ru",
) -> str:
    model = load_whisper(model_size, device)
    audio = pcm16_to_float32(pcm)
    if audio.size < 1600:  # <0.1s
        return ""

    # Short PTT: VAD often eats the whole utterance; pad to ~1.2s so model has context
    min_samples = int(16000 * 1.2)
    if audio.size < min_samples:
        audio = np.pad(audio, (0, min_samples - audio.size))

    try:
        return _run_transcribe(model, audio, language)
    except Exception as e:
        msg = str(e).lower()
        if "cublas" in msg or "cuda" in msg or "cudnn" in msg:
            LOG.exception("Whisper CUDA path failed — retry on CPU")
            model = _force_cpu_reload(model_size)
            return _run_transcribe(model, audio, language)
        raise
