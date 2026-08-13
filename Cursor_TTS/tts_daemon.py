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
DEFAULT_ENGINE = "edge"  # edge | local | piper
DEFAULT_PAUSE_MS = 350  # пауза между кусками (реф: ~300–500ms между предложениями)
DEFAULT_PIPER_MODEL = "models/ru_RU-dmitri-medium.onnx"
DEFAULT_PIPER_MODEL_EN = "models/en_US-ryan-medium.onnx"
DEFAULT_HYBRID_MODE = "dict_only"
DEFAULT_LANG_SWITCH_PAUSE_MS = 80
_ENGINES = {"edge", "local", "piper"}
_HYBRID_MODES = {"off", "dict_only", "dict_and_en"}

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


def load_config() -> dict:
    data = {
        "engine": DEFAULT_ENGINE,
        "voice": DEFAULT_VOICE,
        "local_speaker": DEFAULT_LOCAL_SPEAKER,
        "piper_model": DEFAULT_PIPER_MODEL,
        "piper_model_en": DEFAULT_PIPER_MODEL_EN,
        "hybrid_mode": DEFAULT_HYBRID_MODE,
        "lang_switch_pause_ms": DEFAULT_LANG_SWITCH_PAUSE_MS,
        "volume": DEFAULT_VOLUME / 100.0,
        "interrupt_on_new": False,
    }
    if CONFIG_FILE.is_file():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            engine = str(raw.get("engine", DEFAULT_ENGINE)).strip().lower()
            data["engine"] = engine if engine in _ENGINES else DEFAULT_ENGINE
            data["voice"] = str(raw.get("voice", DEFAULT_VOICE)).strip() or DEFAULT_VOICE
            data["local_speaker"] = (
                str(raw.get("local_speaker", DEFAULT_LOCAL_SPEAKER)).strip()
                or DEFAULT_LOCAL_SPEAKER
            )
            piper_model = str(raw.get("piper_model", DEFAULT_PIPER_MODEL)).strip()
            data["piper_model"] = piper_model or DEFAULT_PIPER_MODEL
            piper_en = str(raw.get("piper_model_en", DEFAULT_PIPER_MODEL_EN)).strip()
            data["piper_model_en"] = piper_en or DEFAULT_PIPER_MODEL_EN
            hybrid = str(raw.get("hybrid_mode", DEFAULT_HYBRID_MODE)).strip().lower()
            data["hybrid_mode"] = hybrid if hybrid in _HYBRID_MODES else DEFAULT_HYBRID_MODE
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
    if "piper_model_en" not in data:
        data["piper_model_en"] = DEFAULT_PIPER_MODEL_EN
    if "hybrid_mode" not in data:
        data["hybrid_mode"] = DEFAULT_HYBRID_MODE
    if "lang_switch_pause_ms" not in data:
        data["lang_switch_pause_ms"] = DEFAULT_LANG_SWITCH_PAUSE_MS
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
    return ".mp3" if engine == "edge" else ".wav"


def render_audio(part: str, cfg: dict, out_path: Path, lang: str = "ru") -> None:
    """edge → mp3, local/piper → wav. lang=en только для Piper hybrid."""
    engine = cfg["engine"]
    if engine == "local":
        from speak_local import synthesize_wav

        synthesize_wav(part, cfg["local_speaker"], out_path)
        return
    if engine == "piper":
        from speak_piper import synthesize_wav as synthesize_piper

        model = cfg.get("piper_model", DEFAULT_PIPER_MODEL)
        if lang == "en":
            model = cfg.get("piper_model_en", DEFAULT_PIPER_MODEL_EN)
        synthesize_piper(part, model, out_path)
        return
    download_mp3_retry(part, cfg["voice"], out_path)


def _prefetch_part(part: str, cfg: dict, out_holder: list, lang: str = "ru") -> None:
    suffix = _audio_suffix(cfg["engine"])
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_path = Path(tmp.name)
    try:
        render_audio(part, cfg, audio_path, lang)
        out_holder[0] = audio_path
    except Exception as error:
        audio_path.unlink(missing_ok=True)
        out_holder[0] = error


def _looks_like_table_speech(text: str) -> bool:
    head = text.lstrip()[:120]
    if head.startswith("Столбцы:"):
        return True
    # Много коротких предложений подряд — типичные строки таблицы
    dots = text.count(". ")
    return dots >= 4 and (len(text) / max(dots, 1)) < 90


def _parts_for_engine(text: str, engine: str) -> list[str]:
    table_like = _looks_like_table_speech(text)
    if engine == "local":
        return split_into_chunks(text, target=160 if table_like else 500)
    if engine == "piper":
        return split_into_chunks(text, target=160 if table_like else 400)
    if table_like:
        return split_into_chunks(text, target=180)
    return split_for_speech(text)


def _effective_hybrid(cfg: dict) -> str:
    """dict_and_en только если Piper и EN-модель на диске, иначе dict_only."""
    mode = str(cfg.get("hybrid_mode", DEFAULT_HYBRID_MODE)).strip().lower()
    if mode not in _HYBRID_MODES:
        mode = DEFAULT_HYBRID_MODE
    if cfg.get("engine") != "piper":
        return "off" if mode == "off" else "dict_only"
    if mode != "dict_and_en":
        return mode
    try:
        from speak_piper import model_exists

        if model_exists(cfg.get("piper_model_en", DEFAULT_PIPER_MODEL_EN)):
            return "dict_and_en"
    except Exception:
        pass
    return "dict_only"


def _speech_units(text: str, cfg: dict) -> list[tuple[str, str]]:
    """Куски [(текст, lang)]. EN-сегменты только в режиме dict_and_en."""
    hybrid = _effective_hybrid(cfg)
    engine = str(cfg.get("engine", DEFAULT_ENGINE))
    if engine == "piper" and hybrid == "dict_and_en":
        try:
            from text_prep import finalize_speech_segments

            segments = finalize_speech_segments(text)
        except Exception as error:
            debug_log(f"text_prep segments skipped: {error}")
            segments = []
        if segments:
            units: list[tuple[str, str]] = []
            for seg in segments:
                for chunk in _parts_for_engine(seg.text, engine):
                    if chunk:
                        units.append((chunk, seg.lang))
            return units
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
        units = _speech_units(text, cfg)
        if not units:
            return
        hybrid = _effective_hybrid(cfg)
        debug_log(f"ENGINE={cfg['engine']} hybrid={hybrid} units={len(units)}")
        log_speak_start(len(text), len(units))
        ok_parts = 0
        fail_parts = 0
        suffix = _audio_suffix(cfg["engine"])
        pause_ms = int(cfg.get("pause_ms", DEFAULT_PAUSE_MS))
        switch_ms = int(cfg.get("lang_switch_pause_ms", DEFAULT_LANG_SWITCH_PAUSE_MS))
        use_prefetch = cfg["engine"] == "edge"
        next_thread: threading.Thread | None = None
        current_path: Path | None = None

        def start_prefetch(part: str, lang: str) -> threading.Thread:
            holder: list = [None]
            thread = threading.Thread(
                target=_prefetch_part, args=(part, cfg, holder, lang), daemon=True
            )
            thread.start()
            thread._holder = holder  # type: ignore[attr-defined]
            return thread

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

                if current_path is None:
                    if use_prefetch and next_thread is not None:
                        next_thread.join(timeout=120)
                        result = getattr(next_thread, "_holder", [None])[0]
                        next_thread = None
                        if isinstance(result, Path):
                            current_path = result
                        else:
                            err = (
                                result
                                if isinstance(result, Exception)
                                else RuntimeError("prefetch returned nothing")
                            )
                            fail_parts += 1
                            log_chunk_fail(index + 1, len(units), part, err)
                            index += 1
                            continue
                    else:
                        with tempfile.NamedTemporaryFile(
                            suffix=suffix, delete=False
                        ) as tmp:
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

                if (
                    use_prefetch
                    and next_thread is None
                    and index + 1 < len(units)
                    and not _stop_event.is_set()
                ):
                    npart, nlang = units[index + 1]
                    if len(npart) >= 2:
                        next_thread = start_prefetch(npart, nlang)

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
            if next_thread is not None:
                next_thread.join(timeout=1)
                result = getattr(next_thread, "_holder", [None])[0]
                if isinstance(result, Path):
                    _safe_unlink(result)

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
            conn.sendall(
                json.dumps(
                    {"ok": True, "paused": is_paused(), "queue": _speech_queue.qsize()},
                    ensure_ascii=False,
                ).encode("utf-8")
                + b"\n"
            )
            return
        if cmd == "warmup":
            cfg = load_config()
            engine = str(cfg.get("engine", DEFAULT_ENGINE))
            if engine == "local":
                try:
                    from speak_local import warmup as warmup_local

                    debug_log("WARMUP local begin")
                    warmup_local()
                    debug_log("WARMUP local done")
                    conn.sendall(b'{"ok":true,"warmed":true,"engine":"local"}\n')
                except Exception as error:
                    debug_log(f"WARMUP fail: {error}")
                    conn.sendall(
                        json.dumps(
                            {"ok": False, "error": str(error)},
                            ensure_ascii=False,
                        ).encode("utf-8")
                        + b"\n"
                    )
            elif engine == "piper":
                try:
                    from speak_piper import warmup_many

                    debug_log("WARMUP piper begin")
                    models = [cfg.get("piper_model", DEFAULT_PIPER_MODEL)]
                    if _effective_hybrid(cfg) == "dict_and_en":
                        models.append(cfg.get("piper_model_en", DEFAULT_PIPER_MODEL_EN))
                    warmup_many(models)
                    debug_log("WARMUP piper done")
                    conn.sendall(b'{"ok":true,"warmed":true,"engine":"piper"}\n')
                except Exception as error:
                    debug_log(f"WARMUP piper fail: {error}")
                    conn.sendall(
                        json.dumps(
                            {"ok": False, "error": str(error)},
                            ensure_ascii=False,
                        ).encode("utf-8")
                        + b"\n"
                    )
            else:
                debug_log("WARMUP edge skip (daemon already warm)")
                conn.sendall(b'{"ok":true,"warmed":true,"engine":"edge"}\n')
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
    """Не блокирует accept: local/piper грузятся в фоне после старта."""

    def run() -> None:
        cfg = load_config()
        engine = cfg.get("engine")
        if engine == "local":
            try:
                from speak_local import warmup as warmup_local

                debug_log("WARMUP bg local begin")
                warmup_local()
                debug_log("WARMUP bg local done")
            except Exception as error:
                debug_log(f"WARMUP bg fail: {error}")
        elif engine == "piper":
            try:
                from speak_piper import warmup_many

                debug_log("WARMUP bg piper begin")
                models = [cfg.get("piper_model", DEFAULT_PIPER_MODEL)]
                if _effective_hybrid(cfg) == "dict_and_en":
                    models.append(cfg.get("piper_model_en", DEFAULT_PIPER_MODEL_EN))
                warmup_many(models)
                debug_log("WARMUP bg piper done")
            except Exception as error:
                debug_log(f"WARMUP bg piper fail: {error}")
        else:
            debug_log("WARMUP bg skip (engine!=local/piper)")

    threading.Thread(target=run, name="tts-warmup", daemon=True).start()


def main() -> int:
    if already_running():
        return 0

    PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    ensure_mixer()
    ensure_worker()
    warmup_engine_background()

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
