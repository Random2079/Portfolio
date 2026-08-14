"""
Прототип kokoro-ru (Sveta): текст → wav + latency.
Отдельный Python 3.12 venv (kokoro не ставится на 3.13):
  C:\\Users\\Home\\.venvs\\kokoro312\\Scripts\\python.exe prototype_kokoro_ru.py
  ...\\python.exe prototype_kokoro_ru.py "Свой текст."
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ASSETS = Path(os.environ.get("KOKORO_RU_ASSETS", r"C:\Users\Home\.kokoro_ru")).resolve()
ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
VOICE = os.environ.get("KOKORO_RU_VOICE", "sveta")
SR = 24000

# ru_g2p.py + espeak-data лежат рядом в ASSETS
if str(ASSETS) not in sys.path:
    sys.path.insert(0, str(ASSETS))


def _ensure_assets() -> None:
    need = [
        ASSETS / "kokoro-ru-v2-base.pth",
        ASSETS / "kokoro-config.json",
        ASSETS / "ru_g2p.py",
        ASSETS / "voices" / f"{VOICE}.pt",
        ASSETS / "espeak-data",
    ]
    missing = [p for p in need if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Нет ассетов kokoro-ru. Скачай zaakirio/kokoro-ru в "
            f"{ASSETS}. Missing: " + ", ".join(str(p) for p in missing)
        )


def synthesize(text: str, out: Path) -> tuple[float, float, float]:
    """Return (load_s, synth_s, audio_s). load_s is 0 if model already warm."""
    import torch
    import soundfile as sf
    from kokoro import KModel
    from ru_g2p import RuG2P

    global _G2P, _MODEL, _PACK, _LOAD_S  # noqa: PLW0603

    if "_MODEL" not in globals() or _MODEL is None:
        t0 = time.perf_counter()
        _G2P = RuG2P()
        _MODEL = KModel(
            repo_id="hexgrad/Kokoro-82M",
            config=str(ASSETS / "kokoro-config.json"),
            model=str(ASSETS / "kokoro-ru-v2-base.pth"),
        ).eval()
        _PACK = torch.load(
            ASSETS / "voices" / f"{VOICE}.pt",
            map_location="cpu",
            weights_only=False,
        )
        _LOAD_S = time.perf_counter() - t0
    else:
        _LOAD_S = 0.0

    t1 = time.perf_counter()
    ipa, oov = _G2P(text)
    if oov:
        print(f"WARN OOV: {oov}")
    with torch.no_grad():
        audio = _MODEL(ipa, _PACK[len(ipa) - 1], 1.0, return_output=True).audio
    synth_s = time.perf_counter() - t1
    wav = audio.detach().cpu().numpy()
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), wav, SR)
    dur = len(wav) / SR
    return _LOAD_S, synth_s, dur  # type: ignore[return-value]


_G2P = None
_MODEL = None
_PACK = None
_LOAD_S = 0.0


def main() -> int:
    text = " ".join(sys.argv[1:]).strip() or (
        "Привет. Это проверка голоса Светы из kokoro-ru для Cursor TTS. "
        "Говорю спокойно и тепло, без пластикового акцента."
    )
    print("=== kokoro-ru prototype ===")
    print(f"assets: {ASSETS}")
    print(f"voice:  {VOICE}")
    print(f"text:   {text}")
    try:
        _ensure_assets()
    except FileNotFoundError as exc:
        print(f"ASSETS FAIL: {exc}")
        return 1

    out = SAMPLES / f"kokoro_{VOICE}_test.wav"
    try:
        load_s, _, _ = synthesize("Прогрев.", SAMPLES / f"kokoro_{VOICE}_warmup.wav")
        print(f"load+warmup g2p/model: {load_s:.2f}s")
        # второй проход — реальная скорость после прогрева
        load2, synth_s, audio_s = synthesize(text, out)
    except Exception as exc:
        print(f"SYNTH FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    rtf = synth_s / audio_s if audio_s > 0 else float("inf")
    print(f"warm synth: {synth_s:.2f}s  audio={audio_s:.2f}s  RTF={rtf:.3f}  ({(1/rtf) if rtf else 0:.1f}x realtime)")
    print(f"wav:   {out}  ({out.stat().st_size} bytes)")

    # Открыть в системном плеере — сразу слушаем
    try:
        os.startfile(str(out))  # type: ignore[attr-defined]
        print("opened with default player")
    except Exception as exc:
        print(f"open fail: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
