"""
JSONL worker для kokoro-ru (только Python 3.12 venv).
stdin:  {"cmd":"warmup"|"synth"|"ping", ...}
stdout: {"ok":true|false, ...}
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

ASSETS = Path(os.environ.get("KOKORO_RU_ASSETS", r"C:\Users\Home\.kokoro_ru")).resolve()
SR = 24000

if str(ASSETS) not in sys.path:
    sys.path.insert(0, str(ASSETS))

_G2P = None
_MODEL = None
_PACKS: dict[str, object] = {}


def _reply(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ensure_voice(voice: str) -> None:
    import torch
    from huggingface_hub import hf_hub_download

    path = ASSETS / "voices" / f"{voice}.pt"
    if not path.is_file():
        hf_hub_download("zaakirio/kokoro-ru", f"voices/{voice}.pt", local_dir=str(ASSETS))
    if voice not in _PACKS:
        _PACKS[voice] = torch.load(path, map_location="cpu", weights_only=False)


def _ensure_model() -> None:
    global _G2P, _MODEL
    if _MODEL is not None:
        return
    from kokoro import KModel
    from ru_g2p import RuG2P

    need = [
        ASSETS / "kokoro-ru-v2-base.pth",
        ASSETS / "kokoro-config.json",
        ASSETS / "ru_g2p.py",
        ASSETS / "espeak-data",
    ]
    missing = [p for p in need if not p.exists()]
    if missing:
        raise FileNotFoundError("kokoro-ru assets missing: " + ", ".join(map(str, missing)))

    _G2P = RuG2P()
    _MODEL = KModel(
        repo_id="hexgrad/Kokoro-82M",
        config=str(ASSETS / "kokoro-config.json"),
        model=str(ASSETS / "kokoro-ru-v2-base.pth"),
    ).eval()


def warmup(voice: str = "sveta") -> None:
    import torch

    _ensure_model()
    _ensure_voice(voice)
    ipa, _ = _G2P("Прогрев.")
    with torch.no_grad():
        _MODEL(ipa, _PACKS[voice][len(ipa) - 1], 1.0, return_output=True)


def synth(text: str, voice: str, out: Path) -> float:
    import torch
    import soundfile as sf

    text = (text or "").strip()
    if len(text) < 1:
        raise ValueError("empty text")
    _ensure_model()
    _ensure_voice(voice)
    t0 = time.perf_counter()
    ipa, oov = _G2P(text)
    if oov:
        sys.stderr.write(f"WARN OOV: {oov}\n")
        sys.stderr.flush()
    with torch.no_grad():
        audio = _MODEL(ipa, _PACKS[voice][len(ipa) - 1], 1.0, return_output=True).audio
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
                warmup(str(req.get("voice", "sveta")).strip() or "sveta")
                _reply({"ok": True, "warmed": True})
            elif cmd == "synth":
                out = Path(str(req["out"]))
                seconds = synth(
                    str(req.get("text", "")),
                    str(req.get("voice", "sveta")).strip() or "sveta",
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
