"""
Локальный TTS через Silero (без интернета после первой загрузки модели).
Модель кэшируется в памяти демона.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# 24k достаточно для речи и заметно быстрее 48k на CPU/GPU.
SAMPLE_RATE = 24000
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

        _synth_lock = threading.RLock()
    return _synth_lock


def _pick_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_model():
    """Ленивая загрузка Silero. Первый раз нужен интернет (скачать модель)."""
    global _model, _device
    with _get_synth_lock():
        if _model is not None:
            return _model

        import torch

        # Не жрать все ядра ноута — иначе UI/демоны душатся.
        try:
            torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
        except Exception:
            pass

        _device = _pick_device()
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
    import time

    import soundfile as sf
    import torch

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

        t0 = time.perf_counter()
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
        try:
            from tts_debug import debug_log

            debug_log(
                f"SILERO_SYNTH chars={len(text)} sec={time.perf_counter() - t0:.2f} "
                f"device={_device}"
            )
        except Exception:
            pass


def warmup() -> None:
    """Прогрев модели (+ крошечный synth на GPU, иначе первый Speak холодный)."""
    get_model()
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        synthesize_wav("Прогрев.", DEFAULT_LOCAL_SPEAKER, path)
    finally:
        path.unlink(missing_ok=True)
