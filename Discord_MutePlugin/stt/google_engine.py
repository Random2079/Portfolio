"""Google Web Speech (speech_recognition) — short RU PTT over the network."""
from __future__ import annotations

import io
import logging
import socket
import wave

LOG = logging.getLogger("voicemute_stt")

SAMPLE_RATE = 16000
# Free Google endpoint can hang forever without this — freezes Discord HUD on /listen/stop
GOOGLE_TIMEOUT_SEC = 8


def pcm_to_wav_bytes(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def transcribe_pcm(pcm: bytes, *, language: str = "ru-RU") -> str:
    """Decode int16 mono PCM via Google free web endpoint (needs internet)."""
    if not pcm or len(pcm) < SAMPLE_RATE // 5:  # <0.1s
        return ""
    try:
        import speech_recognition as sr
    except ImportError as e:
        raise RuntimeError("pip install SpeechRecognition  (in Discord_VoiceMute .venv)") from e

    # Pad very short clips — Google often blanks sub-second utterances
    min_bytes = SAMPLE_RATE * 2  # 1.0s
    if len(pcm) < min_bytes:
        pcm = pcm + (b"\x00" * (min_bytes - len(pcm)))

    wav = pcm_to_wav_bytes(pcm)
    recognizer = sr.Recognizer()
    with sr.AudioFile(io.BytesIO(wav)) as source:
        audio = recognizer.record(source)

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(GOOGLE_TIMEOUT_SEC)
    try:
        text = recognizer.recognize_google(audio, language=language)
    except sr.UnknownValueError:
        LOG.info("google: could not understand audio")
        return ""
    except sr.RequestError as e:
        LOG.warning("google request failed: %s", e)
        raise
    except (TimeoutError, socket.timeout) as e:
        LOG.warning("google timeout after %ss: %s", GOOGLE_TIMEOUT_SEC, e)
        raise RuntimeError(f"google timeout ({GOOGLE_TIMEOUT_SEC}s)") from e
    finally:
        socket.setdefaulttimeout(old_timeout)
    return (text or "").strip()
