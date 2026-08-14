"""
Мост к kokoro-ru: демон (любой Python) → тёплый worker на Python 3.12.
Ассеты: C:\\Users\\Home\\.kokoro_ru  (KOKORO_RU_ASSETS)
Venv:    C:\\Users\\Home\\.venvs\\kokoro312
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKER_SCRIPT = ROOT / "micro_wife" / "kokoro_worker.py"
DEFAULT_VOICE = "sveta"
DEFAULT_ASSETS = Path(os.environ.get("KOKORO_RU_ASSETS", r"C:\Users\Home\.kokoro_ru"))
DEFAULT_PY = Path(
    os.environ.get(
        "KOKORO_PYTHON",
        r"C:\Users\Home\.venvs\kokoro312\Scripts\python.exe",
    )
)
KNOWN_VOICES = ("sveta", "masha", "dima")

_lock = threading.RLock()
_proc: subprocess.Popen | None = None


def _creationflags() -> int:
    if sys.platform == "win32":
        # CREATE_NO_WINDOW
        return 0x08000000
    return 0


def _start_worker() -> subprocess.Popen:
    if not DEFAULT_PY.is_file():
        raise FileNotFoundError(
            f"Kokoro Python 3.12 venv not found: {DEFAULT_PY}\n"
            "Create: py -3.12 -m venv C:\\Users\\Home\\.venvs\\kokoro312 "
            "&& pip install kokoro soundfile huggingface_hub ruaccent"
        )
    if not WORKER_SCRIPT.is_file():
        raise FileNotFoundError(f"Missing worker: {WORKER_SCRIPT}")
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["KOKORO_RU_ASSETS"] = str(DEFAULT_ASSETS)
    proc = subprocess.Popen(
        [str(DEFAULT_PY), str(WORKER_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(ROOT),
        env=env,
        creationflags=_creationflags(),
    )
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        err = ""
        if proc.stderr is not None:
            err = proc.stderr.read()
        raise RuntimeError(f"kokoro worker died on start: {err}")
    try:
        ready = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"kokoro worker bad hello: {line!r}") from exc
    if not ready.get("ok"):
        raise RuntimeError(f"kokoro worker not ready: {ready}")
    return proc


def _ensure_worker() -> subprocess.Popen:
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return _proc
        _proc = _start_worker()
        return _proc


def _request(payload: dict, timeout_s: float = 600.0) -> dict:
    with _lock:
        proc = _ensure_worker()
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = ""
                if proc.stderr is not None:
                    err = proc.stderr.read()
                raise RuntimeError(f"kokoro worker exited: {err}")
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.02)
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not resp.get("ok"):
                raise RuntimeError(resp.get("error") or str(resp))
            return resp
        raise TimeoutError(f"kokoro worker timeout after {timeout_s}s: {payload.get('cmd')}")


def warmup(voice: str | None = None) -> None:
    voice = (voice or DEFAULT_VOICE).strip().lower() or DEFAULT_VOICE
    _request({"cmd": "warmup", "voice": voice}, timeout_s=300.0)


def synthesize_wav(text: str, voice: str | None, out_path: Path) -> None:
    voice = (voice or DEFAULT_VOICE).strip().lower() or DEFAULT_VOICE
    if voice not in KNOWN_VOICES:
        voice = DEFAULT_VOICE
    _request(
        {
            "cmd": "synth",
            "text": text,
            "voice": voice,
            "out": str(Path(out_path).resolve()),
        },
        timeout_s=600.0,
    )


def stop_worker() -> None:
    global _proc
    with _lock:
        if _proc is None:
            return
        try:
            if _proc.poll() is None and _proc.stdin is not None:
                _proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                _proc.stdin.flush()
                _proc.wait(timeout=5)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
        _proc = None
