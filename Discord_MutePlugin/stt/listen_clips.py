"""Re-listen recent PTT wav clips with vosk free + grammar."""
from __future__ import annotations

import array
import json
import math
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from grammar_ru import grammar_json  # noqa: E402
from vosk import KaldiRecognizer, Model, SetLogLevel  # noqa: E402

SetLogLevel(-1)
CLIPS = ROOT / "logs" / "clips"
MODEL = ROOT / "models" / "vosk-model-small-ru-0.22"


def rms(pcm: bytes) -> float:
    a = array.array("h")
    a.frombytes(pcm)
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


def main() -> None:
    files = sorted(CLIPS.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    if not files:
        print("no wav clips")
        return
    model = Model(str(MODEL))
    g = grammar_json()
    for f in files:
        with wave.open(str(f), "rb") as w:
            rate = w.getframerate()
            nch = w.getnchannels()
            sw = w.getsampwidth()
            pcm = w.readframes(w.getnframes())
        dur = len(pcm) / 2 / rate if rate else 0
        r = rms(pcm)
        rec = KaldiRecognizer(model, rate)
        rec.AcceptWaveform(pcm)
        free = (json.loads(rec.FinalResult()).get("text") or "").strip()
        rec2 = KaldiRecognizer(model, rate, g)
        rec2.AcceptWaveform(pcm)
        cmd = (json.loads(rec2.FinalResult()).get("text") or "").strip()
        print(f"=== {f.name} ===")
        print(f"  {dur:.2f}s  ch={nch}  sw={sw}  rate={rate}  rms={r:.0f}  bytes={len(pcm)}")
        print(f"  FREE: {free!r}")
        print(f"  CMD:  {cmd!r}")
        print()


if __name__ == "__main__":
    main()
