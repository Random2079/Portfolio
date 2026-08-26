"""NVIDIA Parakeet ASR (NeMo) — free offline multilingual STT incl. Russian."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

LOG = logging.getLogger("voicemute_stt")

_model = None
_model_name = ""
_device = ""

DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"


def _pick_torch_device(prefer: str) -> str:
    prefer = (prefer or "auto").lower()
    if prefer == "cpu":
        return "cpu"
    try:
        import torch

        if prefer == "cuda":
            if torch.cuda.is_available():
                return "cuda"
            LOG.warning("parakeet_device=cuda but torch.cuda unavailable — CPU")
            return "cpu"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def load_parakeet(model_name: str = DEFAULT_MODEL, device: str = "auto") -> Any:
    global _model, _model_name, _device
    name = (model_name or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    dev = _pick_torch_device(device)
    if _model is not None and _model_name == name and _device == dev:
        return _model

    LOG.info("Loading Parakeet %s on %s (first run downloads ~weights)…", name, dev)
    import nemo.collections.asr as nemo_asr

    asr = nemo_asr.models.ASRModel.from_pretrained(model_name=name)
    asr = asr.eval()
    try:
        asr = asr.to(dev)
    except Exception as e:
        LOG.warning("Parakeet .to(%s) failed (%s) — staying on default device", dev, e)
        dev = "cpu"
        try:
            asr = asr.to("cpu")
        except Exception:
            pass

    _model = asr
    _model_name = name
    _device = dev
    LOG.info("Parakeet ready (%s @ %s)", name, dev)
    return _model


def pcm16_to_float32(pcm: bytes) -> np.ndarray:
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _extract_text(out: Any) -> str:
    if out is None:
        return ""
    if isinstance(out, str):
        return out.strip()
    if isinstance(out, (list, tuple)):
        if not out:
            return ""
        return _extract_text(out[0])
    text = getattr(out, "text", None)
    if isinstance(text, str):
        return text.strip()
    if isinstance(out, dict) and "text" in out:
        return str(out["text"] or "").strip()
    return str(out).strip()


def transcribe_pcm(
    pcm: bytes,
    *,
    model_name: str = DEFAULT_MODEL,
    device: str = "auto",
    sample_rate: int = 16000,
) -> str:
    if not pcm or len(pcm) < 3200:  # <0.1s
        return ""

    model = load_parakeet(model_name, device)
    audio = pcm16_to_float32(pcm)
    # Short PTT: pad a bit so encoder has context
    min_samples = int(sample_rate * 0.8)
    if audio.size < min_samples:
        audio = np.pad(audio, (0, min_samples - audio.size))

    # Prefer in-memory if NeMo accepts ndarray; fallback to temp wav
    try:
        out = model.transcribe([audio], batch_size=1, verbose=False)
        text = _extract_text(out)
        if text:
            return text
    except Exception as e:
        LOG.debug("Parakeet ndarray transcribe failed, wav fallback: %s", e)

    import wave

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm)
        out = model.transcribe([str(path)], batch_size=1, verbose=False)
        return _extract_text(out)
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
