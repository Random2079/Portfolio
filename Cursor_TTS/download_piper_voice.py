"""
Скачать русский голос Piper в Cursor_TTS/models/.

Примеры:
  python download_piper_voice.py
  python download_piper_voice.py ru_RU-dmitri-medium
  python download_piper_voice.py ru_RU-irina-medium
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"

# voice_id -> (onnx_url, json_url) на Hugging Face rhasspy/piper-voices v1.0.0
_VOICES: dict[str, tuple[str, str]] = {
    "ru_RU-dmitri-medium": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx.json",
    ),
    "ru_RU-irina-medium": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json",
    ),
    "ru_RU-ruslan-medium": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx.json",
    ),
    "ru_RU-denis-medium": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx.json",
    ),
}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {dest.name} …")
    urllib.request.urlretrieve(url, dest)
    print(f"  -> {dest} ({dest.stat().st_size // 1024} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Piper ru_RU voice models")
    parser.add_argument(
        "voice",
        nargs="?",
        default="ru_RU-dmitri-medium",
        choices=sorted(_VOICES.keys()),
        help="Voice id (default: ru_RU-dmitri-medium)",
    )
    args = parser.parse_args()
    onnx_url, json_url = _VOICES[args.voice]
    onnx_path = MODELS / f"{args.voice}.onnx"
    json_path = MODELS / f"{args.voice}.onnx.json"
    try:
        _download(onnx_url, onnx_path)
        _download(json_url, json_path)
    except Exception as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    print(f"OK. Set in tts_config.json: \"piper_model\": \"models/{args.voice}.onnx\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
