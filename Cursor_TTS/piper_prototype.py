"""
Прототип Piper: текст → wav → play + замер времени до первого звука.
Запуск (после download_piper_voice.py):
  python piper_prototype.py
  python piper_prototype.py "Привет, это пайпер."
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speak_piper import DEFAULT_MODEL, synthesize_wav, warmup


def main() -> int:
    text = " ".join(sys.argv[1:]).strip() or (
        "Привет. Это проверка локального голоса Пайпер для Cursor TTS."
    )
    if not DEFAULT_MODEL.is_file():
        print(f"Model missing: {DEFAULT_MODEL}")
        print("Run: python download_piper_voice.py ru_RU-dmitri-medium")
        return 1

    print(f"Warmup model: {DEFAULT_MODEL.name}")
    t0 = time.perf_counter()
    warmup(DEFAULT_MODEL)
    print(f"  load: {time.perf_counter() - t0:.3f}s")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out = Path(tmp.name)

    t1 = time.perf_counter()
    synthesize_wav(text, DEFAULT_MODEL, out)
    synth_s = time.perf_counter() - t1
    print(f"  synth: {synth_s:.3f}s  size={out.stat().st_size} bytes")

    try:
        import pygame

        pygame.mixer.init()
        t2 = time.perf_counter()
        pygame.mixer.music.load(str(out))
        pygame.mixer.music.play()
        # «до первого звука» ≈ synth + load/play start (модель уже warm)
        print(f"  play started after synth+load: {synth_s + (time.perf_counter() - t2):.3f}s")
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
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
