"""Offline bench: same WAV clips → several free engines. See docs/TZ-STT.md §4."""
from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPS = ROOT / "logs" / "clips"
OUT = ROOT / "logs" / "bench_free.md"


def read_wav_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        rate = w.getframerate()
        return w.readframes(w.getnframes()), rate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--engines", default="whisper", help="comma: whisper,vosk,google")
    ap.add_argument("--whisper-model", default="small")
    args = ap.parse_args()
    engines = [e.strip() for e in args.engines.split(",") if e.strip()]

    clips = sorted(CLIPS.glob("ptt_*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    clips = clips[: args.limit]
    if not clips:
        print("No clips in", CLIPS)
        return 1

    rows: list[str] = [
        "# Free STT bench",
        "",
        f"clips={len(clips)} engines={engines} whisper_model={args.whisper_model}",
        "",
        "| clip | engine | ms | text |",
        "|------|--------|----|------|",
    ]

    for clip in clips:
        pcm, rate = read_wav_pcm(clip)
        if rate != 16000:
            rows.append(f"| {clip.name} | — | — | skip rate={rate} |")
            continue
        for eng in engines:
            t0 = time.perf_counter()
            text = ""
            err = ""
            try:
                if eng == "whisper":
                    from whisper_engine import transcribe_pcm

                    text = transcribe_pcm(pcm, model_size=args.whisper_model, device="auto", language="ru")
                elif eng == "vosk":
                    from vosk import KaldiRecognizer, Model

                    from grammar_ru import grammar_json

                    model = Model(str(ROOT / "models" / "vosk-model-small-ru-0.22"))
                    rec = KaldiRecognizer(model, 16000, grammar_json())
                    rec.AcceptWaveform(pcm)
                    text = (json.loads(rec.FinalResult()).get("text") or "").strip()
                elif eng == "google":
                    from google_engine import transcribe_pcm as g

                    text = g(pcm, language="ru-RU")
                else:
                    err = f"unknown engine {eng}"
            except Exception as e:
                err = str(e)
            ms = (time.perf_counter() - t0) * 1000
            cell = err if err else (text or "∅")
            cell = cell.replace("|", "\\|")
            rows.append(f"| `{clip.name}` | {eng} | {ms:.0f} | {cell} |")
            print(f"{clip.name} [{eng}] {ms:.0f}ms → {cell}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("Wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
