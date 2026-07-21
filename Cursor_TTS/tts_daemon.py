"""
Фоновый TTS-воркер: держит Python/pygame тёплыми, слушает 127.0.0.1:47391.
Команды (одна JSON-строка):
  {"cmd":"speak","text":"..."}
  {"cmd":"stop"}
  {"cmd":"ping"}
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "tts_config.json"
PID_FILE = ROOT / "tts_daemon.pid"
HOST = "127.0.0.1"
PORT = 47391
DEFAULT_VOICE = "ru-RU-DmitryNeural"
DEFAULT_LOCAL_SPEAKER = "xenia"
DEFAULT_VOLUME = 45
DEFAULT_ENGINE = "edge"  # edge | local
DEFAULT_PAUSE_MS = 350  # пауза между кусками (реф: ~300–500ms между предложениями)

try:
    from tts_debug import (
        debug_log,
        log_chunk_fail,
        log_chunk_ok,
        log_interrupted,
        log_speak_done,
        log_speak_start,
    )
except ImportError:
    def debug_log(message: str) -> None:
        return None

    def log_speak_start(chars: int, parts: int) -> None:
        return None

    def log_chunk_ok(index: int, total: int, part: str) -> None:
        return None

    def log_chunk_fail(index: int, total: int, part: str, error: BaseException) -> None:
        return None

    def log_speak_done(ok_parts: int, fail_parts: int, total_parts: int = 0) -> None:
        return None

    def log_interrupted(reason: str = "new speak") -> None:
        return None

_stop_event = threading.Event()
_speak_lock = threading.Lock()
_mixer_ready = False
_speech_queue: queue.Queue[str | None] = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def load_config() -> dict:
    data = {
        "engine": DEFAULT_ENGINE,
        "voice": DEFAULT_VOICE,
        "local_speaker": DEFAULT_LOCAL_SPEAKER,
        "volume": DEFAULT_VOLUME / 100.0,
        "interrupt_on_new": False,
    }
    if CONFIG_FILE.is_file():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            engine = str(raw.get("engine", DEFAULT_ENGINE)).strip().lower()
            data["engine"] = engine if engine in {"edge", "local"} else DEFAULT_ENGINE
            data["voice"] = str(raw.get("voice", DEFAULT_VOICE)).strip() or DEFAULT_VOICE
            data["local_speaker"] = (
                str(raw.get("local_speaker", DEFAULT_LOCAL_SPEAKER)).strip()
                or DEFAULT_LOCAL_SPEAKER
            )
            data["volume"] = max(10, min(100, int(raw.get("volume", DEFAULT_VOLUME)))) / 100.0
            data["interrupt_on_new"] = bool(raw.get("interrupt_on_new", False))
            try:
                data["pause_ms"] = max(
                    0, min(2000, int(raw.get("pause_ms", DEFAULT_PAUSE_MS)))
                )
            except (TypeError, ValueError):
                data["pause_ms"] = DEFAULT_PAUSE_MS
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    if "pause_ms" not in data:
        data["pause_ms"] = DEFAULT_PAUSE_MS
    return data


def pause_after_chunk(part: str, base_ms: int) -> None:
    """Пауза между кусками: дольше после .!? , короче после запятой, 0 если стоп."""
    if base_ms <= 0 or _stop_event.is_set():
        return
    stripped = part.rstrip()
    if not stripped:
        return
    end = stripped[-1]
    if end in ".!?…":
        delay = int(base_ms * 1.4)  # ~ sentence / paragraph
    elif end in ",:;":
        delay = int(base_ms * 0.6)
    else:
        delay = base_ms
    delay = max(80, min(2000, delay))
    # Режем паузу, если нажали стоп
    end_at = time.monotonic() + delay / 1000.0
    while time.monotonic() < end_at:
        if _stop_event.is_set():
            return
        time.sleep(0.05)


def ensure_mixer() -> None:
    global _mixer_ready
    import pygame

    if not _mixer_ready:
        pygame.mixer.init()
        _mixer_ready = True


def stop_playback() -> None:
    _stop_event.set()
    try:
        import pygame

        if _mixer_ready:
            pygame.mixer.music.stop()
    except Exception:
        pass


def clear_speech_queue() -> int:
    cleared = 0
    while True:
        try:
            _speech_queue.get_nowait()
            cleared += 1
            _speech_queue.task_done()
        except queue.Empty:
            break
    return cleared


def enqueue_speech(text: str) -> int:
    _speech_queue.put(text)
    size = _speech_queue.qsize()
    debug_log(f"QUEUE_ADD chars={len(text)} queue_size={size}")
    return size


def _speech_worker() -> None:
    while True:
        text = _speech_queue.get()
        try:
            if text is None:
                return
            if len(text) >= 2:
                speak_text(text)
        finally:
            _speech_queue.task_done()


def ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_speech_worker, name="tts-queue", daemon=True)
        thread.start()
        _worker_started = True
        debug_log("QUEUE_WORKER started")


CHUNK_TARGET = 900  # символов на кусок — edge-tts быстрее отдаёт короткий кусок
FAST_START = 220


def split_into_chunks(text: str, target: int = CHUNK_TARGET) -> list[str]:
    """Режет длинный текст на куски по предложениям/пробелам."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        if length - start <= target:
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        end = min(start + target, length)
        window = text[start:end]

        cut = -1
        for i in range(len(window) - 1, max(len(window) // 3, 0), -1):
            if window[i] in ".!?\n;":
                cut = i + 1
                break
        if cut < 0:
            space = window.rfind(" ")
            cut = space if space > len(window) // 3 else len(window)

        chunk = text[start : start + cut].strip()
        if chunk:
            chunks.append(chunk)
        start += cut
        while start < length and text[start].isspace():
            start += 1

    return chunks


def split_for_speech(text: str) -> list[str]:
    """Короткий первый кусок + остальные части по ~900 символов."""
    text = text.strip()
    if len(text) <= FAST_START:
        return [text]

    window = text[:320]
    cut = -1
    for i, ch in enumerate(window):
        if i < 80:
            continue
        if ch in ".!?\n":
            cut = i + 1
            break
    if cut < 0:
        cut = min(180, len(text))
        while cut < len(text) and not text[cut].isspace():
            cut += 1
            if cut > 260:
                break

    first = text[:cut].strip()
    rest = text[cut:].strip()
    if not first:
        return split_into_chunks(text)
    if not rest:
        return [first]
    return [first] + split_into_chunks(rest)


async def download_mp3(text: str, voice: str, mp3_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    with mp3_path.open("wb") as file:
        async for chunk in communicate.stream():
            if _stop_event.is_set():
                return
            if chunk["type"] == "audio":
                file.write(chunk["data"])


def download_mp3_retry(text: str, voice: str, mp3_path: Path, tries: int = 3) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, tries + 1):
        if _stop_event.is_set():
            return
        try:
            if mp3_path.exists():
                mp3_path.unlink(missing_ok=True)
            asyncio.run(download_mp3(text, voice, mp3_path))
            if mp3_path.is_file() and mp3_path.stat().st_size >= 64:
                return
            last_error = RuntimeError("empty mp3 / nothing to play")
        except Exception as error:
            last_error = error
        # Короткая пауза и ещё попытка (edge иногда NoAudioReceived)
        if attempt < tries and not _stop_event.is_set():
            import time

            time.sleep(0.4 * attempt)
    if last_error is not None:
        raise last_error


def play_file(mp3_path: Path, volume: float) -> None:
    import pygame

    ensure_mixer()
    if _stop_event.is_set() or mp3_path.stat().st_size < 64:
        return
    try:
        pygame.mixer.music.load(str(mp3_path))
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if _stop_event.is_set():
                pygame.mixer.music.stop()
                break
            pygame.time.wait(40)
    finally:
        # Windows: пока файл в music — unlink зависает / ломает следующий кусок.
        try:
            pygame.mixer.music.unload()
        except Exception:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        try:
            import time

            time.sleep(0.05)
            path.unlink(missing_ok=True)
        except OSError:
            debug_log(f"UNLINK_FAIL path={path}")


def render_audio(part: str, cfg: dict, out_path: Path) -> None:
    """edge → mp3, local → wav. out_path суффикс задаёт вызывающий."""
    if cfg["engine"] == "local":
        from speak_local import synthesize_wav

        synthesize_wav(part, cfg["local_speaker"], out_path)
        return
    download_mp3_retry(part, cfg["voice"], out_path)


def _prefetch_part(part: str, cfg: dict, out_holder: list) -> None:
    suffix = ".wav" if cfg["engine"] == "local" else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_path = Path(tmp.name)
    try:
        render_audio(part, cfg, audio_path)
        out_holder[0] = audio_path
    except Exception as error:
        audio_path.unlink(missing_ok=True)
        out_holder[0] = error


def speak_text(text: str) -> None:
    with _speak_lock:
        _stop_event.clear()
        try:
            from text_prep import finalize_speech_text

            text = finalize_speech_text(text)
        except Exception as error:
            debug_log(f"text_prep skipped: {error}")

        cfg = load_config()
        # Local: ровные куски; без prefetch (Silero + потоки = зависания).
        if cfg["engine"] == "local":
            parts = split_into_chunks(text, target=500)
        else:
            parts = split_for_speech(text)
        if not parts:
            return
        debug_log(f"ENGINE={cfg['engine']}")
        log_speak_start(len(text), len(parts))
        ok_parts = 0
        fail_parts = 0
        suffix = ".wav" if cfg["engine"] == "local" else ".mp3"

        if cfg["engine"] == "local":
            for index, part in enumerate(parts, start=1):
                if _stop_event.is_set() or len(part) < 2:
                    break
                debug_log(
                    f"CHUNK_BEGIN {index}/{len(parts)} chars={len(part)} "
                    f"preview={part[:80]!r}"
                )
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    audio_path = Path(tmp.name)
                try:
                    try:
                        render_audio(part, cfg, audio_path)
                    except Exception as error:
                        fail_parts += 1
                        log_chunk_fail(index, len(parts), part, error)
                        continue
                    if audio_path.stat().st_size < 64:
                        fail_parts += 1
                        log_chunk_fail(
                            index,
                            len(parts),
                            part,
                            RuntimeError("empty audio"),
                        )
                        continue
                    if not _stop_event.is_set():
                        play_file(audio_path, cfg["volume"])
                        ok_parts += 1
                        log_chunk_ok(index, len(parts), part)
                        if index < len(parts):
                            pause_after_chunk(part, int(cfg.get("pause_ms", DEFAULT_PAUSE_MS)))
                finally:
                    _safe_unlink(audio_path)
            log_speak_done(ok_parts, fail_parts, len(parts))
            return

        # Edge: prefetch следующего куска, пока играет текущий.
        next_thread: threading.Thread | None = None

        def start_prefetch(part: str) -> threading.Thread:
            holder: list = [None]
            thread = threading.Thread(
                target=_prefetch_part, args=(part, cfg, holder), daemon=True
            )
            thread.start()
            thread._holder = holder  # type: ignore[attr-defined]
            return thread

        current_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                current_path = Path(tmp.name)
            render_audio(parts[0], cfg, current_path)
        except Exception as error:
            fail_parts += 1
            log_chunk_fail(1, len(parts), parts[0], error)
            current_path = None

        for index, part in enumerate(parts, start=1):
            if _stop_event.is_set():
                break

            if index > 1:
                if next_thread is not None:
                    next_thread.join(timeout=120)
                    result = getattr(next_thread, "_holder", [None])[0]
                    next_thread = None
                    if isinstance(result, Exception):
                        fail_parts += 1
                        log_chunk_fail(index, len(parts), part, result)
                        current_path = None
                    elif isinstance(result, Path):
                        current_path = result
                    else:
                        fail_parts += 1
                        log_chunk_fail(
                            index,
                            len(parts),
                            part,
                            RuntimeError("prefetch returned nothing"),
                        )
                        current_path = None

            if index < len(parts) and not _stop_event.is_set():
                next_thread = start_prefetch(parts[index])

            if current_path is None:
                continue
            try:
                if not _stop_event.is_set():
                    play_file(current_path, cfg["volume"])
                    ok_parts += 1
                    log_chunk_ok(index, len(parts), part)
                    if index < len(parts):
                        pause_after_chunk(part, int(cfg.get("pause_ms", DEFAULT_PAUSE_MS)))
            finally:
                _safe_unlink(current_path)
                current_path = None

        if next_thread is not None:
            next_thread.join(timeout=1)
            result = getattr(next_thread, "_holder", [None])[0]
            if isinstance(result, Path):
                _safe_unlink(result)

        log_speak_done(ok_parts, fail_parts, len(parts))


def handle_client(conn: socket.socket) -> None:
    with conn:
        raw = b""
        while not raw.endswith(b"\n"):
            piece = conn.recv(4096)
            if not piece:
                break
            raw += piece
            if len(raw) > 600_000:
                break
        try:
            data = json.loads(raw.decode("utf-8").strip() or "{}")
        except json.JSONDecodeError:
            conn.sendall(b'{"ok":false,"error":"bad json"}\n')
            return

        cmd = str(data.get("cmd", "")).lower()
        if cmd == "ping":
            conn.sendall(b'{"ok":true,"pong":true}\n')
            return
        if cmd == "stop":
            cleared = clear_speech_queue()
            stop_playback()
            debug_log(f"STOP cleared_queue={cleared}")
            # #region agent log
            try:
                _dbg = ROOT.parent / "debug-45ab72.log"
                with _dbg.open("a", encoding="utf-8") as _f:
                    _f.write(
                        json.dumps(
                            {
                                "sessionId": "45ab72",
                                "hypothesisId": "C",
                                "location": "tts_daemon.py:stop",
                                "message": "daemon stop handled",
                                "data": {
                                    "cleared_queue": cleared,
                                    "stop_event": _stop_event.is_set(),
                                },
                                "timestamp": int(time.time() * 1000),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except OSError:
                pass
            # #endregion
            conn.sendall(b'{"ok":true,"stopped":true}\n')
            return
        if cmd == "speak":
            text = str(data.get("text", "")).strip()
            cfg = load_config()
            ensure_worker()
            if cfg.get("interrupt_on_new"):
                if _speak_lock.locked() or _speech_queue.qsize() > 0:
                    log_interrupted("interrupt_on_new=true")
                cleared = clear_speech_queue()
                stop_playback()
                debug_log(f"INTERRUPT cleared_queue={cleared}")
            if len(text) >= 2:
                size = enqueue_speech(text)
                conn.sendall(
                    f'{{"ok":true,"queued":true,"queue_size":{size}}}\n'.encode("ascii")
                )
            else:
                conn.sendall(b'{"ok":true,"queued":false}\n')
            return
        conn.sendall(b'{"ok":false,"error":"unknown cmd"}\n')


def already_running() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.3) as sock:
            sock.sendall(b'{"cmd":"ping"}\n')
            sock.recv(256)
        return True
    except OSError:
        return False


def main() -> int:
    if already_running():
        return 0

    PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    ensure_mixer()
    ensure_worker()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(8)
    server.settimeout(1.0)

    try:
        while True:
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        stop_playback()
        server.close()
        PID_FILE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
