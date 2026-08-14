"""
Мост к kokoro-ru: демон (любой Python) → тёплый worker на Python 3.12.

Env:
  KOKORO_RU_ASSETS — папка с весами (default: %USERPROFILE%\\.kokoro_ru)
  KOKORO_PYTHON    — python.exe 3.12 venv
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKER_SCRIPT = ROOT / "micro_wife" / "kokoro_worker.py"
DEFAULT_VOICE = "sveta"
KNOWN_VOICES = frozenset({"sveta", "masha", "dima"})


def _default_assets() -> Path:
    env = os.environ.get("KOKORO_RU_ASSETS", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".kokoro_ru"


def _default_python() -> Path:
    env = os.environ.get("KOKORO_PYTHON", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".venvs" / "kokoro312" / "Scripts" / "python.exe"


DEFAULT_ASSETS = _default_assets()
DEFAULT_PY = _default_python()

_lock = threading.RLock()
_proc: subprocess.Popen | None = None
_stderr_thread: threading.Thread | None = None
_generation = 0  # bump on kill so stale readers bail


def _creationflags() -> int:
    if sys.platform == "win32":
        return 0x08000000  # CREATE_NO_WINDOW
    return 0


def _drain_stderr(proc: subprocess.Popen, gen: int) -> None:
    """Читает stderr в фоне — иначе PIPE переполняется и worker зависает."""
    assert proc.stderr is not None
    try:
        for _line in proc.stderr:
            if gen != _generation:
                break
    except Exception:
        pass


def _readline_timeout(proc: subprocess.Popen, timeout_s: float) -> str:
    """Одна строка stdout с таймаутом (Windows-friendly через thread+queue)."""
    assert proc.stdout is not None
    box: queue.Queue[str | None] = queue.Queue(maxsize=1)

    def reader() -> None:
        try:
            box.put(proc.stdout.readline())
        except Exception:
            box.put(None)

    t = threading.Thread(target=reader, name="kokoro-stdout", daemon=True)
    t.start()
    try:
        line = box.get(timeout=timeout_s)
    except queue.Empty:
        raise TimeoutError(f"kokoro worker stdout timeout after {timeout_s}s")
    if line is None:
        return ""
    return line


def _start_worker(*, hello_timeout_s: float = 60.0) -> subprocess.Popen:
    global _stderr_thread, _generation
    py = _default_python()
    assets = _default_assets()
    if not py.is_file():
        raise FileNotFoundError(
            f"Kokoro Python 3.12 venv not found: {py}\n"
            "Create: py -3.12 -m venv %USERPROFILE%\\.venvs\\kokoro312 "
            "&& pip install kokoro soundfile huggingface_hub ruaccent"
        )
    if not WORKER_SCRIPT.is_file():
        raise FileNotFoundError(f"Missing worker: {WORKER_SCRIPT}")

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["KOKORO_RU_ASSETS"] = str(assets)

    _generation += 1
    gen = _generation
    proc = subprocess.Popen(
        [str(py), str(WORKER_SCRIPT)],
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
    _stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, gen), name="kokoro-stderr", daemon=True
    )
    _stderr_thread.start()

    try:
        line = _readline_timeout(proc, hello_timeout_s)
    except TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise
    if not line:
        raise RuntimeError("kokoro worker died on start (no hello)")
    try:
        ready = json.loads(line)
    except json.JSONDecodeError as exc:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError(f"kokoro worker bad hello: {line!r}") from exc
    if not ready.get("ok"):
        try:
            proc.kill()
        except Exception:
            pass
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
        gen = _generation
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if gen != _generation:
                raise RuntimeError("kokoro worker restarted (cancelled)")
            if proc.poll() is not None:
                raise RuntimeError("kokoro worker exited during request")
            remaining = max(0.05, deadline - time.monotonic())
            try:
                line = _readline_timeout(proc, min(remaining, 5.0))
            except TimeoutError:
                continue
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
        raise TimeoutError(
            f"kokoro worker timeout after {timeout_s}s: {payload.get('cmd')}"
        )


def normalize_voice(voice: str | None) -> str:
    v = (voice or DEFAULT_VOICE).strip().lower() or DEFAULT_VOICE
    return v if v in KNOWN_VOICES else DEFAULT_VOICE


def warmup(voice: str | None = None) -> None:
    _request({"cmd": "warmup", "voice": normalize_voice(voice)}, timeout_s=300.0)


def synthesize_wav(text: str, voice: str | None, out_path: Path) -> None:
    _request(
        {
            "cmd": "synth",
            "text": text,
            "voice": normalize_voice(voice),
            "out": str(Path(out_path).resolve()),
        },
        timeout_s=600.0,
    )


def stop_worker() -> None:
    """Убить worker (отмена текущего synth + освобождение RAM)."""
    global _proc, _generation
    with _lock:
        _generation += 1
        proc = _proc
        _proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                    proc.stdin.flush()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def cancel_current() -> None:
    """Алиас для stop: прервать зависший/текущий synth."""
    stop_worker()
