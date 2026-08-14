"""
Qwen3-TTS для micro wife (IDEA-013).

MVP: 0.6B CustomVoice + speaker Serena + instruct из voice_design.txt
(полноценный VoiceDesign = отдельная 1.7B модель, на 4GB легко OOM).

Не читает чужие mp3 — только текст design / preset.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TTS_ROOT = ROOT.parent
DESIGN_FILE = ROOT / "voice_design.txt"
DESIGNS_DIR = ROOT / "designs"
# #region agent log
_DBG_LOG = TTS_ROOT.parent / "debug-45ab72.log"


def _dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        payload = {
            "sessionId": "45ab72",
            "runId": "post-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DBG_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


# #endregion

# HuggingFace id — тянется при первом warmup
DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
DEFAULT_SPEAKER = "serena"  # warm gentle young female (id lowercase)
DEFAULT_LANGUAGE = "russian"

# Пресет design → базовый speaker CustomVoice (иначе всё звучит как Serena)
_DESIGN_SPEAKER: dict[str, str] = {
    "01_bright_male_theater.txt": "ryan",
    "02_soft_high_female.txt": "serena",
    "03_dark_male_suspense.txt": "uncle_fu",
    "04_neutral_baritone.txt": "uncle_fu",
    "05_adult_book_female.txt": "sohee",
}

_lock = threading.RLock()
_model = None
_model_id: str | None = None
_model_backend: str | None = None


def load_voice_design(path: str | Path | None = None) -> str:
    file_path = Path(path) if path else DESIGN_FILE
    if not file_path.is_absolute():
        cand = ROOT / file_path
        if cand.is_file():
            file_path = cand
        else:
            file_path = TTS_ROOT / file_path
    if not file_path.is_file():
        return ""
    return file_path.read_text(encoding="utf-8").strip()


def list_design_presets() -> list[tuple[str, str]]:
    """[(relative_path, label), ...] из designs/*.txt"""
    items: list[tuple[str, str]] = []
    if not DESIGNS_DIR.is_dir():
        return items
    labels = {
        "01_bright_male_theater.txt": "1 · яркий мужской (театр)",
        "02_soft_high_female.txt": "2 · мягкий высокий (micro wife)",
        "03_dark_male_suspense.txt": "3 · тёмный мужской (саспенс)",
        "04_neutral_baritone.txt": "4 · баритон-чтец",
        "05_adult_book_female.txt": "5 · взрослая книжная (не лоли)",
    }
    for path in sorted(DESIGNS_DIR.glob("*.txt")):
        rel = f"micro_wife/designs/{path.name}"
        items.append((rel, labels.get(path.name, path.stem)))
    return items


def speaker_for_design(design_file: str | Path | None) -> str:
    """Какой CustomVoice-speaker взять под design-файл."""
    if not design_file:
        return DEFAULT_SPEAKER
    name = Path(design_file).name
    return _DESIGN_SPEAKER.get(name, DEFAULT_SPEAKER)


def _pick_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


def _pick_dtype():
    import torch

    if torch.cuda.is_available():
        # float16 на 3050 даёт device-side assert в multinomial у qwen-tts;
        # bfloat16 стабилен, но на Laptop 3050 в замере был медленнее fp32 — оставляем fp32.
        # float32 жрёт больше VRAM, но стабильнее на Laptop 4GB.
        return torch.float32
    return torch.float32


def _enable_cuda_fast_paths() -> dict:
    """TF32 + cudnn.benchmark — бесплатный буст на Ampere (3050)."""
    import torch

    before = {
        "tf32": bool(getattr(torch.backends.cuda.matmul, "allow_tf32", False)),
        "cudnn_benchmark": bool(getattr(torch.backends.cudnn, "benchmark", False)),
    }
    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
    return {
        "tf32_before": before["tf32"],
        "cudnn_benchmark_before": before["cudnn_benchmark"],
        "tf32": bool(getattr(torch.backends.cuda.matmul, "allow_tf32", False)),
        "cudnn_benchmark": bool(getattr(torch.backends.cudnn, "benchmark", False)),
    }


def warmup(
    model_id: str | None = None,
    *,
    speaker: str | None = None,
) -> None:
    """Загрузить faster backend; официальный qwen_tts остаётся fallback."""
    global _model, _model_id, _model_backend
    mid = (model_id or DEFAULT_MODEL_ID).strip()
    with _lock:
        # #region agent log
        was_warm = _model is not None and _model_id == mid
        # #endregion
        if was_warm:
            # #region agent log
            _dbg(
                "A",
                "speak_qwen.py:warmup",
                "warmup_skip_already_loaded",
                {"model_id": mid, "was_warm": True},
            )
            # #endregion
            return
        import torch

        device = _pick_device()
        fast = _enable_cuda_fast_paths()
        # #region agent log
        t0 = time.perf_counter()
        vram_free = None
        try:
            if torch.cuda.is_available():
                free_b, total_b = torch.cuda.mem_get_info()
                vram_free = {
                    "free_gb": round(free_b / 1024**3, 2),
                    "total_gb": round(total_b / 1024**3, 2),
                }
        except Exception:
            pass
        # #endregion
        # На RTX 3050 benchmark: first chunk 6.2с, total 16с вместо ~87с.
        # 0.6B CustomVoice не поддерживает instruct ни в одном backend.
        try:
            if not device.startswith("cuda"):
                raise RuntimeError("faster-qwen3-tts requires CUDA")
            from faster_qwen3_tts import FasterQwen3TTS

            _model = FasterQwen3TTS.from_pretrained(
                mid,
                device="cuda",
                dtype=torch.bfloat16,
                attn_implementation="sdpa",
                max_seq_len=512,
            )
            _model.warmup(prefill_len=100)
            _model_backend = "faster"
            dtype = torch.bfloat16
        except Exception as fast_error:
            # Не оставляем частично захваченные CUDA graphs в тесных 4GB VRAM.
            _model = None
            _model_backend = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            from qwen_tts import Qwen3TTSModel

            dtype = _pick_dtype()
            _model = Qwen3TTSModel.from_pretrained(
                mid,
                device_map=device if device.startswith("cuda") else "cpu",
                dtype=dtype,
            )
            _model_backend = "official"
            print(
                f"faster-qwen3-tts unavailable, using official backend: {fast_error}",
                flush=True,
            )
        _model_id = mid
        _ = speaker  # reserved for future speaker-specific preload
        # #region agent log
        _dbg(
            "A,E",
            "speak_qwen.py:warmup",
            "warmup_cold_load",
            {
                "model_id": mid,
                "was_warm": False,
                "load_ms": int((time.perf_counter() - t0) * 1000),
                "device": device,
                "dtype": str(dtype).replace("torch.", ""),
                "backend": _model_backend,
                "tf32": fast.get("tf32"),
                "cudnn_benchmark": fast.get("cudnn_benchmark"),
                "fast_paths": fast,
                "vram": vram_free,
            },
        )
        # #endregion


def synthesize_wav(
    text: str,
    out_path: Path,
    *,
    design: str | None = None,
    design_file: str | Path | None = None,
    model_id: str | None = None,
    speaker: str | None = None,
    language: str | None = None,
) -> None:
    """Текст + instruct → WAV."""
    import soundfile as sf

    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")

    instruct = design if design is not None else load_voice_design(design_file)
    if not instruct:
        instruct = load_voice_design()
    mid = (model_id or DEFAULT_MODEL_ID).strip()
    if speaker:
        spk = speaker.strip().lower() or DEFAULT_SPEAKER
    else:
        spk = speaker_for_design(design_file).lower()
    lang = (language or DEFAULT_LANGUAGE).strip().lower() or DEFAULT_LANGUAGE

    with _lock:
        # #region agent log
        cold_before = _model is None or _model_id != mid
        t_all = time.perf_counter()
        # #endregion
        warmup(mid, speaker=spk)
        assert _model is not None
        # #region agent log
        t_gen = time.perf_counter()
        # #endregion
        wavs, sr = _model.generate_custom_voice(
            text=text,
            language=lang,
            speaker=spk,
            instruct=instruct,
        )
        # #region agent log
        gen_ms = int((time.perf_counter() - t_gen) * 1000)
        # #endregion
        audio = wavs[0]
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), audio, sr)
        # #region agent log
        audio_sec = float(len(audio) / max(sr, 1))
        _dbg(
            "B,F",
            "speak_qwen.py:synthesize_wav",
            "synth_done",
            {
                "cold_before": cold_before,
                "text_chars": len(text),
                "instruct_chars": len(instruct or ""),
                "speaker": spk,
                "backend": _model_backend,
                "generate_ms": gen_ms,
                "total_lock_ms": int((time.perf_counter() - t_all) * 1000),
                "audio_sec": round(audio_sec, 2),
                "rtf": round(gen_ms / 1000.0 / max(audio_sec, 0.01), 2),
                "out_bytes": out_path.stat().st_size if out_path.is_file() else 0,
            },
        )
        # #endregion
