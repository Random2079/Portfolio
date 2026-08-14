"""Изолированный benchmark faster-qwen3-tts; рабочий демон не меняет."""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parent
TTS_ROOT = ROOT.parent
LOG = TTS_ROOT.parent / "debug-45ab72.log"
OUT = ROOT / "faster_qwen_test.wav"
MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"


# #region agent log
def dbg(message: str, data: dict) -> None:
    payload = {
        "sessionId": "45ab72",
        "runId": "faster-qwen-benchmark",
        "hypothesisId": "H1,H2,H3",
        "location": "benchmark_faster_qwen.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
# #endregion


def vram() -> dict:
    free_b, total_b = torch.cuda.mem_get_info()
    return {
        "free_gb": round(free_b / 1024**3, 2),
        "used_gb": round((total_b - free_b) / 1024**3, 2),
        "total_gb": round(total_b / 1024**3, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=8)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--buffer-seconds", type=float, default=0.0)
    parser.add_argument("--dtype", choices=("bfloat16", "float16"), default="bfloat16")
    args = parser.parse_args()
    dtype = torch.bfloat16 if args.dtype == "bfloat16" else torch.float16

    # Освобождаем VRAM от штатного Qwen-демона перед отдельным benchmark.
    import sys

    if str(TTS_ROOT) not in sys.path:
        sys.path.insert(0, str(TTS_ROOT))
    from speak_edge import stop_daemon

    stop_daemon()
    # #region agent log
    dbg(
        "benchmark_start",
        {
            "gpu": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "dtype": args.dtype,
            "attention": "sdpa",
            "vram": vram(),
        },
    )
    # #endregion

    try:
        from faster_qwen3_tts import FasterQwen3TTS

        t0 = time.perf_counter()
        model = FasterQwen3TTS.from_pretrained(
            MODEL,
            device="cuda",
            dtype=dtype,
            attn_implementation="sdpa",
            max_seq_len=512,
        )
        load_ms = int((time.perf_counter() - t0) * 1000)
        # #region agent log
        dbg("model_loaded", {"load_ms": load_ms, "vram": vram()})
        # #endregion

        tw = time.perf_counter()
        model.warmup(prefill_len=100)
        warmup_ms = int((time.perf_counter() - tw) * 1000)
        # #region agent log
        dbg("cuda_graph_warmed", {"warmup_ms": warmup_ms, "vram": vram()})
        # #endregion

        text = (
            "Привет. Это потоковая проверка голоса Серены. "
            "Сейчас станет слышно, есть ли неприятные паузы между частями."
        )
        chunks: list[np.ndarray] = []
        first_ms: int | None = None
        sr = 24000
        play_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        player_thread: threading.Thread | None = None
        buffered: list[np.ndarray] = []
        buffered_seconds = 0.0

        def play_worker(sample_rate: int) -> None:
            import sounddevice as sd

            with sd.OutputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=1024,
            ) as stream:
                while True:
                    item = play_queue.get()
                    if item is None:
                        return
                    stream.write(np.asarray(item, dtype=np.float32).reshape(-1, 1))

        def start_player(sample_rate: int) -> None:
            nonlocal player_thread
            if player_thread is not None:
                return
            player_thread = threading.Thread(
                target=play_worker,
                args=(sample_rate,),
                name="qwen-stream-player",
                daemon=True,
            )
            player_thread.start()
            for item in buffered:
                play_queue.put(item)
            buffered.clear()

        tg = time.perf_counter()
        for audio, sr, timing in model.generate_custom_voice_streaming(
            text=text,
            language="russian",
            speaker="serena",
            chunk_size=args.chunk_size,
        ):
            if first_ms is None:
                first_ms = int((time.perf_counter() - tg) * 1000)
                # #region agent log
                dbg(
                    "first_audio_chunk",
                    {
                        "ttfa_ms": first_ms,
                        "chunk_samples": len(audio),
                        "timing": timing,
                    },
                )
                # #endregion
            chunks.append(np.asarray(audio, dtype=np.float32))
            if args.play:
                chunk = np.asarray(audio, dtype=np.float32)
                if player_thread is None:
                    buffered.append(chunk)
                    buffered_seconds += len(chunk) / max(sr, 1)
                    if buffered_seconds >= args.buffer_seconds:
                        start_player(sr)
                else:
                    play_queue.put(chunk)

        total_ms = int((time.perf_counter() - tg) * 1000)
        if args.play:
            start_player(sr)
            play_queue.put(None)
            if player_thread is not None:
                player_thread.join(timeout=60)
        combined = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        sf.write(str(OUT), combined, sr)
        audio_sec = len(combined) / max(sr, 1)
        # #region agent log
        dbg(
            "benchmark_done",
            {
                "total_ms": total_ms,
                "ttfa_ms": first_ms,
                "audio_sec": round(audio_sec, 2),
                "rtf_seconds_per_audio_second": round(
                    total_ms / 1000 / max(audio_sec, 0.01), 2
                ),
                "chunks": len(chunks),
                "chunk_size": args.chunk_size,
                "played_live": args.play,
                "buffer_seconds": args.buffer_seconds,
                "dtype": args.dtype,
                "output": str(OUT),
                "vram": vram(),
            },
        )
        # #endregion
        return 0
    except Exception as error:
        # #region agent log
        dbg(
            "benchmark_failed",
            {
                "error_type": type(error).__name__,
                "error": str(error),
                "vram": vram() if torch.cuda.is_available() else None,
            },
        )
        # #endregion
        raise


if __name__ == "__main__":
    raise SystemExit(main())
