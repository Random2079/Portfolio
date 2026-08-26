#!/usr/bin/env python3
"""Offline STT daemon for VoiceMuteSlots (Vosk).

Shift+K → POST /listen/start → POST /listen/stop → transcript.
Logs: stt/logs/stt.log  Config: stt/stt_config.json
"""
from __future__ import annotations

import array
import json
import logging
import math
import os
import queue
import sys
import threading
import time
import wave
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "stt_config.json"
HOST = "127.0.0.1"
PORT = int(os.environ.get("VOICEMUTE_STT_PORT", "39281"))
SAMPLE_RATE = 16000

_VENV_PY = Path(r"C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_VoiceMute\.venv\Scripts\python.exe")


def _ensure_deps() -> None:
    try:
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401
    except ImportError:
        print("Need vosk + sounddevice. Use Discord_VoiceMute .venv:", _VENV_PY)
        raise


_ensure_deps()
import sounddevice as sd  # noqa: E402
from vosk import KaldiRecognizer, Model, SetLogLevel  # noqa: E402

from grammar_ru import grammar_json  # noqa: E402

SetLogLevel(-1)


def load_config() -> dict:
    cfg = {
        "gain": 2.5,
        "input_device": 1,
        "use_grammar": True,
        "model_dir": "models/vosk-model-small-ru-0.22",
        "stop_drain_ms": 250,
        "log_file": "logs/stt.log",
        "engine": "whisper",
        "whisper_model": "small",
        "whisper_device": "auto",
        "parakeet_model": "nvidia/parakeet-tdt-0.6b-v3",
        "parakeet_device": "auto",
        "vad_rms_min": 1800,
        "ignore_first_ms": 120,
        "min_speech_ms": 250,
        "save_clips": True,
        "decode_free": True,
    }
    if CONFIG_PATH.is_file():
        try:
            with CONFIG_PATH.open(encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print("Config read failed:", e)
    return cfg


CFG = load_config()
MODEL_PATH = ROOT / str(CFG.get("model_dir", "models/vosk-model-small-ru-0.22"))
LOG_PATH = ROOT / str(CFG.get("log_file", "logs/stt.log"))
GAIN = float(CFG.get("gain", 2.5) or 1.0)
USE_GRAMMAR = bool(CFG.get("use_grammar", True))
STOP_DRAIN_MS = int(CFG.get("stop_drain_ms", 400) or 400)
INPUT_DEVICE = CFG.get("input_device")
VAD_RMS_MIN = float(CFG.get("vad_rms_min", 2200) or 0)
# Close-mic gate for neural engines: drop quiet Discord speaker bleed
LOUD_RMS_MIN = float(CFG.get("loud_rms_min", 0) or 0)
IGNORE_FIRST_MS = int(CFG.get("ignore_first_ms", 180) or 0)
MIN_SPEECH_MS = int(CFG.get("min_speech_ms", 350) or 0)
SAVE_CLIPS = bool(CFG.get("save_clips", True))
DECODE_FREE = bool(CFG.get("decode_free", True))
ENGINE = str(CFG.get("engine", "whisper") or "whisper").lower()
WHISPER_MODEL = str(CFG.get("whisper_model", "small") or "small")
WHISPER_DEVICE = str(CFG.get("whisper_device", "auto") or "auto")
PARAKEET_MODEL = str(CFG.get("parakeet_model", "nvidia/parakeet-tdt-0.6b-v3") or "nvidia/parakeet-tdt-0.6b-v3")
PARAKEET_DEVICE = str(CFG.get("parakeet_device", "auto") or "auto")
GLOBAL_PTT = bool(CFG.get("global_ptt", True))
GLOBAL_PTT_MOUSE = str(CFG.get("global_ptt_mouse", "middle") or "middle").lower()
GLOBAL_PTT_SHIFT_K = bool(CFG.get("global_ptt_shift_k", True))
# Engines that decode full buffer on stop (no vosk streaming)
NEURAL_ENGINES = frozenset({"whisper", "google", "parakeet"})
CLIPS_DIR = LOG_PATH.parent / "clips"
LAST_RESULT_PATH = LOG_PATH.parent / "last_heard.json"
# #region agent log
DEBUG_LOG = Path(r"C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin\debug-121a69.log")
_agent_dbg_warned = False
_agent_dbg_ok_printed = False


def agent_dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    global _agent_dbg_warned, _agent_dbg_ok_printed
    try:
        payload = {
            "sessionId": "121a69",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        if not _agent_dbg_ok_printed:
            _agent_dbg_ok_printed = True
            print(f"agent_dbg ok -> {DEBUG_LOG}", file=sys.stderr)
    except Exception as e:
        log = globals().get("LOG")
        if log is not None:
            log.warning("agent_dbg write failed: %s", e)
        else:
            print(f"agent_dbg write failed: {e}", file=sys.stderr)
        if not _agent_dbg_warned:
            _agent_dbg_warned = True


# #endregion


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("voicemute_stt")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter("[stt] %(message)s"))
    sh.setLevel(logging.INFO)
    log.addHandler(sh)
    return log


LOG = setup_logging()


def list_input_devices() -> list[dict]:
    out: list[dict] = []
    for i, d in enumerate(sd.query_devices()):
        if int(d.get("max_input_channels") or 0) <= 0:
            continue
        out.append({"index": i, "name": d.get("name", "?"), "channels": int(d["max_input_channels"])})
    return out


def resolve_input_device() -> int | None:
    if isinstance(INPUT_DEVICE, int):
        return INPUT_DEVICE
    if isinstance(INPUT_DEVICE, str):
        name = INPUT_DEVICE.casefold()
        for d in list_input_devices():
            if name in d["name"].casefold():
                return d["index"]
    dev = sd.default.device
    if isinstance(dev, (list, tuple)) and dev and dev[0] is not None and int(dev[0]) >= 0:
        return int(dev[0])
    return None


def pcm_rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples:
        return 0.0
    s = sum(x * x for x in samples)
    return math.sqrt(s / len(samples))


def apply_gain(pcm: bytes, gain: float) -> bytes:
    if gain == 1.0 or not pcm:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm)
    for i in range(len(samples)):
        v = int(samples[i] * gain)
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        samples[i] = v
    return samples.tobytes()


def save_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def _decode_pcm(model: Model, pcm: bytes, grammar: str | None) -> str:
    """One-shot decode of a whole PTT buffer (more stable than streaming partials)."""
    if not pcm:
        return ""
    rec = (
        KaldiRecognizer(model, SAMPLE_RATE, grammar)
        if grammar
        else KaldiRecognizer(model, SAMPLE_RATE)
    )
    rec.SetWords(True)
    step = SAMPLE_RATE * 2  # 1s of int16 mono
    bits: list[str] = []
    for i in range(0, len(pcm), step):
        chunk = pcm[i : i + step]
        if rec.AcceptWaveform(chunk):
            t = (json.loads(rec.Result()).get("text") or "").strip()
            if t:
                bits.append(t)
    t = (json.loads(rec.FinalResult()).get("text") or "").strip()
    if t:
        bits.append(t)
    return " ".join(bits).strip()


def decode_free_pcm(model: Model, pcm: bytes) -> str:
    """What Vosk hears WITHOUT command grammar — real speech / noise / lobby bleed."""
    return _decode_pcm(model, pcm, None)


def decode_grammar_pcm(model: Model, pcm: bytes) -> str:
    """Command grammar over the full PTT clip (preferred over live streaming)."""
    return _decode_pcm(model, pcm, grammar_json())


def write_last_heard(obj: dict) -> None:
    try:
        LAST_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RESULT_PATH.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        LOG.warning("last_heard write: %s", e)


class ListenState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.listening = False
        self.partial = ""
        self.final_bits: list[str] = []
        self.q: queue.Queue[bytes] = queue.Queue()
        self.pcm_buf: list[bytes] = []
        self.pcm_fed: list[bytes] = []
        self.pcm_loud: list[bytes] = []
        self.drop_first_ms = 0.0
        self.drop_vad_ms = 0.0
        self.drop_quiet_ms = 0.0
        self.stream: sd.RawInputStream | None = None
        self.rec: KaldiRecognizer | None = None
        self.worker: threading.Thread | None = None
        self.model: Model | None = None
        self.last_error = ""
        self.peak_rms = 0.0
        self.last_rms = 0.0
        self.speech_ms = 0.0
        self.started_at = 0.0
        self.input_device_index: int | None = None
        self.input_device_name = ""
        self.last_result: dict = {}
        self.cmd_seq = 0
        self.pending_commands: list[dict] = []
        # Global PTT + Discord local PTT can both start/stop the same mic —
        # refcount so the first stop doesn't steal PCM from the second.
        self.listen_refs = 0

    def push_command(self, result: dict, *, source: str = "global") -> dict | None:
        """Queue a recognized utterance for the Equicord plugin to poll (global PTT)."""
        transcript = str(result.get("transcript") or "").strip()
        if not transcript:
            # #region agent log
            agent_dbg(
                "E",
                "vosk_daemon.py:push_command",
                "empty_transcript_skip",
                {
                    "source": source,
                    "peak_rms": result.get("peak_rms"),
                    "hint": (result.get("hint") or "")[:80],
                    "free": str(result.get("free_text") or "")[:80],
                },
            )
            # #endregion
            return None
        with self.lock:
            self.cmd_seq += 1
            item = {
                "id": self.cmd_seq,
                "source": source,
                "transcript": transcript,
                "free_text": str(result.get("free_text") or "").strip(),
                "peak_rms": result.get("peak_rms"),
                "hint": result.get("hint") or "",
                "when": datetime.now().isoformat(timespec="seconds"),
            }
            self.pending_commands.append(item)
            if len(self.pending_commands) > 30:
                self.pending_commands = self.pending_commands[-30:]
        LOG.info("Queued command #%s (%s): %r", item["id"], source, transcript)
        # #region agent log
        agent_dbg(
            "C",
            "vosk_daemon.py:push_command",
            "queued_global_command",
            {"id": item["id"], "source": source, "transcript": transcript[:120]},
        )
        # #endregion
        return item

    def pop_pending_commands(self) -> list[dict]:
        with self.lock:
            items = list(self.pending_commands)
            self.pending_commands = []
            return items

    def ack_commands(self, ids: list[int]) -> int:
        idset = set(int(x) for x in ids)
        with self.lock:
            before = len(self.pending_commands)
            self.pending_commands = [c for c in self.pending_commands if c["id"] not in idset]
            return before - len(self.pending_commands)
    def load_model(self) -> None:
        if ENGINE == "whisper":
            from whisper_engine import load_whisper

            load_whisper(WHISPER_MODEL, WHISPER_DEVICE)
            return
        if ENGINE == "parakeet":
            from parakeet_engine import load_parakeet

            load_parakeet(PARAKEET_MODEL, PARAKEET_DEVICE)
            return
        if ENGINE == "google":
            import speech_recognition as sr  # noqa: F401

            LOG.info("Google Web Speech ready (SpeechRecognition)")
            return
        if self.model is not None:
            return
        if not MODEL_PATH.is_dir():
            raise FileNotFoundError(f"Model missing: {MODEL_PATH}")
        LOG.info("Loading vosk model %s", MODEL_PATH)
        self.model = Model(str(MODEL_PATH))

    def _make_recognizer(self) -> KaldiRecognizer | None:
        if ENGINE in NEURAL_ENGINES:
            return None
        assert self.model is not None
        if USE_GRAMMAR:
            return KaldiRecognizer(self.model, SAMPLE_RATE, grammar_json())
        return KaldiRecognizer(self.model, SAMPLE_RATE)

    def _audio_cb(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            LOG.debug("audio status: %s", status)
        if self.listening:
            self.q.put(bytes(indata))

    def _worker_loop(self) -> None:
        while True:
            try:
                data = self.q.get(timeout=0.2)
            except queue.Empty:
                with self.lock:
                    if not self.listening and self.rec is None:
                        break
                continue

            data = apply_gain(data, GAIN)
            rms = pcm_rms(data)
            now = time.monotonic()
            block_ms = (len(data) / 2) / SAMPLE_RATE * 1000.0
            with self.lock:
                self.pcm_buf.append(data)
                # cap ~12s
                max_bytes = SAMPLE_RATE * 2 * 12
                total = sum(len(x) for x in self.pcm_buf)
                while total > max_bytes and self.pcm_buf:
                    total -= len(self.pcm_buf[0])
                    self.pcm_buf.pop(0)
                self.last_rms = rms
                if rms > self.peak_rms:
                    self.peak_rms = rms
                started = self.started_at
                rec = self.rec

            # Skip first ms (button click / burst)
            age_ms = (now - started) * 1000.0 if started else 0.0
            if age_ms < IGNORE_FIRST_MS:
                with self.lock:
                    self.drop_first_ms += block_ms
                continue
            if VAD_RMS_MIN > 0 and rms < VAD_RMS_MIN:
                with self.lock:
                    self.drop_vad_ms += block_ms
                continue

            # Loud gate: keep quiet Discord bleed out of decode buffer (still in pcm_buf for peak/wav)
            if LOUD_RMS_MIN > 0 and rms < LOUD_RMS_MIN:
                with self.lock:
                    self.drop_quiet_ms += block_ms
                if rec is None:
                    continue
                # vosk streaming: also skip quiet for recognizer
                continue

            with self.lock:
                self.speech_ms += block_ms
                self.pcm_fed.append(data)
                if LOUD_RMS_MIN > 0:
                    self.pcm_loud.append(data)

            if rec is None:
                # whisper/google: only buffer + levels; decode on stop
                continue
            if rec.AcceptWaveform(data):
                try:
                    j = json.loads(rec.Result())
                    t = (j.get("text") or "").strip()
                    if t:
                        with self.lock:
                            self.final_bits.append(t)
                            self.partial = ""
                        LOG.info("FINAL chunk (grammar): %r", t)
                except Exception as e:
                    LOG.warning("Result parse: %s", e)
            else:
                try:
                    j = json.loads(rec.PartialResult())
                    p = (j.get("partial") or "").strip()
                    with self.lock:
                        if p != self.partial:
                            self.partial = p
                            if p:
                                LOG.debug("PARTIAL (grammar): %r", p)
                except Exception:
                    pass

    def start(self) -> dict:
        with self.lock:
            self.listen_refs += 1
            if self.listening:
                LOG.info("LISTEN start nested (refs=%s) — keep mic", self.listen_refs)
                return {
                    "ok": True,
                    "already": True,
                    "listening": True,
                    "refs": self.listen_refs,
                    "engine": ENGINE,
                    "device": self.input_device_name,
                }
            self.load_model()
            self.listening = True
            self.partial = ""
            self.final_bits = []
            self.pcm_buf = []
            self.pcm_fed = []
            self.pcm_loud = []
            self.drop_first_ms = 0.0
            self.drop_vad_ms = 0.0
            self.drop_quiet_ms = 0.0
            self.last_error = ""
            self.peak_rms = 0.0
            self.last_rms = 0.0
            self.speech_ms = 0.0
            self.started_at = time.monotonic()
            self.rec = self._make_recognizer()
            if self.rec is not None:
                self.rec.SetWords(True)
            while not self.q.empty():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break

            dev_idx = resolve_input_device()
            self.input_device_index = dev_idx
            if dev_idx is not None:
                info = sd.query_devices(dev_idx)
                self.input_device_name = str(info.get("name", "?"))
            else:
                self.input_device_name = "default"

            kw: dict = {
                "samplerate": SAMPLE_RATE,
                "blocksize": 4000,
                "dtype": "int16",
                "channels": 1,
                "callback": self._audio_cb,
            }
            if dev_idx is not None:
                kw["device"] = dev_idx

            self.stream = sd.RawInputStream(**kw)
            self.stream.start()
            self.worker = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker.start()

        LOG.info(
            "LISTEN start engine=%s mic=%s (#%s) gain=%.1f vad_min=%.0f refs=%s",
            ENGINE,
            self.input_device_name,
            self.input_device_index,
            GAIN,
            VAD_RMS_MIN,
            self.listen_refs,
        )
        return {
            "ok": True,
            "listening": True,
            "engine": ENGINE,
            "device": self.input_device_name,
            "gain": GAIN,
            "grammar": USE_GRAMMAR and ENGINE == "vosk",
            "vad_rms_min": VAD_RMS_MIN,
            "refs": self.listen_refs,
        }

    def stop(self) -> dict:
        with self.lock:
            if self.listen_refs > 0:
                self.listen_refs -= 1
            if self.listen_refs > 0 and self.listening:
                LOG.info("LISTEN stop deferred (refs=%s) — keep PCM", self.listen_refs)
                return {
                    "ok": True,
                    "deferred": True,
                    "listening": True,
                    "refs": self.listen_refs,
                    "transcript": "",
                    "free_text": "",
                    "hint": "ещё держит другой PTT",
                }
            self.listen_refs = 0
            self.listening = False
            stream = self.stream
            rec = self.rec
            peak = self.peak_rms
            speech_ms = self.speech_ms
            drop_first = self.drop_first_ms
            drop_vad = self.drop_vad_ms
            drop_quiet = self.drop_quiet_ms
            started_at = self.started_at
            dev = self.input_device_name
            pcm = b"".join(self.pcm_buf)
            pcm_fed = b"".join(self.pcm_fed)
            pcm_loud = b"".join(self.pcm_loud)
            self.pcm_buf = []
            self.pcm_fed = []
            self.pcm_loud = []
            self.stream = None
        wall_ms = (time.monotonic() - started_at) * 1000.0 if started_at else 0.0
        pcm_ms = (len(pcm) / 2) / SAMPLE_RATE * 1000.0 if pcm else 0.0
        loud_ms = (len(pcm_loud) / 2) / SAMPLE_RATE * 1000.0 if pcm_loud else 0.0
        # Neural: decode only loud close-mic chunks (cuts Discord headphone bleed)
        if ENGINE in NEURAL_ENGINES and LOUD_RMS_MIN > 0:
            pcm_decode = pcm_loud  # may be empty → empty transcript (bleed-only hold)
        else:
            pcm_decode = pcm
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                self.last_error = str(e)
                LOG.error("Stream stop: %s", e)

        time.sleep(max(0.05, STOP_DRAIN_MS / 1000.0))
        final_extra = ""
        if rec is not None:
            try:
                j = json.loads(rec.FinalResult())
                final_extra = (j.get("text") or "").strip()
                if final_extra:
                    LOG.info("FINAL flush: %r", final_extra)
            except Exception as e:
                LOG.warning("FinalResult: %s", e)

        with self.lock:
            bits = list(self.final_bits)
            partial = self.partial
            self.rec = None
            self.final_bits = []
            self.partial = ""

        if final_extra:
            bits.append(final_extra)
        stream_cmd = " ".join(x for x in bits if x).strip()
        if not stream_cmd and partial:
            stream_cmd = partial
        transcript = stream_cmd

        free_text = ""
        free_fed = ""
        offline_cmd = ""
        t0 = time.perf_counter()
        if ENGINE == "whisper":
            try:
                from whisper_engine import transcribe_pcm

                transcript = transcribe_pcm(
                    pcm_decode,
                    model_size=WHISPER_MODEL,
                    device=WHISPER_DEVICE,
                    language="ru",
                )
                free_text = transcript  # no grammar — same text
                # Near-silence → Whisper often dumps initial_prompt («Замутить первого…»)
                if peak < 800 and transcript:
                    LOG.warning("Reject whisper on quiet clip peak=%.0f text=%r", peak, transcript)
                    transcript = ""
                    free_text = ""
                    hint_pre = "тихо — Whisper выдумал текст из подсказки"
                else:
                    hint_pre = ""
            except Exception as e:
                LOG.exception("whisper decode failed")
                self.last_error = str(e)
                transcript = ""
                free_text = f"whisper error: {e}"
                hint_pre = ""
        elif ENGINE == "parakeet":
            try:
                from parakeet_engine import transcribe_pcm as parakeet_pcm

                transcript = parakeet_pcm(
                    pcm_decode,
                    model_name=PARAKEET_MODEL,
                    device=PARAKEET_DEVICE,
                )
                free_text = transcript
                if peak < 800 and transcript:
                    LOG.warning("Reject parakeet on quiet clip peak=%.0f text=%r", peak, transcript)
                    transcript = ""
                    free_text = ""
                    hint_pre = "тихо — Parakeet на шуме"
                else:
                    hint_pre = ""
            except Exception as e:
                LOG.exception("parakeet decode failed")
                self.last_error = str(e)
                transcript = ""
                free_text = f"parakeet error: {e}"
                hint_pre = ""
        elif ENGINE == "google":
            hint_pre = ""
            try:
                from google_engine import transcribe_pcm as google_pcm

                transcript = google_pcm(pcm_decode, language="ru-RU")
                free_text = transcript
            except Exception as e:
                LOG.exception("google decode failed")
                self.last_error = str(e)
                transcript = ""
                free_text = f"google error: {e}"
        elif self.model is not None and pcm:
            hint_pre = ""
            try:
                free_text = decode_free_pcm(self.model, pcm)
            except Exception as e:
                LOG.warning("free decode: %s", e)
            if pcm_fed:
                try:
                    free_fed = decode_free_pcm(self.model, pcm_fed)
                except Exception as e:
                    LOG.warning("free_fed decode: %s", e)
            # Prefer one-shot grammar on full clip over streaming partials (short PTT invents slots)
            if USE_GRAMMAR:
                try:
                    offline_cmd = decode_grammar_pcm(self.model, pcm)
                except Exception as e:
                    LOG.warning("offline grammar: %s", e)
                if offline_cmd:
                    transcript = offline_cmd
        else:
            hint_pre = ""
        decode_ms = (time.perf_counter() - t0) * 1000.0

        rejected_short = False
        # Use wall/pcm length — speech_ms was under-counted when VAD ate frames
        effective_ms = max(speech_ms, pcm_ms * 0.7)
        if (
            transcript
            and MIN_SPEECH_MS > 0
            and effective_ms < MIN_SPEECH_MS
            and ENGINE not in NEURAL_ENGINES
        ):
            LOG.warning(
                "Reject short speech: %r effective_ms=%.0f < %d",
                transcript,
                effective_ms,
                MIN_SPEECH_MS,
            )
            transcript = ""
            rejected_short = True

        clip_path = ""
        if SAVE_CLIPS and pcm:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            clip_file = CLIPS_DIR / f"ptt_{stamp}.wav"
            try:
                save_wav(clip_file, pcm)
                clip_path = str(clip_file)
            except Exception as e:
                LOG.warning("wav save: %s", e)

        hint = hint_pre
        if not hint:
            if not transcript and peak >= 8000:
                hint = "громко в мике, но текст пустой — шум/чужой голос/неразборчиво"
            elif not transcript and peak < 800:
                hint = "тихо — не тот mic или далеко от рта"
            elif ENGINE == "vosk" and free_text and transcript and free_text != transcript:
                hint = "словарь команд ≠ свободная речь — смотри оба поля"
            elif ENGINE == "vosk" and free_text and not transcript:
                hint = "свободная речь есть, команда пустая — bleed/не та фраза"
            elif ENGINE == "google" and transcript:
                hint = "Google Web Speech (нужен интернет)"
            elif ENGINE == "whisper" and not transcript and peak >= 8000 and LOUD_RMS_MIN > 0:
                hint = "громко, но всё отфильтровано как bleed — говори ближе/громче или снизь loud_rms_min"
            elif ENGINE == "parakeet" and not transcript and peak >= 8000 and LOUD_RMS_MIN > 0:
                hint = "громко, но bleed-gate съел буфер — снизь loud_rms_min"
            elif ENGINE == "whisper" and transcript:
                hint = "Whisper — смотри команду; слот лучше «три», не «третьего»"
            elif ENGINE == "parakeet" and transcript:
                hint = "Parakeet — смотри команду"

        # #region agent log
        agent_dbg(
            "A,B,C,D,E",
            "vosk_daemon.py:stop",
            "ptt_metrics",
            {
                "runId": "post-fix",
                "engine": ENGINE,
                "device": dev,
                "gain": GAIN,
                "vad_rms_min": VAD_RMS_MIN,
                "ignore_first_ms": IGNORE_FIRST_MS,
                "use_grammar": USE_GRAMMAR and ENGINE == "vosk",
                "wall_ms": round(wall_ms, 1),
                "pcm_ms": round(pcm_ms, 1),
                "speech_fed_ms": round(speech_ms, 1),
                "drop_first_ms": round(drop_first, 1),
                "drop_vad_ms": round(drop_vad, 1),
                "drop_quiet_ms": round(drop_quiet, 1),
                "loud_rms_min": LOUD_RMS_MIN,
                "loud_ms": round(loud_ms, 1),
                "peak_rms": round(peak, 1),
                "pcm_bytes": len(pcm),
                "pcm_fed_bytes": len(pcm_fed),
                "pcm_loud_bytes": len(pcm_loud),
                "pcm_decode_bytes": len(pcm_decode),
                "free_full": free_text,
                "free_fed_only": free_fed,
                "stream_cmd": stream_cmd,
                "offline_cmd": offline_cmd,
                "cmd_grammar": transcript,
                "partial": partial,
                "rejected_short": rejected_short,
                "decode_ms": round(decode_ms, 1),
                "clip": clip_path,
            },
        )
        # #endregion

        LOG.info("=" * 60)
        LOG.info("ЧТО СЛЫШНО (сырой мик → %s):", ENGINE)
        LOG.info("  mic=%s  peak_rms=%.0f  speech_ms=%.0f  decode_ms=%.0f  pcm_bytes=%d", dev, peak, speech_ms, decode_ms, len(pcm))
        LOG.info("  FREE: %r", free_text)
        LOG.info("  STREAM: %r", stream_cmd)
        LOG.info("  OFFLINE_CMD: %r", offline_cmd)
        LOG.info("  CMD:  %r", transcript)
        LOG.info("  partial=%r  rejected_short=%s", partial, rejected_short)
        if clip_path:
            LOG.info("  WAV: %s", clip_path)
        if hint:
            LOG.info("  HINT: %s", hint)
        LOG.info("=" * 60)

        result = {
            "ok": True,
            "listening": False,
            "engine": ENGINE,
            "transcript": transcript,
            "free_text": free_text,
            "partial": partial,
            "peak_rms": round(peak, 1),
            "speech_ms": round(speech_ms, 1),
            "decode_ms": round(decode_ms, 1),
            "device": dev,
            "clip": clip_path,
            "hint": hint,
            "log": str(LOG_PATH),
            "last_heard": str(LAST_RESULT_PATH),
            "debug": {
                "wall_ms": round(wall_ms, 1),
                "drop_vad_ms": round(drop_vad, 1),
                "free_fed_only": free_fed,
            },
        }
        self.last_result = result
        write_last_heard(
            {
                "when": datetime.now().isoformat(timespec="seconds"),
                "engine": ENGINE,
                "device": dev,
                "peak_rms": round(peak, 1),
                "speech_ms": round(speech_ms, 1),
                "decode_ms": round(decode_ms, 1),
                "free_text": free_text,
                "command_text": transcript,
                "partial": partial,
                "clip": clip_path,
                "hint": hint,
            }
        )
        return result

    def status(self) -> dict:
        with self.lock:
            return {
                "ok": True,
                "listening": self.listening,
                "partial": self.partial,
                "last_rms": round(self.last_rms, 1),
                "peak_rms": round(self.peak_rms, 1),
                "speech_ms": round(self.speech_ms, 1),
                "error": self.last_error,
                "model": str(MODEL_PATH),
                "device": self.input_device_name or resolve_input_device(),
                "gain": GAIN,
                "grammar": USE_GRAMMAR,
                "vad_rms_min": VAD_RMS_MIN,
                "log": str(LOG_PATH),
                "last": self.last_result,
            }


STATE = ListenState()
_last_pending_poll_log = 0.0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        LOG.debug(fmt, *args)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health"):
            try:
                STATE.load_model()
                dev = resolve_input_device()
                dev_name = "?"
                if dev is not None:
                    dev_name = str(sd.query_devices(dev).get("name", "?"))
                self._json(
                    200,
                    {
                        "ok": True,
                        "engine": ENGINE,
                        "whisper_model": WHISPER_MODEL if ENGINE == "whisper" else None,
                        "parakeet_model": PARAKEET_MODEL if ENGINE == "parakeet" else None,
                        "global_ptt": GLOBAL_PTT,
                        "port": PORT,
                        "model": (
                            str(MODEL_PATH)
                            if ENGINE == "vosk"
                            else (
                                "google-web-speech"
                                if ENGINE == "google"
                                else (PARAKEET_MODEL if ENGINE == "parakeet" else WHISPER_MODEL)
                            )
                        ),
                        "gain": GAIN,
                        "grammar": USE_GRAMMAR and ENGINE == "vosk",
                        "vad_rms_min": VAD_RMS_MIN,
                        "device": dev_name,
                        "device_index": dev,
                        "log": str(LOG_PATH),
                    },
                )
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return
        if self.path == "/status":
            self._json(200, STATE.status())
            return
        if self.path == "/devices":
            self._json(200, {"ok": True, "inputs": list_input_devices(), "default": resolve_input_device()})
            return
        if self.path == "/log":
            try:
                lines = (
                    LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
                    if LOG_PATH.is_file()
                    else []
                )
                self._json(200, {"ok": True, "lines": lines, "path": str(LOG_PATH)})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return
        if self.path in ("/last", "/last_heard"):
            if LAST_RESULT_PATH.is_file():
                try:
                    obj = json.loads(LAST_RESULT_PATH.read_text(encoding="utf-8"))
                    self._json(200, {"ok": True, **obj})
                    return
                except Exception as e:
                    self._json(500, {"ok": False, "error": str(e)})
                    return
            self._json(200, {"ok": True, **(STATE.last_result or {"hint": "ещё не было Shift+K"})})
            return
        if self.path in ("/commands/pending", "/commands", "/pending"):
            global _last_pending_poll_log
            with STATE.lock:
                items = list(STATE.pending_commands)
            now = time.time()
            # Heartbeat: prove Equicord poller is alive (was missing entirely in stt.log)
            # Log every poll for ~15s after boot-ish, then every 5s — catch timer throttle
            if items or (now - _last_pending_poll_log) >= 5.0 or len(items) > 0:
                _last_pending_poll_log = now
                LOG.info(
                    "plugin poll /commands/pending count=%s visible_hint_tick",
                    len(items),
                )
            # #region agent log
            agent_dbg(
                "A",
                "vosk_daemon.py:GET_/commands/pending",
                "pending_served",
                {"count": len(items), "ids": [c.get("id") for c in items[:10]]},
            )
            # #endregion
            self._json(200, {"ok": True, "commands": items, "global_ptt": GLOBAL_PTT})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/listen/start":
                self._json(200, STATE.start())
                return
            if self.path == "/listen/stop":
                self._json(200, STATE.stop())
                return
            if self.path == "/commands/ack":
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    body = {}
                ids = body.get("ids") or []
                n = STATE.ack_commands(ids if isinstance(ids, list) else [])
                self._json(200, {"ok": True, "acked": n})
                return
            self._json(404, {"ok": False, "error": "not found"})
        except Exception as e:
            LOG.exception("POST %s", self.path)
            self._json(500, {"ok": False, "error": str(e)})


def _arm_global_ptt() -> None:
    if not GLOBAL_PTT:
        LOG.info("Global PTT disabled in config")
        return

    def on_begin() -> dict:
        return STATE.start()

    def on_end() -> dict:
        result = STATE.stop()
        STATE.push_command(result, source="global")
        return result

    from global_ptt import start_global_ptt

    ok = start_global_ptt(
        on_begin=on_begin,
        on_end=on_end,
        mouse_button=GLOBAL_PTT_MOUSE,
        enable_shift_k=GLOBAL_PTT_SHIFT_K,
    )
    if ok:
        print(f"Global PTT ON — mouse={GLOBAL_PTT_MOUSE} shift+k={GLOBAL_PTT_SHIFT_K} (works in games)")
    else:
        print("Global PTT OFF — install: pip install pynput")


def main() -> int:
    # #region agent log
    agent_dbg(
        "BOOT",
        "vosk_daemon.py:main",
        "daemon_boot",
        {
            "pid": os.getpid(),
            "model": str(MODEL_PATH) if ENGINE == "vosk" else WHISPER_MODEL,
            "grammar": USE_GRAMMAR and ENGINE == "vosk",
        },
    )
    # #endregion
    dev = resolve_input_device()
    dev_name = sd.query_devices(dev).get("name", "?") if dev is not None else "system default"
    print(f"VoiceMute STT ({ENGINE}) http://{HOST}:{PORT}")
    if ENGINE == "whisper":
        print(f"Whisper model: {WHISPER_MODEL}  device={WHISPER_DEVICE}")
    elif ENGINE == "parakeet":
        print(f"Parakeet model: {PARAKEET_MODEL}  device={PARAKEET_DEVICE}")
    elif ENGINE == "google":
        print("Engine: Google Web Speech (ru-RU, needs internet)")
    else:
        print(f"Vosk model: {MODEL_PATH}")
    print(f"Mic: [{dev}] {dev_name}  gain={GAIN}  vad_min={VAD_RMS_MIN}")
    print(f"Log: {LOG_PATH}")
    # Bind port BEFORE global PTT — otherwise a second daemon arms a duplicate mouse hook
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        LOG.error("Port %s busy — another STT already running? %s", PORT, e)
        print(f"FATAL: port {PORT} already in use. Run Start-VoiceStt.ps1 -ForceRestart")
        return 2
    try:
        STATE.load_model()
        LOG.info("Daemon ready engine=%s mic=[%s] %s", ENGINE, dev, dev_name)
        print("Model loaded OK")
    except Exception as e:
        print("Model load failed:", e)
        httpd.server_close()
        return 1
    _arm_global_ptt()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
