"""
Бенч всех доступных движков: Edge, Silero, Kokoro, Vosk, Tera (+ Qwen опционально).
OpenAI пропускаем (дорого / нет ключа).

Запуск:
  python bench_all_tts.py
  python bench_all_tts.py --skip-heavy   # без Kokoro/Qwen/Tera download
  python bench_all_tts.py --with-qwen
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

PHRASE_SHORT = "Привет. Это проверка голоса Cursor TTS. Сравниваем движки."
PHRASE_MEDIUM = (
    "Сделали замер нескольких движков на одной фразе. Смотрим время до готового "
    "файла, длительность звука и real-time factor. Потом по уху и по цифрам решим дефолт."
)

MODELS_DIR = ROOT / "_bench_models"
VOSK_NAME = "vosk-model-tts-ru-0.9-multi"


def audio_duration_sec(path: Path) -> float:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return frames / float(rate)
    if suffix == ".mp3":
        size = path.stat().st_size
        return max(0.1, (size * 8) / 128_000.0)
    return 0.0


def timed(name: str, fn, out: Path) -> dict:
    t0 = time.perf_counter()
    try:
        fn(out)
        err = None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - t0
    if err:
        print(f"  FAIL {name}: {err} ({wall:.1f}s)")
        return {"engine": name, "ok": False, "wall_s": wall, "error": err}
    dur = audio_duration_sec(out)
    rtf = (wall / dur) if dur > 0.05 else None
    print(
        f"  OK   {name:<28} wall={wall:.2f}s  audio={dur:.2f}s  "
        f"RTF={rtf:.2f}  bytes={out.stat().st_size}"
        if rtf is not None
        else f"  OK   {name:<28} wall={wall:.2f}s  audio={dur:.2f}s  bytes={out.stat().st_size}"
    )
    return {
        "engine": name,
        "ok": True,
        "wall_s": wall,
        "audio_s": dur,
        "rtf": rtf,
        "bytes": out.stat().st_size,
    }


# --- engines ---

def ensure_vosk():
    from vosk_tts import Model, Synth

    # Model() качает по имени в свой кэш, если нет
    model = Model(model_name=VOSK_NAME)
    return Synth(model)


_vosk_synth = None


def synth_vosk(text: str, out: Path) -> None:
    global _vosk_synth
    if _vosk_synth is None:
        _vosk_synth = ensure_vosk()
    _vosk_synth.synth(text, str(out), speaker_id=2)


_tera = None


def ensure_tera():
    global _tera
    if _tera is not None:
        return _tera
    from transformers import AutoModel

    print("  … loading TeraTTSv2 (download + ONNX, может быть долго)")
    _tera = AutoModel.from_pretrained(
        "TeraSpace/TeraTTSv2",
        trust_remote_code=True,
        provider="CPUExecutionProvider",
        threads=max(2, (os.cpu_count() or 4) // 2),
    )
    return _tera


def synth_tera(text: str, out: Path) -> None:
    tts = ensure_tera()
    tagged = f"<ru>{text}</ru>"
    waveform = tts.generate_speech(tagged, voice="ru_f1", duration_scale=1)
    tts.save_wav(str(out), waveform)


def synth_edge(text: str, out: Path) -> None:
    from speak_edge_tts import synthesize_wav

    synthesize_wav(text, out, voice="ru-RU-SvetlanaNeural")


def synth_silero(text: str, out: Path) -> None:
    from speak_local import synthesize_wav

    synthesize_wav(text, "baya", out)


def synth_kokoro(text: str, out: Path) -> None:
    from speak_kokoro import synthesize_wav

    synthesize_wav(text, "sveta", out)


def synth_qwen(text: str, out: Path) -> None:
    micro = ROOT / "micro_wife"
    if str(micro) not in sys.path:
        sys.path.insert(0, str(micro))
    from speak_qwen import synthesize_wav, speaker_for_design

    design = "micro_wife/designs/02_soft_high_female.txt"
    synthesize_wav(
        text,
        out,
        design_file=design,
        speaker=speaker_for_design(design),
        language="russian",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true", help="без Kokoro/Tera/Qwen")
    ap.add_argument("--with-qwen", action="store_true", help="включить Qwen (VRAM)")
    ap.add_argument("--skip-tera", action="store_true")
    ap.add_argument("--skip-vosk", action="store_true")
    ap.add_argument("--skip-kokoro", action="store_true")
    args = ap.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="tts_bench_all_"))
    print(f"temp audio: {tmp}\n")

    engines: list[tuple[str, callable, str]] = [
        ("edge", synth_edge, ".mp3"),
        ("silero", synth_silero, ".wav"),
    ]
    if not args.skip_vosk:
        engines.append(("vosk", synth_vosk, ".wav"))
    if not args.skip_heavy and not args.skip_kokoro:
        engines.append(("kokoro", synth_kokoro, ".wav"))
    if not args.skip_heavy and not args.skip_tera:
        engines.append(("tera", synth_tera, ".wav"))
    if args.with_qwen and not args.skip_heavy:
        engines.append(("qwen", synth_qwen, ".wav"))

    print("Engines:", ", ".join(e for e, _, _ in engines))
    print("OpenAI: skip (не хочешь API/деньги)\n")

    all_rows: list[dict] = []
    for label, text in [("short", PHRASE_SHORT), ("medium", PHRASE_MEDIUM)]:
        print(f"=== {label} chars={len(text)} ===")
        for name, fn, suffix in engines:
            # cold
            out = tmp / f"{label}_{name}_cold{suffix}"
            r = timed(f"{name}/cold/{label}", lambda p, t=text, f=fn: f(t, p), out)
            all_rows.append(r)
            if not r["ok"]:
                continue
            # warm x2
            for i in (1, 2):
                out_w = tmp / f"{label}_{name}_w{i}{suffix}"
                r2 = timed(
                    f"{name}/warm{i}/{label}",
                    lambda p, t=text, f=fn: f(t, p),
                    out_w,
                )
                all_rows.append(r2)
        print()

    print("=== SUMMARY warm mean wall ===")
    by: dict[str, list[float]] = {}
    for r in all_rows:
        if not r.get("ok"):
            continue
        if "/cold/" in r["engine"]:
            continue
        parts = r["engine"].split("/")
        key = f"{parts[0]}/{parts[-1]}"
        by.setdefault(key, []).append(float(r["wall_s"]))
    for key in sorted(by):
        vals = by[key]
        mean = sum(vals) / len(vals)
        print(
            f"  {key:<22} n={len(vals)}  mean={mean:.2f}s  "
            f"min={min(vals):.2f}s  max={max(vals):.2f}s"
        )

    print(f"\nСлушать: {tmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
