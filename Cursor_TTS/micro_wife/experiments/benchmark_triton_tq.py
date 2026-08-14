"""
Изолированный эксперимент: Triton / Hybrid / Hybrid+TurboQuant.

НЕ трогает speak_qwen.py / демон / панель.
Отдельный venv: C:\\Users\\Home\\.venvs\\qwen_tq (--system-site-packages → torch от системы).

Запуск:
  C:\\Users\\Home\\.venvs\\qwen_tq\\Scripts\\python.exe micro_wife\\experiments\\benchmark_triton_tq.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # micro_wife
TTS_ROOT = ROOT.parent
OUT_DIR = ROOT / "experiments" / "out"
LOG = TTS_ROOT.parent / "debug-45ab72.log"
MODEL_06 = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
TEXT = (
    "Привет. Это проверка ускорения Qwen через Triton и TurboQuant. "
    "Говорю спокойно и тепло."
)
SPEAKER = "serena"


def dbg(message: str, data: dict) -> None:
    payload = {
        "sessionId": "45ab72",
        "runId": "triton-tq-bench",
        "hypothesisId": "TQ",
        "location": "benchmark_triton_tq.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    print(json.dumps({"msg": message, **data}, ensure_ascii=False), flush=True)


def vram() -> dict:
    import torch

    free_b, total_b = torch.cuda.mem_get_info()
    return {
        "free_gb": round(free_b / 1024**3, 2),
        "used_gb": round((total_b - free_b) / 1024**3, 2),
        "peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
        "total_gb": round(total_b / 1024**3, 2),
    }


def stop_tts_daemon() -> None:
    if str(TTS_ROOT) not in sys.path:
        sys.path.insert(0, str(TTS_ROOT))
    try:
        from speak_edge import stop_daemon

        stop_daemon()
        time.sleep(1.0)
    except Exception as exc:
        dbg("stop_daemon_skip", {"error": str(exc)})


def free_cuda() -> None:
    import torch
    import gc

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def bench_baseline_faster() -> dict:
    """Текущий прод-путь: FasterQwen3TTS BF16+SDPA+graphs, как speak_qwen."""
    import torch
    import soundfile as sf
    from faster_qwen3_tts import FasterQwen3TTS

    free_cuda()
    t_load = time.perf_counter()
    model = FasterQwen3TTS.from_pretrained(
        MODEL_06,
        device="cuda",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        max_seq_len=512,
    )
    model.warmup(prefill_len=100)
    load_s = time.perf_counter() - t_load

    # cold-ish after warmup already ran one graph path; measure second synth
    t0 = time.perf_counter()
    wavs, sr = model.generate_custom_voice(
        text=TEXT,
        language="Russian",
        speaker=SPEAKER,
    )
    gen_s = time.perf_counter() - t0
    audio = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
    import numpy as np

    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.squeeze()
    dur = float(len(arr) / float(sr))
    out = OUT_DIR / "tq_baseline_faster.wav"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), arr, int(sr))
    result = {
        "mode": "baseline_faster_0.6B",
        "load_s": round(load_s, 2),
        "gen_s": round(gen_s, 2),
        "audio_s": round(dur, 2),
        "rtf": round(gen_s / dur, 3) if dur > 0 else None,
        "vram": vram(),
        "wav": str(out),
    }
    del model
    free_cuda()
    return result


def _patch_range_for_model(model_id: str) -> tuple[int, int] | None:
    # 1.7B talker ~28 layers → upstream default (0, 24)
    # 0.6B меньше — патчим все слои
    if "0.6B" in model_id:
        return None
    return (0, 24)


def bench_hybrid(enable_tq: bool) -> dict:
    from qwen3_tts_triton import TritonFasterRunner
    import soundfile as sf
    import numpy as np

    free_cuda()
    mode = "hybrid+tq" if enable_tq else "hybrid"
    runner = TritonFasterRunner(
        model_id=MODEL_06,
        dtype="bf16",
        enable_turboquant=enable_tq,
        tq_bits=4,
        patch_range=_patch_range_for_model(MODEL_06),
    )
    t_load = time.perf_counter()
    runner.load_model()
    # прогрев CUDA graphs после патча
    try:
        if hasattr(runner.model, "warmup"):
            runner.model.warmup(prefill_len=100)
    except Exception as exc:
        dbg("warmup_warn", {"mode": mode, "error": str(exc)})
    load_s = time.perf_counter() - t_load

    t0 = time.perf_counter()
    result = runner.generate(
        text=TEXT,
        language="Russian",
        speaker=SPEAKER,
    )
    gen_s = time.perf_counter() - t0
    audio = result.get("audio")
    sr = int(result.get("sample_rate") or 24000)
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.squeeze()
    dur = float(len(arr) / float(sr))
    out = OUT_DIR / f"tq_{mode.replace('+', '_')}_0.6B.wav"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), arr, sr)
    info = {
        "mode": f"{mode}_0.6B",
        "load_s": round(load_s, 2),
        "gen_s": round(gen_s, 2),
        "audio_s": round(dur, 2),
        "rtf": round(gen_s / dur, 3) if dur > 0 else None,
        "vram": vram(),
        "peak_vram_gb": result.get("peak_vram_gb"),
        "rtf_reported": result.get("rtf"),
        "wav": str(out),
    }
    try:
        runner.unload_model()
    except Exception:
        pass
    free_cuda()
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modes",
        default="baseline,hybrid,hybrid_tq",
        help="comma list: baseline,hybrid,hybrid_tq",
    )
    args = parser.parse_args()
    want = {m.strip() for m in args.modes.split(",") if m.strip()}

    import torch

    if not torch.cuda.is_available():
        print("NO CUDA", flush=True)
        return 2

    dbg(
        "bench_start",
        {
            "gpu": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "modes": sorted(want),
            "vram": vram(),
        },
    )
    stop_tts_daemon()
    free_cuda()

    results: list[dict] = []
    for name, fn in (
        ("baseline", bench_baseline_faster),
        ("hybrid", lambda: bench_hybrid(False)),
        ("hybrid_tq", lambda: bench_hybrid(True)),
    ):
        if name not in want:
            continue
        print(f"\n=== {name} ===", flush=True)
        try:
            row = fn()
            results.append(row)
            dbg("bench_ok", row)
        except Exception as exc:
            err = {
                "mode": name,
                "error": str(exc),
                "traceback": traceback.format_exc()[-2000:],
            }
            results.append(err)
            dbg("bench_fail", err)
            free_cuda()

    summary = OUT_DIR / "tq_bench_summary.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
    print(f"wrote {summary}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
