"""
Локальный TTS через Silero (без интернета после первой загрузки модели).
Модель кэшируется в памяти демона.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
LOCAL_SPEAKERS = [
    ("xenia", "Ксения (жен.)"),
    ("baya", "Бая (жен.)"),
    ("kseniya", "Ксения-2 (жен.)"),
    ("aidar", "Айдар (муж.)"),
    ("eugene", "Евгений (муж.)"),
]
DEFAULT_LOCAL_SPEAKER = "xenia"

_model = None
_device = None
_synth_lock = None


def _get_synth_lock():
    global _synth_lock
    if _synth_lock is None:
        import threading

        _synth_lock = threading.Lock()
    return _synth_lock


def get_model():
    """Ленивая загрузка Silero. Первый раз нужен интернет (скачать модель)."""
    global _model, _device
    if _model is not None:
        return _model

    import torch

    _device = torch.device("cpu")
    _model, _example = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language="ru",
        speaker="v4_ru",
        trust_repo=True,
    )
    _model.to(_device)
    return _model


def synthesize_wav(text: str, speaker: str, wav_path: Path) -> None:
    import torch
    import soundfile as sf

    # Silero/torch не любят параллельные вызовы из разных потоков.
    with _get_synth_lock():
        model = get_model()
        speaker = (
            speaker
            if speaker in {code for code, _ in LOCAL_SPEAKERS}
            else DEFAULT_LOCAL_SPEAKER
        )
        text = text.strip()
        if len(text) > 900:
            text = text[:900]

        with torch.inference_mode():
            audio = model.apply_tts(
                text=text,
                speaker=speaker,
                sample_rate=SAMPLE_RATE,
            )

        if hasattr(audio, "cpu"):
            audio = audio.cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)
        sf.write(str(wav_path), audio, SAMPLE_RATE)


def warmup() -> None:
    """Прогрев модели при старте демона (опционально)."""
    get_model()
