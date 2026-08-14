"""
Прототип micro wife: design → Qwen → wav → play + latency.
  python prototype_micro_wife.py
  python prototype_micro_wife.py "Привет, это проверка."
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speak_qwen import DEFAULT_MODEL_ID, load_voice_design, synthesize_wav, warmup


def main() -> int:
    text = " ".join(sys.argv[1:]).strip() or (
        "Привет. Это проверка голоса micro wife для Cursor TTS. Говорю спокойно и тепло."
    )
    design = load_voice_design()
    print("=== micro wife prototype ===")
    print(f"model: {DEFAULT_MODEL_ID}")
    print(f"design ({len(design)} chars):")
    print(design[:400] + ("…" if len(design) > 400 else ""))
    print("--- warmup ---")
    t0 = time.perf_counter()
    try:
        warmup()
    except Exception as exc:
        print(f"WARMUP FAIL: {exc}")
        print("Нужны: pip install -U qwen-tts и torch с CUDA (см. micro_wife/README.md)")
        return 1
    print(f"warmup: {time.perf_counter() - t0:.2f}s")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out = Path(tmp.name)
    t1 = time.perf_counter()
    try:
        synthesize_wav(text, out)
    except Exception as exc:
        print(f"SYNTH FAIL: {exc}")
        out.unlink(missing_ok=True)
        return 1
    synth_s = time.perf_counter() - t1
    print(f"synth: {synth_s:.2f}s  size={out.stat().st_size} bytes -> {out}")

    try:
        import os

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame

        pygame.mixer.init()
        t2 = time.perf_counter()
        pygame.mixer.music.load(str(out))
        pygame.mixer.music.play()
        print(f"play started (+{time.perf_counter() - t2:.3f}s after synth)")
        while pygame.mixer.music.get_busy():
            pygame.time.wait(40)
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
    finally:
        out.unlink(missing_ok=True)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
