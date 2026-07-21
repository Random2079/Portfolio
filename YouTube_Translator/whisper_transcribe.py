"""Transcribe an audio file with faster-whisper -> .srt + .txt"""
from __future__ import annotations

import sys
from pathlib import Path

from faster_whisper import WhisperModel


def format_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: whisper_transcribe.py <audio_or_dir> [model]")
        return 1

    target = Path(sys.argv[1])
    model_name = sys.argv[2] if len(sys.argv) > 2 else "small"

    if target.is_dir():
        audio_files = sorted(target.glob("*.mp3")) + sorted(target.glob("*.wav")) + sorted(target.glob("*.webm"))
        if not audio_files:
            print(f"No audio in {target}")
            return 1
        audio = audio_files[0]
        out_dir = target
    else:
        audio = target
        out_dir = audio.parent

    stem = "transcript_dZ8FXhRlngM"
    srt_path = out_dir / f"{stem}.srt"
    txt_path = out_dir / f"{stem}.txt"

    safe_name = audio.name.encode("ascii", "replace").decode("ascii")
    print(f"Audio: {safe_name} ({audio.stat().st_size} bytes)")
    print(f"Model: {model_name}")

    # CPU is reliable here; CUDA needs full cuBLAS toolkit which may be missing.
    device = "cpu"
    compute_type = "int8"
    if len(sys.argv) > 3 and sys.argv[3] == "cuda":
        device = "cuda"
        compute_type = "float16"
    print(f"Device: {device} ({compute_type})")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    segments, info = model.transcribe(
        str(audio),
        language="ru",
        vad_filter=True,
        beam_size=5,
    )
    print(f"Detected language: {info.language} (p={info.language_probability:.2f})")

    srt_lines: list[str] = []
    txt_lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        if not text:
            continue
        srt_lines.append(str(i))
        srt_lines.append(f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}")
        srt_lines.append(text)
        srt_lines.append("")
        txt_lines.append(f"[{format_timestamp(seg.start)}] {text}")
        if i % 25 == 0:
            print(f"... {i} segments")

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
    print(f"Wrote {srt_path}")
    print(f"Wrote {txt_path}")
    print(f"Segments: {len(txt_lines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
