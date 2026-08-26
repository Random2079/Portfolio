"""
Сравнение Edge vs OpenAI: время синтеза + длительность аудио + RTF.
Запуск: python bench_cloud_tts.py
Не коммитит, не трогает tts_config.json.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Типичный короткий ответ агента + чуть длиннее кусок
PHRASES = [
    (
        "short",
        "Привет. Это проверка голоса Cursor TTS. Сравниваем Edge и OpenAI.",
    ),
    (
        "medium",
        "Сделали замер двух облачных движков на одной фразе. Смотрим время до готового "
        "файла, длительность звука и real-time factor. Потом по уху и по цифрам решим, "
        "что ставить дефолтом для авто-озвучки ответов в Cursor.",
    ),
]

RUNS = 3  # после одного cold


def _audio_duration_sec(path: Path) -> float:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return frames / float(rate)
    if suffix == ".mp3":
        try:
            from mutagen.mp3 import MP3

            return float(MP3(str(path)).info.length)
        except Exception:
            pass
        # грубо: bitrate ~128kbps → bytes*8/128000
        size = path.stat().st_size
        return max(0.1, (size * 8) / 128_000.0)
    return 0.0


def _run_one(name: str, synth_fn, out: Path, text: str) -> dict:
    t0 = time.perf_counter()
    try:
        synth_fn(text, out)
        err = None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - t0
    if err:
        return {"engine": name, "ok": False, "wall_s": wall, "error": err}
    dur = _audio_duration_sec(out)
    size = out.stat().st_size
    rtf = (wall / dur) if dur > 0.05 else None
    return {
        "engine": name,
        "ok": True,
        "wall_s": wall,
        "audio_s": dur,
        "rtf": rtf,
        "bytes": size,
        "error": None,
    }


def main() -> int:
    from speak_edge_tts import synthesize_wav as synth_edge
    from speak_openai import get_api_key, synthesize_wav as synth_openai

    key = get_api_key()
    if not key:
        print("OPENAI_API_KEY нет в .env / окружении — OpenAI пропустим.")
        do_openai = False
    else:
        do_openai = True
        print(f"OpenAI key: …{key[-4:]} (len={len(key)})")

    print(f"VPN/сеть: меряем wall-clock синтеза (до готового файла), не pygame play.\n")

    rows: list[dict] = []
    tmp = Path(tempfile.mkdtemp(prefix="tts_bench_"))
    print(f"temp: {tmp}\n")

    for label, text in PHRASES:
        print(f"=== phrase={label} chars={len(text)} ===")
        # cold
        for engine, fn, suffix in [
            ("edge", lambda t, p: synth_edge(t, p, voice="ru-RU-SvetlanaNeural"), ".mp3"),
            (
                "openai",
                lambda t, p: synth_openai(t, p, voice="nova"),
                ".wav",
            ),
        ]:
            if engine == "openai" and not do_openai:
                continue
            out = tmp / f"{label}_{engine}_cold{suffix}"
            r = _run_one(f"{engine}/cold/{label}", fn, out, text)
            rows.append(r)
            _print_row(r)

        # warm repeats
        for i in range(1, RUNS + 1):
            for engine, fn, suffix in [
                (
                    "edge",
                    lambda t, p: synth_edge(t, p, voice="ru-RU-SvetlanaNeural"),
                    ".mp3",
                ),
                (
                    "openai",
                    lambda t, p: synth_openai(t, p, voice="nova"),
                    ".wav",
                ),
            ]:
                if engine == "openai" and not do_openai:
                    continue
                out = tmp / f"{label}_{engine}_w{i}{suffix}"
                r = _run_one(f"{engine}/warm{i}/{label}", fn, out, text)
                rows.append(r)
                _print_row(r)
        print()

    _summary(rows)
    print(f"\nФайлы для прослушки: {tmp}")
    print("Открой пару mp3/wav и сравни ухом; цифры — выше.")
    return 0


def _print_row(r: dict) -> None:
    if not r["ok"]:
        print(f"  FAIL {r['engine']}: {r['error']}  ({r['wall_s']:.2f}s)")
        return
    rtf = f"{r['rtf']:.2f}" if r["rtf"] is not None else "?"
    print(
        f"  OK   {r['engine']:<22} wall={r['wall_s']:.2f}s  "
        f"audio={r['audio_s']:.2f}s  RTF={rtf}  bytes={r['bytes']}"
    )


def _summary(rows: list[dict]) -> None:
    print("=== SUMMARY (warm only, mean wall) ===")
    by: dict[str, list[float]] = {}
    for r in rows:
        if not r["ok"]:
            continue
        if "/cold/" in r["engine"]:
            continue
        # edge/warm1/short → edge/short
        parts = r["engine"].split("/")
        key = f"{parts[0]}/{parts[-1]}"
        by.setdefault(key, []).append(float(r["wall_s"]))
    for key, vals in sorted(by.items()):
        mean = sum(vals) / len(vals)
        print(f"  {key:<20} n={len(vals)}  mean={mean:.2f}s  min={min(vals):.2f}s  max={max(vals):.2f}s")


if __name__ == "__main__":
    # не светить ключ в чужих логах
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
