"""
Фоновый TTS-воркер: держит Python/pygame тёплыми, слушает 127.0.0.1:47391.
Команды (одна JSON-строка):
  {"cmd":"speak","text":"..."}
  {"cmd":"stop"}
  {"cmd":"pause"}
  {"cmd":"resume"}
  {"cmd":"pause_toggle"}
  {"cmd":"ping"}
  {"cmd":"warmup"}
"""
from __future__ import annotations

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
DEFAULT_VOLUME = 45
DEFAULT_ENGINE = "kokoro"  # kokoro | qwen
DEFAULT_PAUSE_MS = 350  # пауза между кусками (реф: ~300–500ms между предложениями)
DEFAULT_HYBRID_MODE = "dict_only"
DEFAULT_LANG_SWITCH_PAUSE_MS = 80
DEFAULT_KOKORO_VOICE = "sveta"
DEFAULT_QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
DEFAULT_QWEN_SPEAKER = "serena"
DEFAULT_QWEN_DESIGN = "micro_wife/voice_design.txt"
_ENGINES = {"kokoro", "qwen"}
_HYBRID_MODES = {"off", "dict_only"}

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
_paused = False  # pause/resume: не чистит очередь, ждёт resume
_pause_lock = threading.Lock()
_speak_lock = threading.Lock()
_mixer_ready = False
_speech_queue: queue.Queue[str | None] = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()
_progress_lock = threading.Lock()
_progress: dict[str, object] = {
    "phase": "idle",
    "engine": DEFAULT_ENGINE,
    "current": 0,
    "total": 0,
}
_warmup_active = False


def set_progress(
    phase: str,
    *,
    engine: str | None = None,
    current: int | None = None,
    total: int | None = None,
) -> None:
    with _progress_lock:
        _progress["phase"] = phase
        if engine is not None:
            _progress["engine"] = engine
        if current is not None:
            _progress["current"] = current
        if total is not None:
            _progress["total"] = total


def set_warmup_active(value: bool) -> None:
    global _warmup_active
    with _progress_lock:
        _warmup_active = value


def progress_snapshot() -> dict[str, object]:
    with _progress_lock:
        data = dict(_progress)
        data["warming"] = _warmup_active
    data["paused"] = is_paused()
    data["queue"] = _speech_queue.qsize()
    return data


def load_config() -> dict:
    data = {
        "engine": DEFAULT_ENGINE,
        "kokoro_voice": DEFAULT_KOKORO_VOICE,
        "hybrid_mode": DEFAULT_HYBRID_MODE,
        "lang_switch_pause_ms": DEFAULT_LANG_SWITCH_PAUSE_MS,
        "qwen_model": DEFAULT_QWEN_MODEL,
        "qwen_speaker": DEFAULT_QWEN_SPEAKER,
        "micro_wife_design_file": DEFAULT_QWEN_DESIGN,
        "volume": DEFAULT_VOLUME / 100.0,
        "interrupt_on_new": False,
    }
    if CONFIG_FILE.is_file():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            engine = str(raw.get("engine", DEFAULT_ENGINE)).strip().lower()
            data["engine"] = engine if engine in _ENGINES else DEFAULT_ENGINE
            kokoro_voice = str(raw.get("kokoro_voice", DEFAULT_KOKORO_VOICE)).strip().lower()
            data["kokoro_voice"] = kokoro_voice or DEFAULT_KOKORO_VOICE
            hybrid = str(raw.get("hybrid_mode", DEFAULT_HYBRID_MODE)).strip().lower()
            if hybrid == "dict_and_en":
                hybrid = "dict_only"
            data["hybrid_mode"] = hybrid if hybrid in _HYBRID_MODES else DEFAULT_HYBRID_MODE
            data["qwen_model"] = (
                str(raw.get("qwen_model", DEFAULT_QWEN_MODEL)).strip() or DEFAULT_QWEN_MODEL
            )
            data["qwen_speaker"] = (
                str(raw.get("qwen_speaker", DEFAULT_QWEN_SPEAKER)).strip()
                or DEFAULT_QWEN_SPEAKER
            )
            data["micro_wife_design_file"] = (
                str(raw.get("micro_wife_design_file", DEFAULT_QWEN_DESIGN)).strip()
                or DEFAULT_QWEN_DESIGN
            )
            try:
                data["lang_switch_pause_ms"] = max(
                    0,
                    min(400, int(raw.get("lang_switch_pause_ms", DEFAULT_LANG_SWITCH_PAUSE_MS))),
                )
            except (TypeError, ValueError):
                data["lang_switch_pause_ms"] = DEFAULT_LANG_SWITCH_PAUSE_MS
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
    if "qwen_model" not in data:
        data["qwen_model"] = DEFAULT_QWEN_MODEL
    if "qwen_speaker" not in data:
        data["qwen_speaker"] = DEFAULT_QWEN_SPEAKER
    if "micro_wife_design_file" not in data:
        data["micro_wife_design_file"] = DEFAULT_QWEN_DESIGN
    if "kokoro_voice" not in data:
        data["kokoro_voice"] = DEFAULT_KOKORO_VOICE
    return data


PAUSE_FLAG = ROOT / "TTS_PAUSED"


def _sync_pause_flag(paused: bool) -> None:
    """Файл-индикатор для панели/AHK: есть = на паузе, нет = играет/готово."""
    try:
        if paused:
            PAUSE_FLAG.write_text("1", encoding="ascii")
        else:
            PAUSE_FLAG.unlink(missing_ok=True)
    except OSError:
        pass


def is_paused() -> bool:
    with _pause_lock:
        return _paused


def set_paused(value: bool) -> None:
    global _paused
    with _pause_lock:
        _paused = value
    _sync_pause_flag(value)


def wait_while_paused() -> bool:
    """Ждёт resume. True = можно продолжать, False = stop."""
    while is_paused():
        if _stop_event.is_set():
            return False
        time.sleep(0.05)
    return not _stop_event.is_set()


def pause_after_chunk(part: str, base_ms: int) -> None:
    """Пауза между кусками: дольше после .!? , короче после запятой, 0 если стоп/pause."""
    if base_ms <= 0 or _stop_event.is_set() or is_paused():
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
    end_at = time.monotonic() + delay / 1000.0
    while time.monotonic() < end_at:
        if _stop_event.is_set() or is_paused():
            return
        time.sleep(0.05)


def ensure_mixer() -> None:
    global _mixer_ready
    import pygame

    if not _mixer_ready:
        pygame.mixer.init()
        _mixer_ready = True


def stop_playback() -> None:
    """Полный stop: обрыв текущего play. Очередь чистит вызывающий."""
    set_paused(False)
    _stop_event.set()
    try:
        import pygame

        if _mixer_ready:
            pygame.mixer.music.stop()
    except Exception:
        pass
    # Прервать долгий Kokoro synth (убивает worker; следующий вызов поднимет снова)
    try:
        from speak_kokoro import cancel_current

        cancel_current()
    except Exception:
        pass


def _prepare_engine(engine: str) -> None:
    """При смене движка освобождаем чужой runtime (VRAM / worker RAM)."""
    if engine == "kokoro":
        try:
            micro = Path(__file__).resolve().parent / "micro_wife"
            if str(micro) not in sys.path:
                sys.path.insert(0, str(micro))
            from speak_qwen import unload as unload_qwen

            unload_qwen()
        except Exception as error:
            debug_log(f"unload qwen skip: {error}")
    elif engine == "qwen":
        try:
            from speak_kokoro import stop_worker

            stop_worker()
        except Exception as error:
            debug_log(f"stop kokoro worker skip: {error}")


def _normalize_kokoro_voice(voice: str | None) -> str:
    from speak_kokoro import normalize_voice

    return normalize_voice(voice)


def pause_playback() -> None:
    """Pause: pygame pause(), очередь и текущий кусок не сбрасывать."""
    set_paused(True)
    try:
        import pygame

        if _mixer_ready:
            pygame.mixer.music.pause()
    except Exception:
        pass


def resume_playback() -> None:
    set_paused(False)
    try:
        import pygame

        if _mixer_ready:
            pygame.mixer.music.unpause()
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


CHUNK_TARGET = 900  # символов на кусок (legacy; kokoro/qwen режут в _parts_for_engine)

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


def play_file(mp3_path: Path, volume: float) -> bool:
    """Играть до конца. True = дослушали, False = hard stop.
    get_busy() на паузе False — не считать это концом файла.
    """
    import pygame

    ensure_mixer()
    if mp3_path.stat().st_size < 64:
        return False
    if _stop_event.is_set():
        return False
    if is_paused() and not wait_while_paused():
        return False
    try:
        pygame.mixer.music.load(str(mp3_path))
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play()
        mixer_paused = False
        while True:
            if _stop_event.is_set():
                pygame.mixer.music.stop()
                return False
            if is_paused():
                if not mixer_paused:
                    pygame.mixer.music.pause()
                    mixer_paused = True
                pygame.time.wait(40)
                continue
            if mixer_paused:
                pygame.mixer.music.unpause()
                mixer_paused = False
            if pygame.mixer.music.get_busy():
                pygame.time.wait(40)
                continue
            pygame.time.wait(20)
            if is_paused() or pygame.mixer.music.get_busy():
                continue
            return True
    finally:
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
            time.sleep(0.05)
            path.unlink(missing_ok=True)
        except OSError:
            debug_log(f"UNLINK_FAIL path={path}")


def _audio_suffix(engine: str) -> str:
    return ".wav"


def render_audio(part: str, cfg: dict, out_path: Path, lang: str = "ru") -> None:
    """kokoro / qwen → wav. lang оставлен для совместимости (всегда ru).
    Смену движка (_prepare_engine) делает speak_text/warmup один раз — не на каждый chunk.
    """
    del lang  # EN hybrid убран вместе с Piper
    engine = cfg["engine"]
    if engine == "kokoro":
        from speak_kokoro import synthesize_wav as synthesize_kokoro

        synthesize_kokoro(
            part,
            _normalize_kokoro_voice(cfg.get("kokoro_voice", DEFAULT_KOKORO_VOICE)),
            out_path,
        )
        return
    if engine == "qwen":
        micro = Path(__file__).resolve().parent / "micro_wife"
        if str(micro) not in sys.path:
            sys.path.insert(0, str(micro))
        from speak_qwen import synthesize_wav as synthesize_qwen
        from speak_qwen import speaker_for_design

        design_file = cfg.get("micro_wife_design_file", DEFAULT_QWEN_DESIGN)
        # speaker всегда из пресета design (конфиг мог залипнуть на serena)
        synthesize_qwen(
            part,
            out_path,
            design_file=design_file,
            model_id=cfg.get("qwen_model", DEFAULT_QWEN_MODEL),
            speaker=speaker_for_design(design_file),
            language="russian",
        )
        return
    raise ValueError(f"unknown engine: {engine}")


def _looks_like_table_speech(text: str) -> bool:
    head = text.lstrip()[:120]
    if head.startswith("Столбцы:"):
        return True
    # Много коротких предложений подряд — типичные строки таблицы
    dots = text.count(". ")
    return dots >= 4 and (len(text) / max(dots, 1)) < 90


def _parts_for_engine(text: str, engine: str) -> list[str]:
    table_like = _looks_like_table_speech(text)
    if engine == "kokoro":
        return split_into_chunks(text, target=160 if table_like else 400)
    if engine == "qwen":
        # Короткие куски на Qwen дают хуже RTF (фиксированный overhead generate).
        # table_like раньше резал до 120 — это усугубляло; держим крупные куски.
        return split_into_chunks(text, target=420)
    return split_into_chunks(text, target=160 if table_like else 400)


def _effective_hybrid(cfg: dict) -> str:
    mode = str(cfg.get("hybrid_mode", DEFAULT_HYBRID_MODE)).strip().lower()
    if mode not in _HYBRID_MODES:
        mode = DEFAULT_HYBRID_MODE
    return "off" if mode == "off" else "dict_only"


def _speech_units(text: str, cfg: dict) -> list[tuple[str, str]]:
    """Куски [(текст, lang)]. Всегда ru после удаления Piper EN hybrid."""
    hybrid = _effective_hybrid(cfg)
    engine = str(cfg.get("engine", DEFAULT_ENGINE))
    prepared = text
    try:
        from text_prep import finalize_speech_text

        prepared = finalize_speech_text(text, apply_dict=hybrid != "off")
    except Exception as error:
        debug_log(f"text_prep skipped: {error}")
    return [(chunk, "ru") for chunk in _parts_for_engine(prepared, engine) if chunk]


def speak_text(text: str) -> None:
    with _speak_lock:
        _stop_event.clear()
        set_paused(False)
        cfg = load_config()
        engine = str(cfg["engine"])
        set_progress("preparing", engine=engine, current=0, total=0)
        units = _speech_units(text, cfg)
        if not units:
            set_progress("idle", engine=engine, current=0, total=0)
            return
        hybrid = _effective_hybrid(cfg)
        debug_log(f"ENGINE={cfg['engine']} hybrid={hybrid} units={len(units)}")
        log_speak_start(len(text), len(units))
        ok_parts = 0
        fail_parts = 0
        suffix = _audio_suffix(cfg["engine"])
        pause_ms = int(cfg.get("pause_ms", DEFAULT_PAUSE_MS))
        switch_ms = int(cfg.get("lang_switch_pause_ms", DEFAULT_LANG_SWITCH_PAUSE_MS))
        # Без prefetch: Kokoro/Qwen делят lock/VRAM; сирота после Stop вешала следующий Speak.
        _prepare_engine(str(cfg["engine"]))
        current_path: Path | None = None

        try:
            index = 0
            while index < len(units):
                if _stop_event.is_set():
                    break
                if is_paused():
                    if not wait_while_paused():
                        break
                    continue

                part, lang = units[index]
                if len(part) < 2:
                    index += 1
                    continue
                debug_log(
                    f"CHUNK_BEGIN {index + 1}/{len(units)} lang={lang} "
                    f"chars={len(part)} preview={part[:80]!r}"
                )
                set_progress(
                    "synthesizing",
                    engine=engine,
                    current=index + 1,
                    total=len(units),
                )

                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    current_path = Path(tmp.name)
                try:
                    render_audio(part, cfg, current_path, lang)
                except Exception as error:
                    fail_parts += 1
                    log_chunk_fail(index + 1, len(units), part, error)
                    _safe_unlink(current_path)
                    current_path = None
                    index += 1
                    continue

                if current_path.stat().st_size < 64:
                    fail_parts += 1
                    log_chunk_fail(
                        index + 1,
                        len(units),
                        part,
                        RuntimeError("empty audio"),
                    )
                    _safe_unlink(current_path)
                    current_path = None
                    index += 1
                    continue

                set_progress(
                    "playing",
                    engine=engine,
                    current=index + 1,
                    total=len(units),
                )
                finished = play_file(current_path, cfg["volume"])
                _safe_unlink(current_path)
                current_path = None
                if not finished or _stop_event.is_set():
                    break
                ok_parts += 1
                log_chunk_ok(index + 1, len(units), part)
                index += 1
                if index >= len(units):
                    break
                pause_after_chunk(part, pause_ms)
                if units[index][1] != lang and switch_ms > 0:
                    end_at = time.monotonic() + switch_ms / 1000.0
                    while time.monotonic() < end_at:
                        if _stop_event.is_set() or is_paused():
                            break
                        time.sleep(0.02)
                if is_paused() and not wait_while_paused():
                    break
        finally:
            if current_path is not None:
                _safe_unlink(current_path)
            set_progress("idle", engine=engine, current=0, total=0)

        log_speak_done(ok_parts, fail_parts, len(units))


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
        if cmd == "status":
            status = progress_snapshot()
            status["ok"] = True
            conn.sendall(
                json.dumps(status, ensure_ascii=False).encode("utf-8")
                + b"\n"
            )
            return
        if cmd == "warmup":
            cfg = load_config()
            engine = str(cfg.get("engine", DEFAULT_ENGINE))
            set_progress("idle", engine=engine, current=0, total=0)
            _prepare_engine(engine)
            set_warmup_active(True)
            if engine == "kokoro":
                try:
                    from speak_kokoro import warmup as warmup_kokoro

                    debug_log("WARMUP kokoro begin")
                    warmup_kokoro(
                        _normalize_kokoro_voice(
                            cfg.get("kokoro_voice", DEFAULT_KOKORO_VOICE)
                        )
                    )
                    debug_log("WARMUP kokoro done")
                    conn.sendall(b'{"ok":true,"warmed":true,"engine":"kokoro"}\n')
                except Exception as error:
                    debug_log(f"WARMUP kokoro fail: {error}")
                    conn.sendall(
                        json.dumps(
                            {"ok": False, "error": str(error)},
                            ensure_ascii=False,
                        ).encode("utf-8")
                        + b"\n"
                    )
            elif engine == "qwen":
                try:
                    micro = Path(__file__).resolve().parent / "micro_wife"
                    if str(micro) not in sys.path:
                        sys.path.insert(0, str(micro))
                    from speak_qwen import warmup as warmup_qwen

                    debug_log("WARMUP qwen begin")
                    warmup_qwen(cfg.get("qwen_model", DEFAULT_QWEN_MODEL))
                    debug_log("WARMUP qwen done")
                    conn.sendall(b'{"ok":true,"warmed":true,"engine":"qwen"}\n')
                except Exception as error:
                    debug_log(f"WARMUP qwen fail: {error}")
                    conn.sendall(
                        json.dumps(
                            {"ok": False, "error": str(error)},
                            ensure_ascii=False,
                        ).encode("utf-8")
                        + b"\n"
                    )
            else:
                conn.sendall(
                    json.dumps(
                        {"ok": False, "error": f"unknown engine: {engine}"},
                        ensure_ascii=False,
                    ).encode("utf-8")
                    + b"\n"
                )
            set_warmup_active(False)
            return
        if cmd == "pause":
            pause_playback()
            debug_log("PAUSE")
            conn.sendall(b'{"ok":true,"paused":true}\n')
            return
        if cmd == "resume":
            resume_playback()
            debug_log("RESUME")
            conn.sendall(b'{"ok":true,"paused":false}\n')
            return
        if cmd == "pause_toggle":
            if is_paused():
                resume_playback()
                debug_log("PAUSE_TOGGLE -> resume")
                conn.sendall(b'{"ok":true,"paused":false}\n')
            else:
                pause_playback()
                debug_log("PAUSE_TOGGLE -> pause")
                conn.sendall(b'{"ok":true,"paused":true}\n')
            return
        if cmd == "stop":
            cleared = clear_speech_queue()
            stop_playback()
            debug_log(f"STOP cleared_queue={cleared}")
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


def warmup_engine_background() -> None:
    """Не блокирует accept: kokoro/qwen грузятся в фоне после старта."""

    def run() -> None:
        cfg = load_config()
        engine = cfg.get("engine")
        set_progress(
            "idle",
            engine=str(engine or DEFAULT_ENGINE),
            current=0,
            total=0,
        )
        set_warmup_active(True)
        try:
            _prepare_engine(str(engine or DEFAULT_ENGINE))
            if engine == "kokoro":
                from speak_kokoro import warmup as warmup_kokoro

                debug_log("WARMUP bg kokoro begin")
                warmup_kokoro(
                    _normalize_kokoro_voice(
                        cfg.get("kokoro_voice", DEFAULT_KOKORO_VOICE)
                    )
                )
                debug_log("WARMUP bg kokoro done")
            elif engine == "qwen":
                micro = Path(__file__).resolve().parent / "micro_wife"
                if str(micro) not in sys.path:
                    sys.path.insert(0, str(micro))
                from speak_qwen import warmup as warmup_qwen

                debug_log("WARMUP bg qwen begin")
                warmup_qwen(cfg.get("qwen_model", DEFAULT_QWEN_MODEL))
                debug_log("WARMUP bg qwen done")
            else:
                debug_log(f"WARMUP bg skip (engine={engine})")
        except Exception as error:
            debug_log(f"WARMUP bg {engine} fail: {error}")
        finally:
            set_warmup_active(False)

    threading.Thread(target=run, name="tts-warmup", daemon=True).start()


def main() -> int:
    if already_running():
        return 0

    # Порт захватываем ДО pygame/worker/Qwen warmup. Если несколько клиентов
    # одновременно стартуют демон, проигравшие выходят без загрузки модели и RAM.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((HOST, PORT))
    except OSError:
        server.close()
        return 0
    server.listen(8)
    server.settimeout(1.0)

    PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    ensure_mixer()
    ensure_worker()
    warmup_engine_background()

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
        try:
            from speak_kokoro import stop_worker

            stop_worker()
        except Exception:
            pass
        try:
            micro = Path(__file__).resolve().parent / "micro_wife"
            if str(micro) not in sys.path:
                sys.path.insert(0, str(micro))
            from speak_qwen import unload as unload_qwen

            unload_qwen()
        except Exception:
            pass
        server.close()
        PID_FILE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
