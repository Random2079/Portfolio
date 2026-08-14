"""
JSONL worker для kokoro-ru (только Python 3.12 venv).
stdin:  {"cmd":"warmup"|"synth"|"ping"|"quit", ...}
stdout: {"ok":true|false, ...}
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

ASSETS = Path(os.environ.get("KOKORO_RU_ASSETS", Path.home() / ".kokoro_ru")).resolve()
SR = 24000
KNOWN_VOICES = frozenset({"sveta", "masha", "dima"})
# dima — отдельный чекпоинт (см. zaakirio/kokoro-ru model card)
VOICE_MODELS = {
    "sveta": "kokoro-ru-v2-base.pth",
    "masha": "kokoro-ru-v2-base.pth",
    "dima": "kokoro-ru-v2-dima.pth",
}
_VOICE_RE = re.compile(r"^[a-z0-9_]{1,32}$")

if str(ASSETS) not in sys.path:
    sys.path.insert(0, str(ASSETS))

_G2P = None
_MODELS: dict[str, object] = {}  # checkpoint filename → KModel
_PACKS: dict[str, object] = {}


def _reply(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _normalize_voice(voice: str) -> str:
    v = (voice or "sveta").strip().lower() or "sveta"
    if v not in KNOWN_VOICES or not _VOICE_RE.match(v):
        raise ValueError(f"unknown voice: {voice!r} (want {sorted(KNOWN_VOICES)})")
    return v


def _ensure_checkpoint(filename: str) -> Path:
    from huggingface_hub import hf_hub_download

    path = ASSETS / filename
    if not path.is_file():
        hf_hub_download("zaakirio/kokoro-ru", filename, local_dir=str(ASSETS))
    if not path.is_file():
        raise FileNotFoundError(f"checkpoint missing: {path}")
    return path


def _ensure_voice(voice: str) -> None:
    import torch
    from huggingface_hub import hf_hub_download

    voice = _normalize_voice(voice)
    path = ASSETS / "voices" / f"{voice}.pt"
    if not path.is_file():
        hf_hub_download("zaakirio/kokoro-ru", f"voices/{voice}.pt", local_dir=str(ASSETS))
    voices_dir = (ASSETS / "voices").resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(voices_dir)
    except ValueError as exc:
        raise ValueError(f"voice path escaped assets: {resolved}") from exc
    if voice not in _PACKS:
        # weights_only=True ломает voicepack Kokoro (не чистый тензорный dict)
        _PACKS[voice] = torch.load(resolved, map_location="cpu", weights_only=False)


def _ensure_model(voice: str) -> object:
    global _G2P
    from kokoro import KModel
    from ru_g2p import RuG2P

    voice = _normalize_voice(voice)
    ckpt_name = VOICE_MODELS[voice]
    if ckpt_name in _MODELS:
        return _MODELS[ckpt_name]

    need = [
        ASSETS / "kokoro-config.json",
        ASSETS / "ru_g2p.py",
        ASSETS / "espeak-data",
    ]
    missing = [p for p in need if not p.exists()]
    if missing:
        raise FileNotFoundError("kokoro-ru assets missing: " + ", ".join(map(str, missing)))

    ckpt = _ensure_checkpoint(ckpt_name)
    if _G2P is None:
        _G2P = RuG2P()
    model = KModel(
        repo_id="hexgrad/Kokoro-82M",
        config=str(ASSETS / "kokoro-config.json"),
        model=str(ckpt),
    ).eval()
    _MODELS[ckpt_name] = model
    return model


def warmup(voice: str = "sveta") -> None:
    import torch

    voice = _normalize_voice(voice)
    model = _ensure_model(voice)
    _ensure_voice(voice)
    ipa, _ = _G2P("Прогрев.")
    if not ipa or not str(ipa).strip():
        raise RuntimeError("g2p returned empty IPA on warmup")
    with torch.no_grad():
        model(ipa, _PACKS[voice][len(ipa) - 1], 1.0, return_output=True)


def synth(text: str, voice: str, out: Path) -> float:
    import torch
    import soundfile as sf

    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")
    voice = _normalize_voice(voice)
    # out только как файл, без сюрпризов
    out = Path(out)
    if out.suffix.lower() != ".wav":
        raise ValueError("out must be a .wav path")

    model = _ensure_model(voice)
    _ensure_voice(voice)
    t0 = time.perf_counter()
    ipa, oov = _G2P(text)
    if not ipa or not str(ipa).strip():
        raise RuntimeError("g2p returned empty IPA")
    if oov:
        sys.stderr.write(f"WARN OOV: {oov}\n")
        sys.stderr.flush()
    pack = _PACKS[voice]
    idx = len(ipa) - 1
    if idx < 0 or idx >= len(pack):
        # style vector by phoneme length — clamp to last available
        idx = max(0, len(pack) - 1)
    with torch.no_grad():
        audio = model(ipa, pack[idx], 1.0, return_output=True).audio
    wav = audio.detach().cpu().numpy()
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), wav, SR)
    return time.perf_counter() - t0


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    _reply({"ok": True, "ready": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _reply({"ok": False, "error": f"bad json: {exc}"})
            continue
        cmd = str(req.get("cmd", "")).strip().lower()
        try:
            if cmd == "ping":
                _reply({"ok": True})
            elif cmd == "warmup":
                warmup(str(req.get("voice", "sveta")))
                _reply({"ok": True, "warmed": True})
            elif cmd == "synth":
                out = Path(str(req["out"]))
                seconds = synth(
                    str(req.get("text", "")),
                    str(req.get("voice", "sveta")),
                    out,
                )
                _reply({"ok": True, "seconds": round(seconds, 3), "out": str(out)})
            elif cmd == "quit":
                _reply({"ok": True, "bye": True})
                return 0
            else:
                _reply({"ok": False, "error": f"unknown cmd: {cmd}"})
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            _reply({"ok": False, "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
